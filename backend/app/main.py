"""后端服务的入口文件。

现在包含：流式对话 + trace（trace_id / 耗时 / token 用量）。

trace 是什么？就是"这次请求发生了什么、各阶段花了多久"的记录。
它是排查问题和做优化的唯一依据——没有它，你只能靠猜。
"""

import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app import rag
from app.config import get_settings
from app.llm import Usage, build_provider

app = FastAPI(
    title="Agentic RAG API",
    description="从零搭起来的后端：流式对话 + trace",
    version="0.5.0",
)

# --------------------------------------------------------------------------- #
# CORS（跨域资源共享）—— 前后端分居两个端口时必须配
# --------------------------------------------------------------------------- #
# 前端跑在 localhost:5173，后端跑在 127.0.0.1:8000。
# 浏览器有个安全规则：不同"源"（协议 + 域名 + 端口，三者任一不同就算不同源）
# 之间发请求，默认一律拦截。
#
# 5173 和 8000 端口不同 = 不同源，所以必须由后端**明确声明**允许谁访问。
# 少了这段，前端会看到：
#   Access to fetch at 'http://127.0.0.1:8000/api/chat' from origin
#   'http://localhost:5173' has been blocked by CORS policy
#
# ⚠ 上线时千万别写 allow_origins=["*"]，那等于对全世界开放。
#   要换成你前端的真实域名。
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 由工厂决定用哪个模型。main.py 不关心背后是谁，这就是分层的好处。
llm = build_provider()

# 流式响应必须带的两个响应头
SSE_HEADERS = {
    # 告诉浏览器和中间层：不要缓存
    "Cache-Control": "no-cache",
    # 告诉 nginx 这类反向代理：不要缓冲，收到一点就转发一点。
    # 少了这一行，流式会退化成"一次性返回"，前面所有努力白费。
    "X-Accel-Buffering": "no",
}


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)

    # 检索模式，用于消融实验：
    #   bm25   只用词法通道
    #   vector 只用向量通道
    #   hybrid 两通道 RRF 融合（默认）
    #   agent  查询分解 + 多路检索 + 自评补检
    # 生产环境不该暴露这个参数；这里留着是为了让评测脚本能一组组地对比。
    retrieval_mode: Literal["bm25", "vector", "hybrid", "agent"] = "hybrid"

    # 是否做上下文压缩（只留相关句子）。
    # 压缩之后可以放心把 agent_top_k 调大 —— 用同样的 token 预算看更多资料。
    compress: bool = False

    # agent 模式下给模型几块资料
    agent_top_k: int = Field(default=5, ge=1, le=20)

    # 多路融合时，原问题那一路的权重（1.0 = 等权，即原版 RRF）
    main_query_weight: float = Field(default=1.0, ge=0, le=10)

    # 多路融合的 RRF 平滑常数（越小越看重头部排名）
    rrf_k: int = Field(default=60, ge=1, le=200)

    @model_validator(mode="after")
    def current_turn_must_be_last(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("messages 最后一条必须是当前 user 消息")
        return self


def sse(event: str, data: dict) -> str:
    """把「事件名 + 数据」拼成符合 SSE 格式的字符串。

    格式必须是这样（注意结尾的空行，它是事件的分界符）：
        event: 事件名
        data: {"json":"内容"}
        ← 这里必须是空行，少了它前端无法分帧

    ensure_ascii=False 让中文原样输出，网络里可读、方便调试。
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _code_version() -> str:
    """当前进程实际加载的代码版本（按 app/*.py 的最后修改时间算）。

    ## 为什么需要这个

    在 Windows 上按端口杀 uvicorn **杀不干净**：
    父进程死了，但它 spawn 出来的 multiprocessing 子进程还占着端口继续服务。
    结果就是 —— "重启后端"看起来成功了，**实际跑的仍然是旧代码**，
    而你会在错误的代码上做测量、得出错误结论。这个坑踩过一次。

    有了这个标记，重启后先看一眼 /api/health：
    版本号和最新代码不一致，就说明旧进程还活着。
    """
    app_dir = Path(__file__).resolve().parent
    latest = max((p.stat().st_mtime for p in app_dir.glob("*.py")), default=0.0)
    return datetime.fromtimestamp(latest).strftime("%m-%d %H:%M:%S")


@app.get("/api/health")
async def health() -> dict:
    """健康检查：确认服务活着，并报告在用哪个模型、加载的是哪份代码。"""
    return {
        "status": "ok",
        "provider": llm.name,
        "model": llm.model,
        "code_version": _code_version(),
    }


@app.post("/api/chat")
async def chat(body: ChatRequest) -> StreamingResponse:
    """流式对话。返回的不是普通 JSON，而是一条持续推送的数据流。"""
    messages = [m.model_dump() for m in body.messages]
    return StreamingResponse(
        _event_source(messages, body),
        media_type="text/event-stream; charset=utf-8",
        headers=SSE_HEADERS,
    )


async def _event_source(messages: list[dict[str, str]], options: ChatRequest):
    """真正干活的异步生成器，负责往外吐 SSE 文本。

    事件顺序：start → retrieved → token* →（error）→ done

    options 直接收整个请求对象 —— 消融用的开关越来越多（检索模式、压缩、
    top_k、RRF 参数……），一个个当位置参数传太容易搞错顺序。

    和上一版相比有两处变化：
      1. 多了一个 retrieved 事件，告诉前端"这次用了哪几块资料"
      2. trace 从 1 个 span 变成 2 个 —— 检索花了多久、生成花了多久，分开记
    """

    # ---------- 开始计时，并生成本次请求的唯一编号 ----------
    trace_id = uuid.uuid4().hex[:16]
    request_started = time.perf_counter()

    # 当前 user 消息用于检索，之前的对话作为有限历史上下文传给生成模型。
    question = messages[-1]["content"]
    history = messages[:-1]

    usage = Usage()
    text_chunks = 0
    answer_parts: list[str] = []
    spans: list[dict] = []          # ★ 改成列表，因为现在有两个阶段了
    error: str | None = None

    try:
        # ---- 事件 1：start ----
        yield sse("start", {
            "trace_id": trace_id,
            "provider": llm.name,
            "model": llm.model,
        })

        # ================= 阶段 1：检索（+ 可选压缩） =================
        retrieve_started = time.perf_counter()
        ctx = await rag.prepare(
            question,
            mode=options.retrieval_mode,
            use_compression=options.compress,
            agent_top_k=options.agent_top_k,
            main_query_weight=options.main_query_weight,
            rrf_k=options.rrf_k,
            history=history,
        )
        retrieve_ms = round((time.perf_counter() - retrieve_started) * 1000, 2)

        # ---- 事件 2：retrieved —— 把"用了哪几块资料"告诉前端 ----
        # 前端目前不处理这个事件（会被忽略），但评测脚本要靠它算检索指标。
        #
        # 这里发的是 chunk_texts（模型【实际看到】的正文），不是 chunk.content。
        # 压缩之后两者不同 —— 拿原文算检索指标会虚高。
        yield sse("retrieved", {
            "chunks": [
                {
                    "index": index,          # 对应提示词里的 [1] [2] [3]
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "score": chunk.rrf_score,
                    # 各通道里的排名，用于事后分析"这块是谁找出来的"
                    "channel_ranks": chunk.channel_ranks,
                    "text": text,
                }
                for index, (chunk, text) in enumerate(
                    zip(ctx.chunks, ctx.chunk_texts), start=1
                )
            ],
            # 压缩统计，供消融分析（没压缩时为 None）
            "compression": ctx.compression,
        })
        # 先下发各阶段的子 span（分解 / 检索 / 自评+压缩），
        # 再下发一个总计 span —— 既能看总耗时，也能看时间花在哪。
        spans.extend(ctx.timings)
        spans.append({
            "name": f"retrieve.{options.retrieval_mode}"
            + (".compress" if options.compress else ""),
            "t0": retrieve_started,
            "duration_ms": retrieve_ms,
            "attributes": {
                "mode": options.retrieval_mode,
                "compress": options.compress,
                "top_k": len(ctx.chunks),
                "scores": [c.rrf_score for c in ctx.chunks],
                "compression": ctx.compression,
            },
            "error": None,
        })

        # ================= 阶段 2：生成 =================
        # 注意这里传的是 ctx.messages（带着资料的提示词），不是原始问题
        generate_started = time.perf_counter()
        async for chunk in llm.stream(ctx.messages):
            if chunk.text:
                text_chunks += 1
                answer_parts.append(chunk.text)
                yield sse("token", {"text": chunk.text})
            if chunk.usage:
                usage = chunk.usage

        spans.append({
            "name": "llm.stream",
            "t0": generate_started,
            "duration_ms": round((time.perf_counter() - generate_started) * 1000, 2),
            "attributes": {
                "provider": llm.name,
                "model": llm.model,
                "text_chunks": text_chunks,
                "context_chunks": len(ctx.chunks),
            },
            "error": None,
        })

    except Exception as exc:  # noqa: BLE001
        # 流一旦开始推送，HTTP 状态码（200）就已经发出去了，改不了。
        # 所以出错只能以 error 事件的形式告诉前端，而不是靠状态码。
        error = f"{type(exc).__name__}: {exc}"
        yield sse("error", {"message": error, "retryable": False})

    # ---- 事件 3：done ----
    if error is None:
        citation_audit = _audit_citations("".join(answer_parts), len(ctx.chunk_texts))
        # 把各阶段记下的【绝对计时点 t0】换算成【相对请求起点的偏移 start_ms】。
        # 只有这里知道请求从哪一刻开始，所以换算放在最后统一做。
        # 有了 start_ms，前端才能画甘特图（看出串行/并行、父子嵌套），
        # 而不只是"谁耗时最长"的条形列表。
        for span in spans:
            t0 = span.pop("t0", None)
            if t0 is not None:
                span["start_ms"] = round((t0 - request_started) * 1000, 2)

        yield sse("done", {
            "trace_id": trace_id,
            "duration_ms": round((time.perf_counter() - request_started) * 1000, 2),
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
            "citation_audit": citation_audit,
            # 每个 span 带 start_ms + duration_ms，前端据此画执行时间线。
            # 以后加"回退""引用校验"等步骤时，往这个列表里继续 append 就行。
            "spans": spans,
        })


_CITATION_RE = re.compile(r"\[(\d+)\]")
_REFUSAL_RE = re.compile(r"无法回答|无法确认|资料不足|没有相关资料|未提及|没有提到")


def _audit_citations(answer: str, source_count: int) -> dict:
    """检查引用编号是否落在本次实际提供的资料范围内。"""
    references = sorted({int(value) for value in _CITATION_RE.findall(answer)})
    invalid = [number for number in references if number < 1 or number > source_count]
    if invalid:
        status = "invalid"
        message = f"回答引用了不存在的资料编号：{', '.join(map(str, invalid))}。"
    elif answer.strip() and source_count and not references and not _REFUSAL_RE.search(answer):
        status = "missing"
        message = "回答没有引用资料编号。编号检查不能证明引用内容在语义上支持答案。"
    else:
        status = "valid"
        message = "引用编号均对应本次提供的资料；语义支持关系仍需人工判断。"
    return {
        "status": status,
        "references": references,
        "invalid_references": invalid,
        "source_count": source_count,
        "message": message,
    }
