"""
Data lookup services: invoice, email, order status.

Currently backed by Discord channel search.
Each service is an independent class - any of them can be swapped for a
database query or external API call without touching TicketProcessor.

Implementation: Milestone 5.
"""
