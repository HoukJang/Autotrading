import pytest
from collections import deque
from datetime import datetime, timezone

from autotrader.core.types import Bar
from autotrader.indicators.builtin.volatility import BollingerBands


def _make_bars(closes: list[float], symbol: str = "TEST") -> deque[Bar]:
    bars: deque[Bar] = deque()
    for i, c in enumerate(closes):
        bars.append(Bar(
            symbol=symbol,
            timestamp=datetime(2026, 1, 1, 10, i, tzinfo=timezone.utc),
            open=c,
            high=c + 1.0,
            low=c - 1.0,
            close=c,
            volume=100.0,
        ))
    return bars


class TestBollingerBands:
    def test_returns_none_insufficient_bars(self):
        bb = BollingerBands(period=20)
        bars = _make_bars([float(i) for i in range(19)])  # Only 19 bars
        assert bb.calculate(bars) is None

    def test_returns_dict_with_required_keys(self):
        bb = BollingerBands(period=20)
        bars = _make_bars([float(i + 100) for i in range(25)])
        result = bb.calculate(bars)
        assert result is not None
        assert isinstance(result, dict)
        expected_keys = {"upper", "middle", "lower", "width", "pct_b"}
        assert set(result.keys()) == expected_keys

    def test_upper_gt_middle_gt_lower(self):
        bb = BollingerBands(period=20)
        bars = _make_bars([100.0 + i * 0.5 for i in range(25)])
        result = bb.calculate(bars)
        assert result is not None
        assert result["upper"] > result["middle"]
        assert result["middle"] > result["lower"]

    def test_pct_b_at_middle(self):
        """When close equals SMA, pct_b should be approximately 0.5."""
        bb = BollingerBands(period=5)
        # Use prices where the last close equals the SMA of last 5 closes
        # Prices: 10, 20, 30, 20, 20 -> SMA = 20.0, last close = 20.0
        bars = _make_bars([10.0, 20.0, 30.0, 20.0, 20.0])
        result = bb.calculate(bars)
        assert result is not None
        assert result["pct_b"] == pytest.approx(0.5, abs=0.01)

    def test_pct_b_near_lower(self):
        """When close drops near lower band, pct_b should be near 0."""
        bb = BollingerBands(period=5, num_std=2.0)
        # Prices with a big drop at end: SMA is higher, close is low
        bars = _make_bars([100.0, 100.0, 100.0, 100.0, 80.0])
        result = bb.calculate(bars)
        assert result is not None
        assert result["pct_b"] < 0.2

    def test_width_positive(self):
        bb = BollingerBands(period=20)
        bars = _make_bars([100.0 + i for i in range(25)])
        result = bb.calculate(bars)
        assert result is not None
        assert result["width"] >= 0.0

    def test_constant_prices_zero_width(self):
        """All same price: stdev=0, width=0, pct_b=0.5."""
        bb = BollingerBands(period=5)
        bars = _make_bars([50.0] * 10)
        result = bb.calculate(bars)
        assert result is not None
        assert result["width"] == pytest.approx(0.0)
        assert result["pct_b"] == pytest.approx(0.5)
        assert result["upper"] == pytest.approx(result["middle"])
        assert result["lower"] == pytest.approx(result["middle"])

    def test_warmup_period(self):
        assert BollingerBands(period=20).warmup_period == 20
        assert BollingerBands(period=10).warmup_period == 10

    def test_custom_num_std(self):
        """Wider num_std should produce wider bands."""
        bars = _make_bars([100.0 + i for i in range(25)])
        bb_narrow = BollingerBands(period=20, num_std=1.0)
        bb_wide = BollingerBands(period=20, num_std=3.0)
        narrow = bb_narrow.calculate(bars)
        wide = bb_wide.calculate(bars)
        assert narrow is not None and wide is not None
        assert wide["width"] > narrow["width"]
