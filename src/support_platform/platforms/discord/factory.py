"""
Точка сборки Discord-подсистемы.

Единственное место в проекте, которое одновременно знает:
  - что для Discord нужен именно commands.Bot (класс из discord.py,
    подробнее почему не голый discord.Client - см. _build_client),
  - что DiscordAdapter и DiscordOrderRecordsSource - это две отдельные,
    ничего друг о друге не знающие реализации,
  - что если обе выбраны как Discord (BOT_PLATFORM=discord и
    ORDER_RECORDS_BACKEND=discord одновременно), им обоим стоит отдать
    ОДИН и тот же client, а не открывать два соединения с одним сервером.

main.py про discord.py не знает и не импортирует его напрямую - только
вызывает одну из трёх функций ниже и получает наружу абстракции
(PlatformAdapter, BaseOrderRecordsSource). bot_platform и
order_records_backend - независимые настройки: build_discord_adapter()
и build_discord_order_records() каждая умеет работать сама по себе
(создаёт свой client, если его не передали) - это нужно, когда выбор
разъехался (например BOT_PLATFORM=discord, но ORDER_RECORDS_BACKEND=postgres).
build_discord_pair() - частный случай "оба - Discord", просто передаёт
обеим один и тот же client вместо того, чтобы каждая создавала свой.

build_discord_order_records() (и, соответственно, build_discord_pair())
асинхронные: им нужно поднять пул asyncpg и применить схему БД
(db/pool.py) прежде чем создать DiscordOrderRecordsSource - это тоже
часть "знания про Discord-заказы", раз хранилище сейчас его внутренняя
деталь (см. db/order_store.py).
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
    Создать пустой client с нужными intents. Ничего не подключает
    и не регистрирует - вызывающий код сам вешает на него обработчики.

    commands.Bot, а не голый discord.Client: обычному Client'у можно назначить
    только ОДИН обработчик на событие (client.event() делает setattr и
    перезаписывает предыдущий). add_listener из discord.ext.commands умеет
    держать список обработчиков на одно и то же событие - это и нужно, чтобы
    DiscordAdapter и DiscordOrderRecordsSource (если оба на Discord) слушали
    один client, не зная друг о друге.
    """
    # Intents - явная подписка на типы событий Discord.
    # message_content - "privileged intent": без него поле content у сообщений
    # будет пустым (нужно и тикетам, и парсеру записей о заказах).
    # Включить в Discord Developer Portal -> Bot -> Privileged Gateway Intents.
    intents = discord.Intents.default()
    intents.message_content = True

    client = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

    # По умолчанию commands.Bot.on_message сам пытается распарсить префикс-команду
    # из текста. Команд в проекте нет ни одной, поэтому глушим эту логику -
    # иначе на каждое сообщение шёл бы лишний разбор и потенциальный
    # CommandNotFound в логах библиотеки.
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
    Discord-чат сам по себе.

    client передаётся только когда его создал build_discord_pair (см. ниже);
    при самостоятельном вызове (BOT_PLATFORM=discord, но заказы - не Discord)
    создаёт свой собственный, единственный потребитель которого - этот адаптер.
    """
    if client is None:
        client = _build_client()
    return DiscordAdapter(settings, message_handler=message_handler, client=client)


async def build_discord_order_records(
    settings: Settings,
    client: commands.Bot | None = None,
) -> BaseOrderRecordsSource:
    """
    Discord-заказы сами по себе - симметрично build_discord_adapter.

    client передаётся только когда его создал build_discord_pair; при
    самостоятельном вызове (заказы - Discord, а чат - другая платформа)
    создаёт свой собственный client.
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
    Оба - Discord: один client на двоих вместо двух отдельных соединений.

    Порядок создания order_records/adapter не важен - оба только
    регистрируют обработчики на client (add_listener), ничего не
    отправляют и не читают до вызова adapter.start() в main.py.
    """
    client = _build_client()
    order_records = await build_discord_order_records(settings, client=client)
    adapter = build_discord_adapter(settings, message_handler=message_handler, client=client)
    return adapter, order_records
