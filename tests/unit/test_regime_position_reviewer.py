"""Tests for RegimePositionReviewer.

Verifies that the regime-change position re-evaluation logic correctly
recommends closing positions whose originating strategy is incompatible
with the new market regime, and keeping those that remain compatible.
"""
from __future__ import annotations

import pytest

from autotrader.portfolio.regime_detector import MarketRegime
from autotrader.portfolio.regime_position_reviewer import (
    PositionReview,
    RegimePositionReviewer,
)


@pytest.fixture()
def reviewer() -> RegimePositionReviewer:
    return RegimePositionReviewer()


# ------------------------------------------------------------------
# Individual strategy-regime compatibility tests
# ------------------------------------------------------------------


def test_breakout_momentum_close_in_trend_down(reviewer: RegimePositionReviewer) -> None:
    """breakout_momentum is blocked in TREND_DOWN -- should close."""
    positions = {"AAPL": "breakout_momentum"}
    results = reviewer.review(MarketRegime.TREND_DOWN, positions)

    assert len(results) == 1
    assert results[0].action == "close"
    assert results[0].symbol == "AAPL"
    assert results[0].strategy == "breakout_momentum"


def test_breakout_momentum_keep_in_trend_up(reviewer: RegimePositionReviewer) -> None:
    """breakout_momentum is compatible with TREND_UP -- should keep."""
    positions = {"AAPL": "breakout_momentum"}
    results = reviewer.review(MarketRegime.TREND_UP, positions)

    assert len(results) == 1
    assert results[0].action == "keep"
    assert results[0].reason == "compatible"


def test_rsi_mean_reversion_keep_in_all_regimes(
    reviewer: RegimePositionReviewer,
) -> None:
    """rsi_mean_reversion is compatible with all regimes -- should keep in all."""
    positions = {"GOOG": "rsi_mean_reversion"}
    for regime in MarketRegime:
        results = reviewer.review(regime, positions)
        assert len(results) == 1
        assert results[0].action == "keep", (
            f"rsi_mean_reversion should keep in {regime.value}"
        )


def test_breakout_momentum_keep_in_most_regimes(
    reviewer: RegimePositionReviewer,
) -> None:
    """breakout_momentum is compatible with everything except TREND_DOWN."""
    positions = {"MSFT": "breakout_momentum"}
    for regime in [
        MarketRegime.TREND_UP,
        MarketRegime.RANGING,
        MarketRegime.HIGH_VOLATILITY,
        MarketRegime.UNCERTAIN,
    ]:
        results = reviewer.review(regime, positions)
        assert len(results) == 1
        assert results[0].action == "keep", (
            f"breakout_momentum should keep in {regime.value}"
        )


# ------------------------------------------------------------------
# Multi-position and edge-case tests
# ------------------------------------------------------------------


def test_multiple_positions_mixed_actions(reviewer: RegimePositionReviewer) -> None:
    """Regime change to TREND_DOWN should close breakout_momentum but keep rsi_mr."""
    positions = {
        "AAPL": "breakout_momentum",       # blocked in TREND_DOWN -> close
        "GOOG": "rsi_mean_reversion",      # compatible -> keep
    }
    results = reviewer.review(MarketRegime.TREND_DOWN, positions)

    assert len(results) == 2
    by_symbol = {r.symbol: r for r in results}

    assert by_symbol["AAPL"].action == "close"
    assert by_symbol["GOOG"].action == "keep"


def test_unknown_strategy_keeps(reviewer: RegimePositionReviewer) -> None:
    """An unrecognized strategy should default to keep with reason unknown_strategy."""
    positions = {"XYZ": "some_future_strategy"}
    results = reviewer.review(MarketRegime.TREND_UP, positions)

    assert len(results) == 1
    assert results[0].action == "keep"
    assert results[0].reason == "unknown_strategy"


def test_empty_positions_returns_empty(reviewer: RegimePositionReviewer) -> None:
    """No open positions should return an empty list."""
    results = reviewer.review(MarketRegime.HIGH_VOLATILITY, {})
    assert results == []


def test_review_returns_correct_reasons(reviewer: RegimePositionReviewer) -> None:
    """Verify the exact reason strings for close and keep actions."""
    positions = {
        "AAPL": "breakout_momentum",       # blocked in TREND_DOWN
        "GOOG": "rsi_mean_reversion",      # compatible with TREND_DOWN
    }
    results = reviewer.review(MarketRegime.TREND_DOWN, positions)
    by_symbol = {r.symbol: r for r in results}

    assert by_symbol["AAPL"].reason == "incompatible_with_TREND_DOWN"
    assert by_symbol["GOOG"].reason == "compatible"


def test_position_review_is_frozen_dataclass() -> None:
    """PositionReview should be immutable (frozen dataclass)."""
    review = PositionReview(
        symbol="AAPL", strategy="breakout_momentum", action="close", reason="test"
    )
    with pytest.raises(AttributeError):
        review.action = "keep"  # type: ignore[misc]
