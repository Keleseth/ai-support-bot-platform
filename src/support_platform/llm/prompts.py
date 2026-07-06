"""
Prompt templates and message assembly for the LLM calls.

Builds the system prompts, turns domain objects into the
list[dict[str, str]] shape the LLM providers expect, and parses the raw
intent response back into an Intent. This is the one place that knows both
the LLM message format and the domain objects (IncomingMessage,
CustomerData) - TicketProcessor calls these functions rather than building
message dicts itself.
"""

import logging

from support_platform.core.models import CustomerData, IncomingMessage, Intent

logger = logging.getLogger(__name__)

# Strict format: only the constant name, no extra words - keeps parse_intent
# a plain lookup instead of a small parser.
_INTENT_SYSTEM = """\
You are a customer support intent classifier for an online store.

Classify the customer's message into exactly one of:
- BUY_PRODUCT     — customer wants to buy something, asks about price, payment, or PayPal
- ORDER_FOLLOWUP  — customer asks about an existing order, delivery, tracking, or status
- OTHER           — anything else: greetings, thanks, saying they will come back later,
                    closing the conversation, unclear or off-topic messages

When in doubt, choose OTHER.
Respond with ONLY one of the intents name. Example: ORDER_FOLLOWUP"""

_RESPONSE_SYSTEM = """\
You are a customer support assistant for an online store.
Your job is to help customers with two things only:
1. Questions about existing orders (status, delivery, tracking). Orders are looked up strictly by:
Order ID -> email attached to the order.
2. Buying products via PayPal

Rules:
- Reply in the same language the customer used
- Be brief and friendly - one short paragraph maximum
- Ask only for information you actually need to help (order number OR email)
- Do not ask follow-up questions if the customer is clearly closing the conversation
- Do not mention that you are an AI
- For purchases, use only the PayPal address given below, if any - never invent one"""


def build_intent_messages(messages: list[IncomingMessage]) -> list[dict[str, str]]:
    """Join all customer messages into one block so the LLM sees the full batch's context."""
    customer_text = '\n'.join(m.content for m in messages)
    return [
        {'role': 'system', 'content': _INTENT_SYSTEM},
        {'role': 'user', 'content': customer_text},
    ]


def parse_intent(llm_response: str) -> Intent:
    """Parse the LLM's raw intent text, falling back to OTHER on anything unexpected."""
    normalized = llm_response.strip().upper()
    try:
        return Intent[normalized]
    except KeyError:
        logger.warning('unrecognized intent from LLM: %r', llm_response)
        return Intent.OTHER


def build_response_messages(
    messages: list[IncomingMessage],
    customer_data: CustomerData | None,
    store_paypal_email: str | None = None,
) -> list[dict[str, str]]:
    """
    Build the response prompt.

    Appends customer_data when present. store_paypal_email is only passed by
    the caller for intent=BUY_PRODUCT - it has no place in an order-status
    reply, so this function doesn't gate on intent itself, it just includes
    whatever it's given.
    """
    customer_text = '\n'.join(m.content for m in messages)
    user_content = f'Customer messages:\n{customer_text}'

    if customer_data:
        lines = []
        if customer_data.order_id:
            lines.append(f'Order ID: {customer_data.order_id}')
        if customer_data.email:
            lines.append(f'Email: {customer_data.email}')
        if customer_data.order_status:
            lines.append(f'Order status: {customer_data.order_status}')
        if lines:
            user_content += '\n\nCustomer data:\n' + '\n'.join(lines)

    if store_paypal_email:
        user_content += f'\n\nStore PayPal address: {store_paypal_email}'

    return [
        {'role': 'system', 'content': _RESPONSE_SYSTEM},
        {'role': 'user', 'content': user_content},
    ]
