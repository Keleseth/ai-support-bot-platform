"""
OpenAI-compatible LLM implementation of BaseLLM.

Used for testing with xAI Grok or standard OpenAI.
Both use the same OpenAI Python SDK - only base_url and api_key differ.

Set LLM_PROVIDER=openai_compatible and LLM_BASE_URL in .env to activate.
xAI Grok base URL: https://api.x.ai/v1

Full implementation: Milestone 4.
"""

from openai import AsyncOpenAI

from support_platform.config import Settings
from support_platform.core.models import ChatMessage
from support_platform.llm.base import BaseLLM


class OpenAICompatibleLLM(BaseLLM):
    """LLM provider backed by any OpenAI-compatible API (xAI Grok, OpenAI, etc.)."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,  # None = standard OpenAI endpoint
        )
        self._model = settings.llm_model

    async def complete(self, messages: list[ChatMessage]) -> str:
        """Send messages to the provider and return the response text. Implemented in Milestone 4."""
        raise NotImplementedError
