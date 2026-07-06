"""
TicketDebouncer waits for a lull in the customer's messages before running the pipeline.

Customers often send several short messages in a row instead of one, so
firing on every message would mean answering half-formed thoughts. Instead
the debouncer waits TICKET_DEBOUNCE_SECONDS after the last message, then
hands the whole batch to on_ready as a single list[IncomingMessage] - the
order id might be in the first message and the actual question in the third,
so the processor needs the full batch, not just the last message.

State is keyed by (channel_id, author_id): if several customers post in the
same ticket channel, each gets an independent timer instead of resetting
one another's.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from support_platform.config import Settings
from support_platform.core.models import IncomingMessage

logger = logging.getLogger(__name__)


@dataclass
class ConversationState:
    """
    State of one active conversation.

    Created on the customer's first message, removed once on_ready fires
    or a staff member replies in the channel.
    """

    task: asyncio.Task[None]
    last_message_at: datetime
    messages: list[IncomingMessage] = field(default_factory=list)


class TicketDebouncer:
    """Schedules debounced delivery of accumulated messages, one timer per (channel, author)."""

    def __init__(
        self,
        settings: Settings,
        on_ready: Callable[[list[IncomingMessage]], Awaitable[None]],
    ) -> None:
        self._delay = settings.ticket_debounce_seconds
        self._on_ready = on_ready
        self._states: dict[tuple[str, str], ConversationState] = {}

    async def handle(self, message: IncomingMessage) -> None:
        """Staff message closes the channel's conversations; customer message extends its timer."""
        if message.is_staff:
            self._cancel_channel(message.channel_id)
            return

        key = (message.channel_id, message.author_id)

        if key in self._states:
            state = self._states[key]
            state.task.cancel()
            state.messages.append(message)
            state.last_message_at = message.timestamp
            state.task = asyncio.create_task(self._delayed_fire(key))
        else:
            task = asyncio.create_task(self._delayed_fire(key))
            self._states[key] = ConversationState(
                task=task,
                last_message_at=message.timestamp,
                messages=[message],
            )

        logger.debug(
            'timer reset channel=%s author=%s accumulated=%d delay=%.1fs',
            message.channel_id,
            message.author_id,
            len(self._states[key].messages),
            self._delay,
        )

    def _cancel_channel(self, channel_id: str) -> None:
        """Cancel and drop every active conversation in a channel."""
        keys = [k for k in self._states if k[0] == channel_id]
        for key in keys:
            self._states[key].task.cancel()
            del self._states[key]
        if keys:
            logger.debug('staff replied, closed conversations: %d', len(keys))

    async def _delayed_fire(self, key: tuple[str, str]) -> None:
        """
        Sleep for the debounce delay, then hand the accumulated messages to on_ready.

        The task-identity check in finally exists because asyncio cancellation
        isn't immediate: a cancelled task's finally block can still run after
        state.task has already been replaced by a newer task, which would
        otherwise delete state that belongs to that newer task.
        """
        try:
            await asyncio.sleep(self._delay)
            state = self._states.pop(key, None)
            if state and state.messages:
                logger.info(
                    'timer fired channel=%s author=%s messages=%d',
                    key[0],
                    key[1],
                    len(state.messages),
                )
                await self._on_ready(state.messages)
        except asyncio.CancelledError:
            pass
        finally:
            current = self._states.get(key)
            if current is not None and current.task is asyncio.current_task():
                del self._states[key]
