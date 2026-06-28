"""
TicketDebouncer - delays processing until a customer stops typing.

Why debounce: customers often send multiple short messages in a row.
Without debounce, the bot would respond to each partial message.
With debounce, it waits for silence, then responds to the full thought.

Implementation: one asyncio.Task per active channel.
Each new message cancels the previous task and starts a fresh timer.
When the timer expires without interruption, pre-flight checks run,
and if they pass, TicketProcessor is called.

Pre-flight checks (performed after debounce):
  1. Channel is in a monitored category (e.g. "uncategorized", "orders")
  2. Last message in the channel was sent by the customer, not a staff member

Full implementation: Milestone 3.
"""

import asyncio
from collections.abc import Awaitable, Callable

from support_platform.config import Settings
from support_platform.core.models import IncomingMessage


class TicketDebouncer:
    """
    Per-channel debounce scheduler.
    Maintains one asyncio.Task per active ticket channel.
    """

    def __init__(
        self,
        settings: Settings,
        on_ready: Callable[[IncomingMessage], Awaitable[None]],
    ) -> None:
        self._delay = settings.ticket_debounce_seconds
        self._categories = [c.lower() for c in settings.ticket_category_names]
        self._on_ready = on_ready
        self._pending: dict[str, asyncio.Task[None]] = {}

    async def handle(self, message: IncomingMessage) -> None:
        """
        Accept a new message event.

        Resets the debounce timer for the message's channel.
        Staff messages are ignored - only customer messages trigger the timer.
        """
        raise NotImplementedError
