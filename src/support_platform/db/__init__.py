"""
Postgres infrastructure: a connection pool and CRUD over its tables.

Knows nothing about Discord or Telegram - concrete data sources (e.g.
DiscordOrderRecordsSource) hold objects from here as a dependency.
"""
