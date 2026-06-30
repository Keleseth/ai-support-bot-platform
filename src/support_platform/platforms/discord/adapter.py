"""
Discord реализация PlatformAdapter.

Ответственности:
  - Подключиться к Discord через discord.py
  - Фильтровать входящие сообщения по категории канала
  - Конвертировать discord.Message -> IncomingMessage (платформо-независимый объект)
  - Передавать IncomingMessage во внешний message_handler (TicketDebouncer)
  - Отправлять ответы через TextChannel.send()

Используется только в main.py через абстракцию PlatformAdapter.
Всё остальное приложение не знает, что под ним Discord.
"""

import logging
from collections.abc import Awaitable, Callable

import discord

from support_platform.config import Settings
from support_platform.core.models import Attachment, IncomingMessage, OutgoingMessage
from support_platform.platforms.base import PlatformAdapter

logger = logging.getLogger(__name__)


class _BotClient(discord.Client):
    """
    Внутренний discord.py клиент. Скрыт за DiscordAdapter.

    Почему подкласс, а не @client.event:
      discord.py ожидает обработчики событий как методы Client.
      Подкласс - стандартный способ их зарегистрировать без декораторов.
      Внешний код видит только DiscordAdapter, этот класс - деталь реализации.
    """

    def __init__(self, adapter: 'DiscordAdapter', *, intents: discord.Intents) -> None:
        super().__init__(intents=intents)
        # Ссылка на адаптер нужна, чтобы вызывать его методы из обработчиков событий
        self._adapter = adapter

    async def on_ready(self) -> None:
        """Срабатывает когда бот успешно подключился и авторизовался."""
        logger.info('Бот подключён как %s (id=%s)', self.user, self.user.id if self.user else '?')

    async def on_message(self, message: discord.Message) -> None:
        """Срабатывает при каждом новом сообщении в доступных боту каналах."""
        await self._adapter._handle_message(message)


class DiscordAdapter(PlatformAdapter):
    """
    Реализация PlatformAdapter для Discord.

    Получает Settings в конструкторе - единственная точка,
    где адаптер узнаёт токен и список категорий из .env.
    """

    def __init__(
        self,
        settings: Settings,
        message_handler: Callable[[IncomingMessage], Awaitable[None]],
    ) -> None:
        self._token = settings.discord_token
        self._message_handler = message_handler

        # frozenset для O(1) поиска; lowercase один раз здесь, не при каждом сообщении
        self._monitored_categories: frozenset[str] = frozenset(
            name.lower() for name in settings.ticket_category_names
        )

        # Intents - явная подписка на типы событий Discord.
        # message_content - "privileged intent": без него поле content у сообщений будет пустым.
        # Включить в Discord Developer Portal -> Bot -> Privileged Gateway Intents.
        intents = discord.Intents.default()
        intents.message_content = True

        self._client = _BotClient(adapter=self, intents=intents)

    async def start(self) -> None:
        """Подключиться к Discord и войти в event loop. Блокирует до вызова stop()."""
        await self._client.start(self._token)

    async def stop(self) -> None:
        """Отключиться от Discord без ошибок в логах."""
        await self._client.close()

    async def send_message(self, message: OutgoingMessage) -> None:
        """Отправить сообщение в канал, указанный в OutgoingMessage.channel_id."""
        # get_channel ищет в локальном кеше клиента - работает без доп. запросов к API
        channel = self._client.get_channel(int(message.channel_id))

        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                'send_message: канал %s не найден или не является TextChannel',
                message.channel_id,
            )
            return

        await channel.send(message.content)

    # ------------------------------------------------------------------
    # Внутренние методы - не часть PlatformAdapter API
    # ------------------------------------------------------------------

    async def _handle_message(self, message: discord.Message) -> None:
        """
        Точка входа для каждого входящего сообщения.

        Порядок проверок:
          1. Игнорировать сообщения самого бота - иначе бесконечный цикл
          2. Игнорировать каналы не из мониторируемых категорий
          3. Конвертировать в IncomingMessage и залогировать
          4. (заглушка Milestone 2) Ответить фиксированным текстом
        """
        # Бот не должен реагировать на свои же сообщения
        if message.author == self._client.user:
            return

        if not self._is_monitored(message):
            return

        incoming = self._to_incoming_message(message)
        logger.info(
            '[входящее] channel=%s author=%s text=%r',
            incoming.channel_id,
            incoming.author_id,
            incoming.content,
        )

        await self._message_handler(incoming)

    def _is_monitored(self, message: discord.Message) -> bool:
        """
        Вернуть True если сообщение пришло из канала в мониторируемой категории.

        Три условия:
          1. Канал - текстовый (не голосовой, не DM, не тред)
          2. Канал находится в категории (не вне категорий)
          3. Имя категории совпадает с одним из TICKET_CATEGORY_NAMES из .env
        """
        if not isinstance(message.channel, discord.TextChannel):
            return False

        # У каналов без категории атрибут category равен None
        if message.channel.category is None:
            return False

        return message.channel.category.name.lower() in self._monitored_categories

    def _to_incoming_message(self, message: discord.Message) -> IncomingMessage:
        """Конвертировать discord.Message в платформо-независимый IncomingMessage."""
        attachments = [
            Attachment(
                url=a.url,
                # content_type может быть None для некоторых форматов файлов
                content_type=a.content_type or 'application/octet-stream',
            )
            for a in message.attachments
        ]

        return IncomingMessage(
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
            content=message.content,
            timestamp=message.created_at,
            # Определение is_staff требует проверки ролей сервера - реализуется в Milestone 3
            is_staff=False,
            attachments=attachments,
        )
