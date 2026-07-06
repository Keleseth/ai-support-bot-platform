"""
Application configuration via pydantic-settings.

All settings are read from environment variables or a .env file at startup.
Add new settings here; never read os.environ directly anywhere else.
"""

from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotPlatform(StrEnum):
    DISCORD = 'discord'


class OrderRecordsBackend(StrEnum):
    """
    Where order records come from, independent of BOT_PLATFORM.
    Only one value exists today (the same Discord channel), but the choice
    is explicit so a second backend can be added later without changing
    what this setting means.
    """

    DISCORD = 'discord'


class LLMProvider(StrEnum):
    ANTHROPIC = 'anthropic'
    OPENAI_COMPATIBLE = 'openai_compatible'  # xAI Grok, standard OpenAI, etc.


class Settings(BaseSettings):
    """Central application configuration, populated from .env or environment variables."""

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
    # Category id, not name - two categories on the same server can share a
    # name, but ids are always unique.
    tickets_category_id: str

    # Order records
    order_records_backend: OrderRecordsBackend = OrderRecordsBackend.DISCORD
    # Channel id holding order records (one post = one order). Not the ticket
    # category - a specific, pre-created channel. Only used when
    # order_records_backend is discord.
    order_records_channel_id: str
    # Store's PayPal address, sent to the customer on intent=BUY_PRODUCT.
    store_paypal_email: str

    # Ticket panel: a "Create Ticket" button posted once in a support channel.
    # Channel id where the panel message lives.
    support_channel_id: str
    # Role id granted access to every new ticket channel, alongside its creator.
    moderator_role_id: str

    # Postgres. Separate fields rather than one DATABASE_URL - easier to wire
    # into docker-compose as individual env vars per service.
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str

    @property
    def database_url(self) -> str:
        """asyncpg DSN assembled from the individual DB_* settings."""
        return (
            f'postgresql://{self.db_user}:{self.db_password}'
            f'@{self.db_host}:{self.db_port}/{self.db_name}'
        )


settings = Settings()
