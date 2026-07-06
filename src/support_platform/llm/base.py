"""
Abstract base class for LLM providers.

The Anthropic and OpenAI SDKs have different Python interfaces - different
clients, message formats, response shapes. BaseLLM normalizes them so
TicketProcessor never imports provider-specific code.

Message format is list[dict[str, str]], the OpenAI-compatible convention:
each dict has 'role' ('system' | 'user' | 'assistant') and 'content'.
Messages are assembled by prompts.py, not by a provider or Core.
"""

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """Common interface for all LLM providers."""

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Send messages to the LLM and return the response text."""
        ...
