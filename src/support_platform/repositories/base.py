"""
Abstract base for repository lookup services.

Defines the minimal interface that TicketProcessor depends on.
Concrete implementations (Discord channel search, PostgreSQL, API) live in sibling modules.
"""

from abc import ABC, abstractmethod

from support_platform.core.models import CustomerData, IncomingMessage


class BaseRepository(ABC):
    """Common interface for customer data lookup services."""

    @abstractmethod
    async def lookup(self, message: IncomingMessage) -> CustomerData:
        """Retrieve customer data relevant to the given message."""
        ...
