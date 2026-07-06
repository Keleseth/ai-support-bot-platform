"""Tests for platforms/discord/ticket_panel.py - ticket numbering, button, and startup check."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock

import discord
import pytest

from support_platform.platforms.discord.ticket_panel import (
    _PANEL_MESSAGE,
    _TICKET_WELCOME,
    TicketPanel,
    TicketPanelView,
    _next_ticket_number,
)

_TICKETS_CATEGORY_ID = 111
_MODERATOR_ROLE_ID = 222


def _channel_named(name: str) -> Mock:
    channel = Mock()
    channel.name = name
    return channel


def _category(channel_names: list[str]) -> Mock:
    category = Mock(spec=discord.CategoryChannel)
    category.channels = [_channel_named(name) for name in channel_names]
    category.create_text_channel = AsyncMock()
    return category


@pytest.mark.parametrize(
    ('existing', 'expected'),
    [
        ([], 1),
        (['ticket-1', 'ticket-2'], 3),
        (['ticket-1', 'orders_id_emails', 'ticket-2'], 3),
        (['ticket-1', 'ticket-5'], 6),
        (['Ticket-1'], 1),
    ],
    ids=['empty', 'sequential', 'ignores-unrelated-names', 'numbers-past-a-gap', 'case-sensitive'],
)
def test_next_ticket_number(existing: list[str], expected: int) -> None:
    assert _next_ticket_number(_category(existing)) == expected


def _view() -> TicketPanelView:
    return TicketPanelView(_TICKETS_CATEGORY_ID, _MODERATOR_ROLE_ID)


# @discord.ui.button replaces the decorated method on the instance with a
# Button item; view.create_ticket is that item, not a bound coroutine.
# Its .callback already has self and the button item bound - only
# interaction needs to be passed here.


def _interaction(
    guild: Mock | None,
    user: Mock,
) -> Mock:
    interaction = Mock(spec=discord.Interaction)
    interaction.guild = guild
    interaction.user = user
    interaction.response = Mock()
    interaction.response.send_message = AsyncMock()
    return interaction


async def test_create_ticket_does_nothing_without_a_guild() -> None:
    interaction = _interaction(guild=None, user=Mock(spec=discord.Member))

    await _view().create_ticket.callback(interaction)

    interaction.response.send_message.assert_not_called()


async def test_create_ticket_does_nothing_when_user_is_not_a_member() -> None:
    guild = Mock()
    interaction = _interaction(guild=guild, user=Mock(spec=discord.User))

    await _view().create_ticket.callback(interaction)

    interaction.response.send_message.assert_not_called()


async def test_create_ticket_replies_when_category_missing() -> None:
    guild = Mock()
    guild.get_channel = Mock(return_value=None)
    interaction = _interaction(guild=guild, user=Mock(spec=discord.Member))

    await _view().create_ticket.callback(interaction)

    interaction.response.send_message.assert_awaited_once_with(
        'Ticket creation is not available right now.', ephemeral=True
    )


async def test_create_ticket_happy_path_grants_creator_moderator_and_bot() -> None:
    guild = Mock()
    category = _category([])
    new_channel = Mock()
    new_channel.mention = '#ticket-1'
    new_channel.send = AsyncMock()
    category.create_text_channel.return_value = new_channel

    guild.get_channel = Mock(return_value=category)
    moderator_role = Mock(spec=discord.Role)
    guild.get_role = Mock(return_value=moderator_role)
    guild.default_role = Mock(spec=discord.Role)
    guild.me = Mock(spec=discord.Member)

    member = Mock(spec=discord.Member)
    interaction = _interaction(guild=guild, user=member)

    await _view().create_ticket.callback(interaction)

    category.create_text_channel.assert_awaited_once()
    _, kwargs = category.create_text_channel.call_args
    assert kwargs['name'] == 'ticket-1'

    overwrites = kwargs['overwrites']
    assert overwrites[guild.default_role].view_channel is False
    assert overwrites[member].view_channel is True
    assert overwrites[member].send_messages is True
    assert overwrites[guild.me].view_channel is True
    assert overwrites[moderator_role].view_channel is True

    new_channel.send.assert_awaited_once_with(_TICKET_WELCOME)
    interaction.response.send_message.assert_awaited_once_with(
        'Your ticket: #ticket-1', ephemeral=True
    )


async def test_create_ticket_skips_moderator_overwrite_when_role_not_found() -> None:
    guild = Mock()
    category = _category([])
    new_channel = Mock()
    new_channel.mention = '#ticket-1'
    new_channel.send = AsyncMock()
    category.create_text_channel.return_value = new_channel

    guild.get_channel = Mock(return_value=category)
    guild.get_role = Mock(return_value=None)
    guild.default_role = Mock(spec=discord.Role)
    guild.me = Mock(spec=discord.Member)

    interaction = _interaction(guild=guild, user=Mock(spec=discord.Member))

    await _view().create_ticket.callback(interaction)

    _, kwargs = category.create_text_channel.call_args
    assert len(kwargs['overwrites']) == 3  # default_role, creator, bot - no moderator entry


def _history(messages: list[Mock]) -> AsyncIterator[Mock]:
    async def _generator() -> AsyncIterator[Mock]:
        for message in messages:
            yield message

    return _generator()


def _client(support_channel: Mock | None) -> Mock:
    client = Mock()
    client.get_channel = Mock(return_value=support_channel)
    client.user = Mock()
    return client


async def test_on_ready_posts_panel_when_no_prior_message_exists() -> None:
    channel = Mock(spec=discord.TextChannel)
    channel.history = Mock(return_value=_history([]))
    channel.send = AsyncMock()
    client = _client(channel)

    panel = TicketPanel('1', str(_TICKETS_CATEGORY_ID), str(_MODERATOR_ROLE_ID), client)
    await panel._on_ready()

    channel.send.assert_awaited_once_with(_PANEL_MESSAGE, view=panel._view)


async def test_on_ready_skips_when_panel_message_already_posted() -> None:
    channel = Mock(spec=discord.TextChannel)
    client = _client(channel)
    own_message = Mock(author=client.user)
    channel.history = Mock(return_value=_history([own_message]))
    channel.send = AsyncMock()

    panel = TicketPanel('1', str(_TICKETS_CATEGORY_ID), str(_MODERATOR_ROLE_ID), client)
    await panel._on_ready()

    channel.send.assert_not_awaited()


async def test_on_ready_does_nothing_when_support_channel_missing() -> None:
    client = _client(support_channel=None)

    panel = TicketPanel('1', str(_TICKETS_CATEGORY_ID), str(_MODERATOR_ROLE_ID), client)
    await panel._on_ready()

    client.get_channel.assert_called_once_with(1)
