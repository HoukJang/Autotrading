"""Tests for PositionSizer.

Covers basic sizing, short adjustment, caps, floors, and edge cases.
"""
from __future__ import annotations

import pytest

from autotrader.trading.constants import (
    MAX_POSITION_PCT,
    MIN_POSITION_VALUE,
    SHORT_SIZE_RATIO,
)
from autotrader.trading.position_sizer import PositionSizer


class TestBasicLongSizing:
    """Test fundamental risk-based position sizing for long trades."""

    def test_basic_calculation(self):
        """qty = (equity * risk_pct) / stop_distance."""
        sizer = PositionSizer()
        # equity=10000, risk=2%, stop=5 -> risk_amount=200, qty=200/5=40
        qty = sizer.calculate(
            equity=10000.0,
            price=50.0,
            stop_distance=5.0,
            direction="long",
            risk_pct=0.02,
        )
        assert qty == 40

    def test_larger_risk_more_shares(self):
        """Higher risk pct produces more shares."""
        sizer = PositionSizer()
        qty_low = sizer.calculate(
            equity=10000.0, price=50.0, stop_distance=5.0,
            direction="long", risk_pct=0.01,
        )
        qty_high = sizer.calculate(
            equity=10000.0, price=50.0, stop_distance=5.0,
            direction="long", risk_pct=0.03,
        )
        assert qty_high > qty_low

    def test_wider_stop_fewer_shares(self):
        """Wider stop distance produces fewer shares."""
        sizer = PositionSizer()
        qty_tight = sizer.calculate(
            equity=10000.0, price=50.0, stop_distance=2.0,
            direction="long", risk_pct=0.02,
        )
        qty_wide = sizer.calculate(
            equity=10000.0, price=50.0, stop_distance=10.0,
            direction="long", risk_pct=0.02,
        )
        assert qty_tight > qty_wide


class TestShortSizing:
    """Test that short positions apply SHORT_SIZE_RATIO reduction."""

    def test_short_reduces_by_ratio(self):
        """Short qty = int(long_qty * SHORT_SIZE_RATIO)."""
        sizer = PositionSizer()
        qty_long = sizer.calculate(
            equity=10000.0, price=50.0, stop_distance=5.0,
            direction="long", risk_pct=0.02,
        )
        qty_short = sizer.calculate(
            equity=10000.0, price=50.0, stop_distance=5.0,
            direction="short", risk_pct=0.02,
        )
        expected_short = int(qty_long * SHORT_SIZE_RATIO)
        assert qty_short == expected_short
        assert qty_short < qty_long

    def test_short_ratio_value(self):
        """Verify the constant is 0.65 as per LOCKED params."""
        assert SHORT_SIZE_RATIO == pytest.approx(0.65)


class TestMaxPositionPctCap:
    """Test MAX_POSITION_PCT hard cap."""

    def test_cap_limits_large_position(self):
        """Position size is capped at MAX_POSITION_PCT of equity."""
        sizer = PositionSizer()
        # equity=10000, price=10, stop=0.01 -> risk_qty=200/0.01=20000 (huge)
        # cap = 10000*0.25/10 = 250
        qty = sizer.calculate(
            equity=10000.0, price=10.0, stop_distance=0.01,
            direction="long", risk_pct=0.02,
        )
        max_allowed = int((10000.0 * MAX_POSITION_PCT) / 10.0)
        assert qty == max_allowed
        assert qty == 250

    def test_under_cap_not_reduced(self):
        """Position below cap is not affected."""
        sizer = PositionSizer()
        # equity=10000, price=100, stop=5 -> risk_qty=200/5=40
        # cap = 10000*0.25/100 = 25
        # In this case 40 > 25, so capped
        qty = sizer.calculate(
            equity=10000.0, price=100.0, stop_distance=5.0,
            direction="long", risk_pct=0.02,
        )
        assert qty == 25

    def test_risk_sized_under_cap(self):
        """When risk-sized qty is under cap, return risk-sized qty."""
        sizer = PositionSizer()
        # equity=100000, price=50, stop=10 -> risk_qty=2000/10=200
        # cap = 100000*0.25/50 = 500
        # 200 < 500 -> returns 200
        qty = sizer.calculate(
            equity=100000.0, price=50.0, stop_distance=10.0,
            direction="long", risk_pct=0.02,
        )
        assert qty == 200


class TestMinPositionValue:
    """Test MIN_POSITION_VALUE floor."""

    def test_below_minimum_returns_zero(self):
        """Position below MIN_POSITION_VALUE returns 0."""
        sizer = PositionSizer()
        # equity=1000, price=500, stop=50 -> risk_qty=20/50=0 (int)
        # 0 * 500 = 0 < 200 -> returns 0
        qty = sizer.calculate(
            equity=1000.0, price=500.0, stop_distance=50.0,
            direction="long", risk_pct=0.02,
        )
        assert qty == 0

    def test_at_minimum_returns_qty(self):
        """Position exactly at MIN_POSITION_VALUE is accepted."""
        sizer = PositionSizer()
        # equity=10000, price=100, stop=5 -> risk_qty=200/5=40
        # Capped at 25 by MAX_POSITION_PCT. 25*100=2500 >= 200. OK.
        qty = sizer.calculate(
            equity=10000.0, price=100.0, stop_distance=5.0,
            direction="long", risk_pct=0.02,
        )
        assert qty > 0
        assert qty * 100.0 >= MIN_POSITION_VALUE


class TestEdgeCases:
    """Test edge cases and invalid inputs."""

    def test_zero_stop_distance_returns_zero(self):
        sizer = PositionSizer()
        qty = sizer.calculate(
            equity=10000.0, price=50.0, stop_distance=0.0,
            direction="long", risk_pct=0.02,
        )
        assert qty == 0

    def test_negative_stop_distance_returns_zero(self):
        sizer = PositionSizer()
        qty = sizer.calculate(
            equity=10000.0, price=50.0, stop_distance=-1.0,
            direction="long", risk_pct=0.02,
        )
        assert qty == 0

    def test_zero_price_returns_zero(self):
        sizer = PositionSizer()
        qty = sizer.calculate(
            equity=10000.0, price=0.0, stop_distance=5.0,
            direction="long", risk_pct=0.02,
        )
        assert qty == 0

    def test_negative_price_returns_zero(self):
        sizer = PositionSizer()
        qty = sizer.calculate(
            equity=10000.0, price=-10.0, stop_distance=5.0,
            direction="long", risk_pct=0.02,
        )
        assert qty == 0

    def test_custom_constants(self):
        """PositionSizer accepts overridden constants."""
        sizer = PositionSizer(
            max_position_pct=0.50,
            min_position_value=50.0,
            short_size_ratio=0.80,
        )
        qty_long = sizer.calculate(
            equity=10000.0, price=50.0, stop_distance=5.0,
            direction="long", risk_pct=0.02,
        )
        qty_short = sizer.calculate(
            equity=10000.0, price=50.0, stop_distance=5.0,
            direction="short", risk_pct=0.02,
        )
        # With 50% max position, cap = 10000*0.5/50 = 100
        # risk = 200/5 = 40, 40 < 100 -> qty = 40
        assert qty_long == 40
        # short = int(40 * 0.80) = 32
        assert qty_short == 32
