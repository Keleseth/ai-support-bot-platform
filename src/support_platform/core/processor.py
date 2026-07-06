"""
TicketProcessor - оркестратор пайплайна обработки тикета.

Ответственности:
  1. Определить намерение клиента (LLM вызов #1)
  2. Найти данные клиента в репозитории по намерению (Milestone 5)
  3. Сгенерировать ответ с учётом намерения и данных клиента (LLM вызов #2)
  4. Вернуть заполненный TicketContext

Не знает о Discord, Telegram или конкретном LLM-провайдере.
BaseLLM и prompts инжектируются снаружи.
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

# Номер заказа в свободном тексте клиента: число рядом со словом-триггером
# ("заказ", "order", "№", "#"). \D{0,10} - между триггером и числом допускаем
# короткий кусок нецифрового текста ("заказ номер 32", "order #32").
_ORDER_ID_RE = re.compile(r'(?:заказ\w*|order|№|#)\D{0,10}(\d+)', re.IGNORECASE)
_EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')


class TicketProcessor:
    """
    Оркестратор пайплайна.

    Принимает TicketContext, последовательно обогащает его:
    intent -> customer_data -> response.
    """

    def __init__(self, llm: BaseLLM, order_records: BaseOrderRecordsSource) -> None:
        self._llm = llm
        self._order_records = order_records

    async def process(self, context: TicketContext) -> TicketContext:
        """
        Запустить пайплайн для тикета.
        Возвращает context с заполненными intent, customer_data, response.
        Intent.OTHER - response остаётся None, бот молчит.
        """
        context.intent = await self._detect_intent(context.messages)
        logger.info(
            '[процессор] channel=%s intent=%s',
            context.messages[0].channel_id,
            context.intent,
        )

        if context.intent == Intent.OTHER:
            return context

        context.customer_data = await self._lookup_customer(context.messages)
        context.response = await self._generate_response(context.messages, context.customer_data)
        logger.info('[процессор] response=%r', context.response)

        return context

    async def _detect_intent(self, messages: list[IncomingMessage]) -> Intent:
        """LLM вызов #1: определить намерение клиента."""
        raw = await self._llm.complete(build_intent_messages(messages))
        return parse_intent(raw)

    async def _lookup_customer(self, messages: list[IncomingMessage]) -> CustomerData:
        """
        Найти заказ по номеру или email, упомянутым в тексте клиента.

        Порядок - сначала номер заказа (точнее совпадение), потом email.
        Если ни то, ни другое не упомянуто или заказ не нашёлся - пустой
        CustomerData: LLM сам попросит клиента уточнить данные (см. _RESPONSE_SYSTEM).
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
        """LLM вызов #2: сгенерировать ответ с учётом намерения и данных клиента."""
        return await self._llm.complete(build_response_messages(messages, customer_data))


def _to_customer_data(record: OrderRecord) -> CustomerData:
    """Смэппить запись репозитория (OrderRecord) в доменный CustomerData для промпта."""
    return CustomerData(
        order_id=record.order_id,
        email=record.email,
        order_status=record.status,
    )
