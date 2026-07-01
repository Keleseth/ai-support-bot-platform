"""
Абстрактный базовый класс для LLM-провайдеров.

Почему эта абстракция существует: Anthropic SDK и OpenAI SDK имеют разные
Python-интерфейсы - разные клиенты, форматы сообщений и формы ответов.
BaseLLM нормализует их, чтобы TicketProcessor никогда не импортировал
провайдер-специфичный код.

Формат сообщений: list[dict[str, str]] - стандарт OpenAI-совместимого API.
Каждый dict содержит ключи 'role' и 'content'.
Роли: 'system' | 'user' | 'assistant'.
Сборку этих сообщений выполняет prompts.py - не провайдер и не Core.
"""

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """Общий интерфейс для всех LLM-провайдеров."""

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]]) -> str:
        """Отправить список сообщений в LLM и вернуть текст ответа."""
        ...
