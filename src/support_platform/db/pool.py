"""
Создание пула соединений asyncpg и первичная схема БД.

Отдельно от order_store.py: пул - общий ресурс на всё приложение
(если позже появятся другие таблицы, они будут использовать тот же пул),
а order_store.py - CRUD конкретно над заказами.
"""

import asyncpg

from support_platform.config import Settings

# CREATE TABLE/INDEX IF NOT EXISTS - без Alembic, для одной простой таблицы
# учебного проекта достаточно применять схему при каждом старте.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS order_records (
    message_id BIGINT PRIMARY KEY,
    order_id TEXT NOT NULL,
    email TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_order_records_order_id ON order_records (order_id);
CREATE INDEX IF NOT EXISTS idx_order_records_email ON order_records (email);
"""


async def create_pool(settings: Settings) -> asyncpg.Pool:
    """Открыть пул соединений с БД, указанной в DATABASE_URL."""
    return await asyncpg.create_pool(dsn=settings.database_url)


async def init_schema(pool: asyncpg.Pool) -> None:
    """Создать таблицу заказов и индексы, если их ещё нет."""
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)
