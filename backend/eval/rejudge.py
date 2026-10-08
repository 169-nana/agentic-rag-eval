"""只重判、不重跑系统：改了判分器之后，用它把历史报告重新判一遍。

## 为什么需要这个工具

改了判分提示词之后，**所有历史报告的数字都作废了** ——
因为它们是按旧标准判出来的。但要对比"改判分器之前 vs 之后"，
又**不能重跑系统**：

    LLM 有随机性。重跑一遍会得到不同的回答，
    那就分不清"数字变化"是判分器改的，还是回答本身变了。

所以正确做法是：**拿同一批已经落盘的回答，只把判分这一步重跑一遍。**
这样变量只有一个（判分器），结论才干净。

## 用法

    # 只重判不可回答题（答得对不对的判分逻辑没变，不用重判）
    python -m eval.rejudge <报告.json>

    # 全部重判
    python -m eval.rejudge <报告.json> --all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from eval import metrics
from eval.judges import LLMJudge
from eval.schema import (
    EvalItem,
    ItemResult,
    RetrievalScore,
    SystemAnswer,
    Verdict,
)
from eval.systems import OracleSystem  # noqa: F401  （保持入口一致，实际不用）

BACKEND_DIR = Path(__file__).resolve().parent.parent


def rebuild_item(row: dict) -> ItemResult:
    """从报告 JSON 重建 ItemResult —— 只填判分需要的字段。"""
    item = EvalItem(
        id=row["id"],
        question=row["question"],
        type=row["type"],
        answerable=bool(row["answerable"]),
        gold_answer=row.get("gold_answer"),
    )
    answer = SystemAnswer(
        text=row.get("prediction") or "",
        refused=bool(row.get("prediction_refused")),
        latency_ms=float(row.get("latency_ms") or 0.0),
        prompt_tokens=int(row.get("prompt_tokens") or 0),
        completion_tokens=int(row.get("completion_tokens") or 0),
        trace_id=row.get("trace_id") or "",
        error=row.get("error"),
    )
    verdict = Verdict(**row["verdict"])
    retrieval = RetrievalScore(**row["retrieval"])
    return ItemResult(item=item, answer=answer, verdict=verdict, retrieval=retrieval)


async def rejudge(
    report: dict,
    *,
    only_unanswerable: bool = True,
    concurrency: int = 4,
) -> tuple[list[ItemResult], int]:
    from app.llm import build_provider

    judge = LLMJudge(build_provider())
    semaphore = asyncio.Semaphore(concurrency)
    changed = 0

    async def one(result: ItemResult) -> ItemResult:
        nonlocal changed
        if only_unanswerable and result.item.answerable:
            return result
        async with semaphore:
            new_verdict = await judge.judge(result.item, result.answer)
        if new_verdict.correct != result.verdict.correct:
            changed += 1
        return ItemResult(
            item=result.item,
            answer=result.answer,
            verdict=new_verdict,
            retrieval=result.retrieval,
        )

    results = list(await asyncio.gather(*(one(rebuild_item(r)) for r in report["results"])))
    return results, changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="用当前判分器重判一份历史报告")
    parser.add_argument("report", type=Path)
    parser.add_argument("--all", action="store_true", help="全部重判（默认只重判不可回答题）")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--out", type=Path, default=None)
    return parser


async def main_async(args: argparse.Namespace) -> int:
    report = json.loads(args.report.read_text(encoding="utf-8"))
    before = report["summary"]

    results, changed = await rejudge(
        report, only_unanswerable=not args.all, concurrency=args.concurrency
    )

    summary = metrics.aggregate(results)
    by_type = metrics.aggregate_by_type(results)

    out_path = args.out or args.report.with_name(
        args.report.stem.replace("__", "__rejudged__", 1) + ".json"
    )
    new_report = dict(report)
    new_report["summary"] = summary
    new_report["by_type"] = by_type
    new_report["judge"] = f"{report['judge']}+rejudged"
    new_report["results"] = [
        {
            "id": r.item.id,
            "question": r.item.question,
            "type": r.item.type,
            "answerable": r.item.answerable,
            "gold_answer": r.item.gold_answer,
            "prediction": r.answer.text,
            "prediction_refused": r.answer.refused,
            "verdict": r.verdict.to_dict(),
            "retrieval": r.retrieval.to_dict(),
            "latency_ms": r.answer.latency_ms,
            "prompt_tokens": r.answer.prompt_tokens,
            "completion_tokens": r.answer.completion_tokens,
            "trace_id": r.answer.trace_id,
            "error": r.answer.error,
        }
        for r in results
    ]
    out_path.write_text(
        json.dumps(new_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    keys = [
        ("answer_accuracy", "可回答题正确率"),
        ("refusal_accuracy", "拒答正确率"),
        ("hallucination_rate", "幻觉率"),
    ]
    print("=" * 70)
    print("  重判结果（只改判分，回答内容一字未动）")
    print("=" * 70)
    print(f"  报告 : {args.report.name}")
    print(f"  判定发生变化的条目: {changed} 条")
    print()
    print(f"  {'指标':<18}{'重判前':>10}{'重判后':>10}")
    print("  " + "-" * 42)
    for key, label in keys:
        print(f"  {label:<18}{str(before.get(key)):>10}{str(summary.get(key)):>10}")
    print()
    print(f"  已写入: {out_path.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
