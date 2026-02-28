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


def test_ema_pullback_close_in_ranging(reviewer: RegimePositionReviewer) -> None:
    """ema_pullback has only 10% weight in RANGING -- should close."""
    positions = {"AAPL": "ema_pullback"}
    results = reviewer.review(MarketRegime.RANGING, positions)

    assert len(results) == 1
    assert results[0].action == "close"
    assert results[0].symbol == "AAPL"
    assert results[0].strategy == "ema_pullback"


def test_ema_pullback_keep_in_trend(reviewer: RegimePositionReviewer) -> None:
    """ema_pullback has 40% weight in TREND -- should keep."""
    positions = {"AAPL": "ema_pullback"}
    results = reviewer.review(MarketRegime.TREND, positions)

    assert len(results) == 1
    assert results[0].action == "keep"
    assert results[0].reason == "compatible"


def test_consecutive_down_keep_in_ranging(reviewer: RegimePositionReviewer) -> None:
    """consecutive_down has 30% weight in RANGING -- should keep."""
    positions = {"TSLA": "consecutive_down"}
    results = reviewer.review(MarketRegime.RANGING, positions)

    assert len(results) == 1
    assert results[0].action == "keep"
    assert results[0].reason == "compatible"


def test_volume_divergence_keep_in_high_vol(reviewer: RegimePositionReviewer) -> None:
    """volume_divergence has 35% weight in HIGH_VOLATILITY -- should keep."""
    positions = {"TSLA": "volume_divergence"}
    results = reviewer.review(MarketRegime.HIGH_VOLATILITY, positions)

    assert len(results) == 1
    assert results[0].action == "keep"
    assert results[0].reason == "compatible"


def test_ema_pullback_close_in_high_vol(reviewer: RegimePositionReviewer) -> None:
    """ema_pullback has only 10% weight in HIGH_VOLATILITY -- should close."""
    positions = {"NVDA": "ema_pullback"}
    results = reviewer.review(MarketRegime.HIGH_VOLATILITY, positions)

    assert len(results) == 1
    assert results[0].action == "close"
    assert results[0].reason == "incompatible_with_HIGH_VOLATILITY"


def test_rsi_mean_reversion_keep_in_all_regimes(
    reviewer: RegimePositionReviewer,
) -> None:
    """rsi_mean_reversion has >= 15% weight in all regimes -- should keep in all."""
    positions = {"GOOG": "rsi_mean_reversion"}
    for regime in MarketRegime:
        results = reviewer.review(regime, positions)
        assert len(results) == 1
        assert results[0].action == "keep", (
            f"rsi_mean_reversion should keep in {regime.value}"
        )


def test_volume_divergence_keep_in_all_regimes(
    reviewer: RegimePositionReviewer,
) -> None:
    """volume_divergence has >= 25% weight in all regimes -- should keep in all."""
    positions = {"MSFT": "volume_divergence"}
    for regime in MarketRegime:
        results = reviewer.review(regime, positions)
        assert len(results) == 1
        assert results[0].action == "keep", (
            f"volume_divergence should keep in {regime.value}"
        )


# ------------------------------------------------------------------
# Multi-position and edge-case tests
# ------------------------------------------------------------------


def test_multiple_positions_mixed_actions(reviewer: RegimePositionReviewer) -> None:
    """Regime change to RANGING should close ema_pullback but keep rsi_mr and others."""
    positions = {
        "AAPL": "ema_pullback",           # 10% in RANGING -> close
        "GOOG": "rsi_mean_reversion",     # 35% in RANGING -> keep
        "NVDA": "consecutive_down",       # 30% in RANGING -> keep
        "MSFT": "volume_divergence",      # 25% in RANGING -> keep
    }
    results = reviewer.review(MarketRegime.RANGING, positions)

    assert len(results) == 4
    by_symbol = {r.symbol: r for r in results}

    assert by_symbol["AAPL"].action == "close"
    assert by_symbol["GOOG"].action == "keep"
    assert by_symbol["NVDA"].action == "keep"
    assert by_symbol["MSFT"].action == "keep"


def test_unknown_strategy_keeps(reviewer: RegimePositionReviewer) -> None:
    """An unrecognized strategy should default to keep with reason unknown_strategy."""
    positions = {"XYZ": "some_future_strategy"}
    results = reviewer.review(MarketRegime.TREND, positions)

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
        "AAPL": "ema_pullback",           # incompatible with RANGING
        "GOOG": "rsi_mean_reversion",     # compatible with RANGING
    }
    results = reviewer.review(MarketRegime.RANGING, positions)
    by_symbol = {r.symbol: r for r in results}

    assert by_symbol["AAPL"].reason == "incompatible_with_RANGING"
    assert by_symbol["GOOG"].reason == "compatible"


# ------------------------------------------------------------------
# Additional boundary tests
# ------------------------------------------------------------------


def test_consecutive_down_keep_in_high_vol(reviewer: RegimePositionReviewer) -> None:
    """consecutive_down has 30% weight in HIGH_VOLATILITY -- should keep."""
    positions = {"NVDA": "consecutive_down"}
    results = reviewer.review(MarketRegime.HIGH_VOLATILITY, positions)

    assert len(results) == 1
    assert results[0].action == "keep"
    assert results[0].reason == "compatible"


def test_position_review_is_frozen_dataclass() -> None:
    """PositionReview should be immutable (frozen dataclass)."""
    review = PositionReview(
        symbol="AAPL", strategy="ema_pullback", action="close", reason="test"
    )
    with pytest.raises(AttributeError):
        review.action = "keep"  # type: ignore[misc]
