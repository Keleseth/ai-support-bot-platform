"""
Email lookup service.

Searches a designated Discord channel for a customer email address.

Implementation: Milestone 5.
"""

from support_platform.core.models import CustomerData, IncomingMessage
from support_platform.repositories.base import BaseRepository


class EmailLookup(BaseRepository):
    """Finds a customer's email from the Discord data channel."""

    async def lookup(self, message: IncomingMessage) -> CustomerData:
        """Search for an email matching the customer. Implemented in Milestone 5."""
        raise NotImplementedError
