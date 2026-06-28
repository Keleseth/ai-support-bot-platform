"""
Shared pytest fixtures available to all tests without explicit import.

Add fixtures here as the test suite grows:
- mock Settings (avoid requiring a real .env during tests)
- fake PlatformAdapter
- fake BaseLLM with scripted responses
"""

import pytest
