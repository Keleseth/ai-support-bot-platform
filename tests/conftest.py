"""
Shared pytest fixtures and test doubles available to all tests without explicit import.
"""

import os

# config.py creates Settings() at module level on import, so any test that
# pulls in support_platform.config (directly or transitively, e.g. through
# the debouncer or the adapter) fails without valid required fields.
# setdefault won't override a real .env if one is present, but tests
# shouldn't depend on it existing.
os.environ.setdefault('DISCORD_TOKEN', 'test-token')
os.environ.setdefault('LLM_API_KEY', 'test-key')
os.environ.setdefault('TICKETS_CATEGORY_ID', '1000')
os.environ.setdefault('ORDER_RECORDS_CHANNEL_ID', '2000')
os.environ.setdefault('STORE_PAYPAL_EMAIL', 'store@example.com')
os.environ.setdefault('SUPPORT_CHANNEL_ID', '3000')
os.environ.setdefault('MODERATOR_ROLE_ID', '4000')
os.environ.setdefault('DB_NAME', 'test')
os.environ.setdefault('DB_USER', 'test')
os.environ.setdefault('DB_PASSWORD', 'test')

from datetime import UTC, datetime

from support_platform.core.models import Attachment, IncomingMessage
from support_platform.llm.base import BaseLLM
from support_platform.repositories.order_source import BaseOrderRecordsSource, OrderRecord


class FakeLLM(BaseLLM):
    """
    Scripted LLM: returns queued responses in order, one per call to
    complete(). Records every messages payload it received, so a test can
    assert on what was actually sent, not just the final result.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return self._responses.pop(0)


class FakeOrderRecordsSource(BaseOrderRecordsSource):
    """
    In-memory order records fake. Dict keys are matched exactly - case and
    whitespace normalization is PostgresOrderRecordsStore's job, not tested
    here. Tracks every call so processor tests can assert the lookup order
    (order_id before email) and that no redundant lookup happens.
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
    """IncomingMessage factory with sane defaults - tests usually only care about content."""
    return IncomingMessage(
        channel_id=channel_id,
        author_id=author_id,
        content=content,
        timestamp=datetime.now(UTC),
        is_staff=is_staff,
        attachments=attachments or [],
    )
