import pytest
from datetime import datetime, timezone
from autotrader.portfolio.regime_tracker import RegimeTracker, RegimeTransition
from autotrader.portfolio.regime_detector import MarketRegime


class TestRegimeTransition:
    def test_create_transition(self):
        now = datetime.now(timezone.utc)
        t = RegimeTransition(
            previous=MarketRegime.UNCERTAIN,
            current=MarketRegime.TREND_UP,
            timestamp=now,
            bars_in_new_regime=3,
        )
        assert t.previous == MarketRegime.UNCERTAIN
        assert t.current == MarketRegime.TREND_UP
        assert t.bars_in_new_regime == 3

    def test_transition_is_frozen(self):
        now = datetime.now(timezone.utc)
        t = RegimeTransition(
            previous=MarketRegime.UNCERTAIN,
            current=MarketRegime.TREND_UP,
            timestamp=now,
            bars_in_new_regime=3,
        )
        with pytest.raises(AttributeError):
            t.current = MarketRegime.RANGING


class TestRegimeTracker:
    def test_initial_state(self):
        tracker = RegimeTracker(confirmation_bars=3)
        assert tracker.confirmed_regime == MarketRegime.UNCERTAIN
        assert tracker.history == []

    def test_same_regime_no_transition(self):
        tracker = RegimeTracker(confirmation_bars=3)
        now = datetime.now(timezone.utc)
        result = tracker.update(MarketRegime.UNCERTAIN, now)
        assert result is None

    def test_new_regime_not_confirmed_until_threshold(self):
        tracker = RegimeTracker(confirmation_bars=3)
        now = datetime.now(timezone.utc)
        # 1st bar of TREND_UP - not confirmed yet
        assert tracker.update(MarketRegime.TREND_UP, now) is None
        assert tracker.confirmed_regime == MarketRegime.UNCERTAIN
        # 2nd bar of TREND_UP - still not confirmed
        assert tracker.update(MarketRegime.TREND_UP, now) is None
        assert tracker.confirmed_regime == MarketRegime.UNCERTAIN

    def test_confirmed_after_n_bars(self):
        tracker = RegimeTracker(confirmation_bars=3)
        now = datetime.now(timezone.utc)
        tracker.update(MarketRegime.TREND_UP, now)
        tracker.update(MarketRegime.TREND_UP, now)
        result = tracker.update(MarketRegime.TREND_UP, now)
        assert result is not None
        assert result.previous == MarketRegime.UNCERTAIN
        assert result.current == MarketRegime.TREND_UP
        assert result.bars_in_new_regime == 3
        assert tracker.confirmed_regime == MarketRegime.TREND_UP

    def test_flickering_resets_counter(self):
        tracker = RegimeTracker(confirmation_bars=3)
        now = datetime.now(timezone.utc)
        # 2 bars of TREND_UP, then back to UNCERTAIN
        tracker.update(MarketRegime.TREND_UP, now)
        tracker.update(MarketRegime.TREND_UP, now)
        tracker.update(MarketRegime.UNCERTAIN, now)  # reset!
        # Now need 3 fresh bars of TREND_UP
        tracker.update(MarketRegime.TREND_UP, now)
        assert tracker.confirmed_regime == MarketRegime.UNCERTAIN
        tracker.update(MarketRegime.TREND_UP, now)
        result = tracker.update(MarketRegime.TREND_UP, now)
        assert result is not None
        assert tracker.confirmed_regime == MarketRegime.TREND_UP

    def test_history_records_transitions(self):
        tracker = RegimeTracker(confirmation_bars=2)
        now = datetime.now(timezone.utc)
        # UNCERTAIN -> TREND_UP
        tracker.update(MarketRegime.TREND_UP, now)
        tracker.update(MarketRegime.TREND_UP, now)
        # TREND_UP -> RANGING
        tracker.update(MarketRegime.RANGING, now)
        tracker.update(MarketRegime.RANGING, now)
        assert len(tracker.history) == 2
        assert tracker.history[0].current == MarketRegime.TREND_UP
        assert tracker.history[1].current == MarketRegime.RANGING

    def test_confirmation_bars_one(self):
        """With confirmation_bars=1, first different bar triggers transition."""
        tracker = RegimeTracker(confirmation_bars=1)
        now = datetime.now(timezone.utc)
        result = tracker.update(MarketRegime.TREND_UP, now)
        assert result is not None
        assert tracker.confirmed_regime == MarketRegime.TREND_UP

    def test_default_confirmation_bars_is_one(self):
        """Default confirmation_bars should be 1 (passthrough mode)."""
        tracker = RegimeTracker()
        assert tracker._confirmation_bars == 1
