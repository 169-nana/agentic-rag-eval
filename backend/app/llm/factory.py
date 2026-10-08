"""工厂：根据配置，决定这次要用哪个模型。

"工厂"是编程里的常见说法，意思是"专门负责创建对象的函数/类"。
好处是创建逻辑集中在一处，别处只管说要什么，不管怎么造。
"""

from app.config import get_settings
from app.llm.mock import MockProvider
from app.llm.openai_compat import OpenAICompatProvider
from app.llm.provider import LLMProvider


def build_provider() -> LLMProvider:
    """读配置，返回一个模型实例。"""

    settings = get_settings()
    choice = settings.llm_provider.lower()

    # 情况 1：明确要求用假模型
    if choice == "mock":
        return MockProvider(delay_s=0.5)

    # 情况 2：明确要求用真模型
    if choice == "openai_compat":
        return OpenAICompatProvider(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            timeout_s=settings.llm_timeout_s,
            max_tokens=settings.llm_max_tokens,
            include_usage=settings.llm_include_usage,
        )

    # 情况 3：自动。有 Key 用真的，没 Key 退回假的。
    # 这样别人 clone 你的项目后，不用配任何东西就能先跑起来看看，
    # 降低了"第一次运行就失败"的挫败感。
    if choice == "auto":
        if settings.llm_api_key:
            return OpenAICompatProvider(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                model=settings.llm_model,
                temperature=settings.llm_temperature,
                timeout_s=settings.llm_timeout_s,
                max_tokens=settings.llm_max_tokens,
                include_usage=settings.llm_include_usage,
            )
        print("[提示] 未配置 LLM_API_KEY，已自动使用假模型（mock）")
        return MockProvider(delay_s=0.5)

    # 情况 4：配置写错了，明确报错，别默默用错的东西
    raise ValueError(
        f"未知的 LLM_PROVIDER: {settings.llm_provider}。可选值：auto / mock / openai_compat"
    )
