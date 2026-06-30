"""
TicketDebouncer - задерживает обработку пока клиент не перестанет печатать.

Почему дебаунс: клиенты часто отправляют несколько коротких сообщений подряд.
Без дебаунса бот ответил бы на каждое неполное сообщение.
С дебаунсом - ждёт тишины TICKET_DEBOUNCE_SECONDS, потом передаёт пакет в обработчик.

Агрегация сообщений: накапливаем ВСЕ сообщения пользователя за debounce-окно
и передаём единым list[IncomingMessage]. Критично: клиент часто разбивает мысль
на несколько сообщений - order_id может быть в первом, суть вопроса в пятом.
Процессор получает полную картину, а не только последнее сообщение.

Хранение: один словарь _states: dict[tuple[str,str], ConversationState].
ConversationState группирует task + messages + last_message_at.
Таск хранит только таймер - при его отмене сообщения остаются в state.messages.
Словарь очищается когда таймер сработал (on_ready вызван) или стафф/бот ответил.

Ключ: (channel_id, author_id).
Причина: если в тикет-канале несколько обычных пользователей, каждый получает
независимый таймер - сообщения одного не сбрасывают таймер другого.
Текущая схема 'один тикет = один клиент' также работает корректно.

Масштабирование: in-memory достаточно для Discord-бота на одном инстансе.
При шардинге Discord гарантирует что события одного канала всегда идут в один шард.
Redis нужен в этом проекте для кеша репозитория (Milestone 5), не для дебаунсера.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from support_platform.config import Settings
from support_platform.core.models import IncomingMessage

logger = logging.getLogger(__name__)


@dataclass
class ConversationState:
    """
    Состояние одного активного разговора.

    Создаётся при первом сообщении клиента.
    Удаляется когда on_ready вызван или когда стафф/бот ответил в канале.
    """

    task: asyncio.Task[None]
    last_message_at: datetime
    messages: list[IncomingMessage] = field(default_factory=list)


class TicketDebouncer:
    """
    Планировщик дебаунса с накоплением сообщений для каждой пары (канал, автор).
    Создаётся один экземпляр на всё приложение в main.py.
    """

    def __init__(
        self,
        settings: Settings,
        on_ready: Callable[[list[IncomingMessage]], Awaitable[None]],
    ) -> None:
        self._delay = settings.ticket_debounce_seconds
        self._on_ready = on_ready
        self._states: dict[tuple[str, str], ConversationState] = {}

    async def handle(self, message: IncomingMessage) -> None:
        """
        Принять входящее сообщение.

        Стафф -> закрыть все активные разговоры канала.
        Клиент -> добавить сообщение в разговор и сбросить таймер.
        """
        if message.is_staff:
            self._cancel_channel(message.channel_id)
            return

        key = (message.channel_id, message.author_id)

        if key in self._states:
            state = self._states[key]
            state.task.cancel()
            state.messages.append(message)
            state.last_message_at = message.timestamp
            state.task = asyncio.create_task(self._delayed_fire(key))
        else:
            task = asyncio.create_task(self._delayed_fire(key))
            self._states[key] = ConversationState(
                task=task,
                last_message_at=message.timestamp,
                messages=[message],
            )

        logger.debug(
            '[дебаунс] сброс таймера channel=%s author=%s накоплено=%d delay=%.1fs',
            message.channel_id,
            message.author_id,
            len(self._states[key].messages),
            self._delay,
        )

    def _cancel_channel(self, channel_id: str) -> None:
        """Закрыть все активные разговоры канала (стафф/бот ответил)."""
        keys = [k for k in self._states if k[0] == channel_id]
        for key in keys:
            self._states[key].task.cancel()
            del self._states[key]
        if keys:
            logger.debug('[дебаунс] стафф ответил, закрыто разговоров: %d', len(keys))

    async def _delayed_fire(self, key: tuple[str, str]) -> None:
        """
        Ждёт delay секунд, затем забирает накопленные сообщения и вызывает on_ready.

        Проверка task-identity в finally нужна из-за того что asyncio.cancel
        не выполняется мгновенно: finally отменённого старого таска может сработать
        уже после того как state.task обновлён на новый таск. Без проверки старый таск
        мог бы удалить ConversationState которое уже принадлежит новому таску.
        """
        try:
            await asyncio.sleep(self._delay)
            state = self._states.pop(key, None)
            if state and state.messages:
                logger.info(
                    '[дебаунс] таймер истёк channel=%s author=%s сообщений=%d',
                    key[0],
                    key[1],
                    len(state.messages),
                )
                await self._on_ready(state.messages)
        except asyncio.CancelledError:
            pass
        finally:
            current = self._states.get(key)
            if current is not None and current.task is asyncio.current_task():
                del self._states[key]
