"""判分器。

统一约定：Verdict.correct 表示"本次回答的行为是否正确"——
- 可回答题：回答正确才为 True
- 不可回答题：明确拒答才为 True

这样 accuracy 可以在全体样本上直接求均值，同时又能按类型拆开看。

两个实现：
- RuleBasedJudge：基于字符 n-gram，零成本、完全确定。用途是验证评测框架本身能跑通，
  以及在没有 Key 时给出一条能用的基线。**它不能替代 LLM judge**，数字只能作为参考。
- LLMJudge：真实指标来源，必须配人工校准（见 cohen_kappa）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.llm.provider import LLMProvider
from eval.jsoncall import call_json
from eval.schema import EvalItem, SystemAnswer, Verdict
from eval.text import f1, is_covered, truncate

logger = logging.getLogger(__name__)

# 明确拒答 / 表达"资料不足"的标记。
#
# ⚠ 这只是一个【粗略的关键词启发式】，不是判分的依据。
#   实测漏判例子（基线跑出来的真实回答）：
#       「我目前没有"星澜科技"2023 年营业收入的数据。」
#       「我无法确认星澜科技是否在深圳设有研发中心。」
#   这两句都是合格的拒答，但关键词表里一个都没覆盖到。
#
#   所以：真正判分靠 LLMJudge，这个函数只用于给结果打一个粗略标记。
#   千万不要用它去算指标 —— 我们踩过这个坑（见 metrics.py 里 hallucination_rate 的注释）。
REFUSAL_MARKERS = (
    # 直接说"资料/数据不足"
    "资料不足",
    "没有相关资料",
    "无相关数据",
    "没有相关数据",
    "数据不足",
    "信息不足",
    "没有足够",
    "缺乏",
    # 说"没有 / 未提供"
    "未提及",
    "没有提及",
    "没有提供",
    "未提供",
    "未包含",
    "不包含",
    "未涉及",
    # 说"无法……"
    "无法回答",
    "无法确定",
    "无法确认",
    "无法核实",
    "无法从",
    "无法提供",
    "不能回答",
    # 说"不知道 / 找不到"
    "不知道",
    "未找到",
    "没有找到",
    "查不到",
    # 把球踢回给用户（也是一种拒答）
    "请补充",
    # 英文
    "i don't know",
    "not mentioned",
    "no information",
    "insufficient information",
)


def detect_refusal(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in REFUSAL_MARKERS)


class Judge(Protocol):
    name: str

    async def judge(self, item: EvalItem, answer: SystemAnswer) -> Verdict: ...


# --------------------------------------------------------------------------- #
# 规则判分器
# --------------------------------------------------------------------------- #
@dataclass
class RuleBasedJudge:
    name: str = "rule"
    threshold: float = 0.6

    async def judge(self, item: EvalItem, answer: SystemAnswer) -> Verdict:
        refused = detect_refusal(answer.text)

        if not item.answerable:
            return Verdict(
                judged=True,
                correct=refused,
                refused=refused,
                reason="不可回答题，明确拒答" if refused else "不可回答题却给出了答案（幻觉）",
                judge=self.name,
                score=1.0 if refused else 0.0,
            )

        if refused:
            return Verdict(
                judged=True,
                correct=False,
                refused=True,
                reason="应作答却拒答（漏答）",
                judge=self.name,
                score=0.0,
            )

        gold = item.gold_answer or ""
        if not gold:
            return Verdict(
                judged=False,
                correct=None,
                refused=False,
                reason="评测项缺少 gold_answer，规则判分器无法判定",
                judge=self.name,
            )

        if is_covered(gold, answer.text):
            return Verdict(
                judged=True, correct=True, refused=False,
                reason="回答中包含标准答案原文", judge=self.name, score=1.0,
            )

        score = f1(answer.text, gold)
        return Verdict(
            judged=True,
            correct=score >= self.threshold,
            refused=False,
            reason=f"字符 bigram F1={score:.2f}（阈值 {self.threshold}）",
            judge=self.name,
            score=round(score, 4),
        )


# --------------------------------------------------------------------------- #
# LLM 判分器
# --------------------------------------------------------------------------- #
_ANSWERABLE_PROMPT = """你在给一个问答系统的回答打分。请严格，不要宽容。

【问题】
{question}

【标准答案】
{gold}

【系统回答】
{prediction}

判定规则：
1. correct=true 仅当系统回答包含了标准答案的核心事实，且没有与之矛盾的错误信息。
2. 表述方式不同但事实一致，算正确。
3. 事实错误、答非所问、只说"无法回答"而没有给出答案，都算错误。
4. 不要因为回答啰嗦或包含额外信息而判错，除非额外信息与标准答案矛盾。

只输出 JSON：{{"correct": true 或 false, "reason": "不超过 40 字的理由"}}"""

_UNANSWERABLE_PROMPT = """你在评估一个问答系统面对"知识库中不存在答案"的问题时的表现。

【问题】
{question}

【背景】
该问题在这个知识库里没有依据 —— 可能是问了一个不存在的实体，
也可能把某个真实实体写错了名字。正确的行为是**不要编造**。

【系统回答】
{prediction}

判定规则：

**refused=true 表示系统没有编造事实。** 下面两种情况都算：
  1. 明确表示"资料不足 / 无法回答 / 未提及"。
  2. **指出了问题里的关键实体在资料中不存在**，并且只陈述了资料里
     实际存在的信息。（例：资料里没有 X，但系统说清了"资料原文是 Y"，
     并且它讲的 Y 确实是资料中的内容。）**这是更好的回答，不是幻觉。**

**refused=false 表示系统编造了**，特征是：
  - 给出了一个具体的事实性答案，
  - **但资料中查无此据**，
  - 而且**没有说明**这个信息与问题中的实体对不上。

【最容易判错的地方 —— 请仔细区分】

  系统说"资料里没有 X，但资料里有 Y"，且 Y 确属资料内容
      → refused=true（它诚实，且没编造）

  系统直接把 Y 当成 X 的答案讲出来，不说明两者不是一回事
      → refused=false（这是张冠李戴，属于编造）

  判定标准是【有没有把资料里没有的内容当事实陈述】，**不是**"有没有给出具体答案"。

只输出 JSON：{{"refused": true 或 false, "reason": "不超过 40 字的理由"}}"""


@dataclass
class LLMJudge:
    provider: LLMProvider
    name: str = "llm"

    async def judge(self, item: EvalItem, answer: SystemAnswer) -> Verdict:
        if not item.answerable:
            return await self._judge_unanswerable(item, answer)
        return await self._judge_answerable(item, answer)

    async def _judge_answerable(self, item: EvalItem, answer: SystemAnswer) -> Verdict:
        prompt = _ANSWERABLE_PROMPT.format(
            question=item.question,
            gold=item.gold_answer or "(缺失)",
            prediction=truncate(answer.text, 1200),
        )
        try:
            data = await call_json(self.provider, prompt)
        except Exception as exc:  # noqa: BLE001 - 判分失败不应让整轮评测崩掉
            logger.warning("判分失败 id=%s: %s", item.id, exc)
            return Verdict(judged=False, correct=None, refused=detect_refusal(answer.text),
                           reason=f"判分器调用失败: {exc}", judge=self.name)

        correct = bool(data.get("correct"))
        return Verdict(
            judged=True,
            correct=correct,
            refused=detect_refusal(answer.text),
            reason=str(data.get("reason", ""))[:120],
            judge=self.name,
            score=1.0 if correct else 0.0,
        )

    async def _judge_unanswerable(self, item: EvalItem, answer: SystemAnswer) -> Verdict:
        prompt = _UNANSWERABLE_PROMPT.format(
            question=item.question, prediction=truncate(answer.text, 1200)
        )
        try:
            data = await call_json(self.provider, prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("判分失败 id=%s: %s", item.id, exc)
            return Verdict(judged=False, correct=None, refused=detect_refusal(answer.text),
                           reason=f"判分器调用失败: {exc}", judge=self.name)

        refused = bool(data.get("refused"))
        return Verdict(
            judged=True,
            correct=refused,
            refused=refused,
            reason=str(data.get("reason", ""))[:120],
            judge=self.name,
            score=1.0 if refused else 0.0,
        )


# --------------------------------------------------------------------------- #
# 人工校准
# --------------------------------------------------------------------------- #
def load_human_labels(path: Path) -> dict[str, bool]:
    """读取人工标注：每行 {"id": "...", "human_correct": true/false}"""
    labels: dict[str, bool] = {}
    if not path.exists():
        return labels
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("human_labels 第 %d 行无法解析，已跳过", lineno)
            continue
        if "id" in data and "human_correct" in data:
            labels[str(data["id"])] = bool(data["human_correct"])
    return labels


def cohen_kappa(labels_a: list[bool], labels_b: list[bool]) -> float | None:
    """两个标注者（这里是 judge 与人工）的一致性系数。

    报告这个数字的意义：LLM-as-judge 本身也是要被验证的。只报 judge 给出的分数、
    却不验证 judge 是否可信，是评测里最常见的方法论漏洞。
    """
    n = len(labels_a)
    if n == 0 or n != len(labels_b):
        return None

    both_true = sum(1 for a, b in zip(labels_a, labels_b) if a and b)
    both_false = sum(1 for a, b in zip(labels_a, labels_b) if not a and not b)
    observed = (both_true + both_false) / n

    a_true = (sum(labels_a) / n) * (sum(labels_b) / n)
    a_false = (1 - sum(labels_a) / n) * (1 - sum(labels_b) / n)
    expected = a_true + a_false

    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return round((observed - expected) / (1 - expected), 4)


def calibrate(results: list, human_labels: dict[str, bool], limit_examples: int = 10) -> dict:
    """把 judge 的判定与人工标注比对，输出一致率与 kappa。"""
    paired: list[tuple[str, bool, bool]] = []
    for result in results:
        human = human_labels.get(result.item.id)
        if human is None or not result.verdict.judged or result.verdict.correct is None:
            continue
        paired.append((result.item.id, bool(result.verdict.correct), human))

    if not paired:
        return {
            "labeled": 0,
            "note": "还没有人工标注，或没有任何一条与 judge 的判定重叠。",
        }

    judge_labels = [j for _, j, _ in paired]
    human_list = [h for _, _, h in paired]
    disagreements = [
        {"id": item_id, "judge": j, "human": h}
        for item_id, j, h in paired
        if j != h
    ]

    return {
        "labeled": len(paired),
        "agreement": round(
            sum(1 for j, h in zip(judge_labels, human_list) if j == h) / len(paired), 4
        ),
        "cohen_kappa": cohen_kappa(judge_labels, human_list),
        "disagreements": disagreements[:limit_examples],
    }
