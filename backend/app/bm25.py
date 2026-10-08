"""BM25 检索：给一个问题，返回最相关的片段。

为什么不能"关键词出现次数最多的排最前"？
因为那样常见词会主导排序。「的」「年」「公司」几乎每块都有，
出现次数多，但完全不能说明相关性；「无锡」只出现 1 次，却是极强的信号。

BM25 用三个因素把这件事量化了：
  ① TF  词频        —— 出现越多越相关，但有上限（k1 控制）
  ② IDF 逆文档频率  —— 词越稀有越重要（这就是「的」和「无锡」的差别）
  ③ 长度归一化      —— 长块天然含词多，要打折（b 控制）
"""

import math
from collections import Counter
from dataclasses import dataclass

from app import segment
from app.db import connect

# BM25 的两个调节参数，用学术界常用的默认值
K1 = 1.5    # 控制"词频的饱和速度"：越大，重复出现越占便宜
B = 0.75    # 控制"长度归一化的强度"：0 = 完全不管长度，1 = 完全归一化


@dataclass
class IndexedChunk:
    """索引里的一个片段。"""

    chunk_id: int
    doc_id: int
    ordinal: int
    content: str        # 原文：用来展示和引用溯源
    tokens: list[str]   # 分词结果：用来算分


@dataclass
class ScoredChunk:
    """一次检索命中的结果。"""

    chunk_id: int
    doc_id: int
    ordinal: int
    score: float
    content: str


class BM25Index:
    """一个可以查询的 BM25 索引。

    构造时把所有片段的统计量一次算好，之后每次查询都是纯内存计算，很快。
    """

    def __init__(self, chunks: list[IndexedChunk], k1: float = K1, b: float = B) -> None:
        if not chunks:
            raise ValueError("索引不能为空，请先运行 python -m app.ingest")

        self.chunks = chunks
        self.k1 = k1
        self.b = b

        # 每个片段的词频表：{词: 在这块里出现几次}
        self.term_freqs = [Counter(c.tokens) for c in chunks]

        # 每个片段的长度，用"词的个数"衡量
        self.lengths = [len(c.tokens) for c in chunks]

        # 平均长度（防止除零）
        self.avg_length = sum(self.lengths) / len(self.lengths) or 1.0

        # 文档频率：每个词出现在【多少个片段】里。
        # 注意不是"出现多少次"，是"出现在几个片段里"——这决定了它的区分度。
        doc_freq: Counter[str] = Counter()
        for tf in self.term_freqs:
            doc_freq.update(tf.keys())
        self.doc_freq = doc_freq
        self.total = len(chunks)

    def idf(self, term: str) -> float:
        """逆文档频率：词越稀有，值越大。

        +0.5 和 +1 是平滑项，避免分母为 0、以及结果变成负数。
        一个词如果出现在所有片段里，IDF 会接近 0 —— 等于没有区分度。
        """
        n = self.doc_freq.get(term, 0)
        if n == 0:
            return 0.0
        return math.log((self.total - n + 0.5) / (n + 0.5) + 1)

    def score(self, query_terms: list[str], index: int) -> float:
        """算第 index 个片段对整条查询的总得分。"""

        tf = self.term_freqs[index]
        length = self.lengths[index]

        total = 0.0
        # set() 去重：同一个词在查询里出现多次，不应该重复加分
        for term in set(query_terms):
            freq = tf.get(term, 0)
            if freq == 0:
                continue

            numerator = self.idf(term) * freq * (self.k1 + 1)
            denominator = freq + self.k1 * (1 - self.b + self.b * length / self.avg_length)
            total += numerator / denominator

        return total

    def search(self, query: str, top_k: int = 5) -> list[ScoredChunk]:
        """检索入口：传入自然语言问题，返回得分最高的若干片段。"""

        query_terms = segment.segment_for_query(query)
        if not query_terms:
            return []

        scored: list[tuple[float, IndexedChunk]] = []
        for i, chunk in enumerate(self.chunks):
            s = self.score(query_terms, i)
            if s > 0:                    # 一个查询词都没命中，直接淘汰
                scored.append((s, chunk))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        return [
            ScoredChunk(
                chunk_id=c.chunk_id,
                doc_id=c.doc_id,
                ordinal=c.ordinal,
                score=round(s, 4),
                content=c.content,
            )
            for s, c in scored[:top_k]
        ]


# --------------------------------------------------------------------------- #
# 从数据库加载 + 缓存
# --------------------------------------------------------------------------- #
_index: BM25Index | None = None


def load_index() -> BM25Index:
    """从数据库把所有片段读出来，构建索引。

    为什么全量读进内存？
    因为 BM25 的 IDF 需要"每个词出现在多少个片段里"这个【全局】统计量。
    片段只有几十到几千个时，全量加载最简单、也最准确。

    什么时候要换方案？
    片段涨到十万级以上，内存和构建时间都吃不消。那时的做法是：
    先用数据库的 GIN 索引召回一批候选（比如 200 个），
    再把全局 IDF 统计量缓存起来，只对候选集算分。
    —— 这就是"召回"和"排序"分离，也是工业界检索引擎的标准架构。
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, document_id, ordinal, content, content_seg FROM chunks ORDER BY id"
        )
        rows = cur.fetchall()

    if not rows:
        raise RuntimeError("数据库里没有片段，先运行：python -m app.ingest")

    chunks = [
        IndexedChunk(
            chunk_id=row[0],
            doc_id=row[1],
            ordinal=row[2],
            content=row[3],
            # content_seg 存的是"空格连接的词"，split() 就能还原成词列表
            tokens=row[4].split(),
        )
        for row in rows
    ]
    return BM25Index(chunks)


def get_index(refresh: bool = False) -> BM25Index:
    """拿索引，带缓存。

    为什么缓存？重建索引要读全表，每次查询都重建纯属浪费。
    ⚠ 重新入库之后，要记得 refresh=True，或者重启进程。
    """
    global _index
    if _index is None or refresh:
        _index = load_index()
    return _index


def search(question: str, top_k: int = 5, refresh: bool = False) -> list[ScoredChunk]:
    """对外接口：问一个问题，返回最相关的片段。"""
    return get_index(refresh=refresh).search(question, top_k=top_k)


# --------------------------------------------------------------------------- #
#     cd backend
#     .venv\Scripts\python.exe -m app.bm25
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    index = load_index()
    print(f"索引构建完成：{index.total} 个片段，平均每块 {index.avg_length:.1f} 个词")
    print("=" * 74)

    questions = [
        "无锡市在哪里",
        "林澈毕业于哪所大学",
        "澜芯 X1 是什么时候发布的",
        "企业版 SLA 承诺多少可用性",
        "量子计算机有什么进展",        # 库里没有这个话题
    ]

    for question in questions:
        print(f"\n【问】{question}")
        print(f"  查询分词：{segment.segment_for_query(question)}")

        hits = index.search(question, top_k=3)
        if not hits:
            print("   （无命中）")
        for rank, hit in enumerate(hits, start=1):
            preview = hit.content.replace("\n", " ")[:50]
            print(f"   {rank}. 得分 {hit.score:6.3f}  [块{hit.chunk_id}] {preview}...")