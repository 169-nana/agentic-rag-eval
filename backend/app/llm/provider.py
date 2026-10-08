"""模型接入层：定义"所有 AI 模型都必须会做什么"。

这一层是整个项目最重要的设计决定。它让"接口层"和"具体哪家模型"彻底分开。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


# --------------------------------------------------------------------------- #
# 两个小小的数据结构，用来承载"模型产出的东西"
# --------------------------------------------------------------------------- #
@dataclass
class Usage:
    """token 用量。

    token 是模型计费的单位，大约 1 个汉字 = 1~2 个 token。
    prompt_tokens     = 我们发过去的内容有多少 token（问题 + 系统提示词）
    completion_tokens = 模型生成的内容有多少 token（回答）

    为什么要记录它？因为它是成本的唯一来源，
    也是"这次回答为什么慢"的重要线索（生成 2000 token 必然比 200 token 慢）。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class Chunk:
    """流式产出的一小片。

    为什么一个类型里装两种东西（文字 / 用量）？
    因为模型流式返回时，文字是一段一段来的，
    而 token 用量通常在最后一个包里只给一次。
    两者用同一个类型承载，上层就只需要写一次 async for 循环。
    """

    text: str = ""
    usage: Usage | None = None


class LLMProvider(ABC):
    """所有模型的"统一插座"。

    注意：ABC 这种类**不能被直接创建**。
    它的作用只是规定"想当我子类，就必须实现下面两个方法"。
    如果有人继承了它却忘了实现，Python 会在创建对象时立刻报错，
    而不是等到用户点下发送按钮才炸——错误暴露得越早越好。
    """

    # 这两个属性是给日志和界面看的，子类会覆盖它们
    name: str = "base"
    model: str = ""

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> str:
        """接收一串消息，一次性返回模型生成的完整文字。

        messages 长这样（这个格式是 OpenAI 定的，现在几乎所有厂商都兼容）：
            [
              {"role": "system", "content": "你是一个严谨的助手"},
              {"role": "user",   "content": "什么是 RAG？"}
            ]

        这里只写 raise NotImplementedError，不写真正的实现。
        因为"怎么调用模型"是各家自己的事，父类管不着，只负责立规矩。
        """
        raise NotImplementedError

    @abstractmethod
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[Chunk]:
        """流式版本：一段一段地返回，而不是一次性返回完整回答。

        ⚠ 这里写的是 def 而不是 async def，原因要说清楚：
        这个方法体内**没有 yield**（父类只画签名、不写实现），
        所以它根本不是生成器，只是一行"声明"。
        子类实现时才会用 `async def` + `yield` 写成真正的异步生成器。

        （顺带纠正一个常见误解：实现异步生成器**必须**用 async def + yield。
         如果子类写成 def + yield，得到的是普通生成器，
         调用方用 async for 遍历时会报
         "TypeError: 'async for' requires an object with __aiter__ method, got generator"。）

        返回类型 AsyncIterator[Chunk] 的意思是：
        "这是一个可以被 async for 遍历的东西，每次吐出一个 Chunk"。
        """
        raise NotImplementedError
