"""假模型：不联网、不花钱，用来验证链路通不通。

它不是"玩具"。它的真实用途有两个：
1. 没配 API Key 时，也能把整个流程跑起来，先确认自己的代码没写错
2. 以后写自动化测试时，它完全确定、不会因为网络波动而时好时坏
"""

import asyncio
from collections.abc import AsyncIterator

from app.llm.provider import Chunk, LLMProvider, Usage


class MockProvider(LLMProvider):
    """继承 LLMProvider，就必须实现 complete() 和 stream()。"""

    # 覆盖父类的属性，标明自己是谁
    name = "mock"
    model = "mock-echo"

    def __init__(self, delay_s: float = 0.0) -> None:
        # 故意加一点延迟，模拟真模型的耗时，方便验证"计时"功能
        self.delay_s = delay_s

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """找出最后一条用户消息，然后编一段话返回。"""

        # 从后往前遍历，找到最后一条 role 是 user 的消息
        last_user_content = ""
        for message in reversed(messages):
            if message["role"] == "user":
                last_user_content = message["content"]
                break

        if self.delay_s:
            # await 的意思是"等这件事做完，但这期间可以让出 CPU 去处理别的请求"。
            # 这是 async 的核心价值：等网络/等磁盘时不干等着。
            await asyncio.sleep(self.delay_s)

        return (
            "【假模型】当前没有接入真实 AI，这是本地假模型在回答。\n\n"
            f"我收到的最后一条用户消息是：{last_user_content}\n\n"
            "它的作用是让你先把链路跑通，不消耗任何费用。"
        )

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[Chunk]:
        """把完整回答切成小块，一块一块吐出去。

        实现思路很直接：先让 complete() 生成整段文字，
        再切成小份慢慢吐，模拟"模型边想边写"的效果。

        注意：真模型不会这么干（那样等于没流式）。真模型是真的边收边转发。
        """
        full_text = await self.complete(messages)

        # range(起点, 终点, 步长)：从 0 开始，每次 +4，也就是每 4 个字符切一刀
        step = 4
        for i in range(0, len(full_text), step):
            await asyncio.sleep(0.05)   # 模拟"生成这几个字"需要的时间
            yield Chunk(text=full_text[i : i + step])

        # 最后补一个只带用量的 Chunk。
        # 真模型也是在最后一个包里给用量，这里刻意保持一致，
        # 这样上层处理真假模型的代码完全一样。
        yield Chunk(
            usage=Usage(
                # 粗略估算：大约 2 个字符 = 1 个 token
                prompt_tokens=sum(len(m["content"]) for m in messages) // 2,
                completion_tokens=len(full_text) // 2,
            )
        )
