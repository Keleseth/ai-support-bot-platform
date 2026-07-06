"""
Shared pytest fixtures and test doubles available to all tests without explicit import.
"""

import os

# config.py создаёт Settings() на уровне модуля при импорте - любой тест,
# который тянет за собой support_platform.config (напрямую или транзитивно
# через debouncer/adapter), упадёт без валидных значений обязательных полей.
# setdefault - не перетирает реальный .env, если он есть, но тесты не должны
# от него зависеть.
os.environ.setdefault('DISCORD_TOKEN', 'test-token')
os.environ.setdefault('LLM_API_KEY', 'test-key')
os.environ.setdefault('TICKETS_CATEGORY_ID', '1000')
os.environ.setdefault('ORDER_RECORDS_CHANNEL_ID', '2000')
os.environ.setdefault('STORE_PAYPAL_EMAIL', 'store@example.com')
os.environ.setdefault('DB_NAME', 'test')
os.environ.setdefault('DB_USER', 'test')
os.environ.setdefault('DB_PASSWORD', 'test')

from datetime import UTC, datetime

from support_platform.core.models import Attachment, IncomingMessage
from support_platform.llm.base import BaseLLM
from support_platform.repositories.order_source import BaseOrderRecordsSource, OrderRecord


class FakeLLM(BaseLLM):
    """
    Скриптованный LLM: отдаёт заранее заданные ответы по очереди, один
    per вызов complete(). Хранит все полученные messages - тесты могут
    проверить, что именно ушло в LLM, а не только результат.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self._responses.pop(0)


class FakeOrderRecordsSource(BaseOrderRecordsSource):
    """
    In-memory фейк репозитория заказов. Ключи словарей - точные строки
    (без нормализации регистра/пробелов - это ответственность реального
    PostgresOrderRecordsStore, не тестируется здесь). Считает вызовы
    каждого метода - тесты процессора проверяют, что лукап идёт в нужном
    порядке (order_id раньше email) и не делается лишний раз.
    """

    def __init__(
        self,
        by_order_id: dict[str, OrderRecord] | None = None,
        by_email: dict[str, OrderRecord] | None = None,
    ) -> None:
        self._by_order_id = by_order_id or {}
        self._by_email = by_email or {}
        self.order_id_calls: list[str] = []
        self.email_calls: list[str] = []

    async def find_by_order_id(self, order_id: str) -> OrderRecord | None:
        self.order_id_calls.append(order_id)
        return self._by_order_id.get(order_id)

    async def find_by_email(self, email: str) -> OrderRecord | None:
        self.email_calls.append(email)
        return self._by_email.get(email)


def make_incoming_message(
    content: str,
    *,
    channel_id: str = 'channel-1',
    author_id: str = 'author-1',
    is_staff: bool = False,
    attachments: list[Attachment] | None = None,
) -> IncomingMessage:
    """Фабрика IncomingMessage с разумными дефолтами - тестам обычно важен только content."""
    return IncomingMessage(
        channel_id=channel_id,
        author_id=author_id,
        content=content,
        timestamp=datetime.now(UTC),
        is_staff=is_staff,
        attachments=attachments or [],
    )
