"""Provider 工厂：按 settings.llm_provider 返回实例。"""

from functools import lru_cache

from fastapi import HTTPException

from app.config import settings
from app.core.llm.base import LLMProvider
from app.core.llm.providers.dashscope import DashScopeProvider
from app.core.llm.providers.deepseek import DeepSeekProvider
from app.core.llm.providers.stub import StubProvider


@lru_cache
def get_llm() -> LLMProvider:
    key = settings.llm_provider.lower()
    if key == "stub":
        return StubProvider()
    if key == "deepseek":
        if not settings.deepseek_api_key:
            raise HTTPException(503, "DEEPSEEK_API_KEY 未配置，请在 backend/.env 中填写并重启后端")
        return DeepSeekProvider(
            api_key=settings.deepseek_api_key,
            chat_model=settings.deepseek_model,
            vision_model=settings.deepseek_vision_model,
            base_url=settings.deepseek_base_url,
        )
    if key == "dashscope":
        if not settings.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY 未配置")
        return DashScopeProvider(api_key=settings.dashscope_api_key)
    raise ValueError(f"未实现的 LLM provider: {settings.llm_provider}")
