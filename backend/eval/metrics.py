"""指标计算。

三类指标分开统计，因为它们回答的是完全不同的问题：
- 质量指标：答得对不对（accuracy / hallucination_rate）—— 产品能不能用
- 检索指标：该找到的资料找没找到（span_recall@k / MRR / nDCG）—— 定位问题出在哪一层
- 工程指标：延迟与 token 成本（p50 / p95 / avg_tokens）—— 能不能上线
"""

from __future__ import annotations

import math
from typing import Any

from eval.schema import EvalItem, ItemResult, RetrievalScore, SystemAnswer
from eval.text import is_covered

ITEM_TYPES = ("single_hop", "multi_hop", "unanswerable")


# --------------------------------------------------------------------------- #
# 检索打分
# --------------------------------------------------------------------------- #
def score_retrieval(item: EvalItem, answer: SystemAnswer, k: int = 5) -> RetrievalScore:
    """用 gold 原文片段对检索结果打分。

    注意 gold_spans 为空（不可回答题）时所有检索指标为 None，不参与聚合——
    这类题目的意义在于测幻觉，而不是测召回。
    """
    if not item.gold_spans:
        return RetrievalScore(k=k)

    retrieved = answer.retrieved[:k]
    covered = 0
    first_hit_rank: int | None = None

    for span in item.gold_spans:
        rank = _first_covering_rank(span.text, retrieved)
        if rank is not None:
            covered += 1
            if first_hit_rank is None or rank < first_hit_rank:
                first_hit_rank = rank

    return RetrievalScore(
        k=k,
        span_recall=round(covered / len(item.gold_spans), 4),
        hit=covered > 0,
        first_hit_rank=first_hit_rank,
        ndcg=round(_ndcg(retrieved, [s.text for s in item.gold_spans], k), 4),
    )


def _first_covering_rank(span_text: str, retrieved: list) -> int | None:
    for rank, chunk in enumerate(retrieved, start=1):
        if is_covered(span_text, chunk.text):
            return rank
    return None


def _ndcg(retrieved: list, span_texts: list[str], k: int) -> float:
    """二值相关性 nDCG@k：一个 chunk 只要覆盖任一 gold 片段就算相关。"""
    if not retrieved or not span_texts:
        return 0.0

    gains = [
        1.0 if any(is_covered(span, chunk.text) for span in span_texts) else 0.0
        for chunk in retrieved[:k]
    ]
    dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))

    ideal_count = min(len(span_texts), k, len(retrieved))
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / idcg if idcg > 0 else 0.0


# --------------------------------------------------------------------------- #
# 聚合
# --------------------------------------------------------------------------- #
def aggregate(
    results: list[ItemResult],
    *,
    price_in_per_1m: float = 0.0,
    price_out_per_1m: float = 0.0,
) -> dict[str, Any]:
    if not results:
        return {"count": 0}

    judged = [r for r in results if r.verdict.judged and r.verdict.correct is not None]
    answerable = [r for r in results if r.item.answerable and r.verdict.judged]
    unanswerable = [r for r in results if not r.item.answerable and r.verdict.judged]
    with_retrieval = [r for r in results if r.retrieval.span_recall is not None]

    prompt_tokens = sum(r.answer.prompt_tokens for r in results)
    completion_tokens = sum(r.answer.completion_tokens for r in results)
    latencies = [r.answer.latency_ms for r in results]

    summary: dict[str, Any] = {
        "count": len(results),
        "judged_count": len(judged),
        "judge_coverage": _ratio(len(judged), len(results)),
        # --- 质量 ---
        "accuracy": _mean_bool([r.verdict.correct for r in judged]),
        "answer_accuracy": _mean_bool([r.verdict.correct for r in answerable]),
        "refusal_accuracy": _mean_bool([r.verdict.correct for r in unanswerable]),
        # 幻觉率 = 1 - 拒答正确率，两项必须用【同一个数据源】。
        #
        # ⚠ 这里踩过一个坑：原来用的是 r.answer.refused（关键词匹配"资料不足/无法回答"），
        #   而 refusal_accuracy 用的是 r.verdict.correct（judge 判定）。
        #   结果基线跑出"拒答正确率 0.67 但幻觉率 1.0"这种自相矛盾的数字——
        #   因为模型说的是"我没有相关数据""我无法确认"，关键词表里没有这些说法。
        #   指标互相打架时，一定是定义错了，不是系统表现奇怪。
        "hallucination_rate": _mean_bool([not r.verdict.correct for r in unanswerable]),
        # --- 检索 ---
        "span_recall_at_k": _mean_float([r.retrieval.span_recall for r in with_retrieval]),
        "hit_rate_at_k": _mean_bool([r.retrieval.hit for r in with_retrieval]),
        "mrr": _mean_float(
            [
                1.0 / r.retrieval.first_hit_rank
                if r.retrieval.first_hit_rank
                else 0.0
                for r in with_retrieval
            ]
        ),
        "ndcg_at_k": _mean_float([r.retrieval.ndcg for r in with_retrieval]),
        "retrieval_scored_count": len(with_retrieval),
        # --- 工程 ---
        "latency_p50_ms": _percentile(latencies, 50),
        "latency_p95_ms": _percentile(latencies, 95),
        "latency_mean_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "prompt_tokens_total": prompt_tokens,
        "completion_tokens_total": completion_tokens,
        "tokens_per_item": round((prompt_tokens + completion_tokens) / len(results), 1),
        "errors": sum(1 for r in results if r.answer.error),
        # --- 成本（未配置单价时为 None，不臆造数字）---
        "cost_total_usd": _cost(prompt_tokens, completion_tokens, price_in_per_1m, price_out_per_1m),
    }
    return summary


def aggregate_by_type(results: list[ItemResult], **kwargs: Any) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item_type in ITEM_TYPES:
        subset = [r for r in results if r.item.type == item_type]
        if subset:
            grouped[item_type] = aggregate(subset, **kwargs)
    return grouped


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def _mean_bool(values: list[bool | None]) -> float | None:
    kept = [v for v in values if v is not None]
    return round(sum(1 for v in kept if v) / len(kept), 4) if kept else None


def _mean_float(values: list[float | None]) -> float | None:
    kept = [v for v in values if v is not None]
    return round(sum(kept) / len(kept), 4) if kept else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _percentile(values: list[float], pct: float) -> float | None:
    """线性插值分位数。样本少时(p95)数值仅供参考，报告里会标注样本量。"""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    position = (len(ordered) - 1) * pct / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 1)


def _cost(
    prompt_tokens: int, completion_tokens: int, price_in: float, price_out: float
) -> float | None:
    if price_in <= 0 and price_out <= 0:
        return None
    return round(
        prompt_tokens / 1_000_000 * price_in + completion_tokens / 1_000_000 * price_out, 6
    )
