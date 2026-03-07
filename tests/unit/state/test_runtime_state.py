"""Tests for RuntimeState unified persistence."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from autotrader.state.runtime_state import RuntimeState, bootstrap_from_broker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeComponent:
    """Minimal snapshottable component for testing."""

    def __init__(self, value: int = 0):
        self.value = value

    def to_snapshot(self) -> dict:
        return {"value": self.value}

    def from_snapshot(self, data: dict) -> None:
        self.value = int(data.get("value", 0))


class BrokenComponent:
    """Component whose to_snapshot raises."""

    def to_snapshot(self) -> dict:
        raise RuntimeError("snapshot failed")

    def from_snapshot(self, data: dict) -> None:
        raise RuntimeError("restore failed")


# ---------------------------------------------------------------------------
# RuntimeState save/load round-trip
# ---------------------------------------------------------------------------

class TestRuntimeStateSaveLoad:

    def test_round_trip(self, tmp_path: Path) -> None:
        """Save and load should produce identical snapshots."""
        state_path = tmp_path / "state.json"
        rs = RuntimeState(path=state_path)

        comp_a = FakeComponent(value=42)
        comp_b = FakeComponent(value=99)
        rs.save({"a": comp_a, "b": comp_b})

        loaded = rs.load()
        assert loaded == {"a": {"value": 42}, "b": {"value": 99}}

    def test_exists_property(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        rs = RuntimeState(path=state_path)
        assert rs.exists is False

        rs.save({"x": FakeComponent(1)})
        assert rs.exists is True

    def test_atomic_write_no_tmp_leftover(self, tmp_path: Path) -> None:
        """After save, no .tmp file should remain on disk."""
        state_path = tmp_path / "state.json"
        rs = RuntimeState(path=state_path)

        rs.save({"a": FakeComponent(10)})

        tmp_file = state_path.with_suffix(".tmp")
        assert not tmp_file.exists(), ".tmp file should be removed after atomic rename"
        assert state_path.exists()

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """Loading from a nonexistent file returns empty dict."""
        state_path = tmp_path / "nonexistent.json"
        rs = RuntimeState(path=state_path)
        assert rs.load() == {}

    def test_load_corrupted_file_returns_empty(self, tmp_path: Path) -> None:
        """Loading from a corrupted JSON file returns empty dict."""
        state_path = tmp_path / "state.json"
        state_path.write_text("not valid json {{{{", encoding="utf-8")

        rs = RuntimeState(path=state_path)
        assert rs.load() == {}

    def test_load_empty_file_returns_empty(self, tmp_path: Path) -> None:
        """Loading from an empty file returns empty dict."""
        state_path = tmp_path / "state.json"
        state_path.write_text("", encoding="utf-8")

        rs = RuntimeState(path=state_path)
        assert rs.load() == {}

    def test_save_handles_snapshot_exception(self, tmp_path: Path) -> None:
        """A broken component should not prevent other components from saving."""
        state_path = tmp_path / "state.json"
        rs = RuntimeState(path=state_path)

        rs.save({"good": FakeComponent(5), "broken": BrokenComponent()})

        loaded = rs.load()
        assert "good" in loaded
        assert loaded["good"] == {"value": 5}
        assert "broken" not in loaded

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Save should create parent directories if they don't exist."""
        state_path = tmp_path / "deep" / "nested" / "state.json"
        rs = RuntimeState(path=state_path)

        rs.save({"a": FakeComponent(1)})
        assert state_path.exists()


# ---------------------------------------------------------------------------
# RuntimeState restore
# ---------------------------------------------------------------------------

class TestRuntimeStateRestore:

    def test_restore_updates_components(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        rs = RuntimeState(path=state_path)

        comp = FakeComponent(value=0)
        snapshots = {"comp": {"value": 77}}

        rs.restore({"comp": comp}, snapshots)
        assert comp.value == 77

    def test_restore_missing_snapshot_leaves_component_unchanged(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"
        rs = RuntimeState(path=state_path)

        comp = FakeComponent(value=42)
        rs.restore({"comp": comp}, {})
        assert comp.value == 42

    def test_restore_handles_exception(self, tmp_path: Path) -> None:
        """A broken component should not prevent other components from restoring."""
        state_path = tmp_path / "state.json"
        rs = RuntimeState(path=state_path)

        good = FakeComponent(value=0)
        broken = BrokenComponent()
        snapshots = {"good": {"value": 55}, "broken": {"x": 1}}

        rs.restore({"good": good, "broken": broken}, snapshots)
        assert good.value == 55  # good one restored despite broken one failing


# ---------------------------------------------------------------------------
# GDREngine snapshot
# ---------------------------------------------------------------------------

class TestGDREngineSnapshot:

    def test_round_trip(self) -> None:
        from autotrader.trading.gdr_engine import GDREngine

        engine = GDREngine(initial_capital=10000.0)
        engine.record_trade_pnl("breakout_momentum", -200.0)
        engine.record_trade_pnl("rsi_mean_reversion", 150.0)

        snap = engine.to_snapshot()

        engine2 = GDREngine(initial_capital=10000.0)
        engine2.from_snapshot(snap)

        assert engine2._strategy_cumulative_pnl == engine._strategy_cumulative_pnl
        assert engine2._strategy_peak_pnl == engine._strategy_peak_pnl
        assert engine2._strategy_tiers == engine._strategy_tiers
        assert engine2._portfolio_peak == engine._portfolio_peak
        assert engine2._realized_pnl == engine._realized_pnl
        assert engine2._safety_net_active == engine._safety_net_active

    def test_from_snapshot_handles_missing_keys(self) -> None:
        from autotrader.trading.gdr_engine import GDREngine

        engine = GDREngine(initial_capital=5000.0)
        engine.from_snapshot({})

        assert engine._strategy_cumulative_pnl == {}
        assert engine._strategy_peak_pnl == {}
        assert engine._strategy_tiers == {}
        assert engine._portfolio_peak == 5000.0  # falls back to initial_capital
        assert engine._realized_pnl == 0.0
        assert engine._safety_net_active is False

    def test_strategy_tiers_cast_to_int(self) -> None:
        from autotrader.trading.gdr_engine import GDREngine

        engine = GDREngine(initial_capital=10000.0)
        engine.from_snapshot({"strategy_tiers": {"bm": "1", "mr": "2"}})
        assert engine._strategy_tiers == {"bm": 1, "mr": 2}
        assert all(isinstance(v, int) for v in engine._strategy_tiers.values())


# ---------------------------------------------------------------------------
# GDRManager snapshot
# ---------------------------------------------------------------------------

class TestGDRManagerSnapshot:

    def test_round_trip(self) -> None:
        from autotrader.risk.gdr_manager import GDRManager

        mgr = GDRManager(
            strategy_names=["breakout_momentum", "rsi_mean_reversion"],
            initial_capital=10000.0,
        )
        mgr.record_trade_pnl("breakout_momentum", -300.0)
        mgr.record_entry("breakout_momentum")
        mgr.record_entry("rsi_mean_reversion")

        snap = mgr.to_snapshot()

        mgr2 = GDRManager(
            strategy_names=["breakout_momentum", "rsi_mean_reversion"],
            initial_capital=10000.0,
        )
        mgr2.from_snapshot(snap)

        assert mgr2._entries_today == mgr._entries_today
        assert mgr2._total_entries_today == mgr._total_entries_today
        assert mgr2._cumulative_pnl == mgr._cumulative_pnl
        # Verify engine state was also restored
        assert mgr2._engine._realized_pnl == mgr._engine._realized_pnl


# ---------------------------------------------------------------------------
# RiskManager snapshot
# ---------------------------------------------------------------------------

class TestRiskManagerSnapshot:

    def test_round_trip(self) -> None:
        from autotrader.core.config import RiskConfig
        from autotrader.risk.manager import RiskManager

        cfg = RiskConfig()
        rm = RiskManager(cfg)
        rm._peak_equity = 10000.0
        rm._current_equity = 9500.0
        rm._daily_pnl = -200.0

        snap = rm.to_snapshot()

        rm2 = RiskManager(cfg)
        rm2.from_snapshot(snap)

        assert rm2._peak_equity == 10000.0
        assert rm2._current_equity == 9500.0
        assert rm2._daily_pnl == -200.0

    def test_from_snapshot_handles_missing_keys(self) -> None:
        from autotrader.core.config import RiskConfig
        from autotrader.risk.manager import RiskManager

        cfg = RiskConfig()
        rm = RiskManager(cfg)
        rm.from_snapshot({})
        assert rm._peak_equity == 0.0
        assert rm._daily_pnl == 0.0
        assert rm._current_equity == 0.0


# ---------------------------------------------------------------------------
# EntryManager snapshot
# ---------------------------------------------------------------------------

class TestEntryManagerSnapshot:

    def _make_entry_manager(self):
        """Create an EntryManager with mock dependencies."""
        from autotrader.execution.entry_manager import EntryManager

        return EntryManager(
            order_manager=MagicMock(),
            allocation_engine=MagicMock(),
            risk_manager=MagicMock(),
            exit_rule_engine=MagicMock(),
        )

    def test_round_trip(self) -> None:
        em = self._make_entry_manager()
        em._daily_entry_count = 3
        em._last_entry_date = date(2026, 3, 5)

        snap = em.to_snapshot()

        em2 = self._make_entry_manager()
        em2.from_snapshot(snap)

        assert em2._daily_entry_count == 3
        assert em2._last_entry_date == date(2026, 3, 5)

    def test_from_snapshot_handles_null_date(self) -> None:
        em = self._make_entry_manager()
        em.from_snapshot({"daily_entry_count": 1, "last_entry_date": None})
        assert em._daily_entry_count == 1
        assert em._last_entry_date is None

    def test_from_snapshot_handles_missing_keys(self) -> None:
        em = self._make_entry_manager()
        em._daily_entry_count = 5
        em.from_snapshot({})
        assert em._daily_entry_count == 0
        assert em._last_entry_date is None


# ---------------------------------------------------------------------------
# ExitRuleEngine snapshot
# ---------------------------------------------------------------------------

class TestExitRuleEngineSnapshot:

    def test_round_trip(self) -> None:
        from autotrader.execution.exit_rules import ExitRuleEngine

        ere = ExitRuleEngine()
        ere._unified._closed_today = {"AAPL", "MSFT"}
        ere._unified._last_clear_date = date(2026, 3, 5)

        snap = ere.to_snapshot()

        ere2 = ExitRuleEngine()
        ere2.from_snapshot(snap)

        assert ere2._unified._closed_today == {"AAPL", "MSFT"}
        assert ere2._unified._last_clear_date == date(2026, 3, 5)

    def test_from_snapshot_handles_null_date(self) -> None:
        from autotrader.execution.exit_rules import ExitRuleEngine

        ere = ExitRuleEngine()
        ere.from_snapshot({"closed_today": ["TSLA"], "last_clear_date": None})
        assert ere._unified._closed_today == {"TSLA"}
        assert ere._unified._last_clear_date is None

    def test_from_snapshot_handles_missing_keys(self) -> None:
        from autotrader.execution.exit_rules import ExitRuleEngine

        ere = ExitRuleEngine()
        ere._unified._closed_today = {"NVDA"}
        ere.from_snapshot({})
        assert ere._unified._closed_today == set()
        assert ere._unified._last_clear_date is None


# ---------------------------------------------------------------------------
# Full end-to-end RuntimeState with real components
# ---------------------------------------------------------------------------

class TestRuntimeStateEndToEnd:

    def test_full_pipeline_save_restore(self, tmp_path: Path) -> None:
        """Save all real components, then restore into fresh instances."""
        from autotrader.core.config import RiskConfig
        from autotrader.execution.exit_rules import ExitRuleEngine
        from autotrader.risk.gdr_manager import GDRManager
        from autotrader.risk.manager import RiskManager

        state_path = tmp_path / "runtime_state.json"
        rs = RuntimeState(path=state_path)

        # Set up components with state
        gdr = GDRManager(["breakout_momentum"], initial_capital=10000.0)
        gdr.record_trade_pnl("breakout_momentum", -500.0)
        gdr.record_entry("breakout_momentum")

        risk = RiskManager(RiskConfig(
            max_open_positions=5,
            daily_loss_limit_pct=0.03,
            max_drawdown_pct=0.10,
        ))
        risk._peak_equity = 10000.0
        risk._current_equity = 9700.0
        risk._daily_pnl = -100.0

        exit_eng = ExitRuleEngine()
        exit_eng._unified._closed_today = {"AAPL", "GOOG"}
        exit_eng._unified._last_clear_date = date(2026, 3, 5)

        components = {
            "gdr_manager": gdr,
            "risk_manager": risk,
            "exit_rules": exit_eng,
        }

        # Save
        rs.save(components)
        assert state_path.exists()

        # Verify JSON structure
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        assert "gdr_manager" in raw
        assert "risk_manager" in raw
        assert "exit_rules" in raw

        # Restore into fresh components
        gdr2 = GDRManager(["breakout_momentum"], initial_capital=10000.0)
        risk2 = RiskManager(RiskConfig(
            max_open_positions=5,
            daily_loss_limit_pct=0.03,
            max_drawdown_pct=0.10,
        ))
        exit_eng2 = ExitRuleEngine()

        components2 = {
            "gdr_manager": gdr2,
            "risk_manager": risk2,
            "exit_rules": exit_eng2,
        }

        snapshots = rs.load()
        rs.restore(components2, snapshots)

        # Verify restored state matches originals
        assert gdr2._engine._realized_pnl == -500.0
        assert gdr2._entries_today["breakout_momentum"] == 1
        assert risk2._peak_equity == 10000.0
        assert risk2._current_equity == 9700.0
        assert risk2._daily_pnl == -100.0
        assert exit_eng2._unified._closed_today == {"AAPL", "GOOG"}
        assert exit_eng2._unified._last_clear_date == date(2026, 3, 5)


# ---------------------------------------------------------------------------
# bootstrap_from_broker
# ---------------------------------------------------------------------------

class TestBootstrapFromBroker:

    @pytest.mark.asyncio
    async def test_bootstrap_with_positions(self, tmp_path: Path) -> None:
        """Bootstrap should create HeldPositions from broker positions."""
        broker = AsyncMock()
        pos1 = MagicMock()
        pos1.symbol = "AAPL"
        pos1.side = "long"
        pos1.avg_entry_price = 150.0
        pos1.quantity = 10.0

        pos2 = MagicMock()
        pos2.symbol = "MSFT"
        pos2.side = "short"
        pos2.avg_entry_price = 300.0
        pos2.quantity = 5.0

        broker.get_positions.return_value = [pos1, pos2]

        positions = await bootstrap_from_broker(
            broker, state_path=tmp_path / "state.json",
        )

        assert "AAPL" in positions
        assert "MSFT" in positions
        assert positions["AAPL"].direction == "long"
        assert positions["AAPL"].entry_price == 150.0
        assert positions["AAPL"].qty == 10.0
        assert positions["MSFT"].direction == "short"
        assert positions["MSFT"].entry_price == 300.0

    @pytest.mark.asyncio
    async def test_bootstrap_no_positions(self, tmp_path: Path) -> None:
        """Bootstrap with no broker positions returns empty dict."""
        broker = AsyncMock()
        broker.get_positions.return_value = []

        positions = await bootstrap_from_broker(
            broker, state_path=tmp_path / "state.json",
        )
        assert positions == {}

    @pytest.mark.asyncio
    async def test_bootstrap_broker_failure(self, tmp_path: Path) -> None:
        """Bootstrap should handle broker connection failure gracefully."""
        broker = AsyncMock()
        broker.get_positions.side_effect = ConnectionError("broker down")

        positions = await bootstrap_from_broker(
            broker, state_path=tmp_path / "state.json",
        )
        assert positions == {}

    @pytest.mark.asyncio
    async def test_bootstrap_partial_failure(self, tmp_path: Path) -> None:
        """If one position fails to register, others should still succeed."""
        broker = AsyncMock()
        good_pos = MagicMock()
        good_pos.symbol = "AAPL"
        good_pos.side = "long"
        good_pos.avg_entry_price = 150.0
        good_pos.quantity = 10.0

        bad_pos = MagicMock()
        bad_pos.symbol = "BAD"
        bad_pos.side = "long"
        bad_pos.avg_entry_price = None  # will cause float() to fail
        bad_pos.quantity = 5.0

        broker.get_positions.return_value = [good_pos, bad_pos]

        positions = await bootstrap_from_broker(
            broker, state_path=tmp_path / "state.json",
        )

        assert "AAPL" in positions
        # BAD may or may not be in positions depending on whether
        # HeldPosition constructor raises -- the point is no crash
