"""
CRUD над таблицей order_records - персистентное хранилище заказов.

Ничего не знает про Discord: ключ записи (message_id) для этого класса -
просто уникальный идентификатор строки, откуда он взялся - не его забота.
Используется как зависимость внутри DiscordOrderRecordsSource
(platforms/discord/order_records.py), но сам класс - не реализация
BaseOrderRecordsSource и не часть публичного пайплайна.
"""

import asyncpg

from support_platform.repositories.order_source import OrderRecord


class PostgresOrderRecordsStore:
    """Хранилище заказов поверх Postgres. Один message_id - одна запись."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(self, message_id: int, record: OrderRecord) -> None:
        """Создать запись или обновить существующую (по message_id)."""
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
        """Удалить запись. Не ошибка, если такого message_id уже нет."""
        async with self._pool.acquire() as conn:
            await conn.execute('DELETE FROM order_records WHERE message_id = $1', message_id)

    async def get_by_order_id(self, order_id: str) -> OrderRecord | None:
        """Найти заказ по id. None, если не найден."""
        async with self._pool.acquire() as conn:
            # ORDER BY message_id - на случай дублей (стафф ошибся и указал
            # один order_id в двух постах) детерминированно берём самый старый,
            # как и раньше при переборе dict в порядке вставки.
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
        """Найти заказ по email. Сравнение регистронезависимое."""
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
    """Смэппить строку asyncpg в OrderRecord. None, если строки нет."""
    if row is None:
        return None
    return OrderRecord(order_id=row['order_id'], email=row['email'], status=row['status'])
