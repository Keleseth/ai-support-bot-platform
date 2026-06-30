"""
Composition Root - единственное место где приложение собирается.

Читает BOT_PLATFORM и LLM_PROVIDER из settings и соединяет нужные реализации.
Никакой другой модуль не принимает это решение.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from support_platform.config import BotPlatform, LLMProvider, settings
from support_platform.core.debouncer import TicketDebouncer
from support_platform.core.models import IncomingMessage, OutgoingMessage, TicketContext
from support_platform.core.processor import TicketProcessor
from support_platform.llm.base import BaseLLM
from support_platform.platforms.base import PlatformAdapter

logger = logging.getLogger(__name__)


def build_llm() -> BaseLLM:
    """Создать LLM-клиент согласно LLM_PROVIDER из settings."""
    if settings.llm_provider == LLMProvider.ANTHROPIC:
        from support_platform.llm.anthropic_client import AnthropicLLM

        return AnthropicLLM(settings)

    if settings.llm_provider == LLMProvider.OPENAI_COMPATIBLE:
        from support_platform.llm.openai_client import OpenAICompatibleLLM

        return OpenAICompatibleLLM(settings)

    raise ValueError(f'Unsupported LLM provider: {settings.llm_provider}')


def build_adapter(
    message_handler: Callable[[IncomingMessage], Awaitable[None]],
) -> PlatformAdapter:
    """Создать адаптер платформы согласно BOT_PLATFORM из settings."""
    if settings.bot_platform == BotPlatform.DISCORD:
        from support_platform.platforms.discord.adapter import DiscordAdapter

        return DiscordAdapter(settings, message_handler=message_handler)

    raise ValueError(f'Unsupported platform: {settings.bot_platform}')


async def main() -> None:
    """Точка входа: собрать компоненты и запустить адаптер."""
    processor = TicketProcessor()

    async def _on_ticket_ready(messages: list[IncomingMessage]) -> None:
        """
        Вызывается дебаунсером когда клиент замолчал.
        Создаёт TicketContext, прогоняет через процессор, отправляет ответ.

        adapter доступен через замыкание: Python ищет переменную в момент вызова
        функции, не в момент её определения. К тому моменту adapter уже создан.
        """
        context = TicketContext(messages=messages)
        context = await processor.process(context)

        if context.response:
            await adapter.send_message(OutgoingMessage(
                channel_id=messages[0].channel_id,
                content=context.response,
            ))

    debouncer = TicketDebouncer(settings, on_ready=_on_ticket_ready)
    adapter = build_adapter(message_handler=debouncer.handle)
    await adapter.start()


if __name__ == '__main__':
    asyncio.run(main())
