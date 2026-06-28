"""
Discord implementation of PlatformAdapter.

Responsibilities:
  - Connect to Discord using discord.py
  - Convert discord.Message events into platform-agnostic IncomingMessage
    (including image attachments for Claude API forwarding)
  - Send replies via channel.send()

Wired in main.py; nothing outside this package knows it's Discord.

Full implementation: Milestone 2.
"""

from support_platform.config import Settings
from support_platform.core.models import OutgoingMessage
from support_platform.platforms.base import PlatformAdapter


class DiscordAdapter(PlatformAdapter):
    """PlatformAdapter implementation for Discord. Instantiated in main.py."""

    def __init__(self, settings: Settings) -> None:
        self._token = settings.discord_token

    async def start(self) -> None:
        """Connect to Discord and start the event loop. Implemented in Milestone 2."""
        raise NotImplementedError

    async def stop(self) -> None:
        """Disconnect from Discord cleanly. Implemented in Milestone 2."""
        raise NotImplementedError

    async def send_message(self, message: OutgoingMessage) -> None:
        """Send a reply to a Discord channel. Implemented in Milestone 2."""
        raise NotImplementedError
