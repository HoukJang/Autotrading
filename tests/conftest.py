"""Top-level test configuration and fixtures.

Provides global test isolation to prevent tests from writing
to production data files (trade logs, equity snapshots).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# Production data file paths that must never be written to during tests.
_PRODUCTION_TRADE_LOG = "data/live_trades.jsonl"
_PRODUCTION_EQUITY_LOG = "data/equity_snapshots.jsonl"


@pytest.fixture(autouse=True)
def _isolate_trade_logging(tmp_path, monkeypatch):
    """Redirect TradeLogger writes away from production data files.

    Wraps TradeLogger.__init__ so that any instance created with the
    default production paths gets redirected to tmp_path instead.
    Tests that explicitly provide their own tmp_path-based paths
    (e.g. TestTradeLoggerIntegration) are unaffected.
    """
    from autotrader.portfolio.trade_logger import TradeLogger

    _original_init = TradeLogger.__init__

    def _safe_init(self, trade_log_path: str, equity_log_path: str) -> None:
        safe_trade = trade_log_path
        safe_equity = equity_log_path

        # Redirect production paths to tmp_path
        if Path(trade_log_path).as_posix().endswith(_PRODUCTION_TRADE_LOG):
            safe_trade = str(tmp_path / "test_trades.jsonl")
        if Path(equity_log_path).as_posix().endswith(_PRODUCTION_EQUITY_LOG):
            safe_equity = str(tmp_path / "test_equity.jsonl")

        _original_init(self, safe_trade, safe_equity)

    monkeypatch.setattr(TradeLogger, "__init__", _safe_init)
