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

from support_platform.core.models import CustomerData, IncomingMessage, Intent, TicketContext
from support_platform.llm.base import BaseLLM
from support_platform.llm.prompts import build_intent_messages, build_response_messages, parse_intent

logger = logging.getLogger(__name__)


class TicketProcessor:
    """
    Оркестратор пайплайна.

    Принимает TicketContext, последовательно обогащает его:
    intent -> customer_data -> response.
    """

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

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

        context.customer_data = self._lookup_customer(context.messages)
        context.response = await self._generate_response(context.messages, context.customer_data)
        logger.info('[процессор] response=%r', context.response)

        return context

    async def _detect_intent(self, messages: list[IncomingMessage]) -> Intent:
        """LLM вызов #1: определить намерение клиента."""
        raw = await self._llm.complete(build_intent_messages(messages))
        return parse_intent(raw)

    def _lookup_customer(self, messages: list[IncomingMessage]) -> CustomerData:
        """
        Заглушка поиска данных клиента.
        Milestone 5: заменить на вызов Repository по author_id / тексту сообщений.
        """
        return CustomerData()

    async def _generate_response(
        self,
        messages: list[IncomingMessage],
        customer_data: CustomerData,
    ) -> str:
        """LLM вызов #2: сгенерировать ответ с учётом намерения и данных клиента."""
        return await self._llm.complete(build_response_messages(messages, customer_data))
