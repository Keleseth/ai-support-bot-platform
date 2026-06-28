"""
Abstract base class for LLM provider integrations.

Why this abstraction exists: Anthropic SDK and OpenAI SDK have different Python
interfaces - different clients, message formats, and response shapes.
BaseLLM normalises them so TicketProcessor has a single stable interface
and never imports any provider-specific code.
"""

from abc import ABC, abstractmethod

from support_platform.core.models import ChatMessage


class BaseLLM(ABC):
    """Common interface for all LLM provider implementations."""

    @abstractmethod
    async def complete(self, messages: list[ChatMessage]) -> str:
        """Send a conversation to the LLM and return its text response."""
        ...
