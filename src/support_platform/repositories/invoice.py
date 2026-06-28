"""
Invoice lookup service.

Searches a designated Discord channel for an invoice ID
matching the customer's message context.

Implementation: Milestone 5.
"""

from support_platform.core.models import CustomerData, IncomingMessage
from support_platform.repositories.base import BaseRepository


class InvoiceLookup(BaseRepository):
    """Finds a customer's invoice ID from the Discord data channel."""

    async def lookup(self, message: IncomingMessage) -> CustomerData:
        """Search for an invoice matching the customer. Implemented in Milestone 5."""
        raise NotImplementedError
