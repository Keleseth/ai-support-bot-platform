"""
Application configuration via pydantic-settings.

All settings are read from environment variables (or .env file) at startup.
Add new settings here; never read os.environ directly elsewhere in the codebase.
"""

from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotPlatform(str, Enum):
    DISCORD = 'discord'


class LLMProvider(str, Enum):
    ANTHROPIC = 'anthropic'
    OPENAI_COMPATIBLE = 'openai_compatible'  # xAI Grok, standard OpenAI, etc.


class Settings(BaseSettings):
    """Central application configuration. Populated from .env or environment variables."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
    )

    # Platform
    bot_platform: BotPlatform = BotPlatform.DISCORD

    # Discord
    discord_token: str

    # LLM
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC
    llm_api_key: str
    llm_base_url: str | None = None  # required only for openai_compatible providers
    llm_model: str = 'claude-sonnet-4-6'

    # Ticket behaviour
    ticket_debounce_seconds: int = 150
    ticket_category_names: list[str] = ['uncategorized', 'orders']

    # Future integrations
    database_url: str | None = None
    redis_url: str | None = None


settings = Settings()
