"""
Application configuration via pydantic-settings.

All settings are read from environment variables (or .env file) at startup.
Add new settings here; never read os.environ directly elsewhere in the codebase.
"""

from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class BotPlatform(StrEnum):
    DISCORD = 'discord'


class OrderRecordsBackend(StrEnum):
    """
    Откуда репозиторий заказов берёт данные - независимо от BOT_PLATFORM.
    Сейчас единственное значение - тот же Discord-канал, но выбор явный
    (а не выведен из BOT_PLATFORM), чтобы Milestone 6 (Postgres) не требовал
    менять эту логику, только добавить новое значение и реализацию.
    """

    DISCORD = 'discord'


class LLMProvider(StrEnum):
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
    # id категории с тикет-каналами клиентов, не имя - разные категории
    # на сервере могут называться одинаково, id всегда уникален.
    tickets_category_id: str

    # Order records (Milestone 5)
    # Откуда брать данные о заказах - независимо от bot_platform (см. OrderRecordsBackend).
    order_records_backend: OrderRecordsBackend = OrderRecordsBackend.DISCORD
    # id канала, где хранятся записи о заказах (один пост = один заказ).
    # Это НЕ категория тикетов - конкретный, заранее созданный канал.
    # Нужен, только если order_records_backend=discord.
    order_records_channel_id: str
    # PayPal-реквизиты магазина, отдаются клиенту при intent=BUY_PRODUCT.
    store_paypal_email: str

    # Postgres-хранилище заказов (Milestone 6). Отдельными полями, а не одним
    # DATABASE_URL - удобнее прокидывать в docker-compose (каждая переменная
    # это отдельный env у сервиса backend, без сборки строки в двух местах).
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str

    # Future integrations
    redis_url: str | None = None

    @property
    def database_url(self) -> str:
        """DSN для asyncpg, собранный из отдельных DB_* настроек."""
        return (
            f'postgresql://{self.db_user}:{self.db_password}'
            f'@{self.db_host}:{self.db_port}/{self.db_name}'
        )


settings = Settings()
