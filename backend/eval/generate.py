"""合成评测集：从语料出发，生成「单跳 / 多跳 / 不可回答」三类问题。

三类问题的生成难度和验证方式完全不同，这是本模块设计的核心：

| 类型 | 生成方式 | 关键验证 |
|---|---|---|
| 单跳 | 针对单个片段出事实题 | evidence 必须能定位回原文 |
| 多跳 | 先建实体共现索引，再对"共享实体的跨文档片段对"出桥接题 | 两段 evidence 都要能定位回原文 |
| 不可回答 | 把真实问题里的关键实体替换成语料中不存在的实体 | 替换后的实体必须**确实不在**语料里 |

最后一条是幻觉率指标能否成立的前提：如果替换出来的实体碰巧语料里有，
这道题就变成可回答的了，指标会假性偏高。

用法（在 backend 目录下）：
    python -m eval.generate --single 50 --multi 30 --unanswerable 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from app.config import get_settings
from app.llm import build_provider
from app.llm.provider import LLMProvider
from eval.cli import setup_console
from eval.corpus import Chunk, build_chunk_index, load_corpus
from eval.jsoncall import call_json
from eval.schema import EvalItem, GoldSpan
from eval.text import f1, locate_span, normalize_text

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RAW = BACKEND_DIR / "corpus" / "raw"
DEFAULT_OUT = BACKEND_DIR / "eval" / "datasets" / "qa_v1.jsonl"

logger = logging.getLogger("generate")

ID_PREFIX = {"single_hop": "sh", "multi_hop": "mh", "unanswerable": "un"}


# --------------------------------------------------------------------------- #
# 提示词
# --------------------------------------------------------------------------- #
# ⚠ 这里有个必须知道的 Python 陷阱：
#
#   提示词里含大量 JSON 示例（花括号），所以【绝对不能用 str.format() 填充】。
#   format 会把 {"question": ...} 里的 "question" 当成占位符名，直接抛：
#       KeyError: '"question"'
#   —— 而且五个片段会在同一秒内全部失败，看起来像"网络问题"，很难排查。
#
#   所以我们用 <<NAME>> 这种和 JSON 不会冲突的占位符，配合 .replace() 填充。
#   （另一条路是把 JSON 里的花括号都写成 {{ }}，但可读性差很多。）
# --------------------------------------------------------------------------- #
ENTITY_PROMPT = """你在为一个知识库构建实体索引，目的是后续能把不同片段按共享实体关联起来。

请为下面每个片段抽取 2~5 个关键实体，要求：
- 实体类型限定为：人名、机构/公司名、产品名、地名、编号或型号、具体数字指标。
- 必须是片段中**逐字出现**的字符串，不要改写、不要概括。
- 只抽真正有辨识度的实体，不要抽"公司""系统""平台"这类泛指词。

只输出 JSON，格式：
{"chunks": [{"chunk_id": "片段id", "entities": ["实体1", "实体2"]}]}

片段列表：
<<LISTING>>"""

SINGLE_HOP_PROMPT = """你在为问答系统编写评测题。请根据下面这一段知识库文本，出一道**只能依赖该段文本回答**的事实性问题。

要求：
1. 问题必须能用文本中的原文事实直接回答，不能依赖文本之外的知识。
2. 答案是一个简短的事实（人名 / 机构 / 日期 / 数字 / 名称），不超过 30 字。
3. evidence 必须是文本中**逐字出现**的原文子串（建议 15~60 字），且包含答案所依据的事实。
4. 不要出"这段文字讲了什么"这类概括题。

只输出 JSON：
{"question": "问题", "answer": "简短答案", "evidence": "逐字原文子串"}

知识库文本（标题：<<TITLE>>）：
<<TEXT>>"""

MULTI_HOP_PROMPT = """你在为问答系统编写评测题。下面给出两段来自同一知识库的文本，二者通过某个实体相互关联。

请出一道**必须同时用到两段文本**才能回答的【桥接式】问题。

## 什么算桥接式（必须是这样）

第一段的答案，要成为进入第二段的"钥匙"，形成 A → B → C 的推理链。

✅ 好例子：
    「星澜科技负责边缘计算业务线的负责人是谁？他主导开发的产品搭载了哪家公司的芯片？」
    推理链：第一段得到"林澈/边缘计算团队" → 拿这个结果去第二段找"该团队开发的产品用了谁的芯片"

## 什么不算（会被丢掉，别写成这样）

❌ 并列式：把两个互不相关的问题用逗号拼在一起。
   坏例子：「澜芯 X2 用哪家公司的芯片？企业版客户的支持由哪个团队对接？」
   —— 两个问句之间没有任何推理关系，拆成两道单跳题各答各的就行。

❌ 伪多跳：只用其中一段就能答出来，第二段其实是摆设。

## 其他要求

1. 只用其中任意一段都无法完整回答。
2. 答案是简短事实，不超过 30 字。
3. evidence_a / evidence_b 必须分别是两段文本中**逐字出现**的原文子串。
4. 用自然语言提问，不要暴露"根据片段A、片段B"这种出题痕迹。
5. 代词指代必须明确，不要把第一段某个主体的属性安到第二段的另一个主体身上。

只输出 JSON：
{"question": "问题", "answer": "简短答案", "evidence_a": "片段A原文子串", "evidence_b": "片段B原文子串"}

片段 A：
<<TEXT_A>>

片段 B：
<<TEXT_B>>"""

PERTURB_PROMPT = """下面是一道可在某知识库中回答的问题及其原文依据。
请把问题中的关键实体，替换掉，使这个问题在那个知识库中【完全无法回答】。

## 替换规则（很容易做错，仔细看）

替换后的实体必须是【**虚构的**】—— 现实中不存在，知识库里更不存在。
但要读起来像个真实的同类名字。

❌ 错误做法：换成另一个**真实存在**的同类实体。
   例如把「Vue」换成「React」、「Svelte」——这些名字非常可能在知识库里被提到过
   （技术文档经常拿它们做对比），那这道题就变成可回答的了，会被丢弃。

✅ 正确做法：换成一个**听起来合理的虚构名**。
   · 公司名 → 「云启智造」「星澜芯科」
   · 产品名 → 「澜芯 X3」「智汇云 X9」
   · 版本号 → 「Vue 4」「v9.9」
   · API/指令名 → 造一个同类的新名字，比如把 `v-memo` 改成 `v-cache`

**技术文档语料特别注意**：文档里往往提到大量其它框架和库的名字（React、Svelte、
Vitest、Sentry……），所以绝对不要拿这些真实名字来替换。

只输出 JSON：
{"question": "替换后的问题", "replaced_with": "你替换进去的虚构实体", "original": "被替换掉的实体"}

原问题：<<QUESTION>>
原文依据：<<EVIDENCE>>"""


VALIDATE_DERIVABLE_PROMPT = """下面是一道评测题、它的标准答案，以及出题时依据的两段原文。

请判断：这个标准答案，能否【从这两段原文中推导出来】？

判定规则：
- 原文里明确写着答案 → 算"能推导"。
- 以下情况都算"不能推导"：
  · 答案与原文矛盾；
  · 原文里找不到支撑答案的依据；
  · 张冠李戴 —— 把 A 的属性安到 B 身上（例如原文说 X1 用某芯片，而问题问的是 X2）。

只输出 JSON：
{"derivable": true 或 false, "reason": "不超过 40 字的理由"}

【问题】<<QUESTION>>
【标准答案】<<ANSWER>>
【原文 A】<<TEXT_A>>
【原文 B】<<TEXT_B>>"""

VALIDATE_NECESSITY_PROMPT = """下面是一道评测题、它的标准答案，以及两段原文中的【其中一段】。

请判断：只看这一段原文，能否回答这个问题？

判定规则：
- 如果这一段里已经包含了回答问题所需的全部信息 → sufficient = true
- 只有必须靠另一段补充信息才能回答 → 才回答 sufficient = false
- 判断依据是"信息够不够"，不是"措辞像不像"。

只输出 JSON：
{"sufficient": true 或 false, "reason": "不超过 40 字的理由"}

【问题】<<QUESTION>>
【标准答案】<<ANSWER>>
【这一段原文】<<TEXT>>"""


def fill(template: str, **values: str) -> str:
    """用 <<NAME>> 占位符填充提示词。

    不用 str.format()，因为提示词里的 JSON 示例会让 format 误判占位符（见上方说明）。
    """
    result = template
    for key, value in values.items():
        result = result.replace(f"<<{key.upper()}>>", value)
    return result


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _is_duplicate(candidate: str, existing: list[str], threshold: float = 0.85) -> bool:
    normalized = normalize_text(candidate)
    if not normalized:
        return True
    if any(normalized == normalize_text(other) for other in existing):
        return True
    return any(f1(candidate, other) >= threshold for other in existing)


# --------------------------------------------------------------------------- #
# 阶段 1：实体索引
# --------------------------------------------------------------------------- #
async def extract_entities(
    provider: LLMProvider,
    chunks: list[Chunk],
    *,
    batch_size: int = 8,
    concurrency: int = 3,
    max_chunks: int = 240,
    rng: random.Random | None = None,
) -> dict[str, list[str]]:
    """给片段抽实体，用于后续按"共享实体"配对出多跳题。

    ⚠ 为什么要 max_chunks 采样？
    实体抽取要给【每个片段】都发一次模型请求（按 batch_size=8 打包）。
    语料有 1919 个片段时，那就是 240 次调用 —— 但我们最终只需要几十道多跳题，
    给全部片段抽实体纯属浪费钱和时间。

    采样 240 个片段（30 批）已经足够配出几百个候选片段对，
    而调用量降到 1/8。这是"够用就好"的典型取舍。
    """
    pool = list(chunks)
    if max_chunks and len(pool) > max_chunks:
        (rng or random).shuffle(pool)
        pool = pool[:max_chunks]
        logger.info("实体抽取只采样 %d/%d 个片段（够配多跳题即可）", max_chunks, len(chunks))

    batches = [pool[i : i + batch_size] for i in range(0, len(pool), batch_size)]
    semaphore = asyncio.Semaphore(concurrency)

    async def one(batch: list[Chunk]) -> dict[str, list[str]]:
        listing = "\n\n".join(f"[{c.chunk_id}] ({c.title})\n{c.text}" for c in batch)
        async with semaphore:
            try:
                data = await call_json(provider, fill(ENTITY_PROMPT, listing=listing))
            except Exception as exc:  # noqa: BLE001
                logger.warning("实体抽取失败，跳过该批: %s", exc)
                return {}

        result: dict[str, list[str]] = {}
        for row in data.get("chunks", []):
            chunk_id = _clean(row.get("chunk_id"))
            entities = [_clean(e) for e in row.get("entities", []) if _clean(e)]
            if chunk_id and entities:
                result[chunk_id] = entities
        return result

    merged: dict[str, list[str]] = {}
    for partial in await asyncio.gather(*(one(b) for b in batches)):
        merged.update(partial)

    logger.info("实体索引完成：%d/%d 个片段抽到实体", len(merged), len(chunks))
    return merged


def build_entity_pairs(
    entity_map: dict[str, list[str]],
    chunks_by_id: dict[str, Chunk],
    *,
    cross_doc_only: bool = True,
) -> list[tuple[str, Chunk, Chunk]]:
    """返回 (共享实体, 片段A, 片段B) 列表。优先跨文档——那才是真正的多跳。"""
    inverted: dict[str, list[str]] = defaultdict(list)
    for chunk_id, entities in entity_map.items():
        for entity in entities:
            key = normalize_text(entity)
            if len(key) >= 2:
                inverted[key].append(chunk_id)

    pairs: list[tuple[str, Chunk, Chunk]] = []
    seen: set[tuple[str, str]] = set()

    for key, chunk_ids in inverted.items():
        if len(chunk_ids) < 2:
            continue
        for left, right in combinations(sorted(set(chunk_ids)), 2):
            chunk_a, chunk_b = chunks_by_id.get(left), chunks_by_id.get(right)
            if chunk_a is None or chunk_b is None:
                continue
            if cross_doc_only and chunk_a.doc_id == chunk_b.doc_id:
                continue
            if (left, right) in seen:
                continue
            seen.add((left, right))
            pairs.append((key, chunk_a, chunk_b))

    return pairs


# --------------------------------------------------------------------------- #
# 阶段 2：单跳
# --------------------------------------------------------------------------- #
async def generate_single_hop(
    provider: LLMProvider,
    chunks: list[Chunk],
    count: int,
    *,
    concurrency: int = 4,
    rng: random.Random,
) -> list[EvalItem]:
    pool = list(chunks)
    rng.shuffle(pool)
    pool = pool[: max(count * 2, count)]
    semaphore = asyncio.Semaphore(concurrency)

    async def one(chunk: Chunk) -> EvalItem | None:
        async with semaphore:
            try:
                data = await call_json(
                    provider, fill(SINGLE_HOP_PROMPT, title=chunk.title, text=chunk.text)
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("单跳出题失败 (%s): %s", chunk.chunk_id, exc)
                return None

        question, answer = _clean(data.get("question")), _clean(data.get("answer"))
        evidence = _clean(data.get("evidence"))
        if not question or not answer or not evidence:
            return None

        # 关键验证：evidence 必须能定位回原文，否则 gold span 不可信
        span_text = locate_span(chunk.text, evidence)
        if span_text is None:
            logger.warning("证据无法定位到原文，丢弃：%s", question)
            return None

        return EvalItem(
            id="",
            question=question,
            type="single_hop",
            answerable=True,
            gold_answer=answer,
            gold_spans=[GoldSpan(doc_id=chunk.doc_id, text=span_text)],
            notes=f"来源 {chunk.chunk_id}（{chunk.title}）",
        )

    items = [item for item in await asyncio.gather(*(one(c) for c in pool)) if item]
    logger.info("单跳候选生成 %d 条（目标 %d）", len(items), count)
    return items


# --------------------------------------------------------------------------- #
# 阶段 3：多跳
# --------------------------------------------------------------------------- #
async def generate_multi_hop(
    provider: LLMProvider,
    pairs: list[tuple[str, Chunk, Chunk]],
    count: int,
    *,
    concurrency: int = 3,
    rng: random.Random,
) -> list[EvalItem]:
    rng.shuffle(pairs)
    # 实测淘汰率约 70%（三道校验很严格：证据定位 + 可解答性 + 必要性），
    # 所以候选要按目标的 4 倍生成，否则凑不够数。
    pool = pairs[: max(count * 4, count)]
    semaphore = asyncio.Semaphore(concurrency)

    async def one(pair: tuple[str, Chunk, Chunk]) -> EvalItem | None:
        entity, chunk_a, chunk_b = pair

        # 整个流程（出题 + 三道校验）都在并发闸门内，
        # 否则校验阶段的请求会不受限地打出去。
        async with semaphore:
            # ---------- 第一步：出题 ----------
            try:
                data = await call_json(
                    provider,
                    fill(MULTI_HOP_PROMPT, text_a=chunk_a.text, text_b=chunk_b.text),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("多跳出题失败 (%s|%s): %s", chunk_a.chunk_id, chunk_b.chunk_id, exc)
                return None

            question, answer = _clean(data.get("question")), _clean(data.get("answer"))
            evidence_a = _clean(data.get("evidence_a"))
            evidence_b = _clean(data.get("evidence_b"))
            if not question or not answer or not evidence_a or not evidence_b:
                return None

            # ---------- 校验 1/3：证据必须能定位回原文 ----------
            span_a = locate_span(chunk_a.text, evidence_a)
            span_b = locate_span(chunk_b.text, evidence_b)
            if span_a is None or span_b is None:
                logger.info("丢弃：多跳证据无法定位到原文 —— %s", question)
                return None

            # ---------- 校验 2/3：可解答性（答案真的能从这两段推出吗）----------
            # 抓的是"张冠李戴"：实测出现过 原文说 X1 用某芯片，题却问 X2，答案直接不成立。
            try:
                verdict = await call_json(
                    provider,
                    fill(
                        VALIDATE_DERIVABLE_PROMPT,
                        question=question,
                        answer=answer,
                        text_a=chunk_a.text,
                        text_b=chunk_b.text,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("可解答性校验失败，丢弃：%s（%s）", question, exc)
                return None

            if not verdict.get("derivable"):
                logger.info(
                    "丢弃：答案无法从原文推导 —— %s  |  %s",
                    question,
                    str(verdict.get("reason", ""))[:44],
                )
                return None

            # ---------- 校验 3/3：必要性（只看一段能不能答）----------
            # 抓的是"伪多跳"：出题模型经常写出一道用单段就能答的题，
            # 只是形式上引用了两段，实际上第二段是摆设。
            for label, text in (("A", chunk_a.text), ("B", chunk_b.text)):
                try:
                    verdict = await call_json(
                        provider,
                        fill(
                            VALIDATE_NECESSITY_PROMPT,
                            question=question,
                            answer=answer,
                            text=text,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("必要性校验失败，丢弃：%s（%s）", question, exc)
                    return None

                if verdict.get("sufficient"):
                    logger.info(
                        "丢弃：伪多跳（只看片段 %s 就能答）—— %s  |  %s",
                        label,
                        question,
                        str(verdict.get("reason", ""))[:40],
                    )
                    return None

            return EvalItem(
                id="",
                question=question,
                type="multi_hop",
                answerable=True,
                gold_answer=answer,
                gold_spans=[
                    GoldSpan(doc_id=chunk_a.doc_id, text=span_a),
                    GoldSpan(doc_id=chunk_b.doc_id, text=span_b),
                ],
                notes=f"关联实体「{entity}」，来源 {chunk_a.chunk_id} + {chunk_b.chunk_id}",
            )

    items = [item for item in await asyncio.gather(*(one(p) for p in pool)) if item]
    logger.info("多跳候选生成 %d 条（目标 %d）", len(items), count)
    return items


# --------------------------------------------------------------------------- #
# 阶段 4：不可回答
# --------------------------------------------------------------------------- #
async def generate_unanswerable(
    provider: LLMProvider,
    seeds: list[EvalItem],
    corpus_text_normalized: str,
    count: int,
    *,
    concurrency: int = 3,
    rng: random.Random,
) -> list[EvalItem]:
    pool = [s for s in seeds if s.gold_spans and s.gold_answer]
    rng.shuffle(pool)
    # 不可回答题容易被淘汰（模型替换出来的实体常常在语料里真实存在），
    # 所以按目标的 3 倍取种子。种子总数本身也是上限（每条单跳题只能派生一道）。
    pool = pool[: max(count * 3, count)]
    semaphore = asyncio.Semaphore(concurrency)

    async def one(seed: EvalItem) -> EvalItem | None:
        async with semaphore:
            try:
                data = await call_json(
                    provider,
                    fill(
                        PERTURB_PROMPT,
                        question=seed.question,
                        evidence=seed.gold_spans[0].text,
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("不可回答题生成失败: %s", exc)
                return None

        question = _clean(data.get("question"))
        replaced = _clean(data.get("replaced_with"))
        if not question or not replaced:
            return None

        # 关键验证：替换进去的实体必须真的不在语料里，
        # 否则这道题其实是可回答的，会让幻觉率虚高。
        needle = normalize_text(replaced)
        if len(needle) < 2 or needle in corpus_text_normalized:
            logger.warning("替换实体「%s」在语料中存在，丢弃该题", replaced)
            return None

        if normalize_text(question) == normalize_text(seed.question):
            return None

        return EvalItem(
            id="",
            question=question,
            type="unanswerable",
            answerable=False,
            gold_answer=None,
            gold_spans=[],
            notes=f"由 {seed.id or '单跳题'} 扰动而来，替换实体「{replaced}」（语料中不存在）",
        )

    items = [item for item in await asyncio.gather(*(one(s) for s in pool)) if item]
    logger.info("不可回答题候选生成 %d 条（目标 %d）", len(items), count)
    return items


# --------------------------------------------------------------------------- #
# 收尾：去重 + 编号 + 落盘
# --------------------------------------------------------------------------- #
def dedup_and_trim(
    singles: list[EvalItem], multis: list[EvalItem], unanswerables: list[EvalItem],
    targets: dict[str, int],
) -> list[EvalItem]:
    """按类型分别去重，再按目标数量截断，最后统一编号。

    去重是必须的：模型生成 100 道题时，重复问同一个事实的概率很高，
    而重复样本会直接放大对应指标在总分里的权重。
    """
    buckets: dict[str, list[EvalItem]] = {
        "single_hop": singles,
        "multi_hop": multis,
        "unanswerable": unanswerables,
    }

    final: list[EvalItem] = []
    for item_type, items in buckets.items():
        kept: list[EvalItem] = []
        questions: list[str] = []
        for item in items:
            if item_type == "unanswerable" and not item.question:
                continue
            if _is_duplicate(item.question, questions):
                continue
            questions.append(item.question)
            kept.append(item)

        target = targets.get(item_type, len(kept))
        if len(kept) < target:
            logger.warning(
                "%s 只生成出 %d 条，少于目标 %d 条（生成阶段有校验淘汰，属正常现象）",
                item_type, len(kept), target,
            )
        kept = kept[:target]

        prefix = ID_PREFIX[item_type]
        for index, item in enumerate(kept, start=1):
            item.id = f"{prefix}-{index:03d}"
        final.extend(kept)

    return final


def write_review(items: list[EvalItem], path: Path, raw_dir: Path) -> None:
    """生成人工抽检清单。合成评测集不经过人工复核就直接用，是方法论上的硬伤。"""
    lines = [
        "# 评测集人工抽检清单",
        "",
        f"语料目录：`{raw_dir}`",
        f"共 {len(items)} 条。**发布前请至少抽检 20 条**，重点看下面三项：",
        "",
        "1. 问题是否真的只能靠 gold 片段回答（有没有引入语料外知识）；",
        "2. 不可回答题里被替换的实体，是不是真的在语料中不存在；",
        "3. 多跳题是否确实需要跨两个片段（只用一段就能答的，应删除）。",
        "",
        "抽检结论请回填到 `human_labels.jsonl`，用于校准判分器。",
        "",
    ]
    for item in items:
        lines.append(f"## `{item.id}` · {item.type}")
        lines.append("")
        lines.append(f"- **问题**：{item.question}")
        lines.append(f"- **标准答案**：{item.gold_answer if item.gold_answer else '（不可回答）'}")
        for index, span in enumerate(item.gold_spans, start=1):
            lines.append(f"- **gold 片段 {index}**（doc `{span.doc_id}`）：{span.text}")
        if item.notes:
            lines.append(f"- **备注**：{item.notes}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def load_existing(path: Path) -> list[EvalItem]:
    if not path.exists():
        return []
    items: list[EvalItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            try:
                items.append(EvalItem.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError):
                continue
    return items


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从语料合成评测集")
    parser.add_argument("--raw", type=Path, default=DEFAULT_RAW, help="原始语料目录（.md/.txt）")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--single", type=int, default=50, help="单跳题目标数量")
    parser.add_argument("--multi", type=int, default=30, help="多跳题目标数量")
    parser.add_argument("--unanswerable", type=int, default=20, help="不可回答题目标数量")
    parser.add_argument("--chunk-size", type=int, default=800)
    parser.add_argument("--chunk-overlap", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument(
        "--entity-sample",
        type=int,
        default=240,
        help="实体抽取最多采样多少个片段（只为配多跳题服务，不必全量）",
    )
    parser.add_argument(
        "--allow-mock", action="store_true",
        help="允许用 mock 模型跑（产物是垃圾，只用于验证脚本本身不报错）",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="读取已有输出，跳过已经满足数量的类型（避免重复烧钱）",
    )
    return parser


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()

    if settings.is_mock and not args.allow_mock:
        logger.error(
            "当前是 mock 模式，合成出来的题目没有意义。\n"
            "请先在 backend/.env 填入 LLM_API_KEY，"
            "或加 --allow-mock 仅验证脚本本身能跑通（产物不可用）。"
        )
        return 2

    docs = load_corpus(args.raw)
    chunks = build_chunk_index(docs, size=args.chunk_size, overlap=args.chunk_overlap)
    corpus_normalized = normalize_text("\n".join(d.text for d in docs))
    chunks_by_id = {c.chunk_id: c for c in chunks}
    logger.info("语料：%d 篇文档 / %d 个片段", len(docs), len(chunks))

    provider = build_provider()
    rng = random.Random(args.seed)

    existing = load_existing(args.out) if args.resume else []
    have = Counter(item.type for item in existing)
    targets = {
        "single_hop": args.single,
        "multi_hop": args.multi,
        "unanswerable": args.unanswerable,
    }

    singles = [i for i in existing if i.type == "single_hop"]
    multis = [i for i in existing if i.type == "multi_hop"]
    unanswerables = [i for i in existing if i.type == "unanswerable"]

    # ---- 单跳 ----
    if len(singles) < args.single:
        singles += await generate_single_hop(
            provider, chunks, args.single - len(singles),
            concurrency=args.concurrency, rng=rng,
        )
    else:
        logger.info("单跳题已满足数量，跳过（resume）")

    # ---- 多跳 ----
    if len(multis) < args.multi:
        entity_map = await extract_entities(
            provider,
            chunks,
            concurrency=3,
            max_chunks=args.entity_sample,
            rng=rng,
        )
        pairs = build_entity_pairs(entity_map, chunks_by_id, cross_doc_only=True)
        if not pairs:
            logger.warning("没有找到跨文档共享实体的片段对，放宽为同文档不同片段")
            pairs = build_entity_pairs(entity_map, chunks_by_id, cross_doc_only=False)
        logger.info("可用的多跳片段对：%d", len(pairs))
        if pairs:
            multis += await generate_multi_hop(
                provider, pairs, args.multi - len(multis),
                concurrency=max(2, args.concurrency - 1), rng=rng,
            )
    else:
        logger.info("多跳题已满足数量，跳过（resume）")

    # ---- 不可回答 ----
    if len(unanswerables) < args.unanswerable:
        unanswerables += await generate_unanswerable(
            provider, singles, corpus_normalized, args.unanswerable - len(unanswerables),
            concurrency=args.concurrency, rng=rng,
        )
    else:
        logger.info("不可回答题已满足数量，跳过（resume）")

    items = dedup_and_trim(singles, multis, unanswerables, targets)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fp:
        for item in items:
            fp.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

    stats = {
        "raw_dir": str(args.raw),
        "documents": len(docs),
        "chunks": len(chunks),
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
        "seed": args.seed,
        "counts": dict(Counter(item.type for item in items)),
        "total": len(items),
    }
    (args.out.with_suffix(".stats.json")).write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_review(items, args.out.with_suffix(".review.md"), args.raw)

    logger.info("评测集已写入 %s", args.out)
    for item_type, num in stats["counts"].items():
        logger.info("  %-14s %d", item_type, num)
    logger.info("人工抽检清单：%s", args.out.with_suffix(".review.md"))
    return 0


def main() -> int:
    setup_console()
    args = build_parser().parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
