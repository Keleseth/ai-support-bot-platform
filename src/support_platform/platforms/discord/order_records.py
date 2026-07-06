"""
Источник данных о заказах - канал Discord с записями вида:
    "Заказ: id 5 | email: example@mail.ru - в пути"

Один пост в канале = один заказ. Формат придумал **** для теста,
парсер (regex) заточен именно под него.

Ответственности:
  - распарсить одну строку сообщения в OrderRecord (order_id, email, status)
  - слушать gateway-события Discord (новое сообщение / правка / удаление)
    и передавать результат в PostgresOrderRecordsStore - сам этот класс
    заказы нигде не хранит
  - синхронизировать хранилище БЕЗ повторного чтения истории канала при
    каждом сообщении - Discord сам сообщает, какое именно сообщение изменилось

Почему ключ - message_id, а не order_id:
  message_id никогда не меняется у существующего сообщения.
  order_id - это то, что стафф ВПИСАЛ В ТЕКСТ, и его можно случайно
  отредактировать (опечатка). Если бы ключом был order_id и стафф его
  поправил, в кэше осталась бы "осиротевшая" запись под старым id.
  Поиск по order_id/email при этом - просто перебор значений словаря:
  заказов в учебном магазине немного, и лукап случается редко
  (раз на клиентский тикет), так что O(n) никак не заметен.

Использует discord.py напрямую - так и задумано для Milestone 5
("Repositories backed by Discord channel search"). Когда в Milestone 6
данные переедут в Postgres, этот файл целиком заменится на реализацию
поверх БД - repositories и Core этого изменения не заметят, так как
зависят от абстракции BaseOrderRecordsSource, а не от этого класса напрямую.

Независимость от DiscordAdapter:
  Этот класс НЕ знает про DiscordAdapter и никогда не должен его импортировать.
  Обоим компонентам нужен один и тот же client (одно соединение с Discord на
  процесс), но делят они его как равноправные подписчики: каждый сам
  регистрирует свои обработчики через client.add_listener(...) - метод
  commands.Bot (не голого discord.Client - у того на одно событие можно
  повесить только один обработчик), рассчитанный именно на несколько
  независимых слушателей одного события. Клиент создаёт и раздаёт им обоим
  platforms/discord/factory.py - единственное место, которое знает про оба
  класса одновременно.
"""

import logging
import re

import discord
from discord.ext import commands

from support_platform.db.order_store import PostgresOrderRecordsStore
from support_platform.repositories.order_source import BaseOrderRecordsSource, OrderRecord

logger = logging.getLogger(__name__)

# Разбор строки вида "Заказ: id 5 | email: example@mail.ru - в пути".
#   - "заказ" и двоеточие после него - регистронезависимо, двоеточие необязательно
#   - между частями допускаются любые пробелы (могут быть расставлены не идеально)
#   - email - "всё, что не пробел" (простая проверка формата email тут не нужна,
#     мы просто копируем то, что стафф написал в канале данных)
#   - статус - всё, что осталось после " - " до конца строки
_ORDER_LINE_RE = re.compile(
    r'заказ:?\s*id\s*(?P<order_id>\d+)\s*\|\s*email:\s*(?P<email>\S+)\s*-\s*(?P<status>.+)',
    re.IGNORECASE,
)


class DiscordOrderRecordsSource(BaseOrderRecordsSource):
    """
    Слушает канал заказов и держит PostgresOrderRecordsStore в актуальном виде.

    Создаётся один раз в Composition Root (main.py, через
    platforms/discord/factory.py) и получает уже готовый client (commands.Bot -
    см. platforms/discord/factory.py, почему не голый discord.Client) и store
    (см. db/order_store.py). Сам регистрирует на client свои обработчики
    событий (add_listener) - снаружи никто не обязан знать, что этому классу
    вообще нужны события Discord. Для остального приложения (repositories,
    TicketProcessor) виден только интерфейс BaseOrderRecordsSource - store
    им не виден и не нужен, это деталь конкретно этой реализации.
    """

    def __init__(
        self,
        channel_id: str,
        client: commands.Bot,
        store: PostgresOrderRecordsStore,
    ) -> None:
        # id канала хранится как int - именно в таком виде его отдаёт discord.py
        # в событиях (message.channel.id, payload.channel_id)
        self._channel_id = int(channel_id)
        self._client = client
        self._store = store

        # add_listener (а не переопределение on_ready/on_message в подклассе)
        # позволяет повесить на один client несколько независимых слушателей
        # одного события - вторым таким слушателем будет DiscordAdapter.
        client.add_listener(self._on_ready, 'on_ready')
        client.add_listener(self._on_message, 'on_message')
        client.add_listener(self._on_raw_message_edit, 'on_raw_message_edit')
        client.add_listener(self._on_raw_message_delete, 'on_raw_message_delete')

    async def _on_ready(self) -> None:
        """
        Срабатывает когда client подключился и авторизовался.

        Читаем всю историю канала заказов один раз - до этого момента
        client.get_channel() ничего не найдёт, кеш каналов discord.py
        заполняется только после подключения. Дальше store поддерживается
        событиями (_on_message/_on_raw_message_edit/_on_raw_message_delete),
        повторный history() не нужен. Записи просто перезаписываются теми же
        значениями (upsert) - не проблема, если что-то уже было в БД с прошлого запуска.
        """
        channel = self._client.get_channel(self._channel_id)
        if not isinstance(channel, discord.TextChannel):
            logger.warning(
                '[заказы] канал %s не найден или не текстовый - лукап заказов работать не будет',
                self._channel_id,
            )
            return

        # limit=None - без ограничения в 100 сообщений по умолчанию.
        # Важно: нам нужны ВСЕ записи, а не последние N.
        count = 0
        async for message in channel.history(limit=None):
            await self._ingest(message.id, message.content)
            count += 1

        logger.info('[заказы] обработано %d сообщений канала при старте', count)

    async def _on_message(self, message: discord.Message) -> None:
        """
        Срабатывает на КАЖДОЕ сообщение, видимое боту (fan-out листенер -
        DiscordAdapter получит то же самое сообщение своим отдельным
        обработчиком). Сам проверяет, что сообщение из нужного канала -
        никакой внешний код эту фильтрацию за нас не делает.
        """
        if message.channel.id != self._channel_id:
            return
        await self._ingest(message.id, message.content)

    async def _on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        """
        Срабатывает на правку любого сообщения на сервере.

        Почему raw, а не обычный on_message_edit:
          обычная версия срабатывает только если старое сообщение уже лежит
          во внутреннем кеше discord.py (у него есть предел размера и он
          не гарантирует наличие старых сообщений). raw-версия прилетает
          всегда, независимо от кеша библиотеки - для нас это критично,
          иначе правка статуса заказа может быть просто пропущена.
        """
        if payload.channel_id != self._channel_id:
            return

        # payload.data - сырой JSON из Discord API. Поле "content" в нём
        # присутствует, только если менялся именно текст сообщения
        # (не появляется, например, при добавлении одной только реакции).
        content = payload.data.get('content')
        if content is None:
            return

        await self._ingest(payload.message_id, content)

    async def _on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        """
        Срабатывает на удаление любого сообщения на сервере. Raw - по той же
        причине, что и у правки: не зависит от внутреннего кеша discord.py.
        """
        if payload.channel_id != self._channel_id:
            return
        await self._store.delete(payload.message_id)

    async def find_by_order_id(self, order_id: str) -> OrderRecord | None:
        """Найти заказ по id. Возвращает None, если такого заказа нет в хранилище."""
        return await self._store.get_by_order_id(order_id)

    async def find_by_email(self, email: str) -> OrderRecord | None:
        """Найти заказ по email. Сравнение регистронезависимое (делает store)."""
        return await self._store.get_by_email(email)

    async def _ingest(self, message_id: int, content: str) -> None:
        """Распарсить содержимое сообщения и сохранить/обновить запись в store по его message_id."""
        record = self._parse(content)
        if record is None:
            logger.warning(
                '[заказы] сообщение %s не соответствует формату записи о заказе: %r',
                message_id,
                content,
            )
            return
        await self._store.save(message_id, record)

    def _parse(self, content: str) -> OrderRecord | None:
        """Разобрать одну строку канала в OrderRecord. None, если формат не совпал."""
        match = _ORDER_LINE_RE.search(content)
        if match is None:
            return None
        return OrderRecord(
            order_id=match.group('order_id'),
            email=match.group('email'),
            status=match.group('status').strip(),
        )
