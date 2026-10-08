"""真模型：通过 HTTP 调用"OpenAI 兼容"接口。

为什么一个类能同时支持 DeepSeek、通义千问、硅基流动、月之暗面、OpenAI？
因为它们都刻意模仿了 OpenAI 的接口格式（同样的网址路径、同样的 JSON 结构）。
这是行业事实上的标准，所以一个实现就够了。
"""

import json
from collections.abc import AsyncIterator

import httpx

from app.llm.provider import Chunk, LLMProvider, Usage


class OpenAICompatProvider(LLMProvider):
    """按照 LLMProvider 定的规矩，实现一个真的能联网的模型。"""

    name = "openai_compat"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        temperature: float = 0.3,
        timeout_s: float = 60.0,
        max_tokens: int = 2048,
        include_usage: bool = True,
    ) -> None:
        # 早失败原则：没有 Key 就别往下走了，立刻报错。
        # 总比等到用户点了发送才失败要好。
        if not api_key:
            raise ValueError(
                "缺少 API Key。请在 backend/.env 里填写 LLM_API_KEY，"
                "或把 LLM_PROVIDER 改成 mock 使用假模型。"
            )

        self.api_key = api_key
        # rstrip("/") 去掉结尾多余的斜杠，防止拼出 https://xxx//chat/completions
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self.include_usage = include_usage

    # ----------------------------------------------------------------- #
    # 一次性版本（不流式）：给"不需要流式"的场景用，比如后面做判分、做自查
    # ----------------------------------------------------------------- #
    async def complete(self, messages: list[dict[str, str]]) -> str:
        """发一个 HTTP 请求给模型厂商，把回答取出来。"""

        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        # async with 会在代码块结束后自动关闭连接，不用手动 close
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(url, headers=headers, json=payload)

        # 先检查状态码。200 才是成功，其他都是出错。
        # 如果不管状态码直接解析，出错时你会看到一堆莫名其妙的 KeyError，很难排查。
        if response.status_code != 200:
            raise RuntimeError(
                f"模型接口返回 {response.status_code}：{response.text[:300]}"
            )

        data = response.json()

        # 从嵌套的 JSON 里把回答挖出来。这个路径是 OpenAI 格式规定的。
        return data["choices"][0]["message"]["content"]

    # ----------------------------------------------------------------- #
    # 流式版本：真正的边收边转发
    # ----------------------------------------------------------------- #
    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[Chunk]:
        """真的流式：模型每生成一小段，我们立刻转发出去，不做任何等待。

        和 complete() 的区别只有一个：
        这里不"等整个回答生成完"，而是收到一点就往外吐一点。
        用户因此能提前 2~3 秒看到第一个字。
        """

        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            # ★ 关键：告诉厂商"我要流式，别一次性把结果全给我"
            "stream": True,
            # ★ 让厂商在最后一个包里带上 token 用量（不写这个就拿不到用量）
        }
        if self.include_usage:
            payload["stream_options"] = {"include_usage": True}

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            # 注意是 client.stream(...) 而不是 client.post(...)
            # stream 表示"边收边处理"，post 表示"等全部收完再给我"
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    # 出错时必须先把 body 读出来再抛，否则看不到具体错误内容
                    body = await response.aread()
                    raise RuntimeError(
                        f"模型接口返回 {response.status_code}：{body[:300]!r}"
                    )

                # aiter_lines() 一行一行地读，不用等整个响应结束
                async for line in response.aiter_lines():

                    # 厂商返回的格式和我们发给前端的格式其实是同一种（都叫 SSE）：
                    #     data: {"choices":[{"delta":{"content":"你"}}]}
                    #     data: {"choices":[{"delta":{"content":"好"}}]}
                    #     data: [DONE]
                    if not line.startswith("data:"):
                        continue

                    data = line[len("data:"):].strip()
                    if not data:
                        continue
                    if data == "[DONE]":        # 这个标记表示"我说完了"
                        break

                    event = json.loads(data)

                    # 用量只在最后一个包里出现一次，可能带着空的 choices
                    usage_raw = event.get("usage")
                    if usage_raw:
                        yield Chunk(
                            usage=Usage(
                                prompt_tokens=int(usage_raw.get("prompt_tokens") or 0),
                                completion_tokens=int(usage_raw.get("completion_tokens") or 0),
                            )
                        )

                    choices = event.get("choices") or []
                    if not choices:
                        continue

                    # 流式返回里字段叫 delta（增量），不是 message（完整消息）。
                    # 这是和 complete() 最大的区别，写错了会一直拿到空字符串。
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content")
                    if text:
                        yield Chunk(text=text)
