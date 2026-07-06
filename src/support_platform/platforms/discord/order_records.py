"""
Order records source: a Discord channel where each message is one order, e.g.
    "Заказ: id 5 | email: example@mail.ru - в пути"

One post = one order. The format is whatever the staff typed manually in
the channel, so the parser regex below is written specifically for it.

Responsibilities:
  - parse a single message into an OrderRecord (order_id, email, status)
  - listen to Discord gateway events (new message / edit / delete) and pass
    the result to PostgresOrderRecordsStore - this class stores nothing itself
  - keep the store in sync without rereading the channel history on every
    message, since Discord already tells us which message changed

Why the key is message_id, not order_id:
  message_id never changes for an existing message. order_id is text a
  staff member typed and can edit by mistake (fixing a typo). If order_id
  were the key, that edit would leave an orphaned record under the old id.
  Lookup by order_id/email is a linear scan over the store's values - a
  small shop has few orders and lookups are rare (once per ticket), so the
  O(n) scan is not a concern.

Independence from DiscordAdapter:
  This class must never import DiscordAdapter. Both need the same client
  (one Discord connection per process) but share it as equal subscribers:
  each registers its own handlers via client.add_listener(...), a
  commands.Bot method built for several independent listeners on one event
  (unlike plain discord.Client, which allows only one handler per event).
  platforms/discord/factory.py is the only place that knows about both
  classes at once.
"""

import logging
import re

import discord
from discord.ext import commands

from support_platform.db.order_store import PostgresOrderRecordsStore
from support_platform.repositories.order_source import BaseOrderRecordsSource, OrderRecord

logger = logging.getLogger(__name__)

# Matches lines like "Заказ: id 5 | email: example@mail.ru - в пути".
#   - "заказ" and the colon after it are case-insensitive, colon optional
#   - whitespace between parts is flexible
#   - email is "anything non-whitespace" - no format validation, we just
#     copy whatever staff wrote in the channel
#   - status is everything after " - " to the end of the line
_ORDER_LINE_RE = re.compile(
    r'заказ:?\s*id\s*(?P<order_id>\d+)\s*\|\s*email:\s*(?P<email>\S+)\s*-\s*(?P<status>.+)',
    re.IGNORECASE,
)


class DiscordOrderRecordsSource(BaseOrderRecordsSource):
    """
    Listens to the order records channel and keeps PostgresOrderRecordsStore in sync.

    Built once in the composition root (main.py, via
    platforms/discord/factory.py) with an already-built client (commands.Bot
    - see factory.py for why not a plain discord.Client) and store (see
    db/order_store.py). Registers its own event handlers via add_listener -
    callers don't need to know this class listens to Discord events at all.
    The rest of the app (repositories, TicketProcessor) only sees the
    BaseOrderRecordsSource interface; the store is an implementation detail
    hidden from them.
    """

    def __init__(
        self,
        channel_id: str,
        client: commands.Bot,
        store: PostgresOrderRecordsStore,
    ) -> None:
        # Stored as int - the type discord.py uses in events
        # (message.channel.id, payload.channel_id)
        self._channel_id = int(channel_id)
        self._client = client
        self._store = store

        # add_listener, rather than overriding on_ready/on_message in a
        # subclass, lets a second independent listener (DiscordAdapter)
        # attach to the same client.
        client.add_listener(self._on_ready, 'on_ready')
        client.add_listener(self._on_message, 'on_message')
        client.add_listener(self._on_raw_message_edit, 'on_raw_message_edit')
        client.add_listener(self._on_raw_message_delete, 'on_raw_message_delete')

    async def _on_ready(self) -> None:
        """
        Fires once the client has connected and logged in.

        Reads the whole channel history once - before this point,
        client.get_channel() finds nothing, since discord.py's channel
        cache only fills in after connecting. After startup, the store
        stays in sync through events (_on_message/_on_raw_message_edit/
        _on_raw_message_delete), so history() never runs again. Records
        are simply upserted with the same values if they already exist
        from a previous run.
        """
        channel = self._client.get_channel(self._channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                'channel %s not found or not a text channel - order lookup will not work',
                self._channel_id,
            )
            return

        # limit=None removes the default 100-message cap - every record is
        # needed, not just the most recent ones
        count = 0
        async for message in channel.history(limit=None):
            await self._ingest(message.id, message.content)
            count += 1

        logger.info('processed %d channel messages on startup', count)

    async def _on_message(self, message: discord.Message) -> None:
        """
        Fires on every message the bot can see (a fan-out listener -
        DiscordAdapter gets the same message through its own handler).
        Filters by channel itself; nothing else does that for it.
        """
        if message.channel.id != self._channel_id:
            return
        await self._ingest(message.id, message.content)

    async def _on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        """
        Fires when any message on the server is edited.

        Raw, not the plain on_message_edit: the plain version only fires if
        the old message is already in discord.py's internal cache, which has
        a size limit and no guarantee of holding older messages. The raw
        version always fires regardless of that cache - missing an order
        status edit is not an option here.
        """
        if payload.channel_id != self._channel_id:
            return

        # payload.data is the raw JSON from the Discord API - 'content' is
        # present only when the message text itself changed (not, say, when
        # a reaction was added)
        content = payload.data.get('content')
        if content is None:
            return

        await self._ingest(payload.message_id, content)

    async def _on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """Fires when any message on the server is deleted. Raw for the same reason as edits."""
        if payload.channel_id != self._channel_id:
            return
        await self._store.delete(payload.message_id)

    async def find_by_order_id(self, order_id: str) -> OrderRecord | None:
        return await self._store.get_by_order_id(order_id)

    async def find_by_email(self, email: str) -> OrderRecord | None:
        return await self._store.get_by_email(email)

    async def _ingest(self, message_id: int, content: str) -> None:
        record = self._parse(content)
        if record is None:
            logger.warning(
                'message %s does not match the order record format: %r',
                message_id,
                content,
            )
            return
        await self._store.save(message_id, record)

    def _parse(self, content: str) -> OrderRecord | None:
        """Parse one channel line into an OrderRecord. None if the format doesn't match."""
        match = _ORDER_LINE_RE.search(content)
        if match is None:
            return None
        return OrderRecord(
            order_id=match.group('order_id'),
            email=match.group('email'),
            status=match.group('status').strip(),
        )
