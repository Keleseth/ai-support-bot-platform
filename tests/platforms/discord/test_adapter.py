"""
Tests for platforms/discord/adapter.py - _is_monitored.

Regression test for a live bug: the LLM replied in the order records
channel because filtering used to match on category name, and that name
collided with the tickets category's name. The filter is now an exact
category id, and these tests pin down that behavior.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import discord

from support_platform.config import Settings
from support_platform.platforms.discord.adapter import DiscordAdapter

_TICKETS_CATEGORY_ID = 111


async def _noop(message: Any) -> None:
    pass


def _adapter() -> DiscordAdapter:
    settings = Settings.model_construct(
        discord_token='t',
        tickets_category_id=str(_TICKETS_CATEGORY_ID),
    )
    return DiscordAdapter(settings, message_handler=_noop, client=Mock())


def _message_in_category(category_id: int | None) -> Mock:
    channel = Mock(spec=discord.TextChannel)
    channel.category = SimpleNamespace(id=category_id) if category_id is not None else None
    return Mock(channel=channel)


def test_monitored_when_category_id_matches() -> None:
    adapter = _adapter()
    assert adapter._is_monitored(_message_in_category(_TICKETS_CATEGORY_ID)) is True


def test_not_monitored_when_category_id_differs() -> None:
    adapter = _adapter()
    assert adapter._is_monitored(_message_in_category(999)) is False


def test_not_monitored_without_category() -> None:
    adapter = _adapter()
    assert adapter._is_monitored(_message_in_category(None)) is False


def test_not_monitored_for_non_text_channel() -> None:
    adapter = _adapter()
    message = Mock(channel=Mock())  # no spec=discord.TextChannel, so isinstance fails
    assert adapter._is_monitored(message) is False
