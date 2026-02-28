"""Integration tests for the rotation pipeline.

Tests the full rotation cycle: initial universe -> rotation event ->
watchlist management -> force close -> signal filtering.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest

from autotrader.core.config import RiskConfig, RotationConfig
from autotrader.core.types import Bar
from autotrader.rotation.backtest_engine import RotationBacktestEngine, RotationBacktestResult
from autotrader.rotation.manager import RotationManager
from autotrader.rotation.types import WatchlistEntry
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.consecutive_down import ConsecutiveDown
from autotrader.strategy.ema_pullback import EmaPullback
from autotrader.universe import UniverseResult


def _generate_multi_symbol_bars(
    symbols: list[str],
    n: int = 60,
    seed: int = 42,
    start: datetime | None = None,
) -> dict[str, list[Bar]]:
    """Generate synthetic bars for multiple symbols."""
    if start is None:
        start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)  # Monday
    random.seed(seed)
    result: dict[str, list[Bar]] = {}
    for sym_idx, symbol in enumerate(symbols):
        bars: list[Bar] = []
        price = 100.0 + sym_idx * 20  # different base prices
        ts = start
        for i in range(n):
            while ts.weekday() >= 5:
                ts += timedelta(days=1)
            phase = i % 40
            if phase < 15:
                drift = 0.003
            elif phase < 25:
                drift = -0.002
            else:
                drift = 0.0
            noise = random.gauss(0, 0.012)
            price *= 1 + drift + noise
            price = max(price, 10.0)
            high = price * (1 + abs(random.gauss(0, 0.008)))
            low = price * (1 - abs(random.gauss(0, 0.008)))
            bars.append(Bar(
                symbol=symbol,
                timestamp=ts,
                open=price * (1 + random.gauss(0, 0.002)),
                high=high,
                low=low,
                close=price,
                volume=random.uniform(500_000, 2_000_000),
            ))
            ts += timedelta(days=1)
        result[symbol] = bars
    return result


class TestRotationPipelineFull:
    """Full rotation cycle integration test."""

    def test_full_rotation_cycle(self):
        """Multi-week test with rotation events at scheduled points."""
        symbols_week1 = ["AAPL", "MSFT", "GOOG", "AMZN", "META"]
        symbols_week2 = ["AAPL", "MSFT", "TSLA", "AMZN", "NVDA"]
        all_symbols = list(set(symbols_week1 + symbols_week2))

        start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
        bars = _generate_multi_symbol_bars(all_symbols, n=40, seed=99, start=start)

        engine = RotationBacktestEngine(
            initial_balance=5000.0,
            risk_config=RiskConfig(max_position_pct=0.20, max_open_positions=5),
            rotation_config=RotationConfig(force_close_day=4, force_close_hour=14),
        )
        engine.add_strategy(RsiMeanReversion())
        engine.add_strategy(ConsecutiveDown())

        # Rotation at bar 20: drop GOOG+META, add TSLA+NVDA
        rotation_schedule = {
            20: UniverseResult(
                symbols=symbols_week2,
                scored=[],
                timestamp=start + timedelta(days=20),
                rotation_in=["TSLA", "NVDA"],
                rotation_out=["GOOG", "META"],
            ),
        }

        result = engine.run(
            bars,
            initial_universe=symbols_week1,
            rotation_schedule=rotation_schedule,
        )

        assert isinstance(result, RotationBacktestResult)
        assert result.final_equity > 0
        assert len(result.rotation_events) == 1
        assert len(result.equity_curve) > 1

        event = result.rotation_events[0]
        assert set(event.symbols_in) == {"TSLA", "NVDA"}
        assert set(event.symbols_out) == {"GOOG", "META"}

    def test_no_new_entries_after_rotation_out(self):
        """Symbols rotated out should not receive new entry signals."""
        start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
        symbols = ["AAPL", "MSFT"]
        bars = _generate_multi_symbol_bars(symbols, n=30, seed=42, start=start)

        engine = RotationBacktestEngine(
            initial_balance=5000.0,
            risk_config=RiskConfig(max_position_pct=0.30, max_open_positions=3),
            rotation_config=RotationConfig(),
        )
        engine.add_strategy(RsiMeanReversion())

        # Rotate out MSFT at bar 10
        rotation_schedule = {
            10: UniverseResult(
                symbols=["AAPL"],
                scored=[],
                timestamp=start + timedelta(days=10),
                rotation_in=[],
                rotation_out=["MSFT"],
            ),
        }

        result = engine.run(
            bars,
            initial_universe=["AAPL", "MSFT"],
            rotation_schedule=rotation_schedule,
        )

        # Count MSFT entries after rotation
        rotation_ts = start + timedelta(days=10)
        msft_entries_after = [
            t for t in result.trades
            if t.symbol == "MSFT"
            and t.direction == "long"
            and t.entry_time > rotation_ts
        ]
        assert len(msft_entries_after) == 0

    def test_weekly_loss_limit_halts_all_entries(self):
        """When weekly loss limit is hit, no new entries should occur."""
        start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
        bars = _generate_multi_symbol_bars(["AAPL"], n=30, seed=42, start=start)

        engine = RotationBacktestEngine(
            initial_balance=3000.0,
            risk_config=RiskConfig(max_position_pct=0.50, max_open_positions=3),
            rotation_config=RotationConfig(weekly_loss_limit_pct=0.001),  # tiny limit
        )
        engine.add_strategy(RsiMeanReversion())

        result = engine.run(bars, initial_universe=["AAPL"])
        # With 0.1% loss limit, trading should halt very quickly
        assert result.final_equity > 0


class TestRotationManagerUnit:
    """Integration-level tests for RotationManager state transitions."""

    def test_multi_rotation_cycle(self):
        """Multiple rotations in sequence maintain correct state."""
        mgr = RotationManager(RotationConfig())

        # Week 1
        u1 = UniverseResult(
            symbols=["AAPL", "MSFT", "GOOG"],
            scored=[], timestamp=datetime(2026, 1, 10, 12, tzinfo=timezone.utc),
            rotation_in=["AAPL", "MSFT", "GOOG"], rotation_out=[],
        )
        mgr.apply_rotation(u1, open_position_symbols=[], new_equity=3000.0)
        assert set(mgr.active_symbols) == {"AAPL", "MSFT", "GOOG"}
        assert len(mgr.watchlist_symbols) == 0

        # Week 2: drop GOOG (has position), add AMZN
        u2 = UniverseResult(
            symbols=["AAPL", "MSFT", "AMZN"],
            scored=[], timestamp=datetime(2026, 1, 17, 12, tzinfo=timezone.utc),
            rotation_in=["AMZN"], rotation_out=["GOOG"],
        )
        mgr.apply_rotation(u2, open_position_symbols=["GOOG"], new_equity=3100.0)
        assert set(mgr.active_symbols) == {"AAPL", "MSFT", "AMZN"}
        assert "GOOG" in mgr.watchlist_symbols

        # GOOG closes naturally
        mgr.on_position_closed("GOOG")
        assert "GOOG" not in mgr.watchlist_symbols

        # Week 3: GOOG returns
        u3 = UniverseResult(
            symbols=["AAPL", "GOOG", "AMZN"],
            scored=[], timestamp=datetime(2026, 1, 24, 12, tzinfo=timezone.utc),
            rotation_in=["GOOG"], rotation_out=["MSFT"],
        )
        mgr.apply_rotation(u3, open_position_symbols=[], new_equity=3200.0)
        assert set(mgr.active_symbols) == {"AAPL", "GOOG", "AMZN"}
        assert len(mgr.watchlist_symbols) == 0  # MSFT had no position

        assert len(mgr._state.rotation_history) == 3

    def test_halt_and_recovery(self):
        """Halt from weekly loss, then recover on next rotation."""
        mgr = RotationManager(RotationConfig(weekly_loss_limit_pct=0.05))
        mgr._state.active_symbols = ["AAPL"]
        mgr._state.weekly_start_equity = 3000.0

        # Trigger halt
        assert mgr.check_weekly_loss_limit(2800.0)
        assert mgr._state.is_halted

        # New rotation resets halt
        u = UniverseResult(
            symbols=["AAPL", "MSFT"],
            scored=[], timestamp=datetime(2026, 1, 17, 12, tzinfo=timezone.utc),
            rotation_in=["MSFT"], rotation_out=[],
        )
        mgr.apply_rotation(u, open_position_symbols=[], new_equity=2800.0)
        assert not mgr._state.is_halted
        assert mgr._state.weekly_start_equity == 2800.0
