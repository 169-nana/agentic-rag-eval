"""端到端冒烟测试：不开浏览器验证整条 SSE 链路。

## 这个脚本在验什么

它不只是"能跑通"，而是**逐项断言协议契约**：

  · /api/health 带的 code_version 是否和磁盘上的代码一致
    （不一致说明后端跑的是旧代码 —— 这个坑踩过，会静默污染所有实验）
  · SSE 事件顺序是否为 start → retrieved → token* → done
  · retrieved 里的 chunk 字段是否齐全
  · 每个 span 是否都有 start_ms 和 duration_ms（前端画甘特图要用）
  · 回答里是否有引用标注 [n]

任何一项不满足就以非 0 退出 —— 可以直接放进 CI。

## 用法

    cd backend
    .venv\\Scripts\\python scripts\\smoke_test.py
    .venv\\Scripts\\python scripts\\smoke_test.py "你的问题" --mode hybrid
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_QUESTION = "在 Vue 的计数器组件示例中，驱动视图的响应式状态通过哪个 API 创建？"


def setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def code_version_on_disk() -> str:
    """磁盘上 app/*.py 的最后修改时间 —— 和 /api/health 报告的比对。"""
    app_dir = BACKEND_DIR / "app"
    latest = max((p.stat().st_mtime for p in app_dir.glob("*.py")), default=0.0)
    return datetime.fromtimestamp(latest).strftime("%m-%d %H:%M:%S")


def consume_sse(base_url: str, body: dict, timeout: float) -> dict:
    """发一次请求，把 SSE 事件收集成 {事件名: 载荷}。token 事件会合并。"""
    events: dict[str, object] = {}
    tokens: list[str] = []
    order: list[str] = []

    with httpx.stream("POST", f"{base_url}/api/chat", json=body, timeout=timeout) as response:
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")

        name: str | None = None
        buf: list[str] = []
        for line in response.iter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                buf.append(line[5:].strip())
            elif not line.strip() and buf and name:
                payload = json.loads("\n".join(buf))
                if name == "token":
                    tokens.append(payload.get("text", ""))
                else:
                    events[name] = payload
                order.append(name)
                name, buf = None, []
                # 收到 done 就可以停了
                if order and order[-1] == "done":
                    break

    # 把连续重复的 token 折叠成一个标记，方便检查事件顺序
    collapsed: list[str] = []
    for item in order:
        if item == "token" and collapsed and collapsed[-1] == "token":
            continue
        collapsed.append(item)

    events["_order"] = collapsed
    events["_answer"] = "".join(tokens)
    return events


def main(argv: list[str] | None = None) -> int:
    setup_console()

    parser = argparse.ArgumentParser(description="端到端 SSE 冒烟测试")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", default="agent",
                        choices=["bm25", "vector", "hybrid", "agent"])
    parser.add_argument("--no-compress", action="store_true")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args(argv)

    checks: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append((label, ok, detail))

    print("=" * 78)
    print("  端到端冒烟测试")
    print("=" * 78)

    # ---------- 1. 健康检查 ----------
    try:
        health = httpx.get(f"{args.base_url}/api/health", timeout=30).json()
    except Exception as exc:  # noqa: BLE001
        print(f"\n  ❌ 连不上后端 {args.base_url}")
        print(f"     {type(exc).__name__}: {exc}")
        print("\n  提示：先在另一个终端启动后端")
        print("        cd backend && .venv\\Scripts\\python -m uvicorn app.main:app --port 8000")
        return 1

    disk = code_version_on_disk()
    proc = health.get("code_version")
    print(f"\n  后端      : {health.get('provider')} / {health.get('model')}")
    print(f"  代码版本  : 进程 {proc}  磁盘 {disk}")
    check("进程加载的是最新代码", proc == disk,
          "" if proc == disk else "旧进程还活着 —— Windows 上 uvicorn 会 spawn "
                                  "multiprocessing 子进程，按端口杀杀不干净")

    # ---------- 2. 发一次真实请求 ----------
    body = {
        "messages": [{"role": "user", "content": args.question}],
        "retrieval_mode": args.mode,
        "compress": not args.no_compress,
        "agent_top_k": args.top_k,
    }
    print(f"\n  问题      : {args.question[:60]}")
    print(f"  检索策略  : {args.mode}"
          f"{' + 上下文压缩' if not args.no_compress else ''}")

    started = time.perf_counter()
    try:
        events = consume_sse(args.base_url, body, args.timeout)
    except Exception as exc:  # noqa: BLE001
        print(f"\n  ❌ 请求失败: {type(exc).__name__}: {exc}")
        return 1
    elapsed = (time.perf_counter() - started) * 1000

    # ---------- 3. 协议断言 ----------
    order = events.get("_order", [])
    check("start 事件", "start" in events)
    check("retrieved 事件", "retrieved" in events)
    check("token 事件", "token" in order)
    check("done 事件", "done" in events)
    check("事件顺序 start → retrieved → token → done",
          order == ["start", "retrieved", "token", "done"],
          f"实际: {' → '.join(order)}")

    retrieved = events.get("retrieved") or {}
    chunks = retrieved.get("chunks") or []
    check("retrieved.chunks 非空", len(chunks) > 0)
    if chunks:
        need = {"index", "chunk_id", "doc_id", "score", "text"}
        check("chunk 字段齐全", need <= set(chunks[0]),
              f"缺: {need - set(chunks[0])}" if not need <= set(chunks[0]) else "")

    done = events.get("done") or {}
    spans = done.get("spans") or []
    check("done.spans 非空", len(spans) > 0)
    check("所有 span 都有 duration_ms", all("duration_ms" in s for s in spans))
    check("所有 span 都有 start_ms（前端甘特图需要）",
          all("start_ms" in s for s in spans),
          "" if all("start_ms" in s for s in spans)
          else "后端没记 t0 —— 检查 app/rag.py 的 timed() 和 main.py 的换算")

    usage = done.get("usage") or {}
    check("usage 字段齐全",
          {"prompt_tokens", "completion_tokens", "total_tokens"} <= set(usage))

    answer = events.get("_answer") or ""
    check("回答非空", bool(answer.strip()))
    check("回答带引用标注 [n]", "[" in answer and "]" in answer)

    # ---------- 4. 输出 ----------
    print(f"\n  端到端耗时: {elapsed:.0f} ms")

    compression = retrieved.get("compression")
    if compression:
        ratio = compression["chars_after"] / max(compression["chars_before"], 1)
        print(f"  上下文压缩: {compression['chunks_before']} 块 → "
              f"{compression['chunks_after']} 块 · "
              f"{compression['chars_before']} 字 → {compression['chars_after']} 字 "
              f"（压到 {ratio:.0%}）")

    if spans:
        print("\n  执行时间线:")
        for span in sorted(spans, key=lambda s: s.get("start_ms", 1e9)):
            start = span.get("start_ms")
            start_text = f"{start:>7.0f}" if start is not None else "      —"
            print(f"    {span['name']:<28} 起{start_text} ms   "
                  f"耗时 {span['duration_ms']:>7.0f} ms")

    print(f"\n  回答: {answer[:150]}{'…' if len(answer) > 150 else ''}")

    print()
    print("=" * 78)
    failed = [c for c in checks if not c[1]]
    for label, ok, detail in checks:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {label}" + (f"   ← {detail}" if detail and not ok else ""))
    print("=" * 78)
    print(f"  {'全部通过 ✅' if not failed else f'{len(failed)} 项失败 ❌'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
