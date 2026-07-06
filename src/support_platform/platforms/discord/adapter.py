"""
Discord реализация PlatformAdapter.

Ответственности:
  - Фильтровать входящие сообщения по категории канала
  - Конвертировать discord.Message -> IncomingMessage (платформо-независимый объект)
  - Передавать IncomingMessage во внешний message_handler (TicketDebouncer)
  - Отправлять ответы через TextChannel.send()

Про заказы (DiscordOrderRecordsSource) этот класс ничего не знает - это
отдельный, независимый компонент. Оба делят один discord.Client (создаёт
и раздаёт его platforms/discord/factory.py), но каждый сам вешает свои
обработчики на клиент через add_listener - без этого файла и без ссылок
друг на друга.

Используется только в main.py (через platforms/discord/factory.py)
за абстракцией PlatformAdapter. Всё остальное приложение не знает,
что под ним Discord.
"""

import logging
from collections.abc import Awaitable, Callable

import discord
from discord.ext import commands

from support_platform.config import Settings
from support_platform.core.models import Attachment, IncomingMessage, OutgoingMessage
from support_platform.platforms.base import PlatformAdapter

logger = logging.getLogger(__name__)


class DiscordAdapter(PlatformAdapter):
    """
    Реализация PlatformAdapter для Discord.

    Получает Settings (токен, категории) и уже готовый client - сам client
    создаётся снаружи (platforms/discord/factory.py), потому что может быть
    общим с DiscordOrderRecordsSource. Здесь регистрируются только свои
    обработчики (add_listener), никакой другой код на этот client не
    претендует.

    Тип client - commands.Bot, а не discord.Client: только у commands.Bot
    есть add_listener (несколько независимых обработчиков на одно событие),
    см. подробности в platforms/discord/factory.py.
    """

    def __init__(
        self,
        settings: Settings,
        message_handler: Callable[[IncomingMessage], Awaitable[None]],
        client: commands.Bot,
    ) -> None:
        self._token = settings.discord_token
        self._message_handler = message_handler
        self._client = client

        # id, а не имя категории: разные категории на сервере могут называться
        # одинаково, id категории в Discord всегда уникален.
        self._tickets_category_id = int(settings.tickets_category_id)

        # add_listener (а не переопределение on_ready/on_message в подклассе
        # discord.Client) - именно он позволяет второму независимому
        # компоненту (DiscordOrderRecordsSource) повесить свои обработчики
        # на тот же client, не наследуясь и не подменяя эти же методы.
        client.add_listener(self._on_ready, 'on_ready')
        client.add_listener(self._handle_message, 'on_message')

    async def _on_ready(self) -> None:
        """Срабатывает когда бот успешно подключился и авторизовался."""
        logger.info(
            'Бот подключён как %s (id=%s)',
            self._client.user,
            self._client.user.id if self._client.user else '?',
        )

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

        Условия:
          1. Канал - текстовый (не голосовой, не DM, не тред)
          2. Канал находится в категории (не вне категорий)
          3. id этой категории совпадает с TICKETS_CATEGORY_ID из .env
        """
        if not isinstance(message.channel, discord.TextChannel):
            return False

        # У каналов без категории атрибут category равен None
        if message.channel.category is None:
            return False

        return message.channel.category.id == self._tickets_category_id

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
