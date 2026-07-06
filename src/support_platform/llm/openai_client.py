"""
BaseLLM implementation for OpenAI-compatible APIs.

Used for testing against xAI Grok or a standard OpenAI endpoint - both speak
the same SDK and differ only in base_url and api_key.

Activate with LLM_PROVIDER=openai_compatible and LLM_BASE_URL in .env
(xAI Grok's base URL is https://api.x.ai/v1).
"""

from openai import AsyncOpenAI

from support_platform.config import Settings
from support_platform.llm.base import BaseLLM


class OpenAICompatibleLLM(BaseLLM):
    """LLM provider for any OpenAI-compatible API (xAI Grok, OpenAI, etc.)."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,  # None falls back to the standard OpenAI endpoint
        )
        self._model = settings.llm_model

    async def complete(self, messages: list[dict[str, str]]) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
        )
        return response.choices[0].message.content or ''
