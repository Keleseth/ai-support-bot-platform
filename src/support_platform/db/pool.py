"""
Creates the asyncpg connection pool and applies the initial schema.

Separate from order_store.py: the pool is a shared resource for the whole
app (future tables would reuse it), while order_store.py is CRUD specific
to orders.
"""

import asyncpg

from support_platform.config import Settings

# CREATE TABLE/INDEX IF NOT EXISTS instead of a migration tool - fine for a
# single simple table, applied on every startup.
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
    return await asyncpg.create_pool(dsn=settings.database_url)


async def init_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)
