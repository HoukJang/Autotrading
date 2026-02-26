# Universe Selector Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a stock universe selection module that automatically selects 15 optimal stocks from S&P 500 for the 5-strategy swing trading portfolio, using hybrid proxy + backtest scoring with weekly rotation.

**Architecture:** 3-stage pipeline (hard filter -> hybrid scoring -> portfolio optimization) orchestrated by UniverseSelector. Wikipedia provides S&P 500 list, Alpaca provides price/volume data, yfinance provides earnings calendar. BacktestEngine scores each candidate by running all 5 strategies on 120 days of historical data with train/validation split.

**Tech Stack:** Python 3.11, pandas (scraping), yfinance (earnings), alpaca-py (market data), existing BacktestEngine + 5 strategies

---

## Shared Data Types

All tasks use these types defined in `autotrader/universe/__init__.py`:

```python
@dataclass
class StockInfo:
    symbol: str
    sector: str
    sub_industry: str

@dataclass
class StockCandidate:
    symbol: str
    sector: str
    close: float
    avg_dollar_volume: float
    avg_volume: float
    atr_ratio: float
    gap_frequency: float
    trend_pct: float
    range_pct: float
    vol_cycle: float

@dataclass
class ScoredCandidate:
    candidate: StockCandidate
    proxy_score: float
    backtest_score: float
    final_score: float

@dataclass
class UniverseResult:
    symbols: list[str]
    scored: list[ScoredCandidate]
    timestamp: datetime
    rotation_in: list[str]
    rotation_out: list[str]
```

---

### Task 1: Data Types and SP500 Provider

**Files:**
- Create: `autotrader/universe/__init__.py`
- Create: `autotrader/universe/provider.py`
- Test: `tests/unit/test_universe_provider.py`

**Step 1: Write tests for data types and provider**

```python
# tests/unit/test_universe_provider.py
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from autotrader.universe import StockInfo, StockCandidate, ScoredCandidate, UniverseResult
from autotrader.universe.provider import SP500Provider


class TestStockInfo:
    def test_create(self):
        info = StockInfo(symbol="AAPL", sector="Technology", sub_industry="Consumer Electronics")
        assert info.symbol == "AAPL"
        assert info.sector == "Technology"

    def test_equality(self):
        a = StockInfo("AAPL", "Tech", "HW")
        b = StockInfo("AAPL", "Tech", "HW")
        assert a == b


class TestStockCandidate:
    def test_create(self):
        c = StockCandidate(
            symbol="AAPL", sector="Technology", close=150.0,
            avg_dollar_volume=100e6, avg_volume=2e6,
            atr_ratio=0.02, gap_frequency=0.05,
            trend_pct=0.40, range_pct=0.30, vol_cycle=0.5,
        )
        assert c.symbol == "AAPL"
        assert c.avg_dollar_volume == 100e6


class TestScoredCandidate:
    def test_create(self):
        c = StockCandidate(
            symbol="AAPL", sector="Technology", close=150.0,
            avg_dollar_volume=100e6, avg_volume=2e6,
            atr_ratio=0.02, gap_frequency=0.05,
            trend_pct=0.40, range_pct=0.30, vol_cycle=0.5,
        )
        sc = ScoredCandidate(candidate=c, proxy_score=0.8, backtest_score=0.6, final_score=0.7)
        assert sc.final_score == 0.7


class TestSP500Provider:
    def test_fetch_returns_list_of_stock_info(self):
        fake_df = pd.DataFrame({
            "Symbol": ["AAPL", "MSFT", "GOOGL"],
            "GICS Sector": ["Information Technology", "Information Technology", "Communication Services"],
            "GICS Sub-Industry": ["Technology Hardware", "Systems Software", "Interactive Media"],
        })
        with patch("pandas.read_html", return_value=[fake_df]):
            provider = SP500Provider()
            result = provider.fetch()
        assert len(result) == 3
        assert isinstance(result[0], StockInfo)
        assert result[0].symbol == "AAPL"
        assert result[0].sector == "Information Technology"

    def test_fetch_cleans_dot_symbols(self):
        """BRK.B -> BRK-B for Alpaca compatibility."""
        fake_df = pd.DataFrame({
            "Symbol": ["BRK.B", "BF.B"],
            "GICS Sector": ["Financials", "Consumer Staples"],
            "GICS Sub-Industry": ["Insurance", "Distillers"],
        })
        with patch("pandas.read_html", return_value=[fake_df]):
            provider = SP500Provider()
            result = provider.fetch()
        symbols = [s.symbol for s in result]
        assert "BRK-B" in symbols
        assert "BF-B" in symbols

    def test_fetch_caches_result(self):
        fake_df = pd.DataFrame({
            "Symbol": ["AAPL"],
            "GICS Sector": ["IT"],
            "GICS Sub-Industry": ["HW"],
        })
        with patch("pandas.read_html", return_value=[fake_df]) as mock_read:
            provider = SP500Provider()
            provider.fetch()
            provider.fetch()
        assert mock_read.call_count == 1

    def test_fetch_force_refresh(self):
        fake_df = pd.DataFrame({
            "Symbol": ["AAPL"],
            "GICS Sector": ["IT"],
            "GICS Sub-Industry": ["HW"],
        })
        with patch("pandas.read_html", return_value=[fake_df]) as mock_read:
            provider = SP500Provider()
            provider.fetch()
            provider.fetch(force_refresh=True)
        assert mock_read.call_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_universe_provider.py -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: Implement data types and provider**

```python
# autotrader/universe/__init__.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class StockInfo:
    symbol: str
    sector: str
    sub_industry: str


@dataclass
class StockCandidate:
    symbol: str
    sector: str
    close: float
    avg_dollar_volume: float
    avg_volume: float
    atr_ratio: float
    gap_frequency: float
    trend_pct: float
    range_pct: float
    vol_cycle: float


@dataclass
class ScoredCandidate:
    candidate: StockCandidate
    proxy_score: float
    backtest_score: float
    final_score: float


@dataclass
class UniverseResult:
    symbols: list[str]
    scored: list[ScoredCandidate]
    timestamp: datetime
    rotation_in: list[str] = field(default_factory=list)
    rotation_out: list[str] = field(default_factory=list)
```

```python
# autotrader/universe/provider.py
from __future__ import annotations

import pandas as pd

from autotrader.universe import StockInfo

_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class SP500Provider:
    def __init__(self) -> None:
        self._cache: list[StockInfo] | None = None

    def fetch(self, *, force_refresh: bool = False) -> list[StockInfo]:
        if self._cache is not None and not force_refresh:
            return self._cache

        tables = pd.read_html(_WIKI_URL)
        df = tables[0]

        result: list[StockInfo] = []
        for _, row in df.iterrows():
            symbol = str(row["Symbol"]).replace(".", "-")
            sector = str(row["GICS Sector"])
            sub = str(row.get("GICS Sub-Industry", ""))
            result.append(StockInfo(symbol=symbol, sector=sector, sub_industry=sub))

        self._cache = result
        return result
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_universe_provider.py -v`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add autotrader/universe/__init__.py autotrader/universe/provider.py tests/unit/test_universe_provider.py
git commit -m "feat: SP500 provider with Wikipedia scraping and data types"
```

---

### Task 2: Earnings Calendar

**Files:**
- Create: `autotrader/universe/earnings.py`
- Test: `tests/unit/test_universe_earnings.py`

**Step 1: Write tests**

```python
# tests/unit/test_universe_earnings.py
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest

from autotrader.universe.earnings import EarningsCalendar


class TestEarningsCalendar:
    def test_is_blackout_before_earnings(self):
        cal = EarningsCalendar()
        earnings_date = date(2026, 4, 25)
        cal._cache = {"AAPL": earnings_date}
        # E-5 through E+1 = blackout
        assert cal.is_blackout("AAPL", date(2026, 4, 20)) is True  # E-5 (weekday)
        assert cal.is_blackout("AAPL", date(2026, 4, 24)) is True  # E-1
        assert cal.is_blackout("AAPL", date(2026, 4, 25)) is True  # E day

    def test_is_blackout_after_earnings(self):
        cal = EarningsCalendar()
        earnings_date = date(2026, 4, 25)
        cal._cache = {"AAPL": earnings_date}
        assert cal.is_blackout("AAPL", date(2026, 4, 26)) is True   # E+1
        assert cal.is_blackout("AAPL", date(2026, 4, 27)) is False  # E+2

    def test_no_earnings_not_blackout(self):
        cal = EarningsCalendar()
        cal._cache = {}
        assert cal.is_blackout("AAPL", date(2026, 3, 1)) is False

    def test_should_force_close(self):
        cal = EarningsCalendar()
        earnings_date = date(2026, 4, 25)
        cal._cache = {"AAPL": earnings_date}
        # E-3 = force close
        assert cal.should_force_close("AAPL", date(2026, 4, 22)) is True
        assert cal.should_force_close("AAPL", date(2026, 4, 21)) is False

    def test_unknown_symbol_not_blackout(self):
        cal = EarningsCalendar()
        cal._cache = {}
        assert cal.is_blackout("UNKNOWN", date(2026, 3, 1)) is False
        assert cal.should_force_close("UNKNOWN", date(2026, 3, 1)) is False

    def test_fetch_earnings_calls_yfinance(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [date(2026, 4, 25)]}
        with patch("yfinance.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar()
            cal.fetch(["AAPL"])
        assert "AAPL" in cal._cache

    def test_fetch_earnings_handles_missing(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = None
        with patch("yfinance.Ticker", return_value=mock_ticker):
            cal = EarningsCalendar()
            cal.fetch(["AAPL"])
        assert "AAPL" not in cal._cache

    def test_blackout_symbols_filters_list(self):
        cal = EarningsCalendar()
        cal._cache = {
            "AAPL": date(2026, 4, 25),
            "MSFT": date(2026, 5, 15),
            "GOOGL": date(2026, 4, 28),
        }
        check_date = date(2026, 4, 22)
        blackout = cal.blackout_symbols(["AAPL", "MSFT", "GOOGL"], check_date)
        assert "AAPL" in blackout
        assert "MSFT" not in blackout
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_universe_earnings.py -v`
Expected: FAIL

**Step 3: Implement**

```python
# autotrader/universe/earnings.py
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_BLACKOUT_BEFORE = 5  # business days before earnings
_BLACKOUT_AFTER = 1   # business days after earnings
_FORCE_CLOSE_BEFORE = 3  # business days before earnings


def _business_days_between(d1: date, d2: date) -> int:
    """Count business days from d1 to d2 (d2 > d1 means positive)."""
    if d1 > d2:
        return -_business_days_between(d2, d1)
    days = 0
    current = d1
    while current < d2:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days += 1
    return days


class EarningsCalendar:
    def __init__(self) -> None:
        self._cache: dict[str, date] = {}

    def fetch(self, symbols: list[str]) -> None:
        import yfinance
        for symbol in symbols:
            try:
                ticker = yfinance.Ticker(symbol)
                cal = ticker.calendar
                if cal is None:
                    continue
                if isinstance(cal, dict):
                    dates = cal.get("Earnings Date", [])
                else:
                    dates = []
                if dates:
                    ear_date = dates[0]
                    if isinstance(ear_date, date):
                        self._cache[symbol] = ear_date
                    else:
                        self._cache[symbol] = ear_date.date() if hasattr(ear_date, "date") else ear_date
            except Exception:
                logger.debug("Failed to fetch earnings for %s", symbol)

    def is_blackout(self, symbol: str, check_date: date) -> bool:
        earnings = self._cache.get(symbol)
        if earnings is None:
            return False
        bdays_to_earnings = _business_days_between(check_date, earnings)
        if bdays_to_earnings < 0:
            return abs(bdays_to_earnings) <= _BLACKOUT_AFTER
        return bdays_to_earnings <= _BLACKOUT_BEFORE

    def should_force_close(self, symbol: str, check_date: date) -> bool:
        earnings = self._cache.get(symbol)
        if earnings is None:
            return False
        bdays = _business_days_between(check_date, earnings)
        return bdays == _FORCE_CLOSE_BEFORE

    def blackout_symbols(self, symbols: list[str], check_date: date) -> list[str]:
        return [s for s in symbols if self.is_blackout(s, check_date)]
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_universe_earnings.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add autotrader/universe/earnings.py tests/unit/test_universe_earnings.py
git commit -m "feat: earnings calendar with blackout period detection"
```

---

### Task 3: Hard Filters

**Files:**
- Create: `autotrader/universe/filters.py`
- Test: `tests/unit/test_universe_filters.py`

**Step 1: Write tests**

```python
# tests/unit/test_universe_filters.py
from __future__ import annotations

import pytest

from autotrader.universe import StockCandidate
from autotrader.universe.filters import HardFilter


def _make_candidate(**overrides) -> StockCandidate:
    defaults = dict(
        symbol="AAPL", sector="Technology", close=150.0,
        avg_dollar_volume=100e6, avg_volume=2e6,
        atr_ratio=0.02, gap_frequency=0.05,
        trend_pct=0.40, range_pct=0.30, vol_cycle=0.5,
    )
    defaults.update(overrides)
    return StockCandidate(**defaults)


class TestHardFilter:
    def test_passes_good_candidate(self):
        f = HardFilter()
        c = _make_candidate()
        assert f.passes(c) is True

    def test_rejects_low_dollar_volume(self):
        f = HardFilter()
        c = _make_candidate(avg_dollar_volume=10e6)
        assert f.passes(c) is False

    def test_rejects_low_volume(self):
        f = HardFilter()
        c = _make_candidate(avg_volume=500_000)
        assert f.passes(c) is False

    def test_rejects_price_too_low(self):
        f = HardFilter()
        c = _make_candidate(close=15.0)
        assert f.passes(c) is False

    def test_rejects_price_too_high(self):
        f = HardFilter()
        c = _make_candidate(close=250.0)
        assert f.passes(c) is False

    def test_rejects_atr_ratio_too_low(self):
        f = HardFilter()
        c = _make_candidate(atr_ratio=0.005)
        assert f.passes(c) is False

    def test_rejects_atr_ratio_too_high(self):
        f = HardFilter()
        c = _make_candidate(atr_ratio=0.05)
        assert f.passes(c) is False

    def test_rejects_high_gap_frequency(self):
        f = HardFilter()
        c = _make_candidate(gap_frequency=0.20)
        assert f.passes(c) is False

    def test_filter_list(self):
        f = HardFilter()
        candidates = [
            _make_candidate(symbol="AAPL"),
            _make_candidate(symbol="BAD", avg_dollar_volume=1e6),
            _make_candidate(symbol="MSFT"),
        ]
        result = f.filter(candidates)
        assert len(result) == 2
        assert result[0].symbol == "AAPL"
        assert result[1].symbol == "MSFT"

    def test_custom_thresholds(self):
        f = HardFilter(
            min_dollar_volume=10e6,
            min_volume=100_000,
            min_price=5.0,
            max_price=500.0,
            min_atr_ratio=0.005,
            max_atr_ratio=0.08,
            max_gap_frequency=0.25,
        )
        c = _make_candidate(close=300.0, avg_volume=200_000, avg_dollar_volume=20e6)
        assert f.passes(c) is True
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_universe_filters.py -v`
Expected: FAIL

**Step 3: Implement**

```python
# autotrader/universe/filters.py
from __future__ import annotations

from autotrader.universe import StockCandidate


class HardFilter:
    def __init__(
        self,
        min_dollar_volume: float = 50e6,
        min_volume: float = 1e6,
        min_price: float = 20.0,
        max_price: float = 200.0,
        min_atr_ratio: float = 0.01,
        max_atr_ratio: float = 0.04,
        max_gap_frequency: float = 0.15,
    ) -> None:
        self.min_dollar_volume = min_dollar_volume
        self.min_volume = min_volume
        self.min_price = min_price
        self.max_price = max_price
        self.min_atr_ratio = min_atr_ratio
        self.max_atr_ratio = max_atr_ratio
        self.max_gap_frequency = max_gap_frequency

    def passes(self, c: StockCandidate) -> bool:
        if c.avg_dollar_volume < self.min_dollar_volume:
            return False
        if c.avg_volume < self.min_volume:
            return False
        if c.close < self.min_price or c.close > self.max_price:
            return False
        if c.atr_ratio < self.min_atr_ratio or c.atr_ratio > self.max_atr_ratio:
            return False
        if c.gap_frequency > self.max_gap_frequency:
            return False
        return True

    def filter(self, candidates: list[StockCandidate]) -> list[StockCandidate]:
        return [c for c in candidates if self.passes(c)]
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_universe_filters.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add autotrader/universe/filters.py tests/unit/test_universe_filters.py
git commit -m "feat: hard filter pipeline for stock universe selection"
```

---

### Task 4: Proxy Scorer

**Files:**
- Create: `autotrader/universe/scorer.py`
- Test: `tests/unit/test_universe_scorer.py`

**Step 1: Write tests**

```python
# tests/unit/test_universe_scorer.py
from __future__ import annotations

import pytest

from autotrader.universe import StockCandidate
from autotrader.universe.scorer import ProxyScorer


def _make_candidate(**overrides) -> StockCandidate:
    defaults = dict(
        symbol="AAPL", sector="Technology", close=150.0,
        avg_dollar_volume=100e6, avg_volume=2e6,
        atr_ratio=0.02, gap_frequency=0.05,
        trend_pct=0.40, range_pct=0.30, vol_cycle=0.5,
    )
    defaults.update(overrides)
    return StockCandidate(**defaults)


class TestProxyScorer:
    def test_score_returns_float_between_0_and_1(self):
        scorer = ProxyScorer()
        candidates = [_make_candidate()]
        scores = scorer.score(candidates, current_pool=[])
        assert 0.0 <= scores[0] <= 1.0

    def test_higher_liquidity_higher_score(self):
        scorer = ProxyScorer()
        low = _make_candidate(symbol="LOW", avg_dollar_volume=55e6)
        high = _make_candidate(symbol="HIGH", avg_dollar_volume=500e6)
        scores = scorer.score([low, high], current_pool=[])
        assert scores[1] > scores[0]

    def test_ideal_atr_ratio_scores_highest(self):
        scorer = ProxyScorer()
        ideal = _make_candidate(symbol="IDEAL", atr_ratio=0.02)
        high = _make_candidate(symbol="HIGH", atr_ratio=0.035)
        low = _make_candidate(symbol="LOW", atr_ratio=0.012)
        scores = scorer.score([ideal, high, low], current_pool=[])
        assert scores[0] >= scores[1]
        assert scores[0] >= scores[2]

    def test_low_gap_frequency_higher_score(self):
        scorer = ProxyScorer()
        safe = _make_candidate(symbol="SAFE", gap_frequency=0.02)
        risky = _make_candidate(symbol="RISKY", gap_frequency=0.12)
        scores = scorer.score([safe, risky], current_pool=[])
        assert scores[0] > scores[1]

    def test_incumbent_bonus(self):
        scorer = ProxyScorer()
        c = _make_candidate(symbol="AAPL")
        score_new = scorer.score([c], current_pool=[])[0]
        score_incumbent = scorer.score([c], current_pool=["AAPL"])[0]
        assert score_incumbent > score_new

    def test_strategy_coverage_dual_capable(self):
        scorer = ProxyScorer()
        dual = _make_candidate(symbol="DUAL", trend_pct=0.45, range_pct=0.45)
        trend_only = _make_candidate(symbol="TREND", trend_pct=0.60, range_pct=0.10)
        scores = scorer.score([dual, trend_only], current_pool=[])
        assert scores[0] > scores[1]

    def test_score_all_returns_correct_count(self):
        scorer = ProxyScorer()
        candidates = [_make_candidate(symbol=f"S{i}") for i in range(5)]
        scores = scorer.score(candidates, current_pool=[])
        assert len(scores) == 5
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_universe_scorer.py -v`
Expected: FAIL

**Step 3: Implement**

```python
# autotrader/universe/scorer.py
from __future__ import annotations

from autotrader.universe import StockCandidate


class ProxyScorer:
    """6-factor proxy scoring for stock candidates.

    Factors (weights):
        LIQUIDITY (0.10): dollar volume percentile rank
        VOL_QUALITY (0.15): ATR ratio closeness to 2%
        STRATEGY_COVERAGE (0.15): trend_pct + range_pct balance
        GAP_SAFETY (0.20): low gap frequency
        EXECUTION_QUALITY (0.15): volume consistency proxy
        INCUMBENT_BONUS (0.15): existing pool membership
    """

    W_LIQUIDITY = 0.10
    W_VOL_QUALITY = 0.15
    W_STRATEGY_COVERAGE = 0.15
    W_GAP_SAFETY = 0.20
    W_EXECUTION_QUALITY = 0.15
    W_INCUMBENT = 0.15

    def score(
        self,
        candidates: list[StockCandidate],
        current_pool: list[str],
    ) -> list[float]:
        if not candidates:
            return []

        dv_values = [c.avg_dollar_volume for c in candidates]
        dv_min = min(dv_values)
        dv_range = max(dv_values) - dv_min if len(dv_values) > 1 else 1.0

        scores: list[float] = []
        for c in candidates:
            liquidity = (c.avg_dollar_volume - dv_min) / dv_range if dv_range > 0 else 0.5

            vol_quality = max(0.0, 1.0 - abs(c.atr_ratio - 0.02) / 0.02)

            trend_s = min(1.0, c.trend_pct / 0.50)
            range_s = min(1.0, c.range_pct / 0.60)
            strategy_coverage = (trend_s + range_s) / 2

            gap_safety = max(0.0, 1.0 - c.gap_frequency / 0.15)

            vol_cv = c.vol_cycle
            execution = max(0.0, 1.0 - vol_cv / 1.5)

            incumbent = 1.0 if c.symbol in current_pool else 0.0

            total = (
                self.W_LIQUIDITY * liquidity
                + self.W_VOL_QUALITY * vol_quality
                + self.W_STRATEGY_COVERAGE * strategy_coverage
                + self.W_GAP_SAFETY * gap_safety
                + self.W_EXECUTION_QUALITY * execution
                + self.W_INCUMBENT * incumbent
            )
            scores.append(round(total, 6))

        return scores


class BacktestScorer:
    """Score candidates using backtest results from 5 strategies.

    Factors:
        activity (0.20): did strategies generate trades?
        win_rate (0.30): weighted average win rate
        profit_factor (0.30): normalized profit factor
        diversity (0.20): how many strategies were active?
    """

    def score_from_metrics(
        self,
        total_trades: int,
        win_rate: float,
        profit_factor: float,
        strategies_active: int,
    ) -> float:
        if total_trades == 0:
            return 0.0

        activity = min(1.0, total_trades / 10.0)
        wr = max(0.0, min(1.0, win_rate))
        pf = min(1.0, profit_factor / 3.0) if profit_factor != float("inf") else 1.0
        diversity = strategies_active / 5.0

        return round(
            0.20 * activity + 0.30 * wr + 0.30 * pf + 0.20 * diversity,
            6,
        )
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_universe_scorer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add autotrader/universe/scorer.py tests/unit/test_universe_scorer.py
git commit -m "feat: proxy scorer and backtest scorer for universe selection"
```

---

### Task 5: Backtest Scorer Integration

**Files:**
- Modify: `autotrader/universe/scorer.py` (add BacktestScorer tests)
- Test: `tests/unit/test_backtest_scorer.py`

**Step 1: Write tests**

```python
# tests/unit/test_backtest_scorer.py
from __future__ import annotations

import pytest
from collections import deque
from datetime import datetime, timezone, timedelta

from autotrader.universe.scorer import BacktestScorer
from autotrader.backtest.engine import BacktestEngine, BacktestResult
from autotrader.core.config import RiskConfig
from autotrader.core.types import Bar
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout
from autotrader.strategy.adx_pullback import AdxPullback
from autotrader.strategy.overbought_short import OverboughtShort
from autotrader.strategy.regime_momentum import RegimeMomentum


class TestBacktestScorer:
    def test_zero_trades_returns_zero(self):
        scorer = BacktestScorer()
        assert scorer.score_from_metrics(0, 0.0, 0.0, 0) == 0.0

    def test_perfect_score(self):
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(
            total_trades=15, win_rate=1.0, profit_factor=5.0, strategies_active=5,
        )
        assert score == pytest.approx(1.0)

    def test_moderate_performance(self):
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(
            total_trades=5, win_rate=0.55, profit_factor=1.5, strategies_active=3,
        )
        assert 0.3 < score < 0.7

    def test_high_win_rate_high_score(self):
        scorer = BacktestScorer()
        high = scorer.score_from_metrics(10, 0.70, 2.0, 4)
        low = scorer.score_from_metrics(10, 0.35, 0.8, 4)
        assert high > low

    def test_more_strategies_active_higher_score(self):
        scorer = BacktestScorer()
        diverse = scorer.score_from_metrics(10, 0.55, 1.5, 5)
        narrow = scorer.score_from_metrics(10, 0.55, 1.5, 1)
        assert diverse > narrow

    def test_inf_profit_factor_capped_at_1(self):
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(5, 0.60, float("inf"), 3)
        assert score <= 1.0


class TestBacktestScorerWithEngine:
    """Integration: run BacktestEngine and feed results to BacktestScorer."""

    def _make_bars(self, symbol: str, n: int = 100) -> list[Bar]:
        bars = []
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        price = 100.0
        for i in range(n):
            import random
            random.seed(i + hash(symbol))
            change = random.gauss(0, 2)
            price = max(10.0, price + change)
            bars.append(Bar(
                symbol=symbol,
                timestamp=base + timedelta(days=i),
                open=price - 0.5,
                high=price + 1.5,
                low=price - 1.5,
                close=price,
                volume=1_000_000.0,
            ))
        return bars

    def test_engine_result_feeds_scorer(self):
        risk = RiskConfig(max_position_pct=0.30, max_drawdown_pct=0.30, max_open_positions=5)
        engine = BacktestEngine(3000.0, risk)
        strategies = [
            RsiMeanReversion(), BbSqueezeBreakout(), AdxPullback(),
            OverboughtShort(), RegimeMomentum(),
        ]
        for s in strategies:
            engine.add_strategy(s)

        bars = self._make_bars("AAPL", 120)
        result = engine.run(bars)

        strategy_names = {t.strategy for t in result.trades}
        scorer = BacktestScorer()
        score = scorer.score_from_metrics(
            total_trades=result.total_trades,
            win_rate=result.metrics.get("win_rate", 0.0),
            profit_factor=result.metrics.get("profit_factor", 0.0),
            strategies_active=len(strategy_names),
        )
        assert 0.0 <= score <= 1.0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_backtest_scorer.py -v`
Expected: PASS (BacktestScorer already implemented in Task 4)

**Step 3: Commit**

```bash
git add tests/unit/test_backtest_scorer.py
git commit -m "test: backtest scorer unit and integration tests"
```

---

### Task 6: Portfolio Optimizer

**Files:**
- Create: `autotrader/universe/optimizer.py`
- Test: `tests/unit/test_universe_optimizer.py`

**Step 1: Write tests**

```python
# tests/unit/test_universe_optimizer.py
from __future__ import annotations

import pytest

from autotrader.universe import StockCandidate, ScoredCandidate
from autotrader.universe.optimizer import PortfolioOptimizer


def _scored(symbol: str, sector: str, score: float,
            trend_pct: float = 0.40, range_pct: float = 0.40) -> ScoredCandidate:
    c = StockCandidate(
        symbol=symbol, sector=sector, close=100.0,
        avg_dollar_volume=100e6, avg_volume=2e6,
        atr_ratio=0.02, gap_frequency=0.05,
        trend_pct=trend_pct, range_pct=range_pct, vol_cycle=0.5,
    )
    return ScoredCandidate(candidate=c, proxy_score=score, backtest_score=score, final_score=score)


class TestPortfolioOptimizer:
    def test_selects_top_n(self):
        opt = PortfolioOptimizer(target_size=3)
        candidates = [
            _scored("A", "Tech", 0.9),
            _scored("B", "Finance", 0.8),
            _scored("C", "Health", 0.7),
            _scored("D", "Energy", 0.6),
        ]
        result = opt.optimize(candidates)
        assert len(result) == 3
        assert result[0].candidate.symbol == "A"

    def test_sector_cap_enforced(self):
        opt = PortfolioOptimizer(target_size=5, max_per_sector=2)
        candidates = [
            _scored("A", "Tech", 0.95),
            _scored("B", "Tech", 0.90),
            _scored("C", "Tech", 0.85),
            _scored("D", "Finance", 0.80),
            _scored("E", "Health", 0.75),
            _scored("F", "Energy", 0.70),
        ]
        result = opt.optimize(candidates)
        tech_count = sum(1 for r in result if r.candidate.sector == "Tech")
        assert tech_count <= 2

    def test_min_sectors_enforced(self):
        opt = PortfolioOptimizer(target_size=5, min_sectors=3)
        candidates = [
            _scored("A", "Tech", 0.95),
            _scored("B", "Tech", 0.90),
            _scored("C", "Tech", 0.85),
            _scored("D", "Tech", 0.80),
            _scored("E", "Finance", 0.40),
            _scored("F", "Health", 0.35),
            _scored("G", "Energy", 0.30),
        ]
        result = opt.optimize(candidates)
        sectors = {r.candidate.sector for r in result}
        assert len(sectors) >= 3

    def test_regime_diversity_trend(self):
        opt = PortfolioOptimizer(target_size=6, min_trend_capable=3, min_range_capable=2)
        candidates = [
            _scored("A", "Tech", 0.9, trend_pct=0.50, range_pct=0.10),
            _scored("B", "Fin", 0.85, trend_pct=0.50, range_pct=0.10),
            _scored("C", "Health", 0.80, trend_pct=0.50, range_pct=0.10),
            _scored("D", "Energy", 0.75, trend_pct=0.10, range_pct=0.60),
            _scored("E", "Util", 0.70, trend_pct=0.10, range_pct=0.60),
            _scored("F", "Mat", 0.65, trend_pct=0.10, range_pct=0.60),
        ]
        result = opt.optimize(candidates)
        trend = sum(1 for r in result if r.candidate.trend_pct > 0.30)
        rng = sum(1 for r in result if r.candidate.range_pct > 0.40)
        assert trend >= 3
        assert rng >= 2

    def test_max_rotation(self):
        opt = PortfolioOptimizer(target_size=5, max_rotation=2)
        candidates = [
            _scored("NEW1", "Tech", 0.95),
            _scored("NEW2", "Fin", 0.90),
            _scored("NEW3", "Health", 0.85),
            _scored("OLD1", "Energy", 0.60),
            _scored("OLD2", "Util", 0.55),
            _scored("OLD3", "Mat", 0.50),
        ]
        current_pool = ["OLD1", "OLD2", "OLD3"]
        result = opt.optimize(candidates, current_pool=current_pool)
        new_symbols = [r.candidate.symbol for r in result if r.candidate.symbol not in current_pool]
        assert len(new_symbols) <= 2

    def test_open_positions_protected(self):
        opt = PortfolioOptimizer(target_size=3)
        candidates = [
            _scored("NEW1", "Tech", 0.95),
            _scored("NEW2", "Fin", 0.90),
            _scored("NEW3", "Health", 0.85),
            _scored("HELD", "Energy", 0.30),
        ]
        result = opt.optimize(candidates, open_positions=["HELD"])
        symbols = [r.candidate.symbol for r in result]
        assert "HELD" in symbols

    def test_empty_candidates(self):
        opt = PortfolioOptimizer(target_size=5)
        result = opt.optimize([])
        assert result == []

    def test_fewer_candidates_than_target(self):
        opt = PortfolioOptimizer(target_size=10)
        candidates = [_scored("A", "Tech", 0.9), _scored("B", "Fin", 0.8)]
        result = opt.optimize(candidates)
        assert len(result) == 2
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_universe_optimizer.py -v`
Expected: FAIL

**Step 3: Implement**

```python
# autotrader/universe/optimizer.py
from __future__ import annotations

from autotrader.universe import ScoredCandidate


class PortfolioOptimizer:
    """Greedy portfolio selection with sector, regime, and rotation constraints."""

    def __init__(
        self,
        target_size: int = 15,
        max_per_sector: int = 4,
        min_sectors: int = 4,
        min_trend_capable: int = 5,
        min_range_capable: int = 5,
        max_rotation: int = 3,
        trend_threshold: float = 0.30,
        range_threshold: float = 0.40,
    ) -> None:
        self.target_size = target_size
        self.max_per_sector = max_per_sector
        self.min_sectors = min_sectors
        self.min_trend_capable = min_trend_capable
        self.min_range_capable = min_range_capable
        self.max_rotation = max_rotation
        self.trend_threshold = trend_threshold
        self.range_threshold = range_threshold

    def optimize(
        self,
        candidates: list[ScoredCandidate],
        current_pool: list[str] | None = None,
        open_positions: list[str] | None = None,
    ) -> list[ScoredCandidate]:
        if not candidates:
            return []

        current_pool = current_pool or []
        open_positions = open_positions or []

        sorted_candidates = sorted(candidates, key=lambda s: s.final_score, reverse=True)
        by_symbol = {s.candidate.symbol: s for s in sorted_candidates}

        selected: list[ScoredCandidate] = []
        sector_count: dict[str, int] = {}

        # Phase 1: Force-include open positions
        for sym in open_positions:
            if sym in by_symbol:
                sc = by_symbol[sym]
                selected.append(sc)
                sec = sc.candidate.sector
                sector_count[sec] = sector_count.get(sec, 0) + 1

        # Phase 2: Greedy selection
        new_additions = 0
        for sc in sorted_candidates:
            if len(selected) >= self.target_size:
                break
            if sc in selected:
                continue

            sym = sc.candidate.symbol
            sec = sc.candidate.sector

            # Sector cap
            if sector_count.get(sec, 0) >= self.max_per_sector:
                continue

            # Rotation cap
            if sym not in current_pool:
                if self.max_rotation > 0 and new_additions >= self.max_rotation and current_pool:
                    continue

            selected.append(sc)
            sector_count[sec] = sector_count.get(sec, 0) + 1
            if sym not in current_pool and current_pool:
                new_additions += 1

        # Phase 3: Check min_sectors constraint - swap if needed
        sectors = {s.candidate.sector for s in selected}
        if len(sectors) < self.min_sectors and len(selected) >= self.min_sectors:
            self._enforce_min_sectors(selected, sorted_candidates, sector_count)

        return selected

    def _enforce_min_sectors(
        self,
        selected: list[ScoredCandidate],
        all_candidates: list[ScoredCandidate],
        sector_count: dict[str, int],
    ) -> None:
        current_sectors = {s.candidate.sector for s in selected}
        needed = self.min_sectors - len(current_sectors)
        if needed <= 0:
            return

        selected_symbols = {s.candidate.symbol for s in selected}
        for sc in all_candidates:
            if needed <= 0:
                break
            if sc.candidate.symbol in selected_symbols:
                continue
            if sc.candidate.sector in current_sectors:
                continue

            # Find lowest-scoring same-sector duplicate to replace
            over_sectors = [
                s for s in selected
                if sector_count.get(s.candidate.sector, 0) > 1
            ]
            if not over_sectors:
                break
            worst = min(over_sectors, key=lambda s: s.final_score)
            old_sec = worst.candidate.sector
            selected.remove(worst)
            sector_count[old_sec] -= 1

            selected.append(sc)
            new_sec = sc.candidate.sector
            sector_count[new_sec] = sector_count.get(new_sec, 0) + 1
            current_sectors.add(new_sec)
            selected_symbols.add(sc.candidate.symbol)
            needed -= 1
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_universe_optimizer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add autotrader/universe/optimizer.py tests/unit/test_universe_optimizer.py
git commit -m "feat: portfolio optimizer with sector and regime constraints"
```

---

### Task 7: Universe Selector (Orchestrator)

**Files:**
- Create: `autotrader/universe/selector.py`
- Test: `tests/unit/test_universe_selector.py`

**Step 1: Write tests**

```python
# tests/unit/test_universe_selector.py
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from autotrader.universe import StockInfo, StockCandidate, ScoredCandidate, UniverseResult
from autotrader.universe.selector import UniverseSelector


def _mock_provider(symbols_sectors: list[tuple[str, str]]) -> MagicMock:
    provider = MagicMock()
    provider.fetch.return_value = [
        StockInfo(symbol=s, sector=sec, sub_industry="") for s, sec in symbols_sectors
    ]
    return provider


class TestUniverseSelector:
    def test_creates_with_defaults(self):
        sel = UniverseSelector()
        assert sel is not None

    def test_build_candidates_returns_stock_candidates(self):
        sel = UniverseSelector()
        bars_by_symbol = {
            "AAPL": _make_bar_series("AAPL", 100, 150.0),
        }
        infos = [StockInfo("AAPL", "Tech", "HW")]
        result = sel._build_candidates(infos, bars_by_symbol)
        assert len(result) == 1
        assert isinstance(result[0], StockCandidate)
        assert result[0].symbol == "AAPL"

    def test_build_candidates_skips_insufficient_data(self):
        sel = UniverseSelector()
        bars_by_symbol = {
            "AAPL": _make_bar_series("AAPL", 5, 150.0),  # too few bars
        }
        infos = [StockInfo("AAPL", "Tech", "HW")]
        result = sel._build_candidates(infos, bars_by_symbol)
        assert len(result) == 0

    def test_compute_backtest_scores(self):
        sel = UniverseSelector()
        bars = _make_bar_series("AAPL", 150, 100.0)
        score = sel._run_backtest_for_symbol(bars)
        assert 0.0 <= score <= 1.0

    def test_full_pipeline_returns_universe_result(self):
        sel = UniverseSelector(target_size=3)
        # Mock the data fetching parts, test the scoring/optimization logic
        candidates = [
            StockCandidate("A", "Tech", 100.0, 100e6, 2e6, 0.02, 0.05, 0.40, 0.40, 0.5),
            StockCandidate("B", "Fin", 100.0, 80e6, 1.5e6, 0.025, 0.03, 0.35, 0.45, 0.4),
            StockCandidate("C", "Health", 100.0, 60e6, 1.2e6, 0.018, 0.08, 0.50, 0.20, 0.6),
            StockCandidate("D", "Energy", 100.0, 70e6, 1.8e6, 0.022, 0.04, 0.30, 0.50, 0.3),
        ]
        backtest_scores = {"A": 0.6, "B": 0.5, "C": 0.7, "D": 0.4}
        result = sel._score_and_optimize(candidates, backtest_scores, current_pool=[])
        assert isinstance(result, UniverseResult)
        assert len(result.symbols) == 3


def _make_bar_series(symbol: str, n: int, start_price: float) -> list:
    from autotrader.core.types import Bar
    from datetime import timedelta
    import random
    random.seed(42)
    bars = []
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = start_price
    for i in range(n):
        change = random.gauss(0, 2)
        price = max(10, price + change)
        bars.append(Bar(
            symbol=symbol,
            timestamp=base + timedelta(days=i),
            open=price - 0.5,
            high=price + 1.5,
            low=price - 1.5,
            close=price,
            volume=1_500_000.0,
        ))
    return bars
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_universe_selector.py -v`
Expected: FAIL

**Step 3: Implement**

```python
# autotrader/universe/selector.py
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from statistics import mean, stdev

from autotrader.core.types import Bar
from autotrader.core.config import RiskConfig
from autotrader.universe import StockInfo, StockCandidate, ScoredCandidate, UniverseResult
from autotrader.universe.filters import HardFilter
from autotrader.universe.scorer import ProxyScorer, BacktestScorer
from autotrader.universe.optimizer import PortfolioOptimizer
from autotrader.backtest.engine import BacktestEngine
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout
from autotrader.strategy.adx_pullback import AdxPullback
from autotrader.strategy.overbought_short import OverboughtShort
from autotrader.strategy.regime_momentum import RegimeMomentum

logger = logging.getLogger(__name__)

_MIN_BARS = 60  # minimum bars needed to compute indicators


class UniverseSelector:
    def __init__(
        self,
        initial_balance: float = 3000.0,
        target_size: int = 15,
        proxy_weight: float = 0.50,
        backtest_weight: float = 0.50,
    ) -> None:
        self._initial_balance = initial_balance
        self._target_size = target_size
        self._proxy_weight = proxy_weight
        self._backtest_weight = backtest_weight
        self._hard_filter = HardFilter()
        self._proxy_scorer = ProxyScorer()
        self._backtest_scorer = BacktestScorer()
        self._optimizer = PortfolioOptimizer(target_size=target_size)
        self._risk_config = RiskConfig(
            max_position_pct=0.30,
            max_drawdown_pct=0.30,
            max_open_positions=5,
        )

    def _build_candidates(
        self,
        infos: list[StockInfo],
        bars_by_symbol: dict[str, list[Bar]],
    ) -> list[StockCandidate]:
        candidates: list[StockCandidate] = []
        for info in infos:
            bars = bars_by_symbol.get(info.symbol, [])
            if len(bars) < _MIN_BARS:
                continue
            candidate = self._bars_to_candidate(info, bars)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _bars_to_candidate(self, info: StockInfo, bars: list[Bar]) -> StockCandidate | None:
        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        close = closes[-1]
        avg_volume = mean(volumes[-20:]) if len(volumes) >= 20 else mean(volumes)
        avg_dollar_volume = avg_volume * close

        # ATR ratio (14-period)
        trs: list[float] = []
        for i in range(1, min(15, len(bars))):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
        atr = mean(trs) if trs else 0.0
        atr_ratio = atr / close if close > 0 else 0.0

        # Gap frequency (2%+ overnight gaps in last 60 days)
        recent = bars[-60:] if len(bars) >= 60 else bars
        gaps = 0
        for i in range(1, len(recent)):
            gap_pct = abs(recent[i].open - recent[i - 1].close) / recent[i - 1].close
            if gap_pct >= 0.02:
                gaps += 1
        gap_frequency = gaps / max(1, len(recent) - 1)

        # ADX proxy: trend_pct and range_pct using price momentum
        lookback = bars[-120:] if len(bars) >= 120 else bars
        trend_count = 0
        range_count = 0
        for i in range(14, len(lookback)):
            window = lookback[i - 14 : i + 1]
            rets = [
                (window[j].close - window[j - 1].close) / window[j - 1].close
                for j in range(1, len(window))
            ]
            directional = abs(sum(rets))
            total = sum(abs(r) for r in rets)
            ratio = directional / total if total > 0 else 0.0
            if ratio > 0.30:
                trend_count += 1
            elif ratio < 0.15:
                range_count += 1
        total_windows = max(1, len(lookback) - 14)
        trend_pct = trend_count / total_windows
        range_pct = range_count / total_windows

        # Vol cycle: CV of BB width proxy
        if len(closes) >= 20:
            widths: list[float] = []
            for i in range(20, len(closes)):
                window = closes[i - 20 : i]
                sd = stdev(window) if len(window) > 1 else 0.0
                widths.append(sd)
            vol_cycle = stdev(widths) / mean(widths) if widths and mean(widths) > 0 else 0.0
        else:
            vol_cycle = 0.0

        return StockCandidate(
            symbol=info.symbol,
            sector=info.sector,
            close=close,
            avg_dollar_volume=avg_dollar_volume,
            avg_volume=avg_volume,
            atr_ratio=atr_ratio,
            gap_frequency=gap_frequency,
            trend_pct=trend_pct,
            range_pct=range_pct,
            vol_cycle=vol_cycle,
        )

    def _run_backtest_for_symbol(self, bars: list[Bar]) -> float:
        engine = BacktestEngine(self._initial_balance, self._risk_config)
        strategies = [
            RsiMeanReversion(), BbSqueezeBreakout(), AdxPullback(),
            OverboughtShort(), RegimeMomentum(),
        ]
        for s in strategies:
            engine.add_strategy(s)

        result = engine.run(bars)
        strategy_names = {t.strategy for t in result.trades}

        return self._backtest_scorer.score_from_metrics(
            total_trades=result.total_trades,
            win_rate=result.metrics.get("win_rate", 0.0),
            profit_factor=result.metrics.get("profit_factor", 0.0),
            strategies_active=len(strategy_names),
        )

    def _score_and_optimize(
        self,
        candidates: list[StockCandidate],
        backtest_scores: dict[str, float],
        current_pool: list[str],
        open_positions: list[str] | None = None,
    ) -> UniverseResult:
        proxy_scores = self._proxy_scorer.score(candidates, current_pool)

        scored: list[ScoredCandidate] = []
        for i, c in enumerate(candidates):
            ps = proxy_scores[i]
            bs = backtest_scores.get(c.symbol, 0.0)
            final = self._proxy_weight * ps + self._backtest_weight * bs
            scored.append(ScoredCandidate(
                candidate=c, proxy_score=ps, backtest_score=bs, final_score=round(final, 6),
            ))

        optimized = self._optimizer.optimize(
            scored, current_pool=current_pool, open_positions=open_positions,
        )

        new_symbols = [s.candidate.symbol for s in optimized]
        rotation_in = [s for s in new_symbols if s not in current_pool]
        rotation_out = [s for s in current_pool if s not in new_symbols]

        return UniverseResult(
            symbols=new_symbols,
            scored=optimized,
            timestamp=datetime.now(tz=timezone.utc),
            rotation_in=rotation_in,
            rotation_out=rotation_out,
        )

    def select(
        self,
        infos: list[StockInfo],
        bars_by_symbol: dict[str, list[Bar]],
        current_pool: list[str] | None = None,
        open_positions: list[str] | None = None,
    ) -> UniverseResult:
        current_pool = current_pool or []
        candidates = self._build_candidates(infos, bars_by_symbol)
        filtered = self._hard_filter.filter(candidates)
        logger.info("Hard filter: %d -> %d candidates", len(candidates), len(filtered))

        backtest_scores: dict[str, float] = {}
        for c in filtered:
            bars = bars_by_symbol.get(c.symbol, [])
            if len(bars) >= _MIN_BARS:
                backtest_scores[c.symbol] = self._run_backtest_for_symbol(bars)

        return self._score_and_optimize(
            filtered, backtest_scores, current_pool, open_positions,
        )
```

**Step 4: Run tests**

Run: `pytest tests/unit/test_universe_selector.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add autotrader/universe/selector.py tests/unit/test_universe_selector.py
git commit -m "feat: universe selector orchestrator with hybrid scoring"
```

---

### Task 8: CLI Script

**Files:**
- Create: `scripts/run_universe_selection.py`

**Step 1: Implement CLI script**

```python
# scripts/run_universe_selection.py
"""Universe selection runner: selects optimal stocks from S&P 500.

Usage:
    python scripts/run_universe_selection.py
    python scripts/run_universe_selection.py --days 120 --target 15
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="S&P 500 Universe Selection")
    parser.add_argument("--days", type=int, default=120, help="Calendar days of history (default: 120)")
    parser.add_argument("--target", type=int, default=15, help="Target universe size (default: 15)")
    parser.add_argument("--balance", type=float, default=3000.0, help="Initial balance (default: 3000)")
    parser.add_argument("--max-candidates", type=int, default=50, help="Max candidates to backtest (default: 50)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    load_dotenv(_PROJECT_ROOT / "config" / ".env")
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        print("[ERROR] ALPACA_API_KEY or ALPACA_SECRET_KEY not found in config/.env")
        sys.exit(1)

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    from autotrader.core.types import Bar
    from autotrader.universe.provider import SP500Provider
    from autotrader.universe.selector import UniverseSelector
    from autotrader.universe.earnings import EarningsCalendar

    print("=" * 80)
    print("  AutoTrader v2 -- S&P 500 Universe Selection")
    print("=" * 80)

    # Step 1: Fetch S&P 500 list
    print("\n  [1/5] Fetching S&P 500 constituents...")
    provider = SP500Provider()
    infos = provider.fetch()
    print(f"  Found {len(infos)} constituents")

    # Step 2: Fetch earnings calendar
    print("\n  [2/5] Fetching earnings calendar...")
    earnings_cal = EarningsCalendar()
    symbols = [i.symbol for i in infos]
    try:
        earnings_cal.fetch(symbols[:args.max_candidates])
    except Exception as exc:
        print(f"  [WARN] Earnings fetch partial failure: {exc}")
    today = datetime.now().date()
    blackout = earnings_cal.blackout_symbols(symbols, today)
    print(f"  {len(blackout)} symbols in earnings blackout")

    # Step 3: Fetch historical bars
    print(f"\n  [3/5] Fetching {args.days}-day history (batched)...")
    client = StockHistoricalDataClient(api_key, secret_key)
    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=args.days)

    # Filter out blackout symbols
    active_symbols = [s for s in symbols if s not in blackout][:args.max_candidates]

    bars_by_symbol: dict[str, list[Bar]] = {}
    batch_size = 50
    for i in range(0, len(active_symbols), batch_size):
        batch = active_symbols[i : i + batch_size]
        print(f"  Fetching batch {i // batch_size + 1}: {len(batch)} symbols...")
        try:
            request = StockBarsRequest(
                symbol_or_symbols=batch,
                timeframe=TimeFrame.Day,
                start=start_date,
                end=end_date,
            )
            raw = client.get_stock_bars(request)
            for sym in batch:
                try:
                    alpaca_bars = raw[sym]
                except (KeyError, IndexError):
                    continue
                if not alpaca_bars:
                    continue
                bars_by_symbol[sym] = [
                    Bar(
                        symbol=sym,
                        timestamp=ab.timestamp,
                        open=float(ab.open),
                        high=float(ab.high),
                        low=float(ab.low),
                        close=float(ab.close),
                        volume=float(ab.volume),
                    )
                    for ab in alpaca_bars
                ]
        except Exception as exc:
            print(f"  [ERROR] Batch fetch failed: {exc}")

    print(f"  Received data for {len(bars_by_symbol)} symbols")

    # Step 4: Run universe selection
    print(f"\n  [4/5] Running universe selection (target: {args.target})...")
    selector = UniverseSelector(
        initial_balance=args.balance,
        target_size=args.target,
    )
    result = selector.select(infos, bars_by_symbol)

    # Step 5: Display results
    print(f"\n  [5/5] Selection complete!")

    print("\n\n" + "=" * 80)
    print("  SELECTED UNIVERSE")
    print("=" * 80)

    header = f"  {'#':<4}{'Symbol':<8}{'Sector':<25}{'Score':>8}{'Proxy':>8}{'BT':>8}{'Trend%':>8}{'Range%':>8}"
    print(header)
    print("  " + "-" * 76)

    for i, sc in enumerate(result.scored, 1):
        c = sc.candidate
        print(
            f"  {i:<4}{c.symbol:<8}{c.sector:<25}"
            f"{sc.final_score:>8.3f}{sc.proxy_score:>8.3f}{sc.backtest_score:>8.3f}"
            f"{c.trend_pct:>7.1%}{c.range_pct:>8.1%}"
        )

    if result.rotation_in:
        print(f"\n  IN:  {', '.join(result.rotation_in)}")
    if result.rotation_out:
        print(f"  OUT: {', '.join(result.rotation_out)}")

    print(f"\n  Symbols: {result.symbols}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
git add scripts/run_universe_selection.py
git commit -m "feat: CLI script for S&P 500 universe selection"
```

---

### Task 9: Integration Tests

**Files:**
- Create: `tests/integration/test_universe_pipeline.py`

**Step 1: Write integration tests**

```python
# tests/integration/test_universe_pipeline.py
from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta

import pytest

from autotrader.core.types import Bar
from autotrader.universe import StockInfo, StockCandidate, UniverseResult
from autotrader.universe.filters import HardFilter
from autotrader.universe.scorer import ProxyScorer, BacktestScorer
from autotrader.universe.optimizer import PortfolioOptimizer
from autotrader.universe.selector import UniverseSelector


def _make_bars(symbol: str, n: int = 120, base_price: float = 100.0, seed: int = 42) -> list[Bar]:
    random.seed(seed)
    bars: list[Bar] = []
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = base_price
    for i in range(n):
        change = random.gauss(0, 2)
        price = max(20.0, price + change)
        bars.append(Bar(
            symbol=symbol,
            timestamp=base + timedelta(days=i),
            open=price - 0.5,
            high=price + 2.0,
            low=price - 2.0,
            close=price,
            volume=random.uniform(1e6, 5e6),
        ))
    return bars


def _make_infos(n: int = 10) -> list[StockInfo]:
    sectors = ["Tech", "Finance", "Health", "Energy", "Consumer"]
    return [
        StockInfo(symbol=f"S{i:02d}", sector=sectors[i % len(sectors)], sub_industry="")
        for i in range(n)
    ]


class TestFullPipeline:
    def test_end_to_end_selection(self):
        infos = _make_infos(20)
        bars_by_symbol = {
            info.symbol: _make_bars(info.symbol, 120, 100.0 + i * 5, seed=i)
            for i, info in enumerate(infos)
        }
        selector = UniverseSelector(target_size=8)
        result = selector.select(infos, bars_by_symbol)
        assert isinstance(result, UniverseResult)
        assert 1 <= len(result.symbols) <= 8

    def test_rotation_tracks_changes(self):
        infos = _make_infos(15)
        bars_by_symbol = {
            info.symbol: _make_bars(info.symbol, 120, 100.0, seed=i)
            for i, info in enumerate(infos)
        }
        selector = UniverseSelector(target_size=5)

        # First selection
        r1 = selector.select(infos, bars_by_symbol)
        assert len(r1.rotation_in) > 0
        assert len(r1.rotation_out) == 0

        # Second selection with existing pool
        r2 = selector.select(infos, bars_by_symbol, current_pool=r1.symbols)
        # With same data, should retain most stocks
        assert len(r2.rotation_in) <= 3

    def test_hard_filter_reduces_candidates(self):
        infos = _make_infos(10)
        bars_by_symbol = {}
        for i, info in enumerate(infos):
            # Half with low volume (will be filtered)
            vol = 500_000.0 if i < 5 else 2_000_000.0
            bars = []
            base = datetime(2025, 1, 1, tzinfo=timezone.utc)
            for j in range(120):
                bars.append(Bar(
                    symbol=info.symbol,
                    timestamp=base + timedelta(days=j),
                    open=99, high=101, low=98, close=100,
                    volume=vol,
                ))
            bars_by_symbol[info.symbol] = bars

        selector = UniverseSelector(target_size=5)
        result = selector.select(infos, bars_by_symbol)
        # Only high-volume stocks should pass
        assert len(result.symbols) <= 5

    def test_backtest_scores_are_bounded(self):
        selector = UniverseSelector()
        bars = _make_bars("TEST", 150, 100.0)
        score = selector._run_backtest_for_symbol(bars)
        assert 0.0 <= score <= 1.0

    def test_open_positions_preserved(self):
        infos = _make_infos(10)
        bars_by_symbol = {
            info.symbol: _make_bars(info.symbol, 120, 100.0, seed=i)
            for i, info in enumerate(infos)
        }
        selector = UniverseSelector(target_size=5)
        r1 = selector.select(infos, bars_by_symbol)

        # Pretend we have open position in one stock
        held = r1.symbols[0]
        r2 = selector.select(
            infos, bars_by_symbol,
            current_pool=r1.symbols,
            open_positions=[held],
        )
        assert held in r2.symbols
```

**Step 2: Run tests**

Run: `pytest tests/integration/test_universe_pipeline.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_universe_pipeline.py
git commit -m "test: universe selection integration tests"
```

---

### Task 10: Update pyproject.toml and Final Integration

**Files:**
- Modify: `pyproject.toml` (add yfinance dependency)
- Modify: `autotrader/main.py` (optional: add universe config)

**Step 1: Add yfinance dependency**

Add `yfinance>=0.2.0` to `[project.dependencies]` in `pyproject.toml`.

**Step 2: Install and verify**

Run: `pip install yfinance`
Run: `pytest tests/ -v --tb=short`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add yfinance dependency for earnings calendar"
```

---

## Dependency Graph

```
Task 1 (types + provider) ──┐
Task 2 (earnings)          ──┤
Task 3 (filters)           ──┼──> Task 7 (selector) ──> Task 8 (CLI)
Task 4 (proxy scorer)      ──┤                          Task 9 (integration tests)
Task 5 (backtest scorer)   ──┤                          Task 10 (deps + final)
Task 6 (optimizer)         ──┘
```

Tasks 1-6 are independent and can run in parallel.
Tasks 7-10 depend on 1-6 and must run after.

## Parallel Agent Assignment

| Agent | Tasks | Files |
|-------|-------|-------|
| Agent A | Task 1 + Task 2 | provider.py, earnings.py, __init__.py |
| Agent B | Task 3 + Task 4 | filters.py, scorer.py |
| Agent C | Task 5 + Task 6 | scorer.py (backtest tests), optimizer.py |
| Agent D (after A-C) | Task 7 + Task 8 + Task 9 + Task 10 | selector.py, CLI, integration |
