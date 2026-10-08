"""让模型稳定返回 JSON。

需要结构化输出的地方（查询分解、资料自评、出题、判分）都用它。
不同厂商对 JSON mode 的支持程度不一，所以统一采用
「提示词要求 + 多候选提取 + 重试」的策略，不依赖任何厂商特性。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from app.llm.provider import LLMProvider

_CODE_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

DEFAULT_SYSTEM = (
    "你是一个严格的标注助手。只输出一个 JSON 对象，"
    "不要输出任何解释文字，不要使用 Markdown 代码块。"
)


class JsonParseError(ValueError):
    pass


def extract_json(text: str) -> dict | None:
    """从模型输出里尽力提取一个 JSON 对象。

    模型经常在 JSON 前后夹带解释文字，或者用 ``` 包起来，
    所以依次尝试三种候选：原文、代码块内容、第一个 { 到最后一个 }。
    """
    for candidate in _candidates(text):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _candidates(text: str) -> Iterator[str]:
    stripped = text.strip()
    if stripped:
        yield stripped

    block = _CODE_BLOCK.search(text)
    if block:
        yield block.group(1).strip()

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        yield text[start : end + 1]


async def call_json(
    provider: LLMProvider,
    prompt: str,
    *,
    retries: int = 2,
    system: str = DEFAULT_SYSTEM,
) -> dict:
    """调用模型并要求返回 JSON。解析失败会重试，全部失败抛 JsonParseError。

    provider.complete() 收的是 [{"role": ..., "content": ...}] 这种朴素字典，
    不是对象 —— 这是接口层和模型层之间的边界约定。
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    last = ""
    for _ in range(retries + 1):
        last = await provider.complete(messages)
        data = extract_json(last)
        if data is not None:
            return data

    raise JsonParseError(f"模型未返回可解析的 JSON（已重试 {retries} 次）：{last[:200]!r}")
