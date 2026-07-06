"""
Ticket panel: a "Create Ticket" button posted once in the support channel.

Two independent pieces:
  - TicketPanelView: the persistent button. Registered on the client via
    add_view (not add_listener - Discord routes component clicks by
    custom_id, not through the named-event dispatch used for on_message/
    on_ready), so it keeps working across reconnects and bot restarts.
  - TicketPanel: checks once on startup whether the panel message already
    exists in the support channel, and posts it if not.
"""

import asyncio
import logging
import re

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

_PANEL_MESSAGE = 'Want to place an order or check on an existing one? Create a ticket below.'

_TICKET_WELCOME = (
    'To check your order status, send your order id or email.\n'
    'To place an order, send the product name or its id.'
)

# Matches channel names this feature created, so the next one can be numbered
# right after the highest existing ticket - independent of any tickets that
# were since closed or renamed.
_TICKET_NAME_RE = re.compile(r'^ticket-(\d+)$')

# Matches create_text_channel's overwrites signature - Object is included
# only to satisfy that signature, this code never uses it.
type _OverwriteKey = discord.Role | discord.Member | discord.Object


class TicketPanelView(discord.ui.View):
    """
    The "Create Ticket" button.

    timeout=None makes it a persistent view - without that, discord.py would
    stop listening for clicks on this button after a default 180 seconds.
    """

    def __init__(self, tickets_category_id: int, moderator_role_id: int) -> None:
        super().__init__(timeout=None)
        self._tickets_category_id = tickets_category_id
        self._moderator_role_id = moderator_role_id
        # Serializes channel creation so two near-simultaneous clicks can't
        # both read the same "highest ticket number" and create a duplicate.
        self._lock = asyncio.Lock()

    @discord.ui.button(
        label='Create Ticket',
        style=discord.ButtonStyle.primary,
        custom_id='create_ticket',
    )
    async def create_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button['TicketPanelView'],
    ) -> None:
        guild = interaction.guild
        # A component in a guild channel always carries a Member, never a
        # bare User - the isinstance check just narrows the type for mypy.
        if guild is None or not isinstance(interaction.user, discord.Member):
            return

        category = guild.get_channel(self._tickets_category_id)
        if not isinstance(category, discord.CategoryChannel):
            logger.warning(
                'tickets category %s not found or not a category', self._tickets_category_id
            )
            await interaction.response.send_message(
                'Ticket creation is not available right now.', ephemeral=True
            )
            return

        moderator_role = guild.get_role(self._moderator_role_id)
        overwrites: dict[_OverwriteKey, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        if moderator_role is not None:
            overwrites[moderator_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True
            )

        async with self._lock:
            channel = await category.create_text_channel(
                name=f'ticket-{_next_ticket_number(category)}',
                overwrites=overwrites,
            )

        await channel.send(_TICKET_WELCOME)
        await interaction.response.send_message(f'Your ticket: {channel.mention}', ephemeral=True)


def _next_ticket_number(category: discord.CategoryChannel) -> int:
    numbers = [
        int(match.group(1))
        for existing in category.channels
        if (match := _TICKET_NAME_RE.match(existing.name))
    ]
    return max(numbers, default=0) + 1


class TicketPanel:
    """Owns the panel message in the support channel and its button."""

    def __init__(
        self,
        support_channel_id: str,
        tickets_category_id: str,
        moderator_role_id: str,
        client: commands.Bot,
    ) -> None:
        self._client = client
        self._support_channel_id = int(support_channel_id)
        self._view = TicketPanelView(int(tickets_category_id), int(moderator_role_id))

        client.add_view(self._view)
        client.add_listener(self._on_ready, 'on_ready')

    async def _on_ready(self) -> None:
        """Post the panel message once - skip if it's already there from a previous run."""
        channel = self._client.get_channel(self._support_channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                'support channel %s not found or not a text channel', self._support_channel_id
            )
            return

        async for message in channel.history(limit=None):
            if message.author == self._client.user:
                return

        await channel.send(_PANEL_MESSAGE, view=self._view)
