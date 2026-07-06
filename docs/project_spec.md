# AI Support Bot Platform — Project Specification

> **Source of truth.** All architecture and requirement changes must be reflected here first.

---

## 1. Project Overview

A commercial AI-powered customer support automation platform. Discord is the **first integration** — not the only one. The system is designed so that the messaging platform, LLM provider, and data sources can be swapped without touching business logic.

**Reference:** Based on a real Upwork job posting for a Discord AI Support Bot (Claude API integration).

---

## 2. Goals

- Automate first-line customer support responses in Discord ticket channels
- Detect customer intent using an LLM (Claude)
- Look up relevant customer data (invoice ID, email, order status) via Discord channel search
- Generate a contextual response using an LLM
- Support image attachments passed from Discord → Claude API
- Keep all platform-specific and LLM-specific code behind clean abstractions

---

## 3. Core Principles

| Principle | Description |
|-----------|-------------|
| **Platform-agnostic Core** | Core business logic knows nothing about Discord, Telegram, or any other platform |
| **LLM-agnostic Core** | Core never calls LLM APIs directly — all calls go through `BaseLLM` |
| **Composition Root** | The concrete platform adapter and LLM provider are selected at startup via `.env`, not hardcoded |
| **Single context object** | A `TicketContext` dataclass carries all state through the processing pipeline |

---

## 4. Architecture

### 4.1 High-Level Flow

```
[Platform Adapter]          e.g. DiscordAdapter
        ↓
  IncomingMessage           platform-agnostic dataclass (includes attachments)
        ↓
  TicketDebouncer           waits TICKET_DEBOUNCE_SECONDS after last customer message
        ↓
  Pre-flight Checks         (1) correct category? (2) last message from customer?
        ↓
  TicketProcessor (Core)    orchestrates the full pipeline
        ↓
  BaseLLM → Intent          LLM call #1: classify customer intent
        ↓
  Lookup / Repositories     find invoice, email, order status (Discord channel search)
        ↓
  BaseLLM → Response        LLM call #2: generate reply using customer context
        ↓
  OutgoingMessage           platform-agnostic dataclass
        ↓
[Platform Adapter]          adapter.send_message() — replies in the ticket channel
```

### 4.2 Component Responsibilities

#### `PlatformAdapter` (ABC)
- Connects to the messaging platform
- Converts raw platform events → `IncomingMessage` (with attachments)
- Exposes `send_message(OutgoingMessage)`
- Implementations: `DiscordAdapter`, (future) `TelegramAdapter`

#### `IncomingMessage` (dataclass)
Platform-agnostic message representation:
```python
channel_id: str
author_id: str
content: str
timestamp: datetime
is_staff: bool
attachments: list[Attachment]   # images/files to pass to Claude
```

#### `Attachment` (dataclass)
```python
url: str
content_type: str   # e.g. "image/png"
```

#### `OutgoingMessage` (dataclass)
```python
channel_id: str
content: str
```

#### `TicketDebouncer`
- Receives `IncomingMessage` events from the adapter via injected `message_handler` callback
- Accumulates ALL messages per user during the debounce window — passes `list[IncomingMessage]`
  to `on_ready`, never just the last message (order_id may be in msg #1, question in msg #5)
- State per active conversation: `ConversationState(task, messages, last_message_at)` stored in
  `_states: dict[tuple[channel_id, author_id], ConversationState]`; cleared after `on_ready` fires
- Timer key is `(channel_id, author_id)` — each user has an independent timer so multiple
  customers in one channel cannot push each other's timers back
- Customer message → append to messages, reset timer
- Staff message → cancel ALL active conversations for that channel (staff already replied)
- Pre-flight check "last message from customer" is implicit: timer only starts on customer
  messages and is cancelled when staff replies — no separate check needed
- Category filtering is done by the platform adapter before messages reach the debouncer
- In-memory storage is correct for a single-instance Discord bot; Discord sharding guarantees
  one channel's events always go to the same shard

#### `TicketContext` (dataclass)
Mutable object that lives through the entire pipeline:
```python
@dataclass
class TicketContext:
    messages: list[IncomingMessage]
    intent: Intent | None = None           # set after LLM call #1
    customer_data: CustomerData | None = None  # set after lookup
    response: str | None = None            # set after LLM call #2
```

#### `TicketProcessor` (Core)
- Receives `TicketContext`, orchestrates the pipeline
- Calls `BaseLLM` for intent detection
- Based on intent, calls the appropriate repository
- Calls `BaseLLM` for response generation
- Returns completed `TicketContext` (with `response` populated)
- Knows **nothing** about Discord or the specific LLM provider

#### `Intent` (Enum)
Result of LLM call #1. Only two active intents; `OTHER` means the bot stays silent:
```
BUY_PRODUCT     — customer wants to buy via PayPal
ORDER_FOLLOWUP  — customer is following up on an existing website order
OTHER           — bot stays silent, no response sent
```

#### `BaseLLM` (ABC)
Why this abstraction exists: Anthropic SDK and OpenAI SDK have **different Python interfaces** — different clients, different message formats, different response shapes. `BaseLLM` provides a single stable interface so `TicketProcessor` never imports provider-specific code.

```python
async def complete(self, messages: list[dict[str, str]]) -> str: ...
```

Each dict has `role` (`"system" | "user" | "assistant"`) and `content` — the OpenAI-compatible message convention.

Implementations:
- `AnthropicLLM` — production (Claude API). Note: Anthropic separates `system` messages from the `messages` array; handled internally.
- `OpenAICompatibleLLM` — for testing with xAI Grok or standard OpenAI.

#### `BaseOrderRecordsSource` (ABC)
- `async find_by_order_id(order_id) -> OrderRecord | None`, `async find_by_email(email) -> OrderRecord | None`
- Read-only contract on purpose — write/sync (if the backend needs it at all) is an implementation detail, not part of what `TicketProcessor` depends on
- `DiscordOrderRecordsSource` — listens to the Discord order-records channel (new/edited/deleted message events), parses each into an `OrderRecord`, persists through `PostgresOrderRecordsStore`. Discord is the event source; Postgres is the durable copy so restarts don't require rescanning the whole channel history.
- A future backend (e.g. a direct read against the store owner's own database) would implement the same two methods with no persistence step of its own — no local Postgres duplicate needed in that case.

#### `PostgresOrderRecordsStore` (`db/order_store.py`)
- Plain CRUD over one `order_records` table, keyed by Discord `message_id`
- Not itself a `BaseOrderRecordsSource` — it's a private dependency of `DiscordOrderRecordsSource`, invisible to `TicketProcessor` and the rest of the pipeline
- Knows nothing about Discord; asyncpg only, no ORM (single simple table)

#### `Settings` (pydantic-settings)
Single source of all configuration:
```
BOT_PLATFORM              discord | (future) telegram
DISCORD_TOKEN             bot token
LLM_PROVIDER              anthropic | openai_compatible
LLM_API_KEY               API key
LLM_BASE_URL              override URL for openai_compatible providers (e.g. xAI Grok)
LLM_MODEL                 e.g. claude-sonnet-4-6
TICKET_DEBOUNCE_SECONDS   default: 150
TICKETS_CATEGORY_ID       id of the customer tickets category (id, not name - see adapter.py)
ORDER_RECORDS_BACKEND     discord | (future) other backends
ORDER_RECORDS_CHANNEL_ID  id of the channel holding order records
STORE_PAYPAL_EMAIL        sent to the customer on intent=BUY_PRODUCT
DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD   Postgres connection, one field per var
```

#### Composition Root (`main.py`)
Reads `BOT_PLATFORM` and `LLM_PROVIDER` from settings, creates the correct adapter and LLM, wires all components together. No other file makes this decision.

---

## 5. Directory Structure

```
ai-support-bot-platform/
├── src/
│   └── support_platform/
│       ├── __init__.py
│       ├── config.py               # pydantic-settings Settings class
│       ├── main.py                 # Composition Root
│       ├── core/                   # pure business logic, no platform/LLM deps
│       │   ├── __init__.py
│       │   ├── models.py           # all dataclasses: IncomingMessage, TicketContext, Intent …
│       │   ├── processor.py        # TicketProcessor
│       │   └── debouncer.py        # TicketDebouncer
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── base.py             # BaseLLM ABC
│       │   ├── anthropic_client.py # AnthropicLLM
│       │   ├── openai_client.py    # OpenAICompatibleLLM (Grok / OpenAI)
│       │   └── prompts.py          # prompt templates
│       ├── platforms/
│       │   ├── __init__.py
│       │   ├── base.py             # PlatformAdapter ABC
│       │   └── discord/
│       │       ├── __init__.py
│       │       ├── adapter.py      # DiscordAdapter
│       │       ├── factory.py      # builds client(s) + adapter/order-records pair
│       │       └── order_records.py # DiscordOrderRecordsSource
│       ├── repositories/
│       │   ├── __init__.py
│       │   └── order_source.py     # BaseOrderRecordsSource ABC, OrderRecord
│       └── db/
│           ├── __init__.py
│           ├── pool.py             # asyncpg pool + schema init
│           └── order_store.py      # PostgresOrderRecordsStore
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # shared fixtures and test doubles
│   ├── core/                    # TicketDebouncer, TicketProcessor
│   ├── llm/                     # prompt building and intent parsing
│   └── platforms/discord/       # category filtering, order line parsing
├── docs/
│   └── project_spec.md
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── Makefile
```

---

## 6. Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Package manager | uv |
| Config | pydantic-settings |
| Discord | discord.py |
| LLM (primary) | Anthropic SDK — Claude API |
| LLM (testing) | openai SDK — xAI Grok (OpenAI-compatible, free testing tokens) |
| Database | PostgreSQL + asyncpg |
| Testing | pytest + pytest-asyncio |
| Type checking | mypy (strict) |
| Linting / formatting | Ruff |
| Containerization | Docker + docker-compose |
| CI | GitHub Actions (not set up yet) |

---

## 7. Milestones

### Milestone 1 — Local skeleton
- `pyproject.toml` with all tooling configured
- Package structure under `src/support_platform/`
- `pydantic-settings` config
- `.env.example`
- `Makefile`
- All module stubs with docstrings

### Milestone 2 — Minimal Discord bot
- `DiscordAdapter` connects to Discord
- Receives messages, logs them to console
- `send_message()` works end-to-end

### Milestone 3 — Pipeline without LLM
- `TicketDebouncer` with asyncio timer and pre-flight checks
- `TicketProcessor` skeleton (hardcoded responses)
- `TicketContext` flows end-to-end

### Milestone 4 — LLM integration
- `AnthropicLLM` with intent detection
- Prompt templates
- Response generation with customer context
- Image attachment support (Discord → Claude)

### Milestone 5 — Repositories
- Invoice, email, order status lookup
- Backed by Discord channel search

### Milestone 6 — Infrastructure (practice, current)
- Docker + docker-compose
- PostgreSQL integration
- pytest test suite for the core pipeline
- GitHub Actions CI (pending)
