"""Tests for core/processor.py - the TicketProcessor pipeline orchestrator."""

from support_platform.core.models import Intent, TicketContext
from support_platform.core.processor import TicketProcessor
from support_platform.repositories.order_source import OrderRecord
from tests.conftest import FakeLLM, FakeOrderRecordsSource, make_incoming_message


async def test_other_intent_skips_lookup_and_response() -> None:
    llm = FakeLLM(responses=['OTHER'])
    order_records = FakeOrderRecordsSource()
    processor = TicketProcessor(llm=llm, order_records=order_records)

    context = await processor.process(
        TicketContext(messages=[make_incoming_message('спасибо, все понятно')])
    )

    assert context.intent is Intent.OTHER
    assert context.response is None
    assert order_records.order_id_calls == []
    assert order_records.email_calls == []


async def test_looks_up_by_order_id_when_mentioned_in_text() -> None:
    record = OrderRecord(order_id='23', email='client@mail.ru', status='готов к выдаче')
    llm = FakeLLM(responses=['ORDER_FOLLOWUP', 'Ваш заказ готов к выдаче.'])
    order_records = FakeOrderRecordsSource(by_order_id={'23': record})
    processor = TicketProcessor(llm=llm, order_records=order_records)

    context = await processor.process(
        TicketContext(messages=[make_incoming_message('где заказ #23?')])
    )

    assert order_records.order_id_calls == ['23']
    assert order_records.email_calls == []
    assert context.customer_data is not None
    assert context.customer_data.order_status == 'готов к выдаче'


async def test_looks_up_by_email_when_no_order_id_mentioned() -> None:
    record = OrderRecord(order_id='23', email='client@mail.ru', status='в пути')
    llm = FakeLLM(responses=['ORDER_FOLLOWUP', 'ответ'])
    order_records = FakeOrderRecordsSource(by_email={'client@mail.ru': record})
    processor = TicketProcessor(llm=llm, order_records=order_records)

    await processor.process(
        TicketContext(messages=[make_incoming_message('мой email client@mail.ru, где заказ?')])
    )

    assert order_records.order_id_calls == []
    assert order_records.email_calls == ['client@mail.ru']


async def test_order_id_takes_priority_over_email_when_both_present() -> None:
    llm = FakeLLM(responses=['ORDER_FOLLOWUP', 'ответ'])
    order_records = FakeOrderRecordsSource(
        by_order_id={'23': OrderRecord(order_id='23', email='a@mail.ru', status='в пути')},
    )
    processor = TicketProcessor(llm=llm, order_records=order_records)

    await processor.process(
        TicketContext(messages=[make_incoming_message('заказ 23, email a@mail.ru')])
    )

    assert order_records.order_id_calls == ['23']
    # email was never checked - the order was already found by order_id
    assert order_records.email_calls == []


async def test_empty_customer_data_when_nothing_found() -> None:
    llm = FakeLLM(responses=['ORDER_FOLLOWUP', 'уточните, пожалуйста'])
    order_records = FakeOrderRecordsSource()
    processor = TicketProcessor(llm=llm, order_records=order_records)

    context = await processor.process(
        TicketContext(messages=[make_incoming_message('привет, что с моим заказом?')])
    )

    assert context.customer_data is not None
    assert context.customer_data.order_id is None
    assert context.customer_data.email is None
