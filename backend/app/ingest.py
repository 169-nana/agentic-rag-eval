"""把切好的片段分词后写进 PostgreSQL。

这一步同时解决两件事：
1. 中文分词（jieba）—— 让"边缘计算"这种词能被检索到
2. 数据落库 —— 检索时直接查库，不用每次重新读文件、重新切块
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app import segment
from app.corpus import load_documents, split_into_chunks
from app.db import connect
from app.embedding import embed_documents
from app.vector import to_pg_vector

def make_content_hash(text: str) -> str:
    """算出内容的哈希值，用来判断"这篇文档是不是已经入库过"。

    用途：如果同一篇文档被重复入库，我们希望是"更新"而不是"再来一份"。
    """
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


@dataclass
class IngestStats:
    """入库结果统计。"""

    documents: int = 0
    chunks: int = 0


def ingest(raw_dir: Path | None = None) -> IngestStats:
    """主流程：读文档 -> 切块 -> 分词 -> 写库。"""

    docs = load_documents(raw_dir) if raw_dir else load_documents()
    stats = IngestStats()

    # with connect() as conn: 里所有操作是一个事务，要么全成功要么全回滚
    with connect() as conn:
        for doc in docs:
            chunks = split_into_chunks(doc)

            with conn.cursor() as cur:
                # ---- 第 1 步：写入文档 ----
                # ON CONFLICT ... DO UPDATE 的意思是：
                # "如果 content_hash 撞了（说明这篇文档已存在），就更新它，别报错"
                # RETURNING id 让 INSERT 直接把主键返回给我们，省一次查询
                cur.execute(
                    """
                    INSERT INTO documents (source, title, content, content_hash)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (content_hash) DO UPDATE
                        SET title  = EXCLUDED.title,
                            source = EXCLUDED.source
                    RETURNING id
                    """,
                    (doc.path.name, doc.title, doc.text, make_content_hash(doc.text)),
                )
                document_id = cur.fetchone()[0]

                # ---- 第 2 步：先删掉这篇文档的旧片段，再重新插入 ----
                # 为什么要先删？
                # 如果这次切出的块变少了（比如你改了 chunk_size），
                # 旧的块会残留下来变成"幽灵数据"——检索时能被搜到，但内容已经过时。
                # 先删干净再插，就保证了库里和当前文件永远一致。
                cur.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))

                # ---- 第 3 步：逐块分词 + 向量化，批量插入 ----
                # 分词和向量化都是"按块"的纯计算，先整批算好再一次性写库，
                # 比一块一块地往返数据库快得多。
                texts = [chunk.text for chunk in chunks]
                segs = [segment.segment_for_index(text) for text in texts]

                # 向量化是本流程里最慢的一步（CPU 跑 ONNX 模型），
                # embed_documents 内部是批处理的。
                vectors = embed_documents(texts)

                rows = [
                    (
                        document_id,
                        chunk.ordinal,
                        text,                            # 原文，用于展示和引用溯源
                        seg,                             # 分词结果，给 BM25 用
                        to_pg_vector(vec),               # 向量，给语义检索用
                    )
                    for chunk, text, seg, vec in zip(chunks, texts, segs, vectors)
                ]
                cur.executemany(
                    """
                    INSERT INTO chunks (document_id, ordinal, content, content_seg, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    """,
                    rows,
                )

            stats.documents += 1
            stats.chunks += len(chunks)

    return stats


# --------------------------------------------------------------------------- #
#     cd backend
#     .venv\Scripts\python.exe -m app.ingest
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    print("=== 分词效果演示（入库侧：精确模式）===")
    demo = "边缘计算业务线由林澈负责，毕业于浙江大学"
    print(f"  原文   : {demo}")
    print(f"  分词后 : {segment.segment_for_index(demo)}")
    print()

    print("=== 分词效果演示（查询侧：搜索模式）===")
    demo_query = "无锡市在哪里"
    print(f"  原文   : {demo_query}")
    print(f"  分词后 : {segment.segment_for_query(demo_query)}")
    print()

    print("=== 开始入库 ===")
    result = ingest()
    print(f"  文档 {result.documents} 篇，片段 {result.chunks} 个")
    print("  完成。")