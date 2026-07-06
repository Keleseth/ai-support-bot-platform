"""
Abstraction for the order records data source.

Repositories depend only on this interface, never on a concrete backend
(currently a Discord channel). Same principle already used for BaseLLM and
PlatformAdapter: the composition root (main.py) chooses and builds the
concrete implementation, not the repository itself.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OrderRecord:
    """
    One order record, as returned by a lookup.

    Platform-agnostic - the fields are the same regardless of where the
    record came from (a Discord channel today, possibly a database later).
    """

    order_id: str
    email: str
    status: str


class BaseOrderRecordsSource(ABC):
    """
    Looks up an order by id or email. Knows nothing about where the data lives.

    Methods are async because an implementation may hit a database or an
    external API - I/O that must not block the event loop. The abstraction
    is read-only; writing or syncing data, if a given backend even needs
    that (as the Discord implementation does), is outside this contract.
    """

    @abstractmethod
    async def find_by_order_id(self, order_id: str) -> OrderRecord | None:
        """Look up an order by id. None if not found."""
        ...

    @abstractmethod
    async def find_by_email(self, email: str) -> OrderRecord | None:
        """Look up an order by email. None if not found."""
        ...
