"""Unit tests for event-driven rotation triggers."""
import pytest
from datetime import datetime, timedelta, timezone

from autotrader.rotation.event_driven import EventDrivenRotation
from autotrader.portfolio.regime_detector import MarketRegime


def _make_transition(prev: MarketRegime, curr: MarketRegime, ts=None):
    """Helper to create a RegimeTransition for testing."""
    from autotrader.portfolio.regime_tracker import RegimeTransition

    if ts is None:
        ts = datetime.now(timezone.utc)
    return RegimeTransition(
        previous=prev, current=curr, timestamp=ts, bars_in_new_regime=3
    )


class TestEventDrivenRotation:
    """Tests for EventDrivenRotation trigger logic."""

    def test_trigger_on_trend_to_high_vol(self):
        """Regime transition TREND->HIGH_VOLATILITY should trigger rotation."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["TREND->HIGH_VOLATILITY"],
        )
        transition = _make_transition(MarketRegime.TREND, MarketRegime.HIGH_VOLATILITY)
        should, reason = edr.should_trigger_rotation(transition=transition)
        assert should is True
        assert "TREND->HIGH_VOLATILITY" in reason

    def test_no_trigger_on_unmatched_transition(self):
        """Transition not in regime_triggers should not trigger."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["TREND->HIGH_VOLATILITY"],
        )
        transition = _make_transition(MarketRegime.UNCERTAIN, MarketRegime.TREND)
        should, reason = edr.should_trigger_rotation(transition=transition)
        assert should is False

    def test_wildcard_trigger(self):
        """'*->UNCERTAIN' should match any previous regime."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["*->UNCERTAIN"],
        )
        transition = _make_transition(MarketRegime.TREND, MarketRegime.UNCERTAIN)
        should, reason = edr.should_trigger_rotation(transition=transition)
        assert should is True
        assert "*->UNCERTAIN" in reason

    def test_wildcard_from_ranging(self):
        """'*->UNCERTAIN' should also match RANGING as previous regime."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["*->UNCERTAIN"],
        )
        transition = _make_transition(MarketRegime.RANGING, MarketRegime.UNCERTAIN)
        should, reason = edr.should_trigger_rotation(transition=transition)
        assert should is True

    def test_wildcard_target(self):
        """'TREND->*' should match any target regime."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["TREND->*"],
        )
        transition = _make_transition(MarketRegime.TREND, MarketRegime.RANGING)
        should, reason = edr.should_trigger_rotation(transition=transition)
        assert should is True
        assert "TREND->*" in reason

    def test_cooldown_blocks_trigger(self):
        """Trigger within cooldown period should be blocked."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["TREND->HIGH_VOLATILITY"],
        )
        # Mark as recently triggered
        edr.mark_triggered()
        transition = _make_transition(MarketRegime.TREND, MarketRegime.HIGH_VOLATILITY)
        should, reason = edr.should_trigger_rotation(transition=transition)
        assert should is False
        assert "cooldown" in reason.lower()

    def test_cooldown_expires(self):
        """After cooldown expires, trigger should work again."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["TREND->HIGH_VOLATILITY"],
        )
        # Set triggered long ago
        edr._last_triggered = datetime.now(timezone.utc) - timedelta(hours=49)
        transition = _make_transition(MarketRegime.TREND, MarketRegime.HIGH_VOLATILITY)
        should, reason = edr.should_trigger_rotation(transition=transition)
        assert should is True

    def test_vix_spike_triggers(self):
        """VIX above threshold should trigger rotation."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=[],
        )
        should, reason = edr.should_trigger_rotation(vix_value=35.0)
        assert should is True
        assert "VIX" in reason

    def test_vix_below_threshold_no_trigger(self):
        """VIX below threshold should not trigger."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=[],
        )
        should, reason = edr.should_trigger_rotation(vix_value=25.0)
        assert should is False

    def test_vix_exactly_at_threshold_triggers(self):
        """VIX exactly at threshold should trigger (>= comparison)."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=[],
        )
        should, reason = edr.should_trigger_rotation(vix_value=30.0)
        assert should is True

    def test_disabled_never_triggers(self):
        """When disabled, no trigger should fire regardless of conditions."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["TREND->HIGH_VOLATILITY"],
            enabled=False,
        )
        transition = _make_transition(MarketRegime.TREND, MarketRegime.HIGH_VOLATILITY)
        should, reason = edr.should_trigger_rotation(transition=transition)
        assert should is False
        assert "disabled" in reason.lower()

    def test_disabled_blocks_vix(self):
        """When disabled, VIX spike should not trigger either."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=[],
            enabled=False,
        )
        should, reason = edr.should_trigger_rotation(vix_value=50.0)
        assert should is False

    def test_no_args_no_trigger(self):
        """Calling with no arguments should not trigger."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["TREND->HIGH_VOLATILITY"],
        )
        should, reason = edr.should_trigger_rotation()
        assert should is False

    def test_mark_triggered_sets_timestamp(self):
        """mark_triggered should record the current time."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=[],
        )
        assert edr._last_triggered is None
        edr.mark_triggered()
        assert edr._last_triggered is not None
        # Should be very recent
        elapsed = datetime.now(timezone.utc) - edr._last_triggered
        assert elapsed.total_seconds() < 2.0

    def test_multiple_regime_triggers(self):
        """Multiple configured triggers should all be checked."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=[
                "TREND->HIGH_VOLATILITY",
                "RANGING->HIGH_VOLATILITY",
                "*->UNCERTAIN",
            ],
        )
        # First trigger
        t1 = _make_transition(MarketRegime.TREND, MarketRegime.HIGH_VOLATILITY)
        should1, reason1 = edr.should_trigger_rotation(transition=t1)
        assert should1 is True
        assert "TREND->HIGH_VOLATILITY" in reason1

        # Second trigger
        t2 = _make_transition(MarketRegime.RANGING, MarketRegime.HIGH_VOLATILITY)
        should2, reason2 = edr.should_trigger_rotation(transition=t2)
        assert should2 is True
        assert "RANGING->HIGH_VOLATILITY" in reason2

        # Third trigger (wildcard)
        t3 = _make_transition(MarketRegime.HIGH_VOLATILITY, MarketRegime.UNCERTAIN)
        should3, reason3 = edr.should_trigger_rotation(transition=t3)
        assert should3 is True
        assert "*->UNCERTAIN" in reason3

    def test_both_transition_and_vix_returns_transition_reason(self):
        """When both transition and VIX match, regime transition is checked first."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["TREND->HIGH_VOLATILITY"],
        )
        transition = _make_transition(MarketRegime.TREND, MarketRegime.HIGH_VOLATILITY)
        should, reason = edr.should_trigger_rotation(
            transition=transition, vix_value=35.0
        )
        assert should is True
        # Regime transition is checked first
        assert "TREND->HIGH_VOLATILITY" in reason

    def test_malformed_trigger_pattern_skipped(self):
        """Trigger patterns without '->' delimiter should be safely skipped."""
        edr = EventDrivenRotation(
            cooldown_hours=48,
            vix_spike_trigger=30.0,
            regime_triggers=["INVALID_PATTERN", "TREND->HIGH_VOLATILITY"],
        )
        transition = _make_transition(MarketRegime.TREND, MarketRegime.HIGH_VOLATILITY)
        should, reason = edr.should_trigger_rotation(transition=transition)
        assert should is True
        assert "TREND->HIGH_VOLATILITY" in reason

    def test_cooldown_zero_hours(self):
        """With zero cooldown, repeated triggers should always work."""
        edr = EventDrivenRotation(
            cooldown_hours=0,
            vix_spike_trigger=30.0,
            regime_triggers=["TREND->HIGH_VOLATILITY"],
        )
        edr.mark_triggered()
        transition = _make_transition(MarketRegime.TREND, MarketRegime.HIGH_VOLATILITY)
        should, reason = edr.should_trigger_rotation(transition=transition)
        assert should is True


class TestEventDrivenRotationConfig:
    """Tests for EventDrivenRotationConfig in config.py."""

    def test_defaults(self):
        from autotrader.core.config import EventDrivenRotationConfig

        cfg = EventDrivenRotationConfig()
        assert cfg.enable_event_driven is True
        assert cfg.cooldown_hours == 48
        assert cfg.vix_spike_trigger == 30.0
        assert len(cfg.regime_triggers) == 3

    def test_default_trigger_values(self):
        from autotrader.core.config import EventDrivenRotationConfig

        cfg = EventDrivenRotationConfig()
        assert "TREND->HIGH_VOLATILITY" in cfg.regime_triggers
        assert "RANGING->HIGH_VOLATILITY" in cfg.regime_triggers
        assert "*->UNCERTAIN" in cfg.regime_triggers

    def test_custom_values(self):
        from autotrader.core.config import EventDrivenRotationConfig

        cfg = EventDrivenRotationConfig(
            enable_event_driven=False,
            cooldown_hours=24,
            regime_triggers=["TREND->RANGING"],
        )
        assert cfg.enable_event_driven is False
        assert cfg.cooldown_hours == 24
        assert len(cfg.regime_triggers) == 1

    def test_custom_vix_threshold(self):
        from autotrader.core.config import EventDrivenRotationConfig

        cfg = EventDrivenRotationConfig(vix_spike_trigger=25.0)
        assert cfg.vix_spike_trigger == 25.0

    def test_settings_has_event_rotation(self):
        from autotrader.core.config import Settings

        s = Settings()
        assert hasattr(s, "event_rotation")

    def test_settings_event_rotation_type(self):
        from autotrader.core.config import EventDrivenRotationConfig, Settings

        s = Settings()
        assert isinstance(s.event_rotation, EventDrivenRotationConfig)

    def test_settings_event_rotation_defaults(self):
        from autotrader.core.config import Settings

        s = Settings()
        assert s.event_rotation.enable_event_driven is True
        assert s.event_rotation.cooldown_hours == 48
