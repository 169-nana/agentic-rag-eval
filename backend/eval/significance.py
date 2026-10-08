"""显著性检验：判断两个评测结果之间的差异是真的，还是噪声。

## 为什么必须做这一步

实测教训：加权 RRF 的消融里，不同配置的正确率在 ±0.03 之间乱跳，
而且互相矛盾（正确率最高的配置幻觉率最差）。停下来一算才发现：

    98 道题的评测集，对"正确率"只能分辨约 0.10~0.14 的差异
    小于这个数的一切对比，都是在读噪声

**报数字不报样本量，等于在误导人。**

## 为什么必须用配对检验

两次评测跑的是【同一批题】，只是系统配置不同 —— 这是配对数据。

用独立双样本公式会把"题目难度差异"当成噪声，而配对设计里它已经被消掉了。
实测：同一份数据，独立公式得出"全部不显著"，McNemar 能识别出真实效果。

配对数据看的是【不一致的对】：
    b = 之前错、现在对   （改动救回来的）
    c = 之前对、现在错   （改动弄丢的）
原假设下 b ~ Binomial(b+c, 0.5) → McNemar 精确检验

## 用法

    cd backend
    .venv\\Scripts\\python -m eval.significance A报告.json B报告.json

    不传参数时，自动比对 eval/reports 下 tag 最新的一对报告。
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPORTS_DIR = BACKEND_DIR / "eval" / "reports"

# 判定显著性的阈值。0.05 是惯例，不是真理。
ALPHA = 0.05


@dataclass
class Comparison:
    """一次配对比较的结果。"""

    label_a: str
    label_b: str
    total: int              # 参与比较的题目数
    fixed: int              # b：之前错、现在对
    broken: int             # c：之前对、现在错
    p_value: float

    @property
    def significant(self) -> bool:
        return self.p_value < ALPHA

    @property
    def verdict(self) -> str:
        if not self.significant:
            return "不显著（差异在噪声范围内）"
        return "显著变好 ✅" if self.fixed > self.broken else "显著变差 ❌"


def mcnemar_exact(fixed: int, broken: int) -> float:
    """McNemar 精确检验的双侧 p 值。

    在"改动无效"的原假设下，救回数 b ~ Binomial(b+c, 0.5)。
    双侧 p = 2 × P(X ≤ min(b, c))，封顶 1.0。
    """
    n = fixed + broken
    if n == 0:
        return 1.0
    k = min(fixed, broken)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5**n)
    return min(1.0, 2 * tail)


def load_report(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


def compare(
    report_a: dict,
    report_b: dict,
    label_a: str = "A",
    label_b: str = "B",
    only_type: str | None = None,
) -> Comparison:
    """比较两份报告，只统计【两边的可回答题】中判分不同的那些。"""
    a_map = {r["id"]: r for r in report_a["results"]}
    b_map = {r["id"]: r for r in report_b["results"]}

    fixed = broken = total = 0
    for qid, a in a_map.items():
        b = b_map.get(qid)
        if b is None or not a.get("answerable"):
            continue
        if only_type and a.get("type") != only_type:
            continue
        total += 1
        a_ok = bool(a["verdict"].get("correct"))
        b_ok = bool(b["verdict"].get("correct"))
        if not a_ok and b_ok:
            fixed += 1
        elif a_ok and not b_ok:
            broken += 1

    return Comparison(
        label_a=label_a,
        label_b=label_b,
        total=total,
        fixed=fixed,
        broken=broken,
        p_value=mcnemar_exact(fixed, broken),
    )


def describe(cmp: Comparison) -> str:
    lines = [
        f"  {cmp.label_a}  →  {cmp.label_b}",
        f"      参与比较 {cmp.total} 题   救回 {cmp.fixed} / 弄丢 {cmp.broken}"
        f"   p = {cmp.p_value:.4f}   {cmp.verdict}",
    ]
    if not cmp.significant and (cmp.fixed or cmp.broken):
        lines.append(
            f"      （方向是{'变好' if cmp.fixed > cmp.broken else '变差'}，"
            f"但样本量不足以确认 —— 需要更多题目）"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="两个评测结果之间的配对显著性检验")
    parser.add_argument("report_a", nargs="?", type=Path)
    parser.add_argument("report_b", nargs="?", type=Path)
    parser.add_argument(
        "--type",
        default=None,
        choices=["single_hop", "multi_hop"],
        help="只比某一类题（多跳题样本少，单独看更有意义）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)

    if args.report_a and args.report_b:
        path_a, path_b = args.report_a, args.report_b
    else:
        # 没给参数就自动取最新两份报告
        found = sorted(glob.glob(str(REPORTS_DIR / "*.json")))
        if len(found) < 2:
            print("评测报告不足两份，先跑 eval.run_eval 生成报告", file=sys.stderr)
            return 1
        path_a, path_b = Path(found[-2]), Path(found[-1])

    report_a, report_b = load_report(path_a), load_report(path_b)

    print("=" * 84)
    print("  配对显著性检验（McNemar 精确检验）")
    print("=" * 84)
    print(f"  A: {path_a.name}")
    print(f"  B: {path_b.name}")
    print("=" * 84)
    print()

    if args.type:
        print(describe(compare(report_a, report_b, path_a.stem[:34], path_b.stem[:34], args.type)))
    else:
        print(describe(compare(report_a, report_b, path_a.stem[:34], path_b.stem[:34], None)))
        print()
        print("  按题型拆开：")
        for item_type in ("single_hop", "multi_hop"):
            print(describe(compare(report_a, report_b, "A", "B", item_type)))

    print()
    print("  提醒：p < 0.05 只是惯例阈值。"
          "p 在 0.05~0.15 之间属于【方向明确但样本不足】，")
    print("        正确的做法是补样本，而不是直接下结论或直接丢弃。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
