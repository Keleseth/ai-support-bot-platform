"""
Реализация BaseLLM для OpenAI-совместимых API.

Используется для тестирования с xAI Grok или стандартным OpenAI.
Оба используют один Python SDK - отличаются только base_url и api_key.

Для активации: LLM_PROVIDER=openai_compatible и LLM_BASE_URL в .env.
xAI Grok base URL: https://api.x.ai/v1
"""

from openai import AsyncOpenAI

from support_platform.config import Settings
from support_platform.llm.base import BaseLLM


class OpenAICompatibleLLM(BaseLLM):
    """LLM-провайдер для любого OpenAI-совместимого API (xAI Grok, OpenAI и др.)."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,  # None = стандартный OpenAI endpoint
        )
        self._model = settings.llm_model

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Отправить сообщения в OpenAI-совместимый API и вернуть текст ответа."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
        )
        return response.choices[0].message.content or ''
