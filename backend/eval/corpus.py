"""语料加载与分块。

刻意与 Week 1 的检索栈解耦：出题只需要"文档 + 分块"，
不需要数据库、不需要 embedding。这样评测集的生成可以先于检索系统完成。
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}

# 真实文档目录里必然夹杂大量素材文件（图片、示例代码、样式表……）。
# 这些是【正常存在】的，不该刷 WARNING —— 一份 Vue 文档仓库能刷出 140 行警告，
# 把真正的日志全淹没了。所以对它们静默跳过（需要时用 DEBUG 级别看）。
KNOWN_ASSET_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp",
    ".vue", ".js", ".ts", ".jsx", ".tsx", ".css", ".scss", ".less",
    ".html", ".json", ".yml", ".yaml", ".toml",
    ".woff", ".woff2", ".ttf", ".eot",
}


@dataclass
class SourceDoc:
    doc_id: str
    path: Path
    title: str
    text: str


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    ordinal: int
    text: str
    title: str = ""


def stable_id(*parts: str, length: int = 10) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:length]


def load_corpus(raw_dir: Path) -> list[SourceDoc]:
    """加载 raw_dir 下所有 md/txt 文档，doc_id 由相对路径稳定派生。"""
    if not raw_dir.exists():
        raise FileNotFoundError(f"语料目录不存在: {raw_dir}")

    docs: list[SourceDoc] = []
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            if path.suffix.lower() in KNOWN_ASSET_SUFFIXES:
                logger.debug("跳过素材文件: %s", path.name)
            else:
                # 不认识的类型才值得提醒：可能是你误放了一份该转成文本的文档
                logger.warning("跳过不支持的文件类型: %s", path.name)
            continue

        text = path.read_text(encoding="utf-8").strip()
        if not text:
            logger.warning("跳过空文件: %s", path.name)
            continue

        rel = path.relative_to(raw_dir).as_posix()
        docs.append(
            SourceDoc(
                doc_id=stable_id(rel),
                path=path,
                title=_first_heading(text) or path.stem,
                text=text,
            )
        )

    if not docs:
        raise ValueError(
            f"{raw_dir} 下没有可用的 .md/.txt 文档。"
            "放入你的语料后重试（PDF 需要先转成文本）。"
        )
    return docs


def split_chunks(doc: SourceDoc, size: int = 800, overlap: int = 120) -> list[Chunk]:
    """按字符滑窗切分。

    刻意保持简单：Week 1 会在这里换成正式的分块器（语义分块 / 父子块）。
    因为评测集的 gold 用的是原文片段而不是 chunk id，
    换分块器不需要重新出题——这正是 schema.py 里那个设计决定换来的好处。
    """
    if size <= 0:
        raise ValueError("size 必须为正数")
    if overlap >= size:
        raise ValueError("overlap 必须小于 size")

    step = size - overlap
    chunks: list[Chunk] = []
    for ordinal, start in enumerate(range(0, len(doc.text), step)):
        piece = doc.text[start : start + size].strip()
        if len(piece) < 20:  # 丢弃尾部碎片
            break
        chunks.append(
            Chunk(
                chunk_id=f"{doc.doc_id}#{ordinal:03d}",
                doc_id=doc.doc_id,
                ordinal=ordinal,
                text=piece,
                title=doc.title,
            )
        )
    return chunks


def build_chunk_index(docs: list[SourceDoc], size: int = 800, overlap: int = 120) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        chunks.extend(split_chunks(doc, size=size, overlap=overlap))
    return chunks


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        if stripped:
            return stripped[:40]
    return None
