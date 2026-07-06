"""
Composition root - the only place the application gets assembled.

Reads BOT_PLATFORM and LLM_PROVIDER from settings and wires up the matching
implementations. No other module makes that decision.
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
    Log to both the console (visible in docker compose up) and a file,
    so history survives a scrolled-back terminal.
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
    """Build the LLM client for the configured LLM_PROVIDER."""
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
    Build the platform adapter and the order records source.

    BOT_PLATFORM (chat) and ORDER_RECORDS_BACKEND (orders) are independent
    settings, resolved separately (_build_platform_adapter,
    _build_order_records_source). The one exception is when both point to
    Discord: then a single shared connection is built (build_discord_pair)
    instead of opening two bots against the same server.

    Async because the order records source opens a Postgres connection pool
    (see platforms/discord/factory.py) - that is I/O.

    main.py never imports discord or concrete classes directly, only
    factory functions from the relevant packages.
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
    """Build the platform adapter for BOT_PLATFORM, independent of order records."""
    if settings.bot_platform == BotPlatform.DISCORD:
        from support_platform.platforms.discord.factory import build_discord_adapter

        return build_discord_adapter(settings, message_handler=message_handler)

    raise ValueError(f'Unsupported platform: {settings.bot_platform}')


async def _build_order_records_source() -> BaseOrderRecordsSource:
    """Build the order records source for ORDER_RECORDS_BACKEND, independent of chat."""
    if settings.order_records_backend == OrderRecordsBackend.DISCORD:
        from support_platform.platforms.discord.factory import build_discord_order_records

        return await build_discord_order_records(settings)

    raise ValueError(f'Unsupported order records backend: {settings.order_records_backend}')


async def main() -> None:
    """Entry point: assemble the components and start the adapter."""
    _configure_logging()

    async def _on_ticket_ready(messages: list[IncomingMessage]) -> None:
        """
        Called by the debouncer once the customer goes quiet: builds a
        TicketContext, runs it through the processor, sends the reply.

        processor and adapter are resolved through the closure - Python
        looks up the name when the function runs, not when it's defined,
        and both are already built below by the time the debouncer calls this.
        """
        context = TicketContext(messages=messages)
        context = await processor.process(context)

        if context.response:
            await adapter.send_message(
                OutgoingMessage(
                    channel_id=messages[0].channel_id,
                    content=context.response,
                )
            )

    debouncer = TicketDebouncer(settings, on_ready=_on_ticket_ready)
    adapter, order_records = await build_platform_components(message_handler=debouncer.handle)
    processor = TicketProcessor(llm=build_llm(), order_records=order_records)
    await adapter.start()


if __name__ == '__main__':
    asyncio.run(main())
