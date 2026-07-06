# AI Support Bot Platform

A Discord customer-support bot powered by an LLM. It watches ticket channels, waits for the
customer to finish typing, classifies their intent, looks up order data, and replies with a
contextual response - plus a self-serve panel that lets customers open their own private ticket
channel with one click.

Originally scoped from a real Upwork job posting for a Claude-only Discord support bot; extended
here into a provider-agnostic architecture (Discord today, any chat platform or LLM provider
tomorrow) as a learning/portfolio project.

## Features

- **Debounced ticket pipeline** - aggregates a customer's messages sent in quick succession
  before running them through the LLM, instead of reacting to each half-formed message.
- **Intent detection + contextual replies** - two LLM calls: classify intent
  (`BUY_PRODUCT` / `ORDER_FOLLOWUP` / `OTHER`), then generate a reply enriched with the
  customer's order data when relevant.
- **Order records synced from Discord, persisted in Postgres** - staff post order updates as
  plain messages in a dedicated channel; the bot parses and stores them, so a restart never
  requires rescanning the whole channel history.
- **Self-serve ticket creation** - a persistent "Create Ticket" button that spins up a private,
  auto-numbered channel (`ticket-1`, `ticket-2`, ...) with permissions scoped to its creator,
  moderators, and the bot.
- **Swappable by design** - the LLM provider and the messaging platform are both selected from
  a single `.env` line, with no other code changes required.

## Architecture

```
Discord message
    -> DiscordAdapter        (Discord.Message -> IncomingMessage)
    -> TicketDebouncer        (waits for a lull, batches messages per customer)
    -> TicketProcessor        (orchestrates the pipeline)
        -> BaseLLM             (intent detection - call #1)
        -> BaseOrderRecordsSource  (order lookup)
        -> BaseLLM             (response generation - call #2)
    -> OutgoingMessage
    -> DiscordAdapter.send_message()
```

Two abstractions keep the core logic independent of any specific vendor:

- **`BaseLLM`** - the Anthropic and OpenAI SDKs have different Python interfaces; implementations
  (`AnthropicLLM`, `OpenAICompatibleLLM`) normalize them behind one `complete()` method, so the
  provider is chosen once via `LLM_PROVIDER` and nothing else in the codebase knows which SDK is
  in use.
- **`PlatformAdapter`** - `DiscordAdapter` is the only implementation today; a future platform
  (Telegram, Slack, ...) would add a new implementation without touching `TicketProcessor` at all.

Order records follow the same pattern: `BaseOrderRecordsSource` is the interface `TicketProcessor`
depends on, `DiscordOrderRecordsSource` is the concrete implementation that listens to a Discord
channel and persists through `PostgresOrderRecordsStore`.

See [`docs/project_spec.md`](docs/project_spec.md) for the full architecture writeup and milestone
history.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Package manager | [uv](https://docs.astral.sh/uv/) |
| Config | pydantic-settings |
| Discord | discord.py |
| LLM | Anthropic SDK (Claude) / OpenAI SDK (OpenAI-compatible, e.g. xAI Grok) |
| Database | PostgreSQL + asyncpg |
| Testing | pytest + pytest-asyncio |
| Type checking | mypy (strict) |
| Linting / formatting | Ruff |
| Containerization | Docker + docker-compose |

## Getting Started

### Run with Docker (recommended)

```bash
cp .env.example .env   # fill in the values described below
docker compose up --build
```

This starts the bot together with a PostgreSQL container; the schema is created automatically on
first boot.

### Run locally

```bash
uv sync --group dev
cp .env.example .env   # fill in the values, DB_HOST=localhost if Postgres isn't in Docker
make run
```

### Configuration

All settings are environment variables, documented in [`.env.example`](.env.example). At minimum
you'll need:

- `DISCORD_TOKEN` - a bot token from the [Discord Developer Portal](https://discord.com/developers/applications),
  with the **message content** privileged intent enabled.
- `LLM_PROVIDER` + `LLM_API_KEY` (+ `LLM_BASE_URL` for OpenAI-compatible providers).
- `TICKETS_CATEGORY_ID`, `ORDER_RECORDS_CHANNEL_ID`, `SUPPORT_CHANNEL_ID`, `MODERATOR_ROLE_ID` -
  ids (not names) of the Discord category/channels/role the bot uses, copied via Discord's
  Developer Mode ("Copy ID" on the relevant category, channel, or role).
- `DB_*` - PostgreSQL connection details.

## Testing

```bash
make test      # uv run pytest
make lint       # uv run ruff check
make typecheck  # uv run mypy src
```

## Project Structure

```
src/support_platform/
├── config.py               # pydantic-settings Settings - single source of configuration
├── main.py                 # composition root
├── core/                   # platform- and LLM-agnostic business logic
├── llm/                    # BaseLLM + provider implementations + prompt templates
├── platforms/discord/      # DiscordAdapter, order records sync, ticket panel
├── repositories/           # BaseOrderRecordsSource abstraction
└── db/                     # Postgres pool and order records CRUD
tests/                      # pytest suite, mirrors the src/ layout
docs/project_spec.md        # full architecture and milestone history
```

## License

MIT - see [LICENSE](LICENSE).
