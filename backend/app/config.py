"""应用配置：统一从 .env 文件和环境变量里读设置。

设计原则：所有"会变的东西"（密钥、用哪个模型、模型名字）都放这里，
代码里不出现任何硬编码的值。
"""

# lru_cache 是一个"缓存装饰器"，作用见文件末尾
from functools import lru_cache
from pathlib import Path
from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend 目录的绝对路径。
# 为什么用绝对路径而不是写 ".env"？
# 因为 ".env" 是相对路径，取决于"你在哪个目录敲命令"。
# 从别的目录启动服务就找不到了。用绝对路径永远不会错。
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """配置项。

    命名规则（这是 pydantic-settings 的约定）：
        字段名 llm_api_key  ←→  环境变量 LLM_API_KEY
        小写加下划线          全大写加下划线
    所以你在 .env 里写 LLM_API_KEY=xxx，这里就能读到。
    """

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",   # 去哪里读 .env
        env_file_encoding="utf-8",        # 文件编码，中文注释需要
        extra="ignore",                   # .env 里有不认识的变量？忽略，别报错
    )

    # 用哪个模型：
    #   auto          = 有 Key 就用真的，没有就用假的（推荐，开箱即用）
    #   mock          = 强制用假模型
    #   openai_compat = 强制用真模型
    llm_provider: str = "auto"

    # 真模型的连接信息。默认填的是 DeepSeek，换别家只改这里
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_temperature: float = Field(default=0.3, ge=0, le=2)
    llm_timeout_s: float = Field(default=60, gt=0, le=600)
    llm_max_tokens: int = Field(default=2048, gt=0)
    llm_include_usage: bool = True

    # CORS 允许列表使用逗号分隔，便于 .env 与容器环境配置。
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- 数据库 ----
    # 连接串格式：postgresql://用户名:密码@主机:端口/库名
    database_url: str = "postgresql://agent:agent@127.0.0.1:5432/agent_rag"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_mock(self) -> bool:
        """当前是不是在用假模型。

        两种情况算 mock：
          1. 明确写了 llm_provider=mock
          2. 写了 auto，但没配 API Key —— 此时工厂会自动退回假模型

        评测脚本靠它判断"能不能用 LLM judge"：
        假模型返回的是固定文本，拿它当判分器毫无意义。
        """
        if self.llm_provider.lower() == "mock":
            return True
        return self.llm_provider.lower() == "auto" and not self.llm_api_key

# @lru_cache 的作用：第一次调用时真正读文件，之后每次调用直接返回缓存的结果。
# 为什么要缓存？因为 get_settings() 会在每个请求里被调用，
# 每次都去读磁盘上的 .env 文件纯属浪费。
@lru_cache
def get_settings() -> Settings:
    return Settings()
