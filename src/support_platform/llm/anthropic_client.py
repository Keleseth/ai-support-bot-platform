"""
Реализация BaseLLM для Anthropic Claude API.

Преобразует наш формат list[dict[str, str]] в формат Anthropic Messages API.

Важно: Anthropic выделяет системный промпт отдельно от массива сообщений.
Сообщение с role='system' извлекается и передаётся как параметр system=
в вызов API - оно не может быть в списке messages inline.

Реализация: Milestone 4.
"""

from anthropic import AsyncAnthropic

from support_platform.config import Settings
from support_platform.llm.base import BaseLLM


class AnthropicLLM(BaseLLM):
    """LLM-провайдер на базе Anthropic Claude API."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncAnthropic(api_key=settings.llm_api_key)
        self._model = settings.llm_model

    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Отправить сообщения в Claude и вернуть текст ответа. Реализуется в Milestone 4."""
        raise NotImplementedError
