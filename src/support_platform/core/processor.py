"""
TicketProcessor - orchestrates the full ticket processing pipeline.

Responsibilities:
  1. Call LLM #1 to detect customer intent
  2. Based on intent, call the appropriate repository lookup
  3. Call LLM #2 to generate the response
  4. Return the completed TicketContext

TicketProcessor knows nothing about Discord or any specific LLM provider.
Both are injected as dependencies.

Full implementation: Milestone 4.
"""

from support_platform.core.models import Intent, TicketContext
from support_platform.llm.base import BaseLLM


class TicketProcessor:
    """Orchestrates intent detection, data lookup, and response generation."""

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    async def process(self, context: TicketContext) -> TicketContext:
        """
        Run the full pipeline for a ticket.
        Returns context with intent, customer_data, and response populated.
        """
        raise NotImplementedError
