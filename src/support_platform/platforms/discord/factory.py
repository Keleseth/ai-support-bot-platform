"""
Assembly point for the Discord subsystem.

The only place that knows both that Discord needs a commands.Bot rather
than a plain discord.Client (see _build_client), and that DiscordAdapter
and DiscordOrderRecordsSource are independent implementations unaware of
each other - unless BOT_PLATFORM and ORDER_RECORDS_BACKEND are both
discord, in which case they share one client instead of opening two
connections to the same server.

main.py never imports discord.py directly: it calls one of the functions
below and gets back abstractions (PlatformAdapter, BaseOrderRecordsSource).
Since bot_platform and order_records_backend are independent settings,
build_discord_adapter() and build_discord_order_records() each work
standalone, building their own client if none is passed - needed when the
choice diverges, e.g. chat on Discord but orders read from elsewhere.
build_discord_pair() is the "both are Discord" case: it just hands both
the same client instead of each opening its own connection.

build_discord_order_records() (and build_discord_pair()) are async because
they open the asyncpg pool and apply the schema (db/pool.py) before
constructing DiscordOrderRecordsSource - Postgres is an implementation
detail of that source, not something the rest of the app deals with.
"""

from collections.abc import Awaitable, Callable

import discord
from discord.ext import commands

from support_platform.config import Settings
from support_platform.core.models import IncomingMessage
from support_platform.db.order_store import PostgresOrderRecordsStore
from support_platform.db.pool import create_pool, init_schema
from support_platform.platforms.base import PlatformAdapter
from support_platform.platforms.discord.adapter import DiscordAdapter
from support_platform.platforms.discord.order_records import DiscordOrderRecordsSource
from support_platform.repositories.order_source import BaseOrderRecordsSource


def _build_client() -> commands.Bot:
    """
    Build a bare client with the required intents. Registers no handlers -
    callers attach their own via add_listener.

    commands.Bot, not a plain discord.Client: a plain Client allows only
    one handler per event (client.event() overwrites the previous one).
    add_listener supports several independent handlers on the same event,
    which is what DiscordAdapter and DiscordOrderRecordsSource need when
    both are listening on the same client.
    """
    # message_content is a privileged intent - without it, message.content
    # is empty. Enable it in the Discord Developer Portal under
    # Bot -> Privileged Gateway Intents.
    intents = discord.Intents.default()
    intents.message_content = True

    client = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

    # commands.Bot.on_message tries to parse a command prefix out of every
    # message by default. This project has no commands, so this no-op
    # handler replaces that behavior and avoids the resulting
    # CommandNotFound noise in the logs.
    async def on_message(message: discord.Message) -> None:
        pass

    client.event(on_message)
    return client


def build_discord_adapter(
    settings: Settings,
    message_handler: Callable[[IncomingMessage], Awaitable[None]],
    client: commands.Bot | None = None,
) -> PlatformAdapter:
    """
    Discord chat on its own.

    client is only passed when build_discord_pair created it; a standalone
    call (BOT_PLATFORM=discord but orders on another backend) builds its
    own client, used by nothing else.
    """
    if client is None:
        client = _build_client()
    return DiscordAdapter(settings, message_handler=message_handler, client=client)


async def build_discord_order_records(
    settings: Settings,
    client: commands.Bot | None = None,
) -> BaseOrderRecordsSource:
    """
    Discord order records on their own, symmetric to build_discord_adapter.

    client is only passed when build_discord_pair created it; a standalone
    call (orders on Discord but chat elsewhere) builds its own.
    """
    if client is None:
        client = _build_client()

    pool = await create_pool(settings)
    await init_schema(pool)
    store = PostgresOrderRecordsStore(pool)

    return DiscordOrderRecordsSource(settings.order_records_channel_id, client=client, store=store)


async def build_discord_pair(
    settings: Settings,
    message_handler: Callable[[IncomingMessage], Awaitable[None]],
) -> tuple[PlatformAdapter, BaseOrderRecordsSource]:
    """
    Both chat and order records on Discord: one shared client instead of two connections.

    Creation order between order_records and adapter doesn't matter - both
    only register handlers via add_listener, nothing sends or reads until
    adapter.start() is called in main.py.
    """
    client = _build_client()
    order_records = await build_discord_order_records(settings, client=client)
    adapter = build_discord_adapter(settings, message_handler=message_handler, client=client)
    return adapter, order_records
