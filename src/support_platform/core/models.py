"""
Platform-agnostic data models shared across the entire application.

These dataclasses form the common language of the pipeline.
No model here may import from platforms or llm sub-packages.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Intent(Enum):
    """
    Customer intent as classified by LLM call #1.

    Only BUY_PRODUCT and ORDER_FOLLOWUP trigger a bot response.
    OTHER means the bot stays silent.
    """

    BUY_PRODUCT = 'buy_product'        # customer wants to purchase via PayPal
    ORDER_FOLLOWUP = 'order_followup'  # customer following up on existing order
    OTHER = 'other'                    # bot takes no action


@dataclass
class Attachment:
    """A file or image attached to a message, to be forwarded to the LLM."""

    url: str
    content_type: str  # MIME type, e.g. "image/png"


@dataclass
class IncomingMessage:
    """Платформо-независимое представление входящего сообщения."""

    channel_id: str
    author_id: str
    content: str
    timestamp: datetime
    is_staff: bool
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class OutgoingMessage:
    """Platform-agnostic reply to be delivered via the platform adapter."""

    channel_id: str
    content: str


@dataclass
class ChatMessage:
    """A single turn in an LLM conversation."""

    role: str    # "system" | "user" | "assistant"
    content: str


@dataclass
class CustomerData:
    """Customer information retrieved from lookup repositories."""

    invoice_id: str | None = None
    email: str | None = None
    order_status: str | None = None


@dataclass
class TicketContext:
    """
    Mutable context object that carries all state through the pipeline.

    Enriched at each stage:
      1. messages       - full burst from TicketDebouncer (all messages in window)
      2. intent         - set by TicketProcessor after LLM call #1
      3. customer_data  - set by TicketProcessor after repository lookup
      4. response       - set by TicketProcessor after LLM call #2

    Processor concatenates all messages before sending to the LLM.
    """

    messages: list[IncomingMessage]
    intent: Intent | None = None
    customer_data: CustomerData | None = None
    response: str | None = None
