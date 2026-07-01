"""
Шаблоны промптов и сборка сообщений для LLM-вызовов.

Ответственности:
  - системные промпты для каждого типа вызова (intent / response)
  - сборка list[dict[str, str]] из доменных объектов Core
  - парсинг текстового ответа LLM обратно в доменный тип Intent

Это единственное место где знают и про формат LLM API (роли),
и про доменные объекты (IncomingMessage, CustomerData).
TicketProcessor вызывает функции отсюда, сам не строит dict'ы.
"""

import logging

from support_platform.core.models import CustomerData, IncomingMessage, Intent

logger = logging.getLogger(__name__)

# Строгий формат: только имя константы, без пояснений.
# Это упрощает parse_intent - не нужен сложный парсер.
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
- Do not mention that you are an AI"""


def build_intent_messages(messages: list[IncomingMessage]) -> list[dict[str, str]]:
    """
    Сформировать список сообщений для LLM-вызова определения намерения.
    Все сообщения клиента объединяются в один блок - сохраняем контекст пакета.
    """
    customer_text = '\n'.join(m.content for m in messages)
    return [
        {'role': 'system', 'content': _INTENT_SYSTEM},
        {'role': 'user', 'content': customer_text},
    ]


def parse_intent(llm_response: str) -> Intent:
    """
    Разобрать текстовый ответ LLM в значение Intent.
    LLM может добавить пробелы или регистр - нормализуем.
    При неизвестном значении возвращаем OTHER.
    """
    normalized = llm_response.strip().upper()
    try:
        return Intent[normalized]
    except KeyError:
        logger.warning('[промпт] неизвестный интент от LLM: %r', llm_response)
        return Intent.OTHER


def build_response_messages(
    messages: list[IncomingMessage],
    customer_data: CustomerData | None,
) -> list[dict[str, str]]:
    """
    Сформировать список сообщений для LLM-вызова генерации ответа.
    Данные клиента из репозитория добавляются в user-сообщение если есть.
    """
    customer_text = '\n'.join(m.content for m in messages)
    user_content = f'Customer messages:\n{customer_text}'

    if customer_data:
        lines = []
        if customer_data.invoice_id:
            lines.append(f'Invoice ID: {customer_data.invoice_id}')
        if customer_data.email:
            lines.append(f'Email: {customer_data.email}')
        if customer_data.order_status:
            lines.append(f'Order status: {customer_data.order_status}')
        if lines:
            user_content += '\n\nCustomer data:\n' + '\n'.join(lines)

    return [
        {'role': 'system', 'content': _RESPONSE_SYSTEM},
        {'role': 'user', 'content': user_content},
    ]
