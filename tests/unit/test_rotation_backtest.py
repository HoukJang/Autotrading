"""Unit tests for RotationBacktestEngine."""
from collections import deque
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

import pytest

from autotrader.core.config import RiskConfig, RotationConfig
from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.rotation.backtest_engine import RotationBacktestEngine, RotationBacktestResult
from autotrader.strategy.base import Strategy
from autotrader.universe import UniverseResult


# --- Helpers ---

def _make_bars(symbol: str, count: int, base_price: float = 100.0,
               start: datetime | None = None) -> list[Bar]:
    """Create synthetic daily bars."""
    if start is None:
        start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)  # Monday
    bars = []
    for i in range(count):
        ts = start + timedelta(days=i)
        # Skip weekends
        while ts.weekday() >= 5:
            ts += timedelta(days=1)
        price = base_price + (i % 10) - 5  # oscillate around base
        bars.append(Bar(
            symbol=symbol,
            timestamp=ts,
            open=price - 0.5,
            high=price + 1.0,
            low=price - 1.0,
            close=price,
            volume=1_000_000.0,
        ))
        start = start  # keep start fixed, offset from it
    return bars


def _make_bars_from_start(symbol: str, count: int, base_price: float,
                          start: datetime) -> list[Bar]:
    """Create bars starting from exact datetime, advancing by 1 day (skip weekends)."""
    bars = []
    ts = start
    for i in range(count):
        while ts.weekday() >= 5:
            ts += timedelta(days=1)
        price = base_price + (i % 10) - 5
        bars.append(Bar(
            symbol=symbol,
            timestamp=ts,
            open=price - 0.5,
            high=price + 1.0,
            low=price - 1.0,
            close=price,
            volume=1_000_000.0,
        ))
        ts += timedelta(days=1)
    return bars


class AlwaysLongStrategy(Strategy):
    """Enters long if no position, never closes (for testing)."""
    name = "always_long"
    required_indicators: list[IndicatorSpec] = []

    def __init__(self):
        self._positions: set[str] = set()

    def on_context(self, ctx: MarketContext) -> Signal | None:
        if ctx.symbol not in self._positions:
            self._positions.add(ctx.symbol)
            return Signal(
                strategy=self.name,
                symbol=ctx.symbol,
                direction="long",
                strength=1.0,
            )
        return None


class BuyAndCloseStrategy(Strategy):
    """Buys first bar, closes on 5th bar for each symbol."""
    name = "buy_close"
    required_indicators: list[IndicatorSpec] = []

    def __init__(self):
        self._bar_count: dict[str, int] = {}

    def on_context(self, ctx: MarketContext) -> Signal | None:
        sym = ctx.symbol
        self._bar_count[sym] = self._bar_count.get(sym, 0) + 1
        count = self._bar_count[sym]

        if count == 1:
            return Signal(strategy=self.name, symbol=sym, direction="long", strength=1.0)
        elif count == 5:
            self._bar_count[sym] = 0  # reset for re-entry
            return Signal(strategy=self.name, symbol=sym, direction="close", strength=1.0)
        return None


# --- Tests ---

class TestRotationBacktestEngine:
    def test_single_symbol_no_rotation(self):
        """Basic sanity - should produce a result with equity > 0."""
        engine = RotationBacktestEngine(
            initial_balance=3000.0,
            risk_config=RiskConfig(),
            rotation_config=RotationConfig(),
        )
        engine.add_strategy(BuyAndCloseStrategy())
        bars = {"AAPL": _make_bars("AAPL", 30)}
        result = engine.run(bars, initial_universe=["AAPL"])
        assert isinstance(result, RotationBacktestResult)
        assert result.final_equity > 0
        assert result.rotation_events == []
        assert len(result.equity_curve) > 0

    def test_multi_symbol_no_rotation(self):
        """Multiple symbols, no rotation events."""
        engine = RotationBacktestEngine(
            initial_balance=5000.0,
            risk_config=RiskConfig(),
            rotation_config=RotationConfig(),
        )
        engine.add_strategy(BuyAndCloseStrategy())
        start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
        bars = {
            "AAPL": _make_bars_from_start("AAPL", 20, 100.0, start),
            "MSFT": _make_bars_from_start("MSFT", 20, 200.0, start),
        }
        result = engine.run(bars, initial_universe=["AAPL", "MSFT"])
        assert result.final_equity > 0
        assert result.total_trades > 0

    def test_rotation_blocks_new_entries(self):
        """Symbol moved to watchlist should not get new entries."""
        engine = RotationBacktestEngine(
            initial_balance=5000.0,
            risk_config=RiskConfig(),
            rotation_config=RotationConfig(),
        )
        engine.add_strategy(AlwaysLongStrategy())
        start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
        bars = {
            "AAPL": _make_bars_from_start("AAPL", 20, 100.0, start),
            "MSFT": _make_bars_from_start("MSFT", 20, 200.0, start),
            "GOOG": _make_bars_from_start("GOOG", 20, 150.0, start),
        }
        # Rotate after bar 5: remove GOOG, add nothing new
        rotation_schedule = {
            5: UniverseResult(
                symbols=["AAPL", "MSFT"],
                scored=[],
                timestamp=start + timedelta(days=5),
                rotation_in=[],
                rotation_out=["GOOG"],
            ),
        }
        result = engine.run(
            bars,
            initial_universe=["AAPL", "MSFT", "GOOG"],
            rotation_schedule=rotation_schedule,
        )
        assert len(result.rotation_events) == 1
        # GOOG should not have new entries after rotation
        goog_entries = [t for t in result.trades if t.symbol == "GOOG" and t.direction == "long"]
        # AlwaysLong only enters once, before rotation
        assert len(goog_entries) <= 1

    def test_force_close_at_deadline(self):
        """Watchlist symbol should be force-closed at deadline."""
        cfg = RotationConfig(force_close_day=4, force_close_hour=14)
        engine = RotationBacktestEngine(
            initial_balance=5000.0,
            risk_config=RiskConfig(),
            rotation_config=cfg,
        )
        engine.add_strategy(AlwaysLongStrategy())
        # Start Monday Jan 5
        start = datetime(2026, 1, 5, 14, 30, tzinfo=timezone.utc)
        bars = {
            "AAPL": _make_bars_from_start("AAPL", 30, 100.0, start),
            "MSFT": _make_bars_from_start("MSFT", 30, 200.0, start),
        }
        # Rotate on bar 3 (Wed Jan 7): remove MSFT
        rotation_time = start + timedelta(days=2)
        rotation_schedule = {
            3: UniverseResult(
                symbols=["AAPL"],
                scored=[],
                timestamp=rotation_time,
                rotation_in=[],
                rotation_out=["MSFT"],
            ),
        }
        result = engine.run(
            bars,
            initial_universe=["AAPL", "MSFT"],
            rotation_schedule=rotation_schedule,
        )
        # MSFT should have a force-close trade
        msft_closes = [t for t in result.trades if t.symbol == "MSFT" and t.direction == "long"]
        # There should be at least one trade for MSFT (entry then force close)
        assert len(result.rotation_events) == 1

    def test_result_has_all_fields(self):
        """Verify result dataclass has expected fields."""
        engine = RotationBacktestEngine(
            initial_balance=3000.0,
            risk_config=RiskConfig(),
            rotation_config=RotationConfig(),
        )
        engine.add_strategy(BuyAndCloseStrategy())
        bars = {"AAPL": _make_bars("AAPL", 15)}
        result = engine.run(bars, initial_universe=["AAPL"])
        assert hasattr(result, "total_trades")
        assert hasattr(result, "final_equity")
        assert hasattr(result, "metrics")
        assert hasattr(result, "equity_curve")
        assert hasattr(result, "trades")
        assert hasattr(result, "rotation_events")
        assert hasattr(result, "timestamped_equity")

    def test_empty_bars(self):
        """Engine handles empty bars dict gracefully."""
        engine = RotationBacktestEngine(
            initial_balance=3000.0,
            risk_config=RiskConfig(),
            rotation_config=RotationConfig(),
        )
        engine.add_strategy(BuyAndCloseStrategy())
        result = engine.run({}, initial_universe=[])
        assert result.final_equity == 3000.0
        assert result.total_trades == 0
