"""评测集校验。

合成出来的评测集**必须**过一遍校验才能用。这个模块检查的都是
"看着没问题、但会让指标失真"的隐性缺陷：

- gold 原文片段在语料里根本找不到 → 检索永远不可能命中，召回率被系统性压低
- 不可回答题却带着 gold 片段 → 幻觉率统计口径被污染
- 问题重复 → 同一个事实在总分里被重复计权
- doc_id 对不上 → 说明语料换过，评测集已失效

用法（在 backend 目录下）：
    python -m eval.validate --dataset eval/datasets/qa_seed.jsonl --raw corpus/raw
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from eval.cli import setup_console
from eval.corpus import load_corpus
from eval.schema import EvalItem
from eval.text import is_covered, normalize_text, truncate

logger = logging.getLogger("validate")
BACKEND_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Problem:
    item_id: str
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.item_id}: {self.detail}"


def load_dataset(path: Path) -> list[EvalItem]:
    items: list[EvalItem] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            items.append(EvalItem.from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError) as exc:
            raise ValueError(f"{path.name} 第 {lineno} 行无法解析: {exc}") from exc
    return items


def validate(items: list[EvalItem], raw_dir: Path) -> tuple[list[Problem], dict]:
    docs = load_corpus(raw_dir)
    docs_by_id = {doc.doc_id: doc for doc in docs}
    corpus_normalized = normalize_text("\n".join(doc.text for doc in docs))

    problems: list[Problem] = []
    seen: dict[str, str] = {}

    for item in items:
        if item.type not in ("single_hop", "multi_hop", "unanswerable"):
            problems.append(Problem(item.id, "type", f"未知题型 {item.type}"))

        if item.answerable:
            if not item.gold_answer:
                problems.append(Problem(item.id, "missing_answer", "可回答题缺少 gold_answer"))
            if not item.gold_spans:
                problems.append(Problem(item.id, "missing_span", "可回答题缺少 gold 片段"))
        else:
            if item.gold_spans:
                problems.append(Problem(item.id, "bad_unanswerable", "不可回答题不应带 gold 片段"))
            if item.gold_answer:
                problems.append(Problem(item.id, "bad_unanswerable", "不可回答题不应有 gold_answer"))
            # 不可回答题的关键实体应确实不在语料中（这里只能做粗检，最终靠人工抽检）
            if normalize_text(item.question) and _all_terms_present(item.question, corpus_normalized):
                problems.append(
                    Problem(item.id, "suspect_answerable", "问题中的词几乎都在语料里，可能是可回答的")
                )

        for span in item.gold_spans:
            doc = docs_by_id.get(span.doc_id)
            if doc is None:
                problems.append(
                    Problem(item.id, "unknown_doc", f"doc_id {span.doc_id} 不在当前语料中（语料换过？）")
                )
            elif not is_covered(span.text, doc.text):
                problems.append(
                    Problem(item.id, "span_not_found", f"片段「{truncate(span.text, 40)}」在原文中找不到")
                )

        key = normalize_text(item.question)
        if key in seen:
            problems.append(Problem(item.id, "duplicate", f"与 {seen[key]} 是重复问题"))
        else:
            seen[key] = item.id

    stats = {
        "total": len(items),
        "by_type": dict(Counter(item.type for item in items)),
        "documents": len(docs),
        "answerable": sum(1 for i in items if i.answerable),
        "unanswerable": sum(1 for i in items if not i.answerable),
        "multi_span_items": sum(1 for i in items if len(i.gold_spans) > 1),
        "problems": len(problems),
    }
    return problems, stats


def _all_terms_present(question: str, corpus_normalized: str) -> bool:
    """粗略判断：问题里长度 >= 3 的连续字符串是否都出现在语料中。

    命中越多越可能是可回答题。这是一个启发式，误报率不低，
    所以它只作为 warning 级别的提示，最终仍需人工抽检确认。
    """
    normalized = normalize_text(question)
    if len(normalized) < 6:
        return False
    windows = [normalized[i : i + 3] for i in range(len(normalized) - 2)]
    if not windows:
        return False
    hit = sum(1 for w in windows if w in corpus_normalized)
    return hit / len(windows) > 0.95


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description="校验评测集")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--raw", type=Path, default=BACKEND_DIR / "corpus" / "raw")
    parser.add_argument("--strict", action="store_true", help="有 warning 也返回非零退出码")
    args = parser.parse_args()

    items = load_dataset(args.dataset)
    problems, stats = validate(items, args.raw)

    print(f"数据集   {args.dataset}")
    print(f"语料     {args.raw}（{stats['documents']} 篇）")
    print(f"条数     {stats['total']}  {stats['by_type']}")
    print(f"多片段题 {stats['multi_span_items']} 条（多跳题应全部计入）")
    print("-" * 70)

    if not problems:
        print("通过：没有发现问题。")
    else:
        print(f"发现 {len(problems)} 个问题：")
        for problem in problems:
            print(f"  {problem}")

    print("-" * 70)
    print(f"结论：{'通过' if not problems else '需要修复'}")
    return 0 if not problems else (1 if args.strict else 0)


if __name__ == "__main__":
    sys.exit(main())
