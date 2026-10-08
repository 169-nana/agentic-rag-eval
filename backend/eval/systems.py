"""被测系统（System Under Test, SUT）。

评测框架必须能和被测系统解耦，所以我们只依赖一个 answer(item) 协议。
这样同一个 runner 既能评测"纯 LLM 无检索"的对照组，也能评测完整的 Agent，
还能评测 Week 1 才会出现的真实检索链路——评测代码一行都不用改。

三个实现：
- OracleSystem  ：直接返回标准答案。**它不是基线，而是评测器自检**。
                  如果喂标准答案都判不到 ~100 分，说明判分器或指标写错了。
- BareLLMSystem ：纯 LLM、不接检索。这是消融表的第 0 行，也是幻觉率的上界。
- HttpRagSystem ：调用后端 /api/chat，真实端到端。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from app.llm.provider import LLMProvider, Usage
from eval.schema import EvalItem, RetrievedChunk, SystemAnswer

logger = logging.getLogger(__name__)

# 基线系统用的提示词。
# 刻意保持中性 —— 对照组【不应该】享受 RAG 那套"资料不足要明说、必须标引用"的约束，
# 否则对比就不公平：我们要测的恰恰是"纯模型自己会不会编"。
BARE_SYSTEM_PROMPT = "你是一个乐于助人的助手，请用简洁的中文回答问题。"


class SystemUnderTest(Protocol):
    name: str

    async def answer(self, item: EvalItem) -> SystemAnswer: ...


# --------------------------------------------------------------------------- #
# Oracle：评测器自检
# --------------------------------------------------------------------------- #
class OracleSystem:
    name = "oracle"

    async def answer(self, item: EvalItem) -> SystemAnswer:
        if not item.answerable:
            return SystemAnswer(
                text="资料不足，无法回答该问题。",
                refused=True,
                latency_ms=0.0,
            )
        return SystemAnswer(
            text=item.gold_answer or "资料不足。",
            # 顺手把 gold 片段当成"检索结果"返回，
            # 这样检索指标也能一起自检（span_recall / MRR / nDCG 都应为 1.0）
            retrieved=[
                RetrievedChunk(
                    chunk_id=f"oracle-{item.id}-{index}",
                    doc_id=span.doc_id,
                    text=span.text,
                    score=round(1.0 - index * 0.01, 4),
                )
                for index, span in enumerate(item.gold_spans)
            ],
            latency_ms=0.0,
        )


# --------------------------------------------------------------------------- #
# 纯 LLM 无检索
# --------------------------------------------------------------------------- #
class BareLLMSystem:
    """不接检索，直接把问题丢给模型。

    它的幻觉率就是"问题里问的东西知识库没有，模型会不会硬编"的基线。
    Week 1 接上检索后，A/B 对比的就是它和完整系统的差距。
    """

    def __init__(self, provider: LLMProvider, system_prompt: str = BARE_SYSTEM_PROMPT) -> None:
        self.provider = provider
        self.system_prompt = system_prompt
        self.name = f"bare-llm({provider.name})"

    async def answer(self, item: EvalItem) -> SystemAnswer:
        started = time.perf_counter()
        try:
            # 我们重建后的 provider.complete() 只返回文本，不返回用量，
            # 所以这里用空的 Usage 占位 —— 基线的 token 统计会显示为 0。
            # （后续可以把 complete() 的返回值改成 (text, usage)，两处小改即可。）
            text = await self.provider.complete(
                [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": item.question},
                ]
            )
            usage = Usage()
        except Exception as exc:  # noqa: BLE001 - 单条失败不应中断整轮评测
            return SystemAnswer(
                text="",
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                error=f"{type(exc).__name__}: {exc}",
            )

        from eval.judges import detect_refusal

        return SystemAnswer(
            text=text,
            refused=detect_refusal(text),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )


# --------------------------------------------------------------------------- #
# 真实后端
# --------------------------------------------------------------------------- #
class HttpRagSystem:
    """调用后端 /api/chat。

    这是唯一一个"端到端"的被测系统：检索 + 生成全都在后端真实发生。
    评测脚本通过 retrieved 事件拿到检索结果，才能算检索指标。
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout_s: float = 120.0,
        retrieval_mode: str = "hybrid",
        compress: bool = False,
        agent_top_k: int = 5,
        main_query_weight: float = 1.0,
        rrf_k: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        # 下面这些全部只是透传给后端，用于跑消融对比
        self.retrieval_mode = retrieval_mode
        self.compress = compress
        self.agent_top_k = agent_top_k
        self.main_query_weight = main_query_weight
        self.rrf_k = rrf_k

        suffix = f"{retrieval_mode}{'+c' if compress else ''}"
        if retrieval_mode == "agent":
            suffix += f",k={agent_top_k},w={main_query_weight},rk={rrf_k}"
        self.name = f"http-rag({suffix})"

    async def answer(self, item: EvalItem) -> SystemAnswer:
        started = time.perf_counter()
        parts: list[str] = []
        retrieved: list[RetrievedChunk] = []
        usage: dict = {}
        trace_id = ""
        error: str | None = None

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={
                        "messages": [{"role": "user", "content": item.question}],
                        "retrieval_mode": self.retrieval_mode,
                        "compress": self.compress,
                        "agent_top_k": self.agent_top_k,
                        "main_query_weight": self.main_query_weight,
                        "rrf_k": self.rrf_k,
                    },
                ) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode("utf-8", "replace")
                        error = f"HTTP {response.status_code}: {body[:200]}"
                    else:
                        async for event, payload in _iter_sse(response):
                            if event == "token":
                                parts.append(payload.get("text", ""))
                            elif event == "retrieved":
                                retrieved.extend(
                                    RetrievedChunk.from_dict(c)
                                    for c in payload.get("chunks", [])
                                )
                            elif event == "done":
                                usage = payload.get("usage", {}) or {}
                                trace_id = payload.get("trace_id", "")
                            elif event == "error":
                                error = payload.get("message", "未知错误")
        except httpx.HTTPError as exc:
            error = f"网络错误: {exc}"

        from eval.judges import detect_refusal

        text = "".join(parts)
        return SystemAnswer(
            text=text,
            refused=detect_refusal(text),
            retrieved=retrieved,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            trace_id=trace_id,
            error=error,
        )


async def _iter_sse(response: httpx.Response) -> AsyncIterator[tuple[str, dict]]:
    event = "message"
    data_lines: list[str] = []

    async for line in response.aiter_lines():
        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
        elif not line.strip() and data_lines:
            try:
                yield event, json.loads("\n".join(data_lines))
            except json.JSONDecodeError:
                logger.warning("无法解析的 SSE data 帧: %s", data_lines)
            event, data_lines = "message", []

    if data_lines:
        try:
            yield event, json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            pass
