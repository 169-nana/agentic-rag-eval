"""评测入口。

用法（在 backend 目录下执行）：

    # 1. 先自检评测器本身：喂标准答案，各项指标应该接近满分
    python -m eval.run_eval --system oracle

    # 2. 跑基线：纯 LLM 不接检索，看幻觉率有多高
    python -m eval.run_eval --system bare --tag baseline

    # 3. 端到端（需要后端已启动）
    python -m eval.run_eval --system http --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.config import get_settings
from app.llm import build_provider
from eval.cli import setup_console
from eval.judges import LLMJudge, RuleBasedJudge, calibrate, load_human_labels
from eval.report import write_report
from eval.runner import load_dataset, run_eval
from eval.systems import BareLLMSystem, HttpRagSystem, OracleSystem

BACKEND_DIR = Path(__file__).resolve().parent.parent

# 默认用的评测集。
# ⚠ 这个默认值是"当前语料对应的评测集"，换语料时必须一起换，
#   否则会拿旧评测集跑出新语料上的无意义数字
#   （症状：片段召回率恒为 0，因为旧评测集的 doc_id 在新语料里根本不存在）。
#   历史上踩过一次：report 第一行会打印数据集名字，出问题时先看那一行。
DEFAULT_DATASET = BACKEND_DIR / "eval" / "datasets" / "qa_v1.jsonl"
DEFAULT_OUT = BACKEND_DIR / "eval" / "reports"
DEFAULT_LABELS = BACKEND_DIR / "eval" / "datasets" / "human_labels.jsonl"

logger = logging.getLogger("eval")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行 RAG 评测")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--tag", default=None, help="报告文件名前缀，如 baseline")
    parser.add_argument(
        "--system", default="oracle", choices=["oracle", "bare", "http"],
        help="oracle=评测器自检 / bare=纯LLM无检索 / http=调用后端",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--retrieval-mode",
        default="hybrid",
        choices=["bm25", "vector", "hybrid", "agent"],
        help="只对 --system http 生效；用来跑检索消融对比",
    )
    parser.add_argument(
        "--compress",
        action="store_true",
        help="只对 --system http 生效；开启上下文压缩（只留相关句子）",
    )
    parser.add_argument(
        "--agent-top-k",
        type=int,
        default=5,
        help="agent 模式下给模型几块资料；压缩之后可以调大",
    )
    parser.add_argument(
        "--main-query-weight",
        type=float,
        default=1.0,
        help="多路融合时原问题那一路的权重（1.0 = 等权）",
    )
    parser.add_argument(
        "--rrf-k",
        type=int,
        default=60,
        help="多路融合的 RRF 平滑常数（越小越看重头部排名）",
    )
    parser.add_argument(
        "--judge", default="auto", choices=["auto", "rule", "llm"],
        help="auto：有真实模型用 LLM judge，否则退到规则判分器",
    )
    parser.add_argument("--k", type=int, default=5, help="检索指标截断位置")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--human-labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--price-in", type=float, default=0.0, help="输入价格（美元/百万 token）")
    parser.add_argument("--price-out", type=float, default=0.0, help="输出价格（美元/百万 token）")
    return parser


def build_system(name: str, provider, args: argparse.Namespace):
    if name == "oracle":
        return OracleSystem()
    if name == "bare":
        return BareLLMSystem(provider)
    return HttpRagSystem(
        base_url=args.base_url,
        timeout_s=args.timeout,
        retrieval_mode=args.retrieval_mode,
        compress=args.compress,
        agent_top_k=args.agent_top_k,
        main_query_weight=args.main_query_weight,
        rrf_k=args.rrf_k,
    )


def build_judge(mode: str, provider, is_mock: bool):
    if mode == "rule":
        return RuleBasedJudge()
    if mode == "llm":
        return LLMJudge(provider)
    if is_mock:
        logger.warning(
            "当前是 mock 模式，无法使用 LLM judge，已回退到规则判分器。"
            "本次数值仅用于验证流程，不能作为对外指标。"
        )
        return RuleBasedJudge()
    return LLMJudge(provider)


def print_summary(report) -> None:
    s = report.summary
    print()
    print("=" * 66)
    print(f"  数据集 {report.dataset}")
    print(f"  系统   {report.system}    判分器 {report.judge}")
    print("=" * 66)
    rows = [
        ("样本数", s.get("count")),
        ("综合正确率", s.get("accuracy")),
        ("可回答题正确率", s.get("answer_accuracy")),
        ("拒答正确率", s.get("refusal_accuracy")),
        ("幻觉率", s.get("hallucination_rate")),
        (f"片段召回率@{report.k}", s.get("span_recall_at_k")),
        ("MRR", s.get("mrr")),
        ("延迟 P50/P95 (ms)", f"{s.get('latency_p50_ms')} / {s.get('latency_p95_ms')}"),
        ("单条 token", s.get("tokens_per_item")),
        ("错误数", s.get("errors")),
    ]
    for label, value in rows:
        shown = "—" if value is None else value
        print(f"  {label:<20} {shown}")

    if report.by_type:
        print("-" * 66)
        for item_type, stats in report.by_type.items():
            print(
                f"  {item_type:<12} n={stats.get('count'):<4} "
                f"accuracy={stats.get('accuracy')} "
                f"hallucination={stats.get('hallucination_rate')}"
            )
    print("=" * 66)


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()

    if not args.dataset.exists():
        logger.error("数据集不存在: %s", args.dataset)
        return 1

    items = load_dataset(args.dataset)
    provider = build_provider()
    system = build_system(args.system, provider, args)
    judge = build_judge(args.judge, provider, settings.is_mock)

    logger.info(
        "开始评测：%d 条 / 系统=%s / 判分器=%s / 并发=%d",
        len(items), system.name, getattr(judge, "name", "?"), args.concurrency,
    )

    report = await run_eval(
        items,
        system,
        judge,
        dataset_name=args.dataset.name,
        k=args.k,
        concurrency=args.concurrency,
        price_in_per_1m=args.price_in,
        price_out_per_1m=args.price_out,
    )

    human_labels = load_human_labels(args.human_labels)
    if human_labels:
        report.calibration = calibrate(report.results, human_labels)
        logger.info("人工校准：%s", report.calibration)
    else:
        report.calibration = {
            "labeled": 0,
            "note": (
                f"未找到人工标注文件 {args.human_labels.name}。"
                "LLM judge 的可信度需要人工抽样标注来验证，"
                "建议抽 20~30 条标注后重跑（格式见 human_labels.example.jsonl）。"
            ),
        }

    json_path, md_path = write_report(report, args.out, tag=args.tag)
    print_summary(report)
    print(f"\n  JSON 报告：{json_path}")
    print(f"  Markdown ：{md_path}\n")
    return 0


def main() -> int:
    setup_console()
    args = build_parser().parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
