"""把原始文档读进来，切成可以检索的片段（chunk）。

这是"查资料"的第一步。
关键认知：数据库里存的不是整篇文章，而是一小块一小块的片段。
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

# 复用 config.py 里已经算好的 backend 目录路径，不要重复定义
from app.config import BACKEND_DIR

# 语料目录：backend/corpus/raw/
RAW_DIR = BACKEND_DIR / "corpus" / "raw"

# 只处理这两种文件，其他类型跳过
SUPPORTED_SUFFIXES = {".md", ".txt"}

# 真实文档目录里必然夹杂大量素材文件（图片、示例代码、样式表……）。
# 这些是【正常存在】的，不该刷屏提示 —— Vue 文档仓库能刷出 140 行"跳过"，
# 把真正的日志全淹没了。所以对它们静默跳过。
KNOWN_ASSET_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".vue", ".js", ".ts", ".jsx", ".tsx", ".css", ".scss", ".less",
    ".html", ".json", ".yml", ".yaml", ".toml",
    ".woff", ".woff2", ".ttf", ".eot",
}

# --------------------------------------------------------------------------- #
# 切块参数。故意放在文件顶部，因为它们是要做实验的变量，不是随手写死的数字。
# 后面做"分块策略消融实验"时，改的就是这两个值。
# --------------------------------------------------------------------------- #
CHUNK_SIZE = 300      # 每块最多多少个字符
CHUNK_OVERLAP = 60    # 相邻两块重叠多少个字符


@dataclass
class SourceDoc:
    """一篇原始文档。"""

    doc_id: str
    title: str
    text: str
    path: Path


@dataclass
class Chunk:
    """从文档里切出来的一小块。"""

    chunk_id: str
    doc_id: str
    ordinal: int    # 在这篇文档里是第几块（从 0 开始）
    text: str


def make_doc_id(relative_path: str) -> str:
    """由文件路径算出一个【稳定】的编号。

    为什么不用 1、2、3 这种递增序号？
    因为序号会变：今天 01-company.md 是 1 号，明天你在前面插了一篇新的，
    它就变成 2 号了。于是数据库里上次存的数据全对不上，引用出处也会指错。

    用"路径的哈希值"就稳定：同一个文件，永远算出同一个编号。
    哈希 = 把任意长的内容压成固定长度的一串字符（这里取前 10 位）。
    """
    return hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:10]


def _guess_title(text: str) -> str:
    """拿第一行当标题，纯粹为了打印时好认。"""
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:40]
    return "(无标题)"


def load_documents(raw_dir: Path = RAW_DIR) -> list[SourceDoc]:
    """读目录下所有 .md / .txt 文件。"""

    if not raw_dir.exists():
        raise FileNotFoundError(f"语料目录不存在: {raw_dir}")

    documents: list[SourceDoc] = []

    # rglob("*") 递归找出目录下所有文件；sorted 保证每次运行顺序都一样
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            # 素材文件静默跳过；不认识的类型才提示（可能是误放了该转文本的文档）
            if path.suffix.lower() not in KNOWN_ASSET_SUFFIXES:
                print(f"[跳过] 不支持的文件类型: {path.name}")
            continue

        # encoding="utf-8" 不能省。Windows 默认用 GBK 读文件，中文会乱码甚至报错。
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            print(f"[跳过] 空文件: {path.name}")
            continue

        # relative_to 得到相对路径（如 "01-company-overview.md"）
        relative = path.relative_to(raw_dir).as_posix()
        documents.append(
            SourceDoc(
                doc_id=make_doc_id(relative),
                title=_guess_title(text),
                text=text,
                path=path,
            )
        )

    if not documents:
        raise ValueError(f"{raw_dir} 下没有可用的 .md/.txt 文档")
    return documents


def split_into_chunks(
    doc: SourceDoc,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """把一篇文档切成若干片段。

    切法：用一个固定长度的"窗口"在文本上滑动，每次前进 (chunk_size - overlap) 个字符。

        [0 ────── 300]
                [240 ────── 540]
                        [480 ────── 780]
                ↑↑↑↑
            重叠的部分，保证被切断的句子完整出现在某一块里
    """

    if overlap >= chunk_size:
        # 这个校验很重要：如果重叠 >= 块大小，窗口就永远不往前走（死循环）
        raise ValueError("overlap 必须小于 chunk_size，否则窗口无法前进")

    step = chunk_size - overlap       # 每次往前挪多少
    chunks: list[Chunk] = []

    # range(起点, 终点, 步长)：从 0 开始，每次加 step
    for ordinal, start in enumerate(range(0, len(doc.text), step)):
        piece = doc.text[start : start + chunk_size].strip()

        # 丢掉末尾的碎片：太短的块没有检索价值，只会污染检索结果
        if len(piece) < 20:
            break

        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#{ordinal:03d}",
                doc_id=doc.doc_id,
                ordinal=ordinal,
                text=piece,
            )
        )

    return chunks


# --------------------------------------------------------------------------- #
# 直接运行这个文件时：把切块结果打印出来，方便肉眼检查
#     cd backend
#     .venv\Scripts\python.exe -m app.corpus
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    # Windows 控制台默认是 GBK，中文可能显示成乱码。这三行把输出切成 UTF-8。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    docs = load_documents()
    print(f"读到 {len(docs)} 篇文档")
    print("=" * 74)

    total_chunks = 0
    for doc in docs:
        chunks = split_into_chunks(doc)
        total_chunks += len(chunks)
        print(f"\n【{doc.title}】")
        print(f"  doc_id={doc.doc_id}   原文 {len(doc.text)} 字  ->  {len(chunks)} 块")
        for chunk in chunks:
            preview = chunk.text.replace("\n", " ")
            print(f"    {chunk.chunk_id}  {len(chunk.text):>4} 字  {preview[:56]}...")

    print()
    print("=" * 74)
    print(f"合计：{len(docs)} 篇文档 -> {total_chunks} 个片段")
    print(f"当前参数：chunk_size={CHUNK_SIZE}  overlap={CHUNK_OVERLAP}")