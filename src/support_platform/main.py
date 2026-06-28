"""
Composition Root - the single place where the application is assembled.

Reads BOT_PLATFORM and LLM_PROVIDER from settings and wires the correct
implementations together. No other module in the codebase makes this decision.
"""

import asyncio

from support_platform.config import BotPlatform, LLMProvider, settings
from support_platform.llm.base import BaseLLM
from support_platform.platforms.base import PlatformAdapter


def build_llm() -> BaseLLM:
    """Create the LLM client selected by LLM_PROVIDER in settings."""
    if settings.llm_provider == LLMProvider.ANTHROPIC:
        from support_platform.llm.anthropic_client import AnthropicLLM

        return AnthropicLLM(settings)

    if settings.llm_provider == LLMProvider.OPENAI_COMPATIBLE:
        from support_platform.llm.openai_client import OpenAICompatibleLLM

        return OpenAICompatibleLLM(settings)

    raise ValueError(f'Unsupported LLM provider: {settings.llm_provider}')


def build_adapter() -> PlatformAdapter:
    """Create the platform adapter selected by BOT_PLATFORM in settings."""
    if settings.bot_platform == BotPlatform.DISCORD:
        from support_platform.platforms.discord.adapter import DiscordAdapter

        return DiscordAdapter(settings)

    raise ValueError(f'Unsupported platform: {settings.bot_platform}')


async def main() -> None:
    """Application entry point."""
    adapter = build_adapter()
    await adapter.start()


if __name__ == '__main__':
    asyncio.run(main())
