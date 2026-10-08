"""判分器人工校准：抽样 → 生成盲标工作表 → 算 Cohen's kappa。

## 为什么要做这件事

我们用 LLM-as-judge 判分，但** judge 本身也是要被验证的**。
只报 judge 给出的分数、却不校验 judge 可不可信，
是 LLM 评测里最常见的方法论漏洞 —— 也是最容易被面试官抓住的一点。

抽 30 条左右人工标一遍，算 judge 与人的 Cohen's kappa：

    kappa > 0.8   判分器可信，指标可以直接对外
    0.6 ~ 0.8     可用，但报告里必须说明局限
    < 0.6         判分器需要改提示词或换模型，此时的 accuracy 没有意义

## 两个关键设计

**1. 分层抽样，且刻意多抽"judge 判错"的**

随机抽 30 条的话，按 78:20 的比例只会抽到约 6 条判错的，
kappa 会非常不稳定。所以：**抽全部判错项 + 一部分判对项**。
这样对"judge 能不能识别错误"更有鉴别力。

**2. 工作表里不显示 judge 的判定（盲标）**

先看 judge 说了什么再标，人会不自觉地往它那边靠 ——
算出来的 kappa 就成了自我实现的预言。所以生成的工作表是**盲的**，
judge 判定只存在单独的一份 key 文件里。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from eval.judges import cohen_kappa, load_human_labels

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATASETS_DIR = BACKEND_DIR / "eval" / "datasets"

TYPE_LABELS = {
    "single_hop": "单跳",
    "multi_hop": "多跳",
    "unanswerable": "不可回答",
}


def load_report(path: Path) -> dict:
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


def sample(report: dict, n_correct: int, seed: int = 20261006) -> list[dict]:
    """分层抽样：取全部判错项 + 指定数量的判对项（按题型平均分配）。"""
    results = [r for r in report["results"] if r["verdict"].get("judged")]

    wrong = [r for r in results if not r["verdict"]["correct"]]
    right = [r for r in results if r["verdict"]["correct"]]

    rng = random.Random(seed)

    # 判对项按题型分层，尽量每类都覆盖到
    by_type: dict[str, list[dict]] = {}
    for r in right:
        by_type.setdefault(r["type"], []).append(r)

    picked_right: list[dict] = []
    types = sorted(by_type)
    per_type = max(1, n_correct // max(1, len(types)))
    for t in types:
        pool = by_type[t][:]
        rng.shuffle(pool)
        picked_right.extend(pool[:per_type])
    # 不够就补
    remaining = [r for r in right if r not in picked_right]
    rng.shuffle(remaining)
    picked_right.extend(remaining[: max(0, n_correct - len(picked_right))])

    picked = wrong + picked_right
    rng.shuffle(picked)
    return picked


def _clip(text: str, limit: int = 420) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + " ……（已截断）"


def build_worksheet(items: list[dict]) -> str:
    """生成盲标工作表（不含 judge 判定）。"""
    lines: list[str] = [
        "# 判分器人工校准 —— 标注工作表",
        "",
        f"共 **{len(items)}** 条。预计需要 15~25 分钟。",
        "",
        "## 怎么判断",
        "",
        "对每一条，判断「**系统回答**」是否正确地回答了「**问题**」。",
        "",
        "| 题型 | 标 `对` 的条件 |",
        "|---|---|",
        "| 单跳 / 多跳 | 回答与「标准答案」**语义一致**（说法不同没关系，意思对就行） |",
        "| 不可回答 | 系统**明确表示答不了**（例如「根据现有资料无法回答」）。"
        "**只要编造了内容就算错** |",
        "",
        "> ⚠️ 这张表**故意不显示判分器的判定**。",
        "> 先看它说了什么再标，人会不自觉地往那个结论上靠，",
        "> 算出来的 kappa 就成了自我实现的预言。请独立判断。",
        "",
        "## 怎么回填",
        "",
        "按下面的表填 `对` 或 `错`，然后把表贴回来即可（编号对得上就行）。",
        "",
        "| # | 判定 |",
        "|---|---|",
    ]
    for i in range(1, len(items) + 1):
        lines.append(f"| {i} |  |")
    lines += ["", "---", "", "## 待标注条目", ""]

    for i, item in enumerate(items, start=1):
        kind = TYPE_LABELS.get(item["type"], item["type"])
        lines.append(f"### {i}. `{item['id']}` · {kind}")
        lines.append("")
        lines.append(f"**问题**：{_clip(item['question'], 260)}")
        lines.append("")
        if item["answerable"]:
            lines.append(f"**标准答案**：{_clip(item.get('gold_answer') or '（无）', 260)}")
            lines.append("")
        else:
            lines.append("**标准答案**：*（这道题的资料库里没有答案，正确做法是拒答）*")
            lines.append("")
        lines.append(f"**系统回答**：{_clip(item.get('prediction') or '（空）', 420)}")
        lines.append("")

    return "\n".join(lines)


def build_key(items: list[dict]) -> str:
    """生成对照 key（judge 的判定），用于事后算 kappa。"""
    rows = []
    for i, item in enumerate(items, start=1):
        rows.append(json.dumps(
            {
                "n": i,
                "id": item["id"],
                "type": item["type"],
                "judge_correct": bool(item["verdict"]["correct"]),
                "judge_reason": item["verdict"].get("reason", ""),
            },
            ensure_ascii=False,
        ))
    return "\n".join(rows) + "\n"


def calibrate_from_report(report: dict, human_labels: dict[str, bool]) -> dict:
    """用【已有的报告】算 kappa —— **不重跑评测**。

    ⚠️ 为什么必须这样，而不是跑 `run_eval --human-labels`：

    LLM 有随机性。重跑一遍会得到**不同的回答和判定**，
    人工标注的那几十条就对不上了 —— 算出来的 kappa 毫无意义。
    **必须用标注时看的那一份报告。**

    （`run_eval --human-labels` 适合"标注和评测同一次跑完"的流程；
      我们的标注是在评测之后做的，所以要用这个函数。）

    另外：人工标注里"不确定"的条目**不应该被强行二值化** ——
    那等于往数据里注入噪声。这类条目不出现在 labels 里，自然被排除，
    函数会报告实际参与计算的条数。
    """
    paired: list[tuple[dict, bool, bool]] = []
    for result in report["results"]:
        verdict = result.get("verdict") or {}
        if not verdict.get("judged") or verdict.get("correct") is None:
            continue
        human = human_labels.get(result["id"])
        if human is None:
            continue
        paired.append((result, bool(verdict["correct"]), human))

    if not paired:
        return {"labeled": 0, "note": "没有任何一条同时有人工标注和 judge 判定。"}

    judge_labels = [j for _, j, _ in paired]
    human_list = [h for _, _, h in paired]

    disagreements = [
        {
            "id": result["id"],
            "type": result["type"],
            "judge": j,
            "human": h,
            "judge_reason": (result.get("verdict") or {}).get("reason", ""),
            "question": result["question"],
            "gold_answer": result.get("gold_answer") or "（不可回答题）",
            "prediction": " ".join((result.get("prediction") or "").split())[:300],
        }
        for result, j, h in paired
        if j != h
    ]

    # 按题型拆开，能定位"判分器在哪类题上不可靠"
    by_type: dict[str, dict] = {}
    for result, j, h in paired:
        stat = by_type.setdefault(result["type"], {"n": 0, "agree": 0})
        stat["n"] += 1
        stat["agree"] += int(j == h)
    for stat in by_type.values():
        stat["agreement"] = round(stat["agree"] / stat["n"], 4)

    return {
        "labeled": len(paired),
        "agreement": round(
            sum(1 for j, h in zip(judge_labels, human_list) if j == h) / len(paired), 4
        ),
        "cohen_kappa": cohen_kappa(judge_labels, human_list),
        "judge_true_count": sum(judge_labels),
        "human_true_count": sum(human_list),
        "by_type": by_type,
        "disagreements": disagreements,
    }


def kappa_verdict(kappa: float | None) -> str:
    """按惯例阈值给结论（阈值是惯例，不是真理）。"""
    if kappa is None:
        return "无法计算"
    if kappa > 0.8:
        return "判分器可信，指标可以直接对外"
    if kappa >= 0.6:
        return "可用，但报告里必须说明局限"
    return "判分器需要改提示词或换模型，此时的 accuracy 没有意义"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="判分器人工校准：生成盲标工作表，或用已有报告算 Cohen's kappa"
    )
    parser.add_argument("report", type=Path, help="评测报告 JSON（建议用当前最优配置那份）")
    parser.add_argument(
        "--labels",
        type=Path,
        default=None,
        help="给了就进入【校准模式】：用这份报告 + 人工标注算 kappa（不重跑评测）",
    )
    parser.add_argument("--correct", type=int, default=12, help="生成模式下额外抽多少条 judge 判对的")
    parser.add_argument("--out", type=Path, default=DATASETS_DIR / "calibration_worksheet.md")
    parser.add_argument("--key", type=Path, default=DATASETS_DIR / "calibration_key.jsonl")
    parser.add_argument("--seed", type=int, default=20261006)
    return parser


def _run_calibration(args: argparse.Namespace) -> int:
    report = load_report(args.report)
    labels = load_human_labels(args.labels)

    print("=" * 84)
    print("  判分器人工校准（Cohen's kappa）")
    print("=" * 84)
    print(f"  报告 : {args.report.name}")
    print(f"  标注 : {args.labels.name}（文件里 {len(labels)} 条）")
    print("=" * 84)
    print()

    result = calibrate_from_report(report, labels)
    if not result.get("labeled"):
        print(f"  {result.get('note')}")
        return 1

    kappa = result["cohen_kappa"]
    print(f"  参与计算      : {result['labeled']} 条")
    print(f"  原始一致率    : {result['agreement']:.1%}"
          f"   （judge 判对 {result['judge_true_count']} / 人工判对 {result['human_true_count']}）")
    print(f"  Cohen's kappa : {kappa}")
    print(f"  结论          : {kappa_verdict(kappa)}")
    print()
    print("  按题型拆开（判分器在哪类题上不可靠）：")
    for item_type, stat in sorted(result["by_type"].items()):
        print(f"    {item_type:<16} n={stat['n']:<4} 一致 {stat['agree']}/{stat['n']}"
              f" = {stat['agreement']:.1%}")
    print()
    print(f"  分歧 {len(result['disagreements'])} 条 —— 每一条都指出了判分器的边界：")
    for d in result["disagreements"]:
        side = "judge 说对、人工说错" if d["judge"] else "judge 说错、人工说对"
        print()
        print(f"    [{d['id']} · {d['type']}]  {side}")
        print(f"      问题  : {d['question'][:78]}")
        print(f"      标准  : {d['gold_answer'][:78]}")
        print(f"      回答  : {d['prediction'][:110]}")
        print(f"      judge : {d['judge_reason'][:96]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)

    if args.labels:
        return _run_calibration(args)

    report = load_report(args.report)
    items = sample(report, args.correct, args.seed)
    wrong = sum(1 for r in items if not r["verdict"]["correct"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_worksheet(items), encoding="utf-8")
    args.key.write_text(build_key(items), encoding="utf-8")

    print(f"  报告           : {args.report.name}")
    print(f"  抽样 {len(items)} 条      : judge 判错 {wrong} 条 / 判对 {len(items) - wrong} 条")
    print(f"  工作表（盲标） : {args.out}")
    print(f"  对照 key       : {args.key}")
    print()
    print("  注意：工作表里【没有】judge 的判定，这是故意的（防止锚定）。")
    print("  标注完成后用 --labels 算 kappa（**不要重跑评测**）：")
    print("      .venv\\Scripts\\python -m eval.calibration <同一份报告.json> \\")
    print("          --labels eval\\datasets\\human_labels.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
