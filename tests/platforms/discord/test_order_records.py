"""Tests for platforms/discord/order_records.py - parsing an order channel line (_parse)."""

from unittest.mock import Mock

import pytest

from support_platform.platforms.discord.order_records import DiscordOrderRecordsSource


def _source() -> DiscordOrderRecordsSource:
    return DiscordOrderRecordsSource('123', client=Mock(), store=Mock())


@pytest.mark.parametrize(
    ('line', 'order_id', 'email', 'status'),
    [
        ('Заказ: id 5 | email: a@mail.ru - в пути', '5', 'a@mail.ru', 'в пути'),
        ('заказ id23|email:b@mail.ru-доставлен', '23', 'b@mail.ru', 'доставлен'),
        ('ЗАКАЗ:   id  7   |  email:   c@mail.ru   -   утерян', '7', 'c@mail.ru', 'утерян'),
    ],
    ids=['normal-spacing', 'no-spaces', 'extra-spaces-and-case'],
)
def test_parse_valid_line(line: str, order_id: str, email: str, status: str) -> None:
    record = _source()._parse(line)

    assert record is not None
    assert (record.order_id, record.email, record.status) == (order_id, email, status)


@pytest.mark.parametrize(
    'line',
    ['случайное сообщение без формата', 'Заказ: id | email: a@mail.ru - в пути', ''],
    ids=['unrelated-text', 'missing-order-id', 'empty'],
)
def test_parse_invalid_line_returns_none(line: str) -> None:
    assert _source()._parse(line) is None
