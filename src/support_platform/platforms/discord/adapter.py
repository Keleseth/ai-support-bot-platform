"""
Discord implementation of PlatformAdapter.

Responsibilities:
  - Filter incoming messages by the channel's category
  - Convert discord.Message into IncomingMessage, the platform-agnostic type
  - Hand IncomingMessage off to the external message_handler (TicketDebouncer)
  - Send replies through TextChannel.send()

Knows nothing about order records (DiscordOrderRecordsSource) - that is a
separate, independent component. Both share one discord.Client (created and
handed out by platforms/discord/factory.py), but each registers its own
handlers via add_listener without referencing the other.

Used only from main.py, through platforms/discord/factory.py, behind the
PlatformAdapter abstraction - the rest of the application doesn't know
Discord is underneath.
"""

import logging
from collections.abc import Awaitable, Callable

import discord
from discord.ext import commands

from support_platform.config import Settings
from support_platform.core.models import Attachment, IncomingMessage, OutgoingMessage
from support_platform.platforms.base import PlatformAdapter

logger = logging.getLogger(__name__)


class DiscordAdapter(PlatformAdapter):
    """
    PlatformAdapter implementation for Discord.

    Takes an already-built client instead of creating its own, since it may
    need to share one with DiscordOrderRecordsSource. Only commands.Bot
    supports add_listener (several independent handlers per event) - a plain
    discord.Client allows just one handler per event, which would let either
    component silently overwrite the other's.
    """

    def __init__(
        self,
        settings: Settings,
        message_handler: Callable[[IncomingMessage], Awaitable[None]],
        client: commands.Bot,
    ) -> None:
        self._token = settings.discord_token
        self._message_handler = message_handler
        self._client = client

        # Category id, not name: two categories on the same server can share
        # a name, but ids are always unique.
        self._tickets_category_id = int(settings.tickets_category_id)

        client.add_listener(self._on_ready, 'on_ready')
        client.add_listener(self._handle_message, 'on_message')

    async def _on_ready(self) -> None:
        logger.info(
            'logged in as %s (id=%s)',
            self._client.user,
            self._client.user.id if self._client.user else '?',
        )

    async def start(self) -> None:
        await self._client.start(self._token)

    async def stop(self) -> None:
        await self._client.close()

    async def send_message(self, message: OutgoingMessage) -> None:
        # get_channel reads from the client's local cache, no extra API call
        channel = self._client.get_channel(int(message.channel_id))

        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                'send_message: channel %s not found or not a TextChannel',
                message.channel_id,
            )
            return

        await channel.send(message.content)

    # ------------------------------------------------------------------
    # Internal - not part of the PlatformAdapter interface
    # ------------------------------------------------------------------

    async def _handle_message(self, message: discord.Message) -> None:
        # Ignore the bot's own messages, otherwise it would reply to itself
        if message.author == self._client.user:
            return

        if not self._is_monitored(message):
            return
        incoming = self._to_incoming_message(message)
        logger.info(
            'channel=%s author=%s text=%r',
            incoming.channel_id,
            incoming.author_id,
            incoming.content,
        )

        await self._message_handler(incoming)

    def _is_monitored(self, message: discord.Message) -> bool:
        """True if the message is in a text channel under the configured tickets category."""
        if not isinstance(message.channel, discord.TextChannel):
            return False

        # Channels with no category have category=None
        if message.channel.category is None:
            return False

        return message.channel.category.id == self._tickets_category_id

    def _to_incoming_message(self, message: discord.Message) -> IncomingMessage:
        attachments = [
            # content_type is None for some file formats, hence the fallback
            Attachment(url=a.url, content_type=a.content_type or 'application/octet-stream')
            for a in message.attachments
        ]

        return IncomingMessage(
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
            content=message.content,
            timestamp=message.created_at,
            is_staff=False,  # TODO: derive from the author's server roles
            attachments=attachments,
        )
