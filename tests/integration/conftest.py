"""Shared fixtures for integration tests.

Provides AlpacaAdapter instances configured for paper trading
using credentials loaded from config/.env.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load environment variables from config/.env
_env_path = Path(__file__).resolve().parents[2] / "config" / ".env"
load_dotenv(_env_path)

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

has_alpaca_creds = ALPACA_API_KEY is not None and ALPACA_SECRET_KEY is not None

skip_no_creds = pytest.mark.skipif(
    not has_alpaca_creds,
    reason="ALPACA_API_KEY and ALPACA_SECRET_KEY not set in config/.env",
)


@pytest.fixture
async def alpaca_adapter():
    """Provide a connected AlpacaAdapter instance for paper trading.

    Connects before yielding and disconnects after the test completes.
    Skipped automatically when credentials are missing.
    """
    from autotrader.broker.alpaca_adapter import AlpacaAdapter

    adapter = AlpacaAdapter(
        api_key=ALPACA_API_KEY,
        secret_key=ALPACA_SECRET_KEY,
        paper=True,
    )
    await adapter.connect()
    yield adapter
    await adapter.disconnect()
