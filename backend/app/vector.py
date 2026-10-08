"""向量检索：用 pgvector 在数据库里找「语义最近」的片段。

和 BM25 的分工：

    BM25  比的是「有多少个词一样」     → 快、准，但换个说法就找不到
    向量  比的是「意思有多近」         → 能救回同义改述，但会漏掉精确的编号/型号

两者组合才是完整的检索能力。
"""

from app.bm25 import ScoredChunk
from app.db import connect
from app.embedding import embed_queries, embed_query

# 每个通道先各捞多少候选出来做融合。
# 这个值比最终 top_k 大，因为融合的目的是"把两个通道各自认为好的都拿出来重排"。
DEFAULT_CANDIDATES = 20


def to_pg_vector(vec: list[float]) -> str:
    """把 Python 列表转成 pgvector 认得的字符串：[0.1,0.2,...]

    为什么用字符串而不是装 pgvector 的 Python 包？
    少一个依赖，而且 `%s::vector` 这种显式转换让 SQL 意图更清楚。
    """
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def search(question: str, top_k: int = 5) -> list[ScoredChunk]:
    """向量检索：返回语义最相近的若干片段。"""
    return search_many([question], top_k)[0]


def _search_by_vector(query_vec: str, top_k: int) -> list[ScoredChunk]:
    """用【已经算好的】向量去库里捞。"""
    # `<=>` 是 pgvector 的余弦距离算子：0 表示完全同向，2 表示完全反向。
    # 习惯上把它转成"相似度"（越大越像）：similarity = 1 - distance
    sql = """
        SELECT id,
               document_id,
               ordinal,
               content,
               1 - (embedding <=> %(vec)s::vector) AS score
        FROM chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %(vec)s::vector
        LIMIT %(limit)s
    """

    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, {"vec": query_vec, "limit": top_k})
        rows = cur.fetchall()

    return [
        ScoredChunk(
            chunk_id=row[0],
            doc_id=row[1],
            ordinal=row[2],
            score=round(float(row[4]), 4),
            content=row[3],
        )
        for row in rows
    ]


def search_many(questions: list[str], top_k: int = 5) -> list[list[ScoredChunk]]:
    """一次批量检索多个问题。

    **性能关键**：向量化是本项目最重的 CPU 操作（本机约 300~400 ms/次）。
    如果 N 个问题各调一次 search()，就是 N 次独立的 ONNX 推理；
    这里先把 N 个问题【合成一批】送进模型，再各自查库。

    数据库那 N 次查询是分开的，但它们每次只要 10~20 ms
    （HNSW 索引），相比向量化的开销可以忽略 —— 所以先优化大头。
    """
    if not questions:
        return []
    vectors = embed_queries(questions)
    return [_search_by_vector(to_pg_vector(vec), top_k) for vec in vectors]


# --------------------------------------------------------------------------- #
#     cd backend
#     .venv\\Scripts\\python.exe -m app.vector "怎么让数据自动更新"
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    question = sys.argv[1] if len(sys.argv) > 1 else "怎么让数据自动更新"
    print(f"【向量检索】{question}")
    print("=" * 76)
    for rank, hit in enumerate(search(question, top_k=5), start=1):
        preview = " ".join(hit.content.split())[:56]
        print(f"  {rank}. 相似度 {hit.score:7.4f}  块{hit.chunk_id:<5} {preview}...")
