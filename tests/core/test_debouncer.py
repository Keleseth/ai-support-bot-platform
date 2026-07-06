"""Tests for core/debouncer.py - message aggregation and timing of TicketDebouncer."""

import asyncio
from collections.abc import Awaitable, Callable

from support_platform.config import Settings
from support_platform.core.debouncer import TicketDebouncer
from support_platform.core.models import IncomingMessage
from tests.conftest import make_incoming_message

# Small delay - these tests wait on real time, but 0.05s doesn't noticeably
# slow the suite down, and the 3x margin below absorbs asyncio scheduler jitter.
_DELAY = 0.05


def _settings() -> Settings:
    return Settings.model_construct(ticket_debounce_seconds=_DELAY)


def _collector() -> tuple[
    list[list[IncomingMessage]],
    Callable[[list[IncomingMessage]], Awaitable[None]],
]:
    """on_ready callback that just collects every call into a list for assertions."""
    fired: list[list[IncomingMessage]] = []

    async def on_ready(messages: list[IncomingMessage]) -> None:
        fired.append(messages)

    return fired, on_ready


async def test_fires_once_after_delay_with_single_message() -> None:
    fired, on_ready = _collector()
    debouncer = TicketDebouncer(_settings(), on_ready=on_ready)

    await debouncer.handle(make_incoming_message('привет'))
    await asyncio.sleep(_DELAY * 3)

    assert len(fired) == 1
    assert [m.content for m in fired[0]] == ['привет']


async def test_aggregates_messages_sent_before_delay_expires() -> None:
    fired, on_ready = _collector()
    debouncer = TicketDebouncer(_settings(), on_ready=on_ready)

    await debouncer.handle(make_incoming_message('первое'))
    await asyncio.sleep(_DELAY / 2)
    await debouncer.handle(make_incoming_message('второе'))
    await asyncio.sleep(_DELAY * 3)

    assert len(fired) == 1
    assert [m.content for m in fired[0]] == ['первое', 'второе']


async def test_staff_message_cancels_pending_conversation() -> None:
    fired, on_ready = _collector()
    debouncer = TicketDebouncer(_settings(), on_ready=on_ready)

    await debouncer.handle(make_incoming_message('привет', channel_id='c1', author_id='u1'))
    await debouncer.handle(
        make_incoming_message('ответ стаффа', channel_id='c1', author_id='staff', is_staff=True)
    )
    await asyncio.sleep(_DELAY * 3)

    assert fired == []


async def test_independent_timers_per_author_in_same_channel() -> None:
    fired, on_ready = _collector()
    debouncer = TicketDebouncer(_settings(), on_ready=on_ready)

    await debouncer.handle(make_incoming_message('от первого', channel_id='c1', author_id='u1'))
    await asyncio.sleep(_DELAY / 2)
    await debouncer.handle(make_incoming_message('от второго', channel_id='c1', author_id='u2'))
    await asyncio.sleep(_DELAY * 3)

    assert len(fired) == 2
    contents = {messages[0].content for messages in fired}
    assert contents == {'от первого', 'от второго'}
