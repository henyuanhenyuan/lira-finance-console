"""集中配置。所有可调项走环境变量，前端设置页读同一份。"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Lira 财务智能体控制台"
    version: str = "2.0.0"

    database_url: str = os.getenv(
        "LIRA_DATABASE_URL",
        "postgresql://lira:lira_dev_2026@127.0.0.1:5433/lira",
    )

    jwt_secret: str = os.getenv("LIRA_JWT_SECRET", "lira-dev-secret-change-me")
    jwt_ttl_minutes: int = 12 * 60

    # 正式模型：OpenAI 兼容协议。qwen-plus 走 DashScope compatible-mode。
    llm_provider: str = os.getenv("LIRA_LLM_PROVIDER", "qwen")
    llm_base_url: str = os.getenv(
        "LIRA_LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    llm_model: str = os.getenv("LIRA_LLM_MODEL", "qwen-plus")
    llm_api_key: str = os.getenv("LIRA_LLM_API_KEY", "")
    llm_timeout_s: float = 60.0

    # 仅测试用途：本机 Ollama 4b。绝不用作生产结论来源。
    test_llm_base_url: str = os.getenv("LIRA_TEST_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    test_llm_model: str = os.getenv("LIRA_TEST_LLM_MODEL", "qwen3:4b")

    embed_model: str = os.getenv("LIRA_EMBED_MODEL", "text-embedding-v3")
    embed_dim: int = 1024

    max_react_steps: int = 6

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
