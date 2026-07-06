"""
Абстракция источника данных о заказах.

Repositories (например будущий OrderLookup) зависят ТОЛЬКО от этого
интерфейса, а не от конкретного backend'а (сейчас - Discord-канал,
в будущем - Postgres, Milestone 6). Тот же принцип, что уже применён
в проекте для BaseLLM и PlatformAdapter: конкретную реализацию
выбирает и создаёт Composition Root (main.py), а не сам репозиторий.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OrderRecord:
    """
    Одна запись о заказе - результат поиска.

    Платформо-независимый: неважно, откуда взялась запись
    (Discord-канал сейчас, БД потом) - поля одни и те же.
    """

    order_id: str
    email: str
    status: str


class BaseOrderRecordsSource(ABC):
    """
    Умеет искать заказ по order_id или email. Не знает, откуда берутся данные.

    Методы async: реализация может ходить в БД или внешний API (сетевой I/O),
    и это не должно блокировать event loop. Абстракция - только чтение;
    запись/синхронизация данных (если она вообще нужна конкретному backend'у,
    как Discord-реализации) - деталь реализации, не часть этого контракта.
    """

    @abstractmethod
    async def find_by_order_id(self, order_id: str) -> OrderRecord | None:
        """Найти заказ по id. None, если не найден."""
        ...

    @abstractmethod
    async def find_by_email(self, email: str) -> OrderRecord | None:
        """Найти заказ по email. None, если не найден."""
        ...
