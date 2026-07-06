"""
Composition Root - единственное место где приложение собирается.

Читает BOT_PLATFORM и LLM_PROVIDER из settings и соединяет нужные реализации.
Никакой другой модуль не принимает это решение.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from support_platform.config import BotPlatform, LLMProvider, OrderRecordsBackend, settings
from support_platform.core.debouncer import TicketDebouncer
from support_platform.core.models import IncomingMessage, OutgoingMessage, TicketContext
from support_platform.core.processor import TicketProcessor
from support_platform.llm.base import BaseLLM
from support_platform.platforms.base import PlatformAdapter
from support_platform.repositories.order_source import BaseOrderRecordsSource

logger = logging.getLogger(__name__)

_LOG_DIR = Path(__file__).resolve().parent / 'logs'


def _configure_logging() -> None:
    """
    И в консоль (видно прямо в терминале docker compose up), и в файл
    (support_platform/logs/app.log - история для ручных тестов, не пропадает
    вместе со скроллбеком терминала).
    """
    _LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(_LOG_DIR / 'app.log', encoding='utf-8'),
        ],
    )


def build_llm() -> BaseLLM:
    """Создать LLM-клиент согласно LLM_PROVIDER из settings."""
    if settings.llm_provider == LLMProvider.ANTHROPIC:
        from support_platform.llm.anthropic_client import AnthropicLLM

        return AnthropicLLM(settings)

    if settings.llm_provider == LLMProvider.OPENAI_COMPATIBLE:
        from support_platform.llm.openai_client import OpenAICompatibleLLM

        return OpenAICompatibleLLM(settings)

    raise ValueError(f'Unsupported LLM provider: {settings.llm_provider}')


async def build_platform_components(
    message_handler: Callable[[IncomingMessage], Awaitable[None]],
) -> tuple[PlatformAdapter, BaseOrderRecordsSource]:
    """
    Создать адаптер платформы и источник данных о заказах.

    BOT_PLATFORM (чат) и ORDER_RECORDS_BACKEND (заказы) - независимые
    настройки, выбираются и резолвятся по отдельности (_build_platform_adapter,
    _build_order_records_source). Единственное исключение - если обе указывают
    на Discord: тогда вместо двух независимых соединений создаётся одно общее
    (build_discord_pair), чтобы не открывать двух ботов на один сервер.

    Асинхронная: источник заказов поднимает пул соединений с Postgres
    (см. platforms/discord/factory.py), это I/O.

    main.py не импортирует ни discord, ни конкретные классы напрямую -
    только фабричные функции нужных пакетов.
    """
    both_discord = (
        settings.bot_platform == BotPlatform.DISCORD
        and settings.order_records_backend == OrderRecordsBackend.DISCORD
    )
    if both_discord:
        from support_platform.platforms.discord.factory import build_discord_pair

        return await build_discord_pair(settings, message_handler=message_handler)

    return _build_platform_adapter(message_handler), await _build_order_records_source()


def _build_platform_adapter(
    message_handler: Callable[[IncomingMessage], Awaitable[None]],
) -> PlatformAdapter:
    """Создать адаптер платформы согласно BOT_PLATFORM (вне связки с заказами)."""
    if settings.bot_platform == BotPlatform.DISCORD:
        from support_platform.platforms.discord.factory import build_discord_adapter

        return build_discord_adapter(settings, message_handler=message_handler)

    raise ValueError(f'Unsupported platform: {settings.bot_platform}')


async def _build_order_records_source() -> BaseOrderRecordsSource:
    """Создать источник данных о заказах согласно ORDER_RECORDS_BACKEND (вне связки с чатом)."""
    if settings.order_records_backend == OrderRecordsBackend.DISCORD:
        from support_platform.platforms.discord.factory import build_discord_order_records

        return await build_discord_order_records(settings)

    raise ValueError(f'Unsupported order records backend: {settings.order_records_backend}')


async def main() -> None:
    """Точка входа: собрать компоненты и запустить адаптер."""
    _configure_logging()

    async def _on_ticket_ready(messages: list[IncomingMessage]) -> None:
        """
        Вызывается дебаунсером когда клиент замолчал.
        Создаёт TicketContext, прогоняет через процессор, отправляет ответ.

        processor и adapter доступны через замыкание: Python ищет переменную
        в момент вызова функции, не в момент её определения. К тому моменту,
        как дебаунсер реально вызовет этот колбэк, обе уже созданы ниже.
        """
        context = TicketContext(messages=messages)
        context = await processor.process(context)

        if context.response:
            await adapter.send_message(OutgoingMessage(
                channel_id=messages[0].channel_id,
                content=context.response,
            ))

    debouncer = TicketDebouncer(settings, on_ready=_on_ticket_ready)
    adapter, order_records = await build_platform_components(message_handler=debouncer.handle)
    processor = TicketProcessor(llm=build_llm(), order_records=order_records)
    await adapter.start()


if __name__ == '__main__':
    asyncio.run(main())
