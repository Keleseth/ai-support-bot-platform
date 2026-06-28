"""
Order status lookup service.

Searches a designated Discord channel for order status by invoice ID or email.

Implementation: Milestone 5.
"""

from support_platform.core.models import CustomerData, IncomingMessage
from support_platform.repositories.base import BaseRepository


class OrderStatusLookup(BaseRepository):
    """Finds order status from the Discord data channel."""

    async def lookup(self, message: IncomingMessage) -> CustomerData:
        """Search for order status matching the customer. Implemented in Milestone 5."""
        raise NotImplementedError
