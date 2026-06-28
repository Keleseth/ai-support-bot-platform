"""
Abstract base class defining the contract for all messaging platform adapters.

Why ABC over Protocol: we want explicit inheritance enforcement.
Every new platform integration must subclass PlatformAdapter and implement
all three methods - structural duck typing alone is not sufficient here.
"""

from abc import ABC, abstractmethod

from support_platform.core.models import IncomingMessage, OutgoingMessage


class PlatformAdapter(ABC):
    """Base class for all platform-specific adapters (Discord, Telegram, etc.)."""

    @abstractmethod
    async def start(self) -> None:
        """Connect to the platform and begin listening for incoming messages."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Disconnect from the platform cleanly."""
        ...

    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> None:
        """Deliver a reply to the channel specified in OutgoingMessage."""
        ...
