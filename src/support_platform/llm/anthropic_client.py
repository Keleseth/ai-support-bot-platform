"""
Anthropic Claude implementation of BaseLLM.

Converts our internal ChatMessage list to the Anthropic messages API format.

Important: Anthropic separates the system prompt from the messages array.
A ChatMessage with role="system" is extracted and passed as the `system=`
parameter to the API - it cannot appear inline in the messages list.

Full implementation: Milestone 4.
"""

from anthropic import AsyncAnthropic

from support_platform.config import Settings
from support_platform.core.models import ChatMessage
from support_platform.llm.base import BaseLLM


class AnthropicLLM(BaseLLM):
    """LLM provider backed by the Anthropic Claude API."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncAnthropic(api_key=settings.llm_api_key)
        self._model = settings.llm_model

    async def complete(self, messages: list[ChatMessage]) -> str:
        """Send messages to Claude and return the response text. Implemented in Milestone 4."""
        raise NotImplementedError
