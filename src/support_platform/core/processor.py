"""
TicketProcessor orchestrates the ticket pipeline.

Detects intent (LLM call #1), looks up the customer's order if the intent
warrants it, then generates a reply informed by both (LLM call #2). Knows
nothing about Discord, Telegram, or which provider sits behind BaseLLM -
the LLM client and the order records repository are both injected.
"""

import logging
import re

from support_platform.core.models import CustomerData, IncomingMessage, Intent, TicketContext
from support_platform.llm.base import BaseLLM
from support_platform.llm.prompts import (
    build_intent_messages,
    build_response_messages,
    parse_intent,
)
from support_platform.repositories.order_source import BaseOrderRecordsSource, OrderRecord

logger = logging.getLogger(__name__)

# Order number in free-form customer text: a number near a trigger word
# ('заказ', 'order', '№', '#'). \D{0,10} allows a short run of non-digit
# text between the trigger and the number ('заказ номер 32', 'order #32').
_ORDER_ID_RE = re.compile(r'(?:заказ\w*|order|№|#)\D{0,10}(\d+)', re.IGNORECASE)
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')


class TicketProcessor:
    """Enriches a TicketContext in order: intent -> customer_data -> response."""

    def __init__(self, llm: BaseLLM, order_records: BaseOrderRecordsSource) -> None:
        self._llm = llm
        self._order_records = order_records

    async def process(self, context: TicketContext) -> TicketContext:
        """Run the pipeline. Intent.OTHER leaves response as None - the bot stays silent."""
        context.intent = await self._detect_intent(context.messages)
        logger.info('channel=%s intent=%s', context.messages[0].channel_id, context.intent)

        if context.intent == Intent.OTHER:
            return context

        context.customer_data = await self._lookup_customer(context.messages)
        context.response = await self._generate_response(context.messages, context.customer_data)
        logger.info('response=%r', context.response)

        return context

    async def _detect_intent(self, messages: list[IncomingMessage]) -> Intent:
        raw = await self._llm.complete(build_intent_messages(messages))
        return parse_intent(raw)

    async def _lookup_customer(self, messages: list[IncomingMessage]) -> CustomerData:
        """
        Look up the order by the number or email mentioned in the customer's text.

        Order number is checked first, since it is a more exact match, email
        second. Falls back to an empty CustomerData if neither is mentioned
        or the lookup finds nothing - the LLM will ask the customer to
        clarify instead of failing.
        """
        text = '\n'.join(m.content for m in messages)

        order_id_match = _ORDER_ID_RE.search(text)
        if order_id_match:
            record = await self._order_records.find_by_order_id(order_id_match.group(1))
            if record:
                return _to_customer_data(record)

        email_match = _EMAIL_RE.search(text)
        if email_match:
            record = await self._order_records.find_by_email(email_match.group(0))
            if record:
                return _to_customer_data(record)

        return CustomerData()

    async def _generate_response(
        self,
        messages: list[IncomingMessage],
        customer_data: CustomerData,
    ) -> str:
        return await self._llm.complete(build_response_messages(messages, customer_data))


def _to_customer_data(record: OrderRecord) -> CustomerData:
    return CustomerData(
        order_id=record.order_id,
        email=record.email,
        order_status=record.status,
    )
