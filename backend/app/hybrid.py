"""混合检索：把「词法通道（BM25）」和「向量通道」的结果融合起来。

## 为什么不能直接相加分数

两个通道的分数**量纲不同、不可比**：

    BM25 分数      没有上界，实测能到 30 以上
    向量相似度     固定落在 [-1, 1]

直接把分数加起来，BM25 会完全主导（它的数值大几十倍）。

## RRF：只看排名，不看分数

Reciprocal Rank Fusion 的思路很朴素：
**一个片段在任何通道里排第 1 名，就给它 1/(k+1) 分；排第 2 名给 1/(k+2) 分……**
最后把各通道的分数相加。

    分数 = Σ  1 / (k + 该片段在这个通道里的排名)

这样就彻底绕开了「量纲不同」的问题 —— 因为它压根不看原始分数。

k 是平滑常数（原论文取 60），作用是压低"排名靠前"带来的差距，
避免某个通道的第 1 名一枝独秀。

## 这个模块的另一个用途：消融实验

`search(mode=...)` 支持三种模式，正好构成消融表的前三行：

    mode="bm25"    只用词法通道          → 第 1 行
    mode="vector"  只用向量通道          → 第 2 行
    mode="hybrid"  两者融合（默认）      → 第 3 行

**改一个参数就能跑出三行对比数据**，这就是把架构设计成可实验的价值。
"""

from dataclasses import dataclass, field
from typing import Literal

from app import bm25, vector
from app.bm25 import ScoredChunk

SearchMode = Literal["bm25", "vector", "hybrid"]

# RRF 的平滑常数，原论文值
RRF_K = 60

# 每个通道先各捞多少候选参与融合
CANDIDATES_PER_CHANNEL = 20


@dataclass
class HybridHit:
    """融合后的一个结果。

    比 ScoredChunk 多带两样东西，都是为了后面做分析和消融：
      - rrf_score     融合得分
      - channel_ranks 这个片段在各通道里的排名 {通道名: 名次}
    """

    chunk_id: int
    doc_id: int
    ordinal: int
    content: str
    rrf_score: float
    channel_ranks: dict[str, int] = field(default_factory=dict)


def rrf_fuse(
    rankings: dict[str, list[int]],
    k: int = RRF_K,
    weights: dict[str, float] | None = None,
) -> dict[int, float]:
    """把多个通道的排名列表融合成一个得分表。

    rankings 形如：
        {"bm25": [12, 7, 33, ...], "vector": [7, 91, 12, ...]}
    值是 chunk_id，顺序就是排名（第 0 个是第 1 名）。

    ## 两个可调参数

    **k（平滑常数）**：控制"排名靠前"能带来多大优势。
        k=60（原论文值）  第1名 1/61=0.0164，第20名 1/80=0.0125  → 只差 31%
        k=10             第1名 1/11=0.0909，第20名 1/30=0.0333  → 差 2.7 倍
      **k 越小，头部排名越占优势。** 列表多的时候，小的 k 能防止
      "某个通道的第 1 名被其他通道的中等名次淹掉"。

    **weights（通道权重）**：不同来源的可信度不一样。
        原问题检索出来的结果，比子查询的更可靠 —— 给原问题更高权重。

    默认（k=60、等权）就是原论文的 RRF，不给参数时行为完全不变。
    """
    scores: dict[int, float] = {}
    for name, chunk_ids in rankings.items():
        weight = (weights or {}).get(name, 1.0)
        for rank, chunk_id in enumerate(chunk_ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)
    return scores


def search(
    question: str,
    top_k: int = 5,
    *,
    mode: SearchMode = "hybrid",
    candidates: int = CANDIDATES_PER_CHANNEL,
) -> list[HybridHit]:
    """检索入口。

    mode="bm25"   只用词法通道
    mode="vector" 只用向量通道
    mode="hybrid" 两个通道融合（默认）
    """
    channel_hits: dict[str, list[ScoredChunk]] = {}

    if mode in ("bm25", "hybrid"):
        channel_hits["bm25"] = bm25.search(question, top_k=candidates)

    if mode in ("vector", "hybrid"):
        channel_hits["vector"] = vector.search(question, top_k=candidates)

    return _fuse_channels(channel_hits, top_k)


def search_many(
    questions: list[str],
    top_k: int = 5,
    *,
    mode: SearchMode = "hybrid",
    candidates: int = CANDIDATES_PER_CHANNEL,
) -> list[list[HybridHit]]:
    """一次批量检索多个问题。

    结果和"逐个调 search()"完全一样，区别只在**向量化的批次**：

    向量化是本项目最重的 CPU 操作（本机约 300~400 ms/次）。
    N 个问题各调一次 search = N 次独立的 ONNX 推理，每次都有启动开销；
    这里把 N 个问题合成一批送进模型，算子能吃满。

    查询分解一次就会产生 2~4 个子查询，这个函数正是为它准备的。

    ⚠ 输入顺序 = 输出顺序。
    """
    if not questions:
        return []

    # 词法通道：纯内存倒排计算，很快（毫秒级），逐个做就行
    bm25_results: list[list[ScoredChunk]] = []
    if mode in ("bm25", "hybrid"):
        bm25_results = [bm25.search(q, top_k=candidates) for q in questions]

    # 向量通道：批量向量化 —— 这是性能关键
    vector_results: list[list[ScoredChunk]] = []
    if mode in ("vector", "hybrid"):
        vector_results = vector.search_many(questions, top_k=candidates)

    return [
        _fuse_channels(
            {
                **({"bm25": bm25_results[i]} if bm25_results else {}),
                **({"vector": vector_results[i]} if vector_results else {}),
            },
            top_k,
        )
        for i in range(len(questions))
    ]


def _fuse_channels(
    channel_hits: dict[str, list[ScoredChunk]],
    top_k: int,
) -> list[HybridHit]:
    """把各通道的结果用 RRF 融合成最终排名。

    抽成独立函数是为了让 search() 和 search_many() 共用同一套融合逻辑 ——
    否则两者很容易在后续改动中悄悄走偏（比如只给其中一个加了权重）。
    """
    if not channel_hits:
        return []

    pool: dict[int, ScoredChunk] = {}
    rankings: dict[str, list[int]] = {}
    ranks_of: dict[int, dict[str, int]] = {}

    for channel, hits in channel_hits.items():
        rankings[channel] = [h.chunk_id for h in hits]
        for rank, hit in enumerate(hits, start=1):
            pool[hit.chunk_id] = hit
            ranks_of.setdefault(hit.chunk_id, {})[channel] = rank

    # 单通道模式下，排名就是最终排名（RRF 在这里不做任何改变，只是统一了出口）
    fused = rrf_fuse(rankings)
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    return [
        HybridHit(
            chunk_id=chunk_id,
            doc_id=pool[chunk_id].doc_id,
            ordinal=pool[chunk_id].ordinal,
            content=pool[chunk_id].content,
            rrf_score=round(score, 6),
            channel_ranks=ranks_of.get(chunk_id, {}),
        )
        for chunk_id, score in ordered
        if chunk_id in pool
    ]


def rrf_merge(
    hit_lists: list[list[HybridHit]],
    top_k: int,
    k: int = RRF_K,
    weights: list[float] | None = None,
) -> list[HybridHit]:
    """把【多路】检索结果用 RRF 合并去重。

    和 search() 内部的融合是同一个原理，只是输入从"两个检索通道"
    变成了"多个子查询各自的检索结果"。

    复用的好处：查询分解出 2 个还是 5 个子查询，合并逻辑都不用改。
    这也是把 RRF 单独抽成函数的价值 —— 它本质上就是"融合多个排名列表"，
    至于这些列表来自不同通道还是不同查询，它不关心。

    weights 按位置对应每一路（第 0 个对应 hit_lists[0]）。
    查询分解时，hit_lists[0] 是【原问题】的检索结果，通常给它更高权重。
    """
    pool: dict[int, ScoredChunk] = {}
    rankings: dict[str, list[int]] = {}
    ranks_of: dict[int, dict[str, int]] = {}
    label_weights: dict[str, float] = {}

    for list_index, hits in enumerate(hit_lists):
        label = f"q{list_index}"
        rankings[label] = [h.chunk_id for h in hits]
        label_weights[label] = (weights[list_index] if weights else 1.0)
        for rank, hit in enumerate(hits, start=1):
            # 同一个块可能被多路捞到，保留第一次的分数信息即可
            pool.setdefault(
                hit.chunk_id,
                ScoredChunk(
                    chunk_id=hit.chunk_id,
                    doc_id=hit.doc_id,
                    ordinal=hit.ordinal,
                    score=hit.rrf_score,
                    content=hit.content,
                ),
            )
            ranks_of.setdefault(hit.chunk_id, {})[label] = rank

    fused = rrf_fuse(rankings, k=k, weights=label_weights)
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    return [
        HybridHit(
            chunk_id=chunk_id,
            doc_id=pool[chunk_id].doc_id,
            ordinal=pool[chunk_id].ordinal,
            content=pool[chunk_id].content,
            rrf_score=round(score, 6),
            channel_ranks=ranks_of.get(chunk_id, {}),
        )
        for chunk_id, score in ordered
        if chunk_id in pool
    ]


# --------------------------------------------------------------------------- #
#     cd backend
#     .venv\\Scripts\\python.exe -m app.hybrid "怎么让数据自动更新"
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    question = sys.argv[1] if len(sys.argv) > 1 else "怎么让数据自动更新"
    print(f"【混合检索】{question}")
    print("=" * 80)

    for mode in ("bm25", "vector", "hybrid"):
        print(f"\n--- mode = {mode} ---")
        for rank, hit in enumerate(search(question, top_k=3, mode=mode), start=1):
            preview = " ".join(hit.content.split())[:52]
            ranks = " ".join(f"{k}#{v}" for k, v in sorted(hit.channel_ranks.items()))
            print(f"  {rank}. rrf={hit.rrf_score:.5f} [{ranks:<18}] 块{hit.chunk_id:<5} {preview}...")
