# AI Support Bot Platform — Project Specification

> **Source of truth.** All architecture and requirement changes must be reflected here first.
> Internal docs are written in Russian going forward; this file stays in English (first version).

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
- In-memory storage is correct for single-instance Discord bot; Discord sharding guarantees
  one channel's events always go to the same shard (Redis needed for repo cache, not debouncer)

#### `TicketContext` (dataclass)
Mutable object that lives through the entire pipeline:
```python
@dataclass
class TicketContext:
    message: IncomingMessage
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
async def complete(self, messages: list[ChatMessage]) -> str: ...
```

Implementations:
- `AnthropicLLM` — production (Claude API). Note: Anthropic separates `system` messages from the `messages` array; handled internally.
- `OpenAICompatibleLLM` — for testing with xAI Grok or standard OpenAI.

#### `ChatMessage` (dataclass)
```python
role: str     # "system" | "user" | "assistant"
content: str
```

#### Repositories / Lookup Services
- `InvoiceLookup` — finds invoice by ID
- `EmailLookup` — finds customer by email
- `OrderStatusLookup` — finds order status
- Initially backed by Discord channel search; later replaceable with DB/API without touching Core

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
TICKET_CATEGORY_NAMES     JSON array, default: ["uncategorized", "orders"]
DATABASE_URL              (future) PostgreSQL
REDIS_URL                 (future) Redis
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
│       │   └── prompts.py          # prompt templates (Milestone 4)
│       ├── platforms/
│       │   ├── __init__.py
│       │   ├── base.py             # PlatformAdapter ABC
│       │   └── discord/
│       │       ├── __init__.py
│       │       └── adapter.py      # DiscordAdapter
│       └── repositories/
│           ├── __init__.py
│           ├── base.py             # BaseRepository ABC (future)
│           ├── invoice.py          # InvoiceLookup
│           ├── email.py            # EmailLookup
│           └── order_status.py     # OrderStatusLookup
├── tests/
│   ├── __init__.py
│   └── conftest.py
├── docs/
│   └── project_spec.md
├── .env.example
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
| Database | PostgreSQL + asyncpg (future milestone) |
| Cache / state | Redis (future milestone) |
| Testing | pytest + pytest-asyncio |
| Type checking | mypy (strict) |
| Linting / formatting | Ruff |
| Containerization | Docker (future milestone) |
| CI | GitHub Actions (future milestone, after tests exist) |

---

## 7. Milestones

### Milestone 1 — Local skeleton (current)
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

### Milestone 6 — Infrastructure (practice)
- Docker + docker-compose
- PostgreSQL + Redis integration
- GitHub Actions CI

---

## 8. Open Questions — Resolved

| Question | Answer |
|----------|--------|
| Discord channel(s) for data lookup? | Sasha will create a test server and provide API access when Milestone 5 begins |
| Intent classification — strict or free-form? | Strict enum: `BUY_PRODUCT`, `ORDER_FOLLOWUP`, `OTHER` |
| Response language? | Detect from customer message — Claude handles multilingual natively |
| Reply in DM or ticket channel? | Reply in the ticket channel |
