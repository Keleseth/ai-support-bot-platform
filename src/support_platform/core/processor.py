"""
TicketProcessor - оркестратор пайплайна обработки тикета.

Ответственности:
  1. Определить намерение клиента (LLM вызов #1)
  2. Найти данные клиента в репозитории по намерению
  3. Сгенерировать ответ (LLM вызов #2)
  4. Вернуть заполненный TicketContext

Не знает о Discord, Telegram или любой конкретной LLM.
Обе зависимости инжектируются снаружи.

Milestone 3: _detect_intent и _lookup_customer - заглушки с хардкодом.
Milestone 4: в __init__ добавится llm: BaseLLM, заглушки заменятся на вызовы LLM.
Milestone 5: в __init__ добавится repository, _lookup_customer обратится к БД.
"""

import logging

from support_platform.core.models import (
    CustomerData,
    IncomingMessage,
    Intent,
    TicketContext,
)

logger = logging.getLogger(__name__)

# Хардкод-ответы для Milestone 3.
# Milestone 4: удалить, ответ будет генерировать LLM.
_STUB_RESPONSES: dict[Intent, str] = {
    Intent.ORDER_FOLLOWUP: (
        'Спасибо за обращение! Уточните номер заказа, '
        'и мы проверим его статус в ближайшее время.'
    ),
    Intent.BUY_PRODUCT: (
        'Благодарим за интерес! Напишите какой товар вас интересует, '
        'наш менеджер поможет оформить заказ через PayPal.'
    ),
}


class TicketProcessor:
    """
    Оркестратор пайплайна.

    Принимает TicketContext, последовательно обогащает его:
    intent -> customer_data -> response.

    Milestone 3: без LLM, всё хардкод.
    """

    async def process(self, context: TicketContext) -> TicketContext:
        """
        Запустить пайплайн для тикета.
        Возвращает context с заполненными intent, customer_data, response.
        Intent.OTHER - response остаётся None, бот молчит.
        """
        context.intent = self._detect_intent(context.messages)
        logger.info(
            '[процессор] channel=%s intent=%s',
            context.messages[0].channel_id,
            context.intent,
        )

        if context.intent == Intent.OTHER:
            return context

        context.customer_data = self._lookup_customer(context.messages)
        context.response = _STUB_RESPONSES.get(context.intent)
        logger.info('[процессор] response=%r', context.response)

        return context

    def _detect_intent(self, messages: list[IncomingMessage]) -> Intent:
        """
        Заглушка определения намерения по ключевым словам.
        Milestone 4: заменить на BaseLLM.complete() с системным промптом.
        """
        text = ' '.join(m.content.lower() for m in messages)

        if any(w in text for w in ('купить', 'buy', 'paypal', 'оплат', 'цена', 'price')):
            return Intent.BUY_PRODUCT

        if any(w in text for w in ('заказ', 'order', 'доставк', 'статус', 'трекинг')):
            return Intent.ORDER_FOLLOWUP

        # Дефолт для тестов - в Milestone 4 LLM вернёт OTHER если не ясно
        return Intent.ORDER_FOLLOWUP

    def _lookup_customer(self, messages: list[IncomingMessage]) -> CustomerData:
        """
        Заглушка поиска данных клиента.
        Milestone 5: заменить на вызов Repository по author_id / тексту сообщений.
        """
        return CustomerData()
