"""
BaseLLM implementation backed by the Anthropic Claude API.

Converts our list[dict[str, str]] message format into the Anthropic Messages
API format. Anthropic takes the system prompt as its own parameter rather
than a message in the list, so a role='system' entry has to be pulled out
and passed as system= instead of staying inline.
"""

from anthropic import AsyncAnthropic

from support_platform.config import Settings
from support_platform.llm.base import BaseLLM


class AnthropicLLM(BaseLLM):
    """LLM provider backed by the Anthropic Claude API."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncAnthropic(api_key=settings.llm_api_key)
        self._model = settings.llm_model

    async def complete(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError
