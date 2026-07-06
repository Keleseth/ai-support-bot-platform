"""Tests for llm/prompts.py - parsing the LLM's intent response and assembling call messages."""

import pytest

from support_platform.core.models import CustomerData, Intent
from support_platform.llm.prompts import (
    build_intent_messages,
    build_response_messages,
    parse_intent,
)
from tests.conftest import make_incoming_message


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('BUY_PRODUCT', Intent.BUY_PRODUCT),
        ('order_followup', Intent.ORDER_FOLLOWUP),
        ('  Other  ', Intent.OTHER),
    ],
    ids=['exact-upper', 'lowercase', 'padded-mixed-case'],
)
def test_parse_intent_valid_values(raw: str, expected: Intent) -> None:
    assert parse_intent(raw) is expected


@pytest.mark.parametrize(
    'raw',
    ['', 'MAYBE', 'buy product', 'BUY_PRODUCT extra text'],
    ids=['empty', 'unknown-word', 'space-not-underscore', 'trailing-text'],
)
def test_parse_intent_unknown_falls_back_to_other(raw: str) -> None:
    assert parse_intent(raw) is Intent.OTHER


def test_build_intent_messages_joins_multiple_messages() -> None:
    messages = [make_incoming_message('первое'), make_incoming_message('второе')]

    result = build_intent_messages(messages)

    assert result[0]['role'] == 'system'
    assert result[1] == {'role': 'user', 'content': 'первое\nвторое'}


def test_build_response_messages_includes_only_present_customer_fields() -> None:
    data = CustomerData(order_id='23', email=None, order_status='готов к выдаче')

    result = build_response_messages([make_incoming_message('где мой заказ')], data)
    user_content = result[1]['content']

    assert 'Order ID: 23' in user_content
    assert 'Order status: готов к выдаче' in user_content
    assert 'Email:' not in user_content


def test_build_response_messages_omits_customer_data_block_when_none() -> None:
    result = build_response_messages([make_incoming_message('привет')], None)

    assert 'Customer data:' not in result[1]['content']


def test_build_response_messages_omits_customer_data_block_when_empty() -> None:
    result = build_response_messages([make_incoming_message('привет')], CustomerData())

    assert 'Customer data:' not in result[1]['content']
