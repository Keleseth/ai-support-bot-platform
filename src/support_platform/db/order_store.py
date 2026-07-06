"""
CRUD over the order_records table - persistent storage for orders.

Knows nothing about Discord: message_id is just a unique row key to this
class, where it came from is not its concern. Used as a dependency inside
DiscordOrderRecordsSource (platforms/discord/order_records.py), but this
class is not itself a BaseOrderRecordsSource implementation or part of the
public pipeline.
"""

import asyncpg

from support_platform.repositories.order_source import OrderRecord


class PostgresOrderRecordsStore:
    """Order storage on top of Postgres. One message_id maps to one record."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(self, message_id: int, record: OrderRecord) -> None:
        """Insert a new record or update the existing one for this message_id."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO order_records (message_id, order_id, email, status)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (message_id) DO UPDATE SET
                    order_id = EXCLUDED.order_id,
                    email = EXCLUDED.email,
                    status = EXCLUDED.status
                """,
                message_id,
                record.order_id,
                record.email,
                record.status,
            )

    async def delete(self, message_id: int) -> None:
        """Delete a record. Not an error if message_id doesn't exist."""
        async with self._pool.acquire() as conn:
            await conn.execute('DELETE FROM order_records WHERE message_id = $1', message_id)

    async def get_by_order_id(self, order_id: str) -> OrderRecord | None:
        """Look up an order by id. None if not found."""
        async with self._pool.acquire() as conn:
            # ORDER BY message_id: if staff duplicated an order_id across
            # two posts by mistake, deterministically pick the oldest one.
            row = await conn.fetchrow(
                """
                SELECT order_id, email, status FROM order_records
                WHERE order_id = $1
                ORDER BY message_id ASC
                LIMIT 1
                """,
                order_id,
            )
        return _to_record(row)

    async def get_by_email(self, email: str) -> OrderRecord | None:
        """Look up an order by email, case-insensitive."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT order_id, email, status FROM order_records
                WHERE lower(email) = lower($1)
                ORDER BY message_id ASC
                LIMIT 1
                """,
                email.strip(),
            )
        return _to_record(row)


def _to_record(row: asyncpg.Record | None) -> OrderRecord | None:
    if row is None:
        return None
    return OrderRecord(order_id=row['order_id'], email=row['email'], status=row['status'])
