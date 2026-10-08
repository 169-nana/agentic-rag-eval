"""向量化（embedding）：把一段文字变成一串固定长度的数字。

## 为什么需要它

BM25 只能匹配「字面上相同或包含的词」。用户说"怎么让数据自动更新"，
文档里写"响应式系统"，**用词一变，词法检索就找不到**。
向量能把「意思相近」的文字映射到相近的位置，补上这个盲区。

## 模型选型

`BAAI/bge-small-zh-v1.5` —— 中文专用，512 维，约 90MB。

选它的三个理由：
1. **完全本地运行**：不花钱、不联网、数据不出机器
2. **走 ONNX（fastembed）**：不需要 2GB 的 PyTorch，装完即用
3. **中文专用**：比通用多语言小模型在中文上明显更好

⚠️ **换模型 = 换维度 = 必须改表结构 + 重新入库。**
所以维度写成了常量 `EMBEDDING_DIM`，数据库那边（`db/init/001_init.sql`）
的 `vector(512)` 必须和它一致，不一致会在插入时报错。
"""

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# ⚠ 这些必须在 import fastembed 之前设置
# --------------------------------------------------------------------------- #
# huggingface 在国内直连不通（和 Docker Hub 一样）。
# 1) 走国内镜像站
# 2) 关掉 Xet 存储后端 —— 镜像站不代理 Xet，不关会报 401
#
# 用 setdefault 而不是直接赋值：已经手动设过的环境变量优先。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# --------------------------------------------------------------------------- #
# 模型缓存目录 —— 这一行是踩坑换来的
# --------------------------------------------------------------------------- #
# fastembed 默认把模型下载到 %TEMP%，而 **Windows 会清理临时目录**。
#
# 实测症状：2.4GB 的 Qwen3 模型在某次系统清理后消失，
#   表现为"后端启动时突然卡在 `Fetching 6 files: 83%`，健康检查超时"，
#   而且没有任何一行报错指向真正的原因，排查了很久。
#
# 所以显式指定一个【不会被系统清理】的项目内目录。模型不入版本库（见 .gitignore）。
CACHE_DIR = Path(__file__).resolve().parent.parent / ".models"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

from fastembed import TextEmbedding  # noqa: E402  （必须在设置环境变量之后导入）

# --------------------------------------------------------------------------- #
# 模型选择
# --------------------------------------------------------------------------- #
# 用环境变量覆盖，默认 Qwen3-Embedding-0.6B：
#     $env:EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")

# 维度查表：模型名 → 输出维度。
#
# 为什么要查表而不是写死一个数？
# 因为【数据库的 vector(N) 必须等于模型输出维度】，
# 而"换模型忘了改表"是这一层最容易犯、报错最难懂的错
# （插入时才会炸，信息是 "expected 512 dimensions, not 1024"）。
# 有了这张表，换模型时能立刻看出要不要动表结构。
KNOWN_DIMS: dict[str, int] = {
    "BAAI/bge-small-zh-v1.5": 512,
    "jinaai/jina-embeddings-v2-base-zh": 768,
    "intfloat/multilingual-e5-large": 1024,
    "Qwen/Qwen3-Embedding-0.6B": 1024,
    "Qwen/Qwen3-Embedding-0.6B-Q": 1024,
}

# 未知模型默认按 1024 处理，并在自检里报出来
EMBEDDING_DIM = KNOWN_DIMS.get(EMBEDDING_MODEL, 1024)

# --------------------------------------------------------------------------- #
# 查询指令前缀（instruction-tuned 模型专用）
# --------------------------------------------------------------------------- #
# Qwen3-Embedding 这类 instruction-tuned 模型，**查询侧要加一段指令前缀**，
# 文档侧不加。加了效果明显更好。
#
# ⚠ 实测：fastembed 对 Qwen3-Embedding **不会自动加**
#   （query_embed 和 passage_embed 输出完全相同）。
#   不加**不会报错**，只是检索质量悄悄下降 —— 这类问题最难排查，
#   所以专门加进了 diagnose() 自检。
#
# 前缀用官方示例里的英文指令（模型是按英文指令训练的，最稳）。
QUERY_INSTRUCTIONS: dict[str, str] = {
    "Qwen/Qwen3-Embedding-0.6B": (
        "Instruct: Given a web search query, retrieve relevant passages that answer the query\n"
        "Query: "
    ),
    "Qwen/Qwen3-Embedding-0.6B-Q": (
        "Instruct: Given a web search query, retrieve relevant passages that answer the query\n"
        "Query: "
    ),
}

# 模型实例只加载一次（加载要几百毫秒，还占内存）
_model: TextEmbedding | None = None


def get_model() -> TextEmbedding:
    """拿到模型实例，带缓存。

    cache_dir 必须显式传 —— 不传就会落在 %TEMP%，被系统清理掉（见文件顶部说明）。
    """
    global _model
    if _model is None:
        _model = TextEmbedding(EMBEDDING_MODEL, cache_dir=str(CACHE_DIR))
    return _model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """【入库用】把文档片段批量转成向量。

    用 passage_embed 而不是 query_embed —— bge 系列模型对"文档"和"查询"
    用的是两种不同的编码方式（查询侧要加一段指令前缀）。两侧用错会导致
    检索质量明显下降，而且症状很隐蔽（相似度普遍偏低，但不会报错）。
    """
    if not texts:
        return []
    return [vec.tolist() for vec in get_model().passage_embed(texts)]


def embed_queries(texts: list[str]) -> list[list[float]]:
    """【查询用·批量】一次把多个问题转成向量。

    为什么要有批量版：
    查询分解会产生 2~4 个子查询，如果每个都单独调一次 embed_query，
    就是 N 次独立的 ONNX 推理 —— 每次都有模型启动、内存分配、算子调度开销。
    合成一批送进去，模型能复用计算、把算子吃满，实测明显更快。

    ⚠ 输入顺序 = 输出顺序，调用方靠下标对应。
    """
    if not texts:
        return []
    instruction = QUERY_INSTRUCTIONS.get(EMBEDDING_MODEL, "")
    prefixed = [instruction + text for text in texts]
    return [vec.tolist() for vec in get_model().query_embed(prefixed)]


def embed_query(text: str) -> list[float]:
    """【查询用·单条】把用户问题转成向量。

    对 instruction-tuned 模型，这里会自动加上查询指令前缀（见 QUERY_INSTRUCTIONS）。
    文档侧不加前缀 —— 两侧不对称是这类模型的设计要求，不是笔误。
    """
    return embed_queries([text])[0]


# --------------------------------------------------------------------------- #
# 自检：换模型前后都该跑一遍
# --------------------------------------------------------------------------- #
def diagnose() -> dict:
    """检查模型、维度、数据库三者是否协调。

    换 embedding 模型涉及**三个必须同步的地方**，漏一个就会在插入时才炸：
        1. 模型名（环境变量 / 本文件默认值）
        2. 本文件的 EMBEDDING_DIM
        3. 数据库 chunks.embedding 的 vector(N)

    这个函数把三处一次性查清楚，省得靠报错反推。
    """
    import numpy as np

    result: dict[str, object] = {
        "model": EMBEDDING_MODEL,
        "declared_dim": EMBEDDING_DIM,
        "in_known_table": EMBEDDING_MODEL in KNOWN_DIMS,
    }

    # ---- 1. 模型实际输出维度 ----
    probe = list(get_model().embed(["维度探针"]))[0]
    actual_dim = len(probe)
    result["actual_dim"] = actual_dim
    result["dim_ok"] = actual_dim == EMBEDDING_DIM

    # 查询侧和文档侧的编码路径是否不同。
    # 对 instruction-tuned 模型，如果这里相同，说明查询指令前缀没生效 —— 质量会悄悄下降。
    q = np.array(embed_query("测试"))
    p = np.array(embed_documents(["测试"])[0])
    result["query_passage_differ"] = not np.allclose(q, p)
    result["query_instruction"] = QUERY_INSTRUCTIONS.get(EMBEDDING_MODEL, "(此模型不需要)")

    # ---- 2. 数据库里的维度 ----
    try:
        from app.db import connect

        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT format_type(atttypid, atttypmod)
                FROM pg_attribute
                WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'
                """
            )
            row = cur.fetchone()
            db_type = row[0] if row else "(表不存在)"
            result["db_type"] = db_type
            result["db_matches"] = db_type == f"vector({actual_dim})"
    except Exception as exc:  # noqa: BLE001
        result["db_type"] = f"查询失败: {exc}"
        result["db_matches"] = False

    return result


# --------------------------------------------------------------------------- #
#     cd backend
#     .venv\\Scripts\\python.exe -m app.embedding
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    import numpy as np

    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    print("=" * 78)
    print("自检：模型 / 维度 / 数据库 三者是否协调")
    print("=" * 78)
    print(f"  模型名            : {EMBEDDING_MODEL}")
    print(f"  在已知维度表里    : {EMBEDDING_MODEL in KNOWN_DIMS}")

    info = diagnose()
    print(f"  模型实际输出维度  : {info['actual_dim']}")
    print(f"  代码声明的维度    : {info['declared_dim']}   {'一致' if info['dim_ok'] else '!! 不一致'}")
    print(f"  数据库列类型      : {info['db_type']}   {'匹配' if info['db_matches'] else '!! 不匹配'}")
    print(f"  query/passage 区分 : {info['query_passage_differ']}   "
          f"{'已生效' if info['query_passage_differ'] else '!! 未生效'}")
    instr = str(info["query_instruction"])
    print(f"  查询指令前缀      : {instr[:56]}{'...' if len(instr) > 56 else ''}")

    if not info["db_matches"]:
        print()
        print("  ⚠ 数据库维度不匹配。改 db/init/001_init.sql 后执行：")
        print("      docker compose down -v && docker compose up -d")
        print("      .venv\\Scripts\\python -m app.ingest")

    print()
    print("=" * 78)
    print("检索效果抽查")
    print("=" * 78)

    docs = [
        "Vue 的响应式系统基于 JavaScript 的 Proxy 实现。",
        "组件注册分为全局注册和局部注册两种方式。",
        "今天天气不错，适合出去散步。",
    ]
    doc_vecs = embed_documents(docs)

    for question in ["Vue 是怎么实现响应式的", "怎么让数据自动更新", "明天会下雨吗"]:
        qv = np.array(embed_query(question))
        print(f"\n查询: {question}")
        scored = []
        for i, dv in enumerate(doc_vecs):
            dv_arr = np.array(dv)
            sim = float(qv @ dv_arr / (np.linalg.norm(qv) * np.linalg.norm(dv_arr)))
            scored.append((sim, docs[i]))
        for sim, text in sorted(scored, reverse=True):
            print(f"  {sim:.4f}  {text}")
