"""BatchBacktester: simulates the nightly batch trading architecture over historical data.

Full simulation cycle per trading day:
  1. Evening (signal generation): run all 3 strategies against the symbol universe.
  2. Gap filter: discard signals where the next-day open gap exceeds the threshold.
  3. Signal ranking: select top-N candidates by composite score.
  4. Next-day entry: simulate fills at next-day open price.
  5. Daily exit evaluation: check SL/TP/trailing/time rules using daily high/low.
  6. Intraday SL/TP approximation: if daily low <= SL -> stopped out at SL price;
     if daily high >= TP -> took profit at TP price. Both-hit disambiguation by
     checking whether open is closer to SL or TP.
  7. Track MFE/MAE per position using bar high/low.
  8. Re-entry block: same symbol cannot be re-entered on the same date it was closed.
  9. Collect all completed trades with full metadata for downstream analysis.

Key design decisions:
  - Uses the actual strategy implementations from autotrader.strategy (no mocking).
  - Uses IndicatorEngine for correct indicator computation on rolling bar history.
  - ExitRuleEngine handles the SL/TP/trailing/time logic exactly as in live trading.
  - Positions are sized via a simplified ATR-based risk formula (2% account risk
    per trade, same as the live AllocationEngine's risk-based sizing).
  - No intraday bar data required; SL/TP checks use daily high/low bars.
  - Graduated Drawdown Response (GDR): per-strategy drawdown tracking with
    independent tier assignments. Portfolio safety net overrides when total DD
    is extreme. Backward-compatible with portfolio-level GDR via toggle.
"""
from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from autotrader.batch.ranking import SignalRanker
from autotrader.batch.types import Candidate, ScanResult
from autotrader.core.types import Bar, MarketContext, Timeframe
from autotrader.execution.exit_rules import (
    ExitRuleEngine,
    HeldPosition,
    _MAX_HOLD_DAYS,
    _SL_ATR_MULT,
    _TP_ATR_MULT,
    _TRAILING_STRATEGIES,
    _TRAILING_ATR_MULT,
    _TRAILING_ACTIVATION_ATR,
    _STAGE1_BE_ACTIVATION_ATR,
    _STAGE2_PROFIT_ACTIVATION_ATR,
    _STAGE2_PROFIT_LOCK_ATR,
    _EMERGENCY_LOSS_IMMEDIATE_PCT,
)
from autotrader.indicators.base import IndicatorSpec
from autotrader.indicators.engine import IndicatorEngine
from autotrader.strategy.consecutive_down import ConsecutiveDown
# from autotrader.strategy.ema_cross_trend import EmaCrossTrend  # disabled after backtest RED LINE fail
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants matching live system configuration
# ---------------------------------------------------------------------------

# Strategies in each entry group
_GROUP_A: frozenset[str] = frozenset({"rsi_mean_reversion", "consecutive_down"})
_GROUP_B: frozenset[str] = frozenset()

# Position sizing constants
_RISK_PER_TRADE_PCT: float = 0.02       # 2% of equity at risk per trade (legacy default)
_MAX_POSITION_PCT: float = 0.20         # hard cap: max 20% of equity per position
_MAX_LONG_POSITIONS: int = 4            # hard cap on concurrent long positions
_MAX_SHORT_POSITIONS: int = 3           # hard cap on concurrent short positions
_MAX_TOTAL_POSITIONS: int = 5           # overall position cap
_MAX_LOSS_PER_TRADE_PCT: float = 0.03   # hard cap: max 3% of equity loss per trade

# --- Per-Strategy GDR Configuration ---
_PER_STRATEGY_GDR: bool = True          # Toggle: True = per-strategy, False = portfolio-level

# Per-strategy base risk (replaces single _RISK_PER_TRADE_PCT for all)
_STRATEGY_BASE_RISK: dict[str, float] = {
    "rsi_mean_reversion": 0.01,          # 1% (reduced from 2%)
    "consecutive_down": 0.015,           # 1.5% (reduced: wider SL compensated by lower risk)
    "ema_cross_trend": 0.015,            # 1.5%
}
_DEFAULT_BASE_RISK: float = 0.02        # fallback for unknown strategies

# Per-strategy GDR thresholds: (tier1_dd, tier2_dd)
_STRATEGY_GDR_THRESHOLDS: dict[str, tuple[float, float]] = {
    "rsi_mean_reversion": (0.025, 0.05),  # Tier 1 at 2.5% DD, Tier 2 at 5% DD
    "consecutive_down": (0.03, 0.06),     # Tier 1 at 3% DD, Tier 2 at 6% DD
    "ema_cross_trend": (0.04, 0.08),      # Tier 1 at 4% DD, Tier 2 at 8% DD
}

# GDR Risk Multipliers (Tier 2 = HALT, 0 entries)
_GDR_RISK_MULT: dict[int, float] = {
    0: 1.0,    # Tier 0: normal
    1: 0.5,    # Tier 1: reduced
    2: 0.0,    # Tier 2: HALTED (no entries)
}

# Per-strategy entry limits per tier
_GDR_STRATEGY_ENTRIES: dict[int, int] = {
    0: 1,   # Tier 0: 1 entry per strategy per day
    1: 1,   # Tier 1: 1 entry per strategy per day
    2: 0,   # Tier 2: 0 entries (halted)
}

_MAX_DAILY_ENTRIES: int = 3             # portfolio-level total cap (was 2)

# Portfolio Safety Net (overrides per-strategy GDR when total DD is extreme)
_PORTFOLIO_SAFETY_NET_DD: float = 0.20          # 20% total portfolio DD
_PORTFOLIO_SAFETY_NET_RECOVERY: float = 0.15    # resume per-strategy GDR when DD < 15%
_PORTFOLIO_SAFETY_NET_ENTRIES: int = 1           # 1 entry total when safety net active
_PORTFOLIO_SAFETY_NET_RISK: float = 0.005        # 0.5% risk when safety net active

# --- Legacy Portfolio-Level GDR (backward compat when _PER_STRATEGY_GDR = False) ---
_GDR_ROLLING_WINDOW: int = 60           # rolling peak lookback (trading days)
_GDR_TIER1_DD: float = 0.15            # DD > 15% -> Tier 1 (legacy)
_GDR_TIER2_DD: float = 0.25            # DD > 25% -> Tier 2 (legacy)

_GDR_LEGACY_RISK_MULT: dict[int, float] = {
    0: 1.0,    # Tier 0: normal  (RISK_PER_TRADE_PCT * 1.0 = 2%)
    1: 0.5,    # Tier 1: reduced (RISK_PER_TRADE_PCT * 0.5 = 1%)
    2: 0.25,   # Tier 2: minimal (RISK_PER_TRADE_PCT * 0.25 = 0.5%)
}

_GDR_MAX_ENTRIES: dict[int, int] = {
    0: 2,   # Tier 0: 2 entries/day (same as legacy _MAX_DAILY_ENTRIES)
    1: 1,   # Tier 1: 1 entry/day
    2: 1,   # Tier 2: 1 entry/day
}

_STRATEGY_NAMES: list[str] = ["rsi_mean_reversion", "consecutive_down"]

# Soft per-strategy position cap (applied when 2+ strategies have pending signals)
_SOFT_STRATEGY_CAP: int = 2             # max positions per strategy under multi-strategy competition

# Minimum bars needed before a symbol can generate a valid signal
_MIN_BARS_WARMUP: int = 60

# Gap filter threshold (3%, tightened from 5%)
_DEFAULT_GAP_THRESHOLD: float = 0.03

# Slippage model: 3 basis points on entry and exit fills
_SLIPPAGE_BPS: float = 0.0003

# Commission per share (approx $0.005 for most retail brokers)
_COMMISSION_PER_SHARE: float = 0.005

# Top-N candidates selected per day
_TOP_N_CANDIDATES: int = 12

# Strategies instantiated once per simulator instance
_STRATEGY_CLASSES = [
    RsiMeanReversion,
    ConsecutiveDown,
]


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class BatchTradeRecord:
    """Complete record of a single closed position from the batch backtest.

    Attributes:
        trade_id: Sequential trade identifier.
        symbol: Ticker symbol.
        strategy: Strategy that generated the entry signal.
        direction: "long" or "short".
        entry_date: Date of position entry (next-day fill date).
        exit_date: Date of position exit.
        entry_price: Simulated fill price at open (with slippage).
        exit_price: Simulated exit price (SL/TP/time, with slippage).
        qty: Number of shares held.
        pnl: Dollar PnL for the trade (net of commissions).
        pnl_pct: Percentage PnL from entry price.
        bars_held: Number of daily bars held.
        exit_reason: Reason for exit (stop_loss, take_profit, trailing_stop,
                     time_exit, emergency_immediate, emergency_confirmed).
        mfe_pct: Maximum favourable excursion (peak unrealized gain %).
        mae_pct: Maximum adverse excursion (peak unrealized loss %).
        entry_atr: ATR value at entry (for parameter analysis).
        signal_strength: Strength of the entry signal.
        gap_pct: Overnight gap at entry date (open vs prior close).
    """
    trade_id: int
    symbol: str
    strategy: str
    direction: Literal["long", "short"]
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    pnl_pct: float
    bars_held: int
    exit_reason: str
    mfe_pct: float
    mae_pct: float
    entry_atr: float
    signal_strength: float
    gap_pct: float
    entry_day_skip_applied: bool = True


@dataclass
class DailySnapshot:
    """Portfolio equity snapshot for one trading day."""
    date: date
    equity: float
    cash: float
    open_positions: int
    new_entries: int
    exits: int
    daily_pnl: float


@dataclass
class BatchBacktestResult:
    """Aggregated results from a full batch backtest run.

    Attributes:
        trades: All completed trade records.
        daily_snapshots: Day-by-day portfolio equity.
        equity_curve: List of (date, equity) pairs.
        metrics: Portfolio-level performance metrics dict.
        per_strategy_metrics: Metrics broken down by strategy name.
        config: Configuration dict used for this run.
    """
    trades: list[BatchTradeRecord]
    daily_snapshots: list[DailySnapshot]
    equity_curve: list[tuple[date, float]]
    metrics: dict
    per_strategy_metrics: dict[str, dict]
    config: dict


# ---------------------------------------------------------------------------
# Internal position state (extends HeldPosition with MFE/MAE tracking)
# ---------------------------------------------------------------------------

@dataclass
class _SimPosition:
    """Live simulation position tracking per symbol.

    Extends HeldPosition with PnL and MFE/MAE tracking needed for
    reporting that ExitRuleEngine doesn't expose directly.
    """
    held: HeldPosition
    qty: float
    entry_date: date
    signal_strength: float
    gap_pct: float
    # MFE/MAE in price terms (will be converted to % at close)
    mfe_price: float = field(init=False)
    mae_price: float = field(init=False)

    def __post_init__(self) -> None:
        self.mfe_price = self.held.entry_price
        self.mae_price = self.held.entry_price

    def update_extremes(self, bar_high: float, bar_low: float) -> None:
        """Update MFE/MAE price records with a new bar."""
        if self.held.direction == "long":
            self.mfe_price = max(self.mfe_price, bar_high)
            self.mae_price = min(self.mae_price, bar_low)
        else:  # short
            # For short: MFE = lower lows, MAE = higher highs
            self.mfe_price = min(self.mfe_price, bar_low)
            self.mae_price = max(self.mae_price, bar_high)

    @property
    def mfe_pct(self) -> float:
        ep = self.held.entry_price
        if ep <= 0:
            return 0.0
        if self.held.direction == "long":
            return (self.mfe_price - ep) / ep
        else:
            return (ep - self.mfe_price) / ep

    @property
    def mae_pct(self) -> float:
        ep = self.held.entry_price
        if ep <= 0:
            return 0.0
        if self.held.direction == "long":
            return max(0.0, (ep - self.mae_price) / ep)
        else:
            return max(0.0, (self.mae_price - ep) / ep)


# ---------------------------------------------------------------------------
# Synthetic data generator
# ---------------------------------------------------------------------------

class SyntheticDataGenerator:
    """Generates realistic S&P 500-like daily bars using geometric random walk.

    Parameters are calibrated to approximate S&P 500 individual stock
    characteristics: ~25% annual vol, ~10% annual drift, realistic ATR
    relative to price, and OHLCV relationships.

    Usage::

        gen = SyntheticDataGenerator(seed=42)
        bars = gen.generate("AAPL", start_price=180.0, num_bars=504)
    """

    def __init__(self, seed: int = 42) -> None:
        import random
        self._rng = random.Random(seed)

    def generate(
        self,
        symbol: str,
        start_price: float = 100.0,
        num_bars: int = 504,
        annual_drift: float = 0.10,
        annual_vol: float = 0.25,
        start_date: date | None = None,
    ) -> list[Bar]:
        """Generate a list of synthetic daily bars for one symbol.

        Args:
            symbol: Ticker symbol to embed in each Bar.
            start_price: Initial price for the first bar.
            num_bars: Number of trading days to generate.
            annual_drift: Expected annual log return (default 10%).
            annual_vol: Annual volatility (default 25%).
            start_date: Starting calendar date; defaults to 504 trading
                        days before today.

        Returns:
            List of Bar objects ordered oldest-first.
        """
        if start_date is None:
            # Approximate: 252 trading days per year
            approx_days = int(num_bars * 365 / 252)
            start_date = date.today() - timedelta(days=approx_days)

        daily_drift = annual_drift / 252.0
        daily_vol = annual_vol / math.sqrt(252.0)

        bars: list[Bar] = []
        price = start_price
        current_date = start_date

        for _ in range(num_bars):
            # Skip weekends for realistic trading calendar
            while current_date.weekday() >= 5:
                current_date += timedelta(days=1)

            # GBM log return
            z = self._rng.gauss(0, 1)
            log_return = daily_drift - 0.5 * daily_vol**2 + daily_vol * z
            close = price * math.exp(log_return)

            # Generate realistic OHLC from close
            daily_range_pct = abs(self._rng.gauss(0, daily_vol * 0.7)) + daily_vol * 0.3
            half_range = close * daily_range_pct * 0.5

            # Open: slight gap from prior close (0-0.5% typical)
            gap = self._rng.gauss(0, close * 0.002)
            open_ = max(price + gap, price * 0.90)

            high = max(open_, close) + abs(self._rng.gauss(0, half_range * 0.8))
            low = min(open_, close) - abs(self._rng.gauss(0, half_range * 0.8))
            low = max(low, close * 0.90)  # cap max intraday loss at 10%

            # Volume: log-normal distribution around 1M shares
            volume = max(10_000, int(self._rng.lognormvariate(13.8, 0.8)))

            ts = datetime(current_date.year, current_date.month, current_date.day, 9, 30, tzinfo=timezone.utc)
            bars.append(Bar(
                symbol=symbol,
                timestamp=ts,
                open=round(open_, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=float(volume),
                timeframe=Timeframe.DAILY,
            ))

            price = close
            current_date += timedelta(days=1)

        return bars

    def generate_universe(
        self,
        symbols: list[str],
        num_bars: int = 504,
        start_date: date | None = None,
    ) -> dict[str, list[Bar]]:
        """Generate bars for a universe of symbols with correlated returns.

        Uses a market factor (beta-weighted SPY-like return) plus idiosyncratic
        noise to produce correlated but not identical price series.

        Args:
            symbols: List of symbol names.
            num_bars: Number of daily bars per symbol.
            start_date: Common start date for all symbols.

        Returns:
            Dict mapping symbol -> list[Bar].
        """
        if start_date is None:
            approx_days = int(num_bars * 365 / 252)
            start_date = date.today() - timedelta(days=approx_days)

        # Generate correlated market factor returns first
        market_returns = self._generate_market_returns(num_bars)

        result: dict[str, list[Bar]] = {}
        for i, symbol in enumerate(symbols):
            # Each symbol has a random beta [0.5, 1.8] and random idiosyncratic vol
            beta = 0.5 + self._rng.random() * 1.3
            idio_vol = 0.15 + self._rng.random() * 0.20  # 15-35% idiosyncratic
            start_price = 20.0 + self._rng.random() * 280.0  # $20-$300

            bars = self._generate_correlated_bars(
                symbol=symbol,
                start_price=start_price,
                market_returns=market_returns,
                beta=beta,
                idio_vol=idio_vol / math.sqrt(252.0),
                start_date=start_date,
            )
            result[symbol] = bars

        return result

    def _generate_market_returns(self, num_bars: int) -> list[float]:
        """Generate a sequence of daily market (SPY-like) log returns."""
        daily_drift = 0.10 / 252.0
        daily_vol = 0.15 / math.sqrt(252.0)
        returns = []
        for _ in range(num_bars):
            z = self._rng.gauss(0, 1)
            r = daily_drift - 0.5 * daily_vol**2 + daily_vol * z
            returns.append(r)
        return returns

    def _generate_correlated_bars(
        self,
        symbol: str,
        start_price: float,
        market_returns: list[float],
        beta: float,
        idio_vol: float,
        start_date: date,
    ) -> list[Bar]:
        """Generate bars correlated with a market factor."""
        bars: list[Bar] = []
        price = start_price
        current_date = start_date

        for mkt_ret in market_returns:
            while current_date.weekday() >= 5:
                current_date += timedelta(days=1)

            idio_z = self._rng.gauss(0, 1)
            log_return = beta * mkt_ret + idio_vol * idio_z
            close = price * math.exp(log_return)

            daily_vol = abs(log_return) * 0.5 + idio_vol
            half_range = close * daily_vol * 0.5

            gap = self._rng.gauss(0, close * 0.002)
            open_ = max(price + gap, price * 0.88)
            high = max(open_, close) + abs(self._rng.gauss(0, half_range * 0.8))
            low = min(open_, close) - abs(self._rng.gauss(0, half_range * 0.8))
            low = max(low, close * 0.88)

            volume = max(10_000, int(self._rng.lognormvariate(13.8, 0.8)))
            ts = datetime(current_date.year, current_date.month, current_date.day, 9, 30, tzinfo=timezone.utc)

            bars.append(Bar(
                symbol=symbol,
                timestamp=ts,
                open=round(open_, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=float(volume),
                timeframe=Timeframe.DAILY,
            ))

            price = close
            current_date += timedelta(days=1)

        return bars


# ---------------------------------------------------------------------------
# Core BatchBacktester
# ---------------------------------------------------------------------------

class BatchBacktester:
    """Simulate nightly batch trading over historical daily bar data.

    Simulates the full nightly batch cycle:
      1. Each evening: run strategies on daily bars for all symbols.
      2. Apply gap filter to next-day open price.
      3. Rank surviving signals and select top N.
      4. Execute MOO or confirmation entries at next-day open.
      5. Each subsequent bar: evaluate exit rules (SL/TP/trailing/time).
      6. Track MFE/MAE and produce full trade records.
      7. Calculate portfolio metrics after the simulation completes.

    Usage::

        bars_by_symbol = {"AAPL": [...], "MSFT": [...], ...}
        backtester = BatchBacktester(initial_capital=100_000)
        result = backtester.run(bars_by_symbol)
        print(result.metrics)

    Args:
        initial_capital: Starting portfolio cash balance.
        top_n: Maximum candidates to select per evening scan.
        max_daily_entries: Max new positions to open per trading day.
        max_hold_days_override: If set, overrides strategy-specific max hold days.
        gap_threshold: Max allowed overnight gap (fraction) for entry.
        entry_day_skip: If True, no SL/TP checks on the entry day (Day 1 skip).
        apply_gap_filter: If True, apply the gap filter to next-day open.
        apply_slippage: If True, add slippage to fill prices.
        apply_commission: If True, deduct commissions from PnL.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        top_n: int = _TOP_N_CANDIDATES,
        max_daily_entries: int = _MAX_DAILY_ENTRIES,
        max_hold_days_override: int | None = None,
        gap_threshold: float = _DEFAULT_GAP_THRESHOLD,
        entry_day_skip: bool = True,
        apply_gap_filter: bool = True,
        apply_slippage: bool = True,
        apply_commission: bool = True,
        use_per_strategy_gdr: bool = _PER_STRATEGY_GDR,
    ) -> None:
        self._initial_capital = initial_capital
        self._top_n = top_n
        self._max_daily_entries = max_daily_entries
        self._max_hold_days_override = max_hold_days_override
        self._gap_threshold = gap_threshold
        self._entry_day_skip = entry_day_skip
        self._apply_gap_filter = apply_gap_filter
        self._apply_slippage = apply_slippage
        self._apply_commission = apply_commission
        self._use_per_strategy_gdr = use_per_strategy_gdr

        # Build indicator engine with the union of all strategy requirements
        self._indicator_specs = self._collect_indicator_specs()
        self._ranker = SignalRanker(top_n=top_n)

        # State reset on each run() call
        self._cash: float = initial_capital
        self._positions: dict[str, _SimPosition] = {}
        self._exit_engine = ExitRuleEngine()
        self._trade_records: list[BatchTradeRecord] = []
        self._next_trade_id: int = 1
        self._daily_snapshots: list[DailySnapshot] = []
        self._equity_curve: list[tuple[date, float]] = []
        self._closed_today: set[str] = set()
        # Legacy portfolio-level GDR state
        self._equity: float = initial_capital
        self._peak_equity: float = initial_capital
        self._equity_history: deque[float] = deque(maxlen=_GDR_ROLLING_WINDOW)
        self._gdr_tier: int = 0
        self._realized_pnl: float = 0.0  # cumulative realized PnL for DD tracking
        # Per-strategy GDR state
        self._strategy_cumulative_pnl: dict[str, float] = {s: 0.0 for s in _STRATEGY_NAMES}
        self._strategy_peak_pnl: dict[str, float] = {s: 0.0 for s in _STRATEGY_NAMES}
        self._strategy_gdr_tier: dict[str, int] = {s: 0 for s in _STRATEGY_NAMES}
        self._strategy_entries_today: dict[str, int] = {s: 0 for s in _STRATEGY_NAMES}
        # Portfolio safety net state
        self._portfolio_safety_net_active: bool = False
        # Regime guard: symbols pending forced close on next day
        self._regime_guard_pending: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        strategy_filter: list[str] | None = None,
    ) -> BatchBacktestResult:
        """Execute the full historical simulation.

        Args:
            bars_by_symbol: Dict of symbol -> list[Bar] (oldest first, daily bars).
            strategy_filter: If provided, only run the named strategies
                             (subset of the 5 available strategies).

        Returns:
            BatchBacktestResult with trades, equity curve, and metrics.
        """
        # Reset all state for a fresh run
        self._reset()

        # Determine the common date range across all symbols
        all_dates = self._extract_sorted_dates(bars_by_symbol)
        if len(all_dates) < _MIN_BARS_WARMUP + 2:
            logger.warning(
                "Insufficient data: %d dates found, need at least %d",
                len(all_dates),
                _MIN_BARS_WARMUP + 2,
            )
            return self._build_result({})

        # Build per-symbol rolling history and indicator engines
        symbol_histories: dict[str, deque[Bar]] = {
            sym: deque(maxlen=500) for sym in bars_by_symbol
        }
        symbol_ind_engines: dict[str, IndicatorEngine] = {
            sym: self._build_indicator_engine() for sym in bars_by_symbol
        }

        # Pre-index bars by date per symbol for O(1) lookups
        bars_by_date: dict[str, dict[date, Bar]] = self._index_by_date(bars_by_symbol)

        # Build fresh strategy instances (respecting filter)
        strategies = self._build_strategies(strategy_filter)

        logger.info(
            "BatchBacktester: running %d symbols over %d dates, capital=%.0f",
            len(bars_by_symbol),
            len(all_dates),
            self._initial_capital,
        )

        # Pending signals from previous day's evening scan
        pending_signals: list[tuple[str, ScanResult, float]] = []  # (symbol, result, prev_close)

        for day_idx, trading_date in enumerate(all_dates):
            # Clear re-entry block at start of each new day
            self._closed_today.clear()
            self._exit_engine.on_new_trading_day(trading_date)

            # --- Step 1: Update rolling histories for all symbols ---
            day_bars: dict[str, Bar] = {}
            for sym in bars_by_symbol:
                bar = bars_by_date[sym].get(trading_date)
                if bar is None:
                    continue
                day_bars[sym] = bar
                symbol_histories[sym].append(bar)

            # --- Step 2: Execute pending entries (from last night's scan) ---
            entries_today = 0
            if pending_signals and day_bars:
                entries_today = self._execute_pending_entries(
                    pending_signals=pending_signals,
                    day_bars=day_bars,
                    trading_date=trading_date,
                )
            pending_signals = []  # consumed

            # --- Step 3: Evaluate exit rules for held positions ---
            exits_today = 0
            daily_pnl = 0.0
            if day_bars:
                exits_today, daily_pnl = self._evaluate_exits(
                    day_bars=day_bars,
                    symbol_histories=symbol_histories,
                    symbol_ind_engines=symbol_ind_engines,
                    trading_date=trading_date,
                )

            # --- Step 4: Compute equity and record snapshot ---
            equity = self._compute_equity(day_bars)
            self._equity = equity

            # Update peak equity using realized equity (MTM-free)
            realized_eq = self._compute_realized_equity()
            self._peak_equity = max(self._peak_equity, realized_eq)
            self._update_gdr()

            self._equity_curve.append((trading_date, equity))
            self._daily_snapshots.append(DailySnapshot(
                date=trading_date,
                equity=equity,
                cash=self._cash,
                open_positions=len(self._positions),
                new_entries=entries_today,
                exits=exits_today,
                daily_pnl=daily_pnl,
            ))

            # --- Step 5: Evening scan (generate signals for tomorrow) ---
            if day_idx < len(all_dates) - 1:
                scan_results = self._run_evening_scan(
                    day_bars=day_bars,
                    symbol_histories=symbol_histories,
                    symbol_ind_engines=symbol_ind_engines,
                    strategies=strategies,
                )
                pending_signals = self._rank_and_filter(scan_results, day_bars)

        # Close all remaining open positions at last known price
        self._force_close_all(bars_by_date, all_dates)

        # Re-record equity after force-closing all positions so that
        # final_equity reflects realized PnL (including slippage/commission)
        # rather than the pre-close mark-to-market value.
        last_date = all_dates[-1]
        final_equity = self._compute_equity({})  # no open positions left
        self._equity_curve.append((last_date, final_equity))

        config = {
            "initial_capital": self._initial_capital,
            "top_n": self._top_n,
            "max_daily_entries": self._max_daily_entries,
            "max_hold_days_override": self._max_hold_days_override,
            "gap_threshold": self._gap_threshold,
            "entry_day_skip": self._entry_day_skip,
            "apply_gap_filter": self._apply_gap_filter,
            "risk_per_trade_pct": _RISK_PER_TRADE_PCT,
            "max_total_positions": _MAX_TOTAL_POSITIONS,
            "max_long_positions": _MAX_LONG_POSITIONS,
            "gdr_tier1_dd": _GDR_TIER1_DD,
            "gdr_tier2_dd": _GDR_TIER2_DD,
            "per_strategy_gdr": self._use_per_strategy_gdr,
            "strategy_base_risk": dict(_STRATEGY_BASE_RISK),
            "strategy_gdr_thresholds": dict(_STRATEGY_GDR_THRESHOLDS),
            "portfolio_safety_net_dd": _PORTFOLIO_SAFETY_NET_DD,
        }

        logger.info(
            "BatchBacktester: simulation complete. %d trades recorded.",
            len(self._trade_records),
        )

        return self._build_result(config)

    # ------------------------------------------------------------------
    # Simulation steps
    # ------------------------------------------------------------------

    def _run_evening_scan(
        self,
        day_bars: dict[str, Bar],
        symbol_histories: dict[str, deque[Bar]],
        symbol_ind_engines: dict[str, IndicatorEngine],
        strategies: list,
    ) -> list[ScanResult]:
        """Run all strategies on the evening's closing bars.

        Returns a list of ScanResult objects (entry signals only).
        """
        scan_results: list[ScanResult] = []

        for sym, bar in day_bars.items():
            history = symbol_histories[sym]
            if len(history) < _MIN_BARS_WARMUP:
                continue

            ind_engine = symbol_ind_engines[sym]
            indicators = ind_engine.compute(history)

            # Check warmup is complete for core indicators
            if not self._has_required_indicators(indicators):
                continue

            # Skip symbols that already have an open position
            if sym in self._positions:
                continue

            ctx = MarketContext(
                symbol=sym,
                bar=bar,
                indicators=indicators,
                history=history,
            )

            for strategy in strategies:
                try:
                    signal = strategy.on_context(ctx)
                except Exception as exc:
                    logger.debug("Strategy %s failed on %s: %s", strategy.name, sym, exc)
                    continue

                if signal is None or signal.direction == "close":
                    continue

                scan_results.append(ScanResult(
                    symbol=sym,
                    strategy=strategy.name,
                    direction=signal.direction,
                    signal_strength=signal.strength,
                    indicators=self._flatten_indicators(indicators),
                    prev_close=bar.close,
                    scanned_at=datetime.now(tz=timezone.utc),
                    metadata=dict(signal.metadata),
                ))

        return scan_results

    def _rank_and_filter(
        self,
        scan_results: list[ScanResult],
        day_bars: dict[str, Bar],
    ) -> list[tuple[str, ScanResult, float]]:
        """Rank signals and return (symbol, ScanResult, prev_close) tuples.

        The gap filter is applied in _execute_pending_entries when we have
        the next day's open price available.

        Current positions are passed to the ranker so that the strategy
        diversity bonus can be applied (strategies with fewer open positions
        receive a higher composite score).
        """
        if not scan_results:
            return []

        # Build a lightweight proxy list for position strategy diversity bonus.
        # Each proxy exposes a .strategy attribute for the ranker.
        class _StrategyProxy:
            __slots__ = ("strategy",)
            def __init__(self, s: str) -> None:
                self.strategy = s

        current_pos_list = [
            _StrategyProxy(sim_pos.held.strategy)
            for sim_pos in self._positions.values()
        ]
        candidates: list[Candidate] = self._ranker.rank(
            scan_results,
            current_positions=current_pos_list,
        )
        result = []
        for cand in candidates:
            result.append((cand.symbol, cand.scan_result, cand.prev_close))
        return result

    def _execute_pending_entries(
        self,
        pending_signals: list[tuple[str, ScanResult, float]],
        day_bars: dict[str, Bar],
        trading_date: date,
    ) -> int:
        """Open positions for last night's ranked signals at today's open.

        Applies the gap filter before entering; enforces daily entry limit
        and position caps.  GDR tier reduces both the daily entry limit and
        per-trade risk when drawdown thresholds are exceeded.

        Returns:
            Number of new positions opened.
        """
        # Reset per-strategy daily entry counters
        for s in self._strategy_entries_today:
            self._strategy_entries_today[s] = 0

        # Determine effective daily entry limit and risk multiplier source
        if self._use_per_strategy_gdr:
            if self._portfolio_safety_net_active:
                # Safety net overrides: 1 entry total at 0.5% risk
                effective_daily_entries = min(self._max_daily_entries, _PORTFOLIO_SAFETY_NET_ENTRIES)
                logger.info(
                    "Portfolio safety net active: entry limit=%d, risk=%.1f%%",
                    effective_daily_entries, _PORTFOLIO_SAFETY_NET_RISK * 100,
                )
            else:
                effective_daily_entries = self._max_daily_entries
        else:
            # Legacy portfolio-level GDR
            gdr_entry_limit = _GDR_MAX_ENTRIES[self._gdr_tier]
            effective_daily_entries = min(self._max_daily_entries, gdr_entry_limit)
            if self._gdr_tier > 0:
                logger.info(
                    "GDR Tier %d active: entry limit=%d, risk_mult=%.2f",
                    self._gdr_tier, effective_daily_entries,
                    _GDR_LEGACY_RISK_MULT[self._gdr_tier],
                )

        # Count how many strategies have pending signals (for soft cap logic)
        strategies_with_signals: set[str] = {sr.strategy for _, sr, _ in pending_signals}
        multi_strategy_mode = len(strategies_with_signals) >= 2

        entries = 0
        total_positions = len(self._positions)

        for sym, scan_result, prev_close in pending_signals:
            strategy_name = scan_result.strategy

            # Enforce overall portfolio-level daily entry limit
            if entries >= effective_daily_entries:
                break
            if total_positions >= _MAX_TOTAL_POSITIONS:
                break

            # Per-strategy GDR entry limit check
            if self._use_per_strategy_gdr and not self._portfolio_safety_net_active:
                strat_tier = self._strategy_gdr_tier.get(strategy_name, 0)
                strat_entry_limit = _GDR_STRATEGY_ENTRIES[strat_tier]
                strat_entries_so_far = self._strategy_entries_today.get(strategy_name, 0)
                if strat_entries_so_far >= strat_entry_limit:
                    logger.debug(
                        "Per-strategy GDR: %s at tier %d, entry limit %d reached, skipping %s",
                        strategy_name, strat_tier, strat_entry_limit, sym,
                    )
                    continue

            bar = day_bars.get(sym)
            if bar is None:
                continue

            # Re-entry block check
            if sym in self._closed_today:
                logger.debug("Entry skipped for %s: re-entry block (same day)", sym)
                continue

            # Already holding this symbol
            if sym in self._positions:
                continue

            # Direction-based position cap
            direction = scan_result.direction
            longs = sum(1 for p in self._positions.values() if p.held.direction == "long")
            shorts = sum(1 for p in self._positions.values() if p.held.direction == "short")
            if direction == "long" and longs >= _MAX_LONG_POSITIONS:
                continue
            if direction == "short" and shorts >= _MAX_SHORT_POSITIONS:
                continue

            # Soft per-strategy cap: when 2+ strategies are competing for slots,
            # limit any single strategy to _SOFT_STRATEGY_CAP open positions.
            if multi_strategy_mode:
                strategy_count = sum(
                    1 for p in self._positions.values()
                    if p.held.strategy == strategy_name
                )
                if strategy_count >= _SOFT_STRATEGY_CAP:
                    logger.debug(
                        "Soft strategy cap: %s already has %d/%d positions, skipping %s",
                        strategy_name, strategy_count, _SOFT_STRATEGY_CAP, sym,
                    )
                    continue

            # Apply gap filter: compare today's open to yesterday's close
            gap_pct = (bar.open - prev_close) / prev_close if prev_close > 0 else 0.0

            if self._apply_gap_filter and abs(gap_pct) > self._gap_threshold:
                logger.debug(
                    "Gap filter rejected %s: gap=%.2f%% (threshold=%.1f%%)",
                    sym, gap_pct * 100, self._gap_threshold * 100,
                )
                continue

            # Get ATR from the scan result indicators for position sizing
            atr_raw = scan_result.indicators.get("ATR_14")
            atr = float(atr_raw) if isinstance(atr_raw, (int, float)) and atr_raw > 0 else bar.close * 0.02

            # Calculate position size using risk-based sizing
            equity = self._compute_equity(day_bars)
            fill_price = self._apply_slippage_to_fill(
                price=bar.open,
                direction=direction,
                is_entry=True,
            )

            sl_mult = _SL_ATR_MULT.get(strategy_name, {}).get(direction, 2.0)
            stop_distance = sl_mult * atr

            # Determine GDR risk multiplier based on mode
            if self._use_per_strategy_gdr:
                if self._portfolio_safety_net_active:
                    gdr_mult = 1.0  # safety net risk is handled in _calculate_qty
                else:
                    strat_tier = self._strategy_gdr_tier.get(strategy_name, 0)
                    gdr_mult = _GDR_RISK_MULT[strat_tier]
            else:
                gdr_mult = _GDR_LEGACY_RISK_MULT[self._gdr_tier]

            qty = self._calculate_qty(
                equity=equity,
                fill_price=fill_price,
                stop_distance=stop_distance,
                gdr_risk_mult=gdr_mult,
                strategy=strategy_name,
            )

            if qty <= 0:
                continue

            # Cash check
            cost = fill_price * qty
            if direction == "long" and cost > self._cash:
                logger.debug(
                    "Insufficient cash for %s: need %.2f, have %.2f",
                    sym, cost, self._cash,
                )
                continue

            # Open the position
            if direction == "long":
                self._cash -= cost
            else:
                # Short: receive proceeds (simplified - no margin requirement)
                self._cash += cost

            held = HeldPosition(
                symbol=sym,
                strategy=strategy_name,
                direction=direction,  # type: ignore[arg-type]
                entry_price=fill_price,
                entry_atr=atr,
                entry_date_et=trading_date,
                bars_held=0,
                qty=qty,
                highest_price=fill_price,
                lowest_price=fill_price,
            )

            # Store entry ADX for regime guard downstream
            adx_entry = scan_result.indicators.get("ADX_14")
            if isinstance(adx_entry, (int, float)):
                held.entry_adx = float(adx_entry)

            sim_pos = _SimPosition(
                held=held,
                qty=qty,
                entry_date=trading_date,
                signal_strength=scan_result.signal_strength,
                gap_pct=gap_pct,
            )

            self._positions[sym] = sim_pos
            entries += 1
            total_positions += 1
            # Track per-strategy entries for this day
            self._strategy_entries_today[strategy_name] = (
                self._strategy_entries_today.get(strategy_name, 0) + 1
            )

            logger.debug(
                "Entry: %s %s %.0f @ %.2f (strategy=%s, atr=%.2f, gap=%.2f%%)",
                direction, sym, qty, fill_price,
                strategy_name, atr, gap_pct * 100,
            )

        return entries

    def _evaluate_exits(
        self,
        day_bars: dict[str, Bar],
        symbol_histories: dict[str, deque[Bar]],
        symbol_ind_engines: dict[str, IndicatorEngine],
        trading_date: date,
    ) -> tuple[int, float]:
        """Evaluate exit conditions for all held positions.

        Uses daily high/low to approximate intraday SL/TP hits.
        If both SL and TP would have been hit in the same day, the
        disambiguation rule is: if open is closer to SL -> stopped out;
        if open is closer to TP -> took profit.

        Returns:
            (exits_count, daily_pnl)
        """
        exits = 0
        daily_pnl = 0.0
        to_close: list[tuple[str, str, float]] = []  # (symbol, reason, exit_price)

        # Execute pending regime guard forced closes (from yesterday's detection)
        regime_guard_closes: list[str] = []
        for sym in list(self._regime_guard_pending):
            if sym in self._positions:
                bar = day_bars.get(sym)
                if bar is not None:
                    exit_price = self._apply_slippage_to_fill(
                        bar.open, self._positions[sym].held.direction, is_entry=False,
                    )
                    to_close.append((sym, "regime_guard", exit_price))
                    regime_guard_closes.append(sym)
        for sym in regime_guard_closes:
            self._regime_guard_pending.discard(sym)

        for sym, sim_pos in self._positions.items():
            bar = day_bars.get(sym)
            if bar is None:
                continue

            held = sim_pos.held

            # Increment bars held counter
            held.bars_held += 1

            # Update MFE/MAE tracking
            sim_pos.update_extremes(bar.high, bar.low)
            held.update_price_extremes(bar.high, bar.low)

            # Get indicators for this bar
            history = symbol_histories.get(sym)
            if history:
                indicators = symbol_ind_engines[sym].compute(history)
            else:
                indicators = {}

            # Apply entry day skip: on Day 1, only check emergency exits
            is_entry_day = (held.entry_date_et == trading_date)
            if is_entry_day and self._entry_day_skip:
                # Only emergency -10% single-bar check on entry day
                loss_pct = self._loss_pct(held, bar.close)
                if loss_pct >= _EMERGENCY_LOSS_IMMEDIATE_PCT:
                    exit_price = self._apply_slippage_to_fill(bar.close, held.direction, is_entry=False)
                    to_close.append((sym, "emergency_immediate", exit_price))
                continue

            # Day 2+: check SL/TP/trailing using daily high/low
            exit_price, exit_reason = self._check_sl_tp_intraday(
                held=held,
                bar=bar,
                indicators=indicators,
                bar_history=history,
            )

            if exit_price is not None and exit_reason is not None:
                to_close.append((sym, exit_reason, exit_price))
            elif _MAX_LOSS_PER_TRADE_PCT < 1.0:
                # Equity-based hard cap: if unrealized loss exceeds threshold
                # of equity, force exit. Only triggers when SL/TP did not fire.
                unrealized_loss = self._unrealized_loss_dollars(sim_pos, bar.close)
                equity = self._equity if self._equity > 0 else self._initial_capital
                if unrealized_loss > equity * _MAX_LOSS_PER_TRADE_PCT:
                    cap_exit_price = self._apply_slippage_to_fill(
                        bar.close, held.direction, is_entry=False,
                    )
                    to_close.append((sym, "max_loss_cap", cap_exit_price))

            # Regime guard detection for rsi_mean_reversion (detect today, close tomorrow)
            if held.strategy == "rsi_mean_reversion" and exit_price is None:
                current_adx = indicators.get("ADX_14")
                if (
                    isinstance(current_adx, (int, float))
                    and held.entry_adx > 0
                    and current_adx > 23.0
                    and (current_adx - held.entry_adx) >= 3.0
                ):
                    self._regime_guard_pending.add(sym)
                    logger.info(
                        "Regime guard flagged %s for next-day close: ADX=%.1f "
                        "(entry=%.1f, delta=+%.1f)",
                        sym, current_adx, held.entry_adx,
                        current_adx - held.entry_adx,
                    )

        # Execute the closes
        for sym, reason, exit_price in to_close:
            if sym not in self._positions:
                continue  # already closed (e.g. regime guard + normal exit same day)
            sim_pos = self._positions.pop(sym)
            # Clean up regime guard pending if this symbol is being closed normally
            self._regime_guard_pending.discard(sym)
            pnl = self._compute_pnl(sim_pos, exit_price)
            daily_pnl += pnl

            # Add commission cost
            if self._apply_commission:
                commission = _COMMISSION_PER_SHARE * sim_pos.qty * 2  # entry + exit
                pnl -= commission

            # Track realized PnL for DD calculation (MTM-free)
            self._realized_pnl += pnl

            # Return cash
            if sim_pos.held.direction == "long":
                self._cash += exit_price * sim_pos.qty
            else:
                self._cash -= exit_price * sim_pos.qty  # cover short

            self._record_trade(sim_pos, exit_price, reason, trading_date)
            self._closed_today.add(sym)
            self._exit_engine.record_close(sym)
            exits += 1

            # Update per-strategy GDR with the realized PnL (including commission)
            if self._use_per_strategy_gdr:
                self._update_per_strategy_gdr(sim_pos.held.strategy, pnl)

            logger.debug(
                "Exit: %s %s %.0f @ %.2f (reason=%s, pnl=%.2f, bars=%d)",
                sim_pos.held.direction, sym, sim_pos.qty, exit_price,
                reason, pnl, sim_pos.held.bars_held,
            )

        return exits, daily_pnl

    def _check_sl_tp_intraday(
        self,
        held: HeldPosition,
        bar: Bar,
        indicators: dict,
        bar_history: deque | None = None,
    ) -> tuple[float | None, str | None]:
        """Check if SL or TP would have been hit using the daily high/low.

        Returns:
            (exit_price, reason) or (None, None) if no exit triggered.
        """
        atr = self._get_atr(indicators, held.entry_atr)
        strategy = held.strategy
        direction = held.direction

        # --- Stop Loss check (with 2-stage SL upgrade) ---
        sl_mult = _SL_ATR_MULT.get(strategy, {}).get(direction, 2.0)
        sl_distance = sl_mult * atr
        if direction == "long":
            sl_price = held.entry_price - sl_distance
            # 2-stage SL upgrade
            if held.highest_price >= held.entry_price + _STAGE2_PROFIT_ACTIVATION_ATR * atr:
                # Stage 2: lock in profit
                sl_price = max(sl_price, held.entry_price + _STAGE2_PROFIT_LOCK_ATR * atr)
            elif held.highest_price >= held.entry_price + _STAGE1_BE_ACTIVATION_ATR * atr:
                # Stage 1: breakeven
                sl_price = max(sl_price, held.entry_price)
            sl_hit = bar.low <= sl_price
        else:
            sl_price = held.entry_price + sl_distance
            # 2-stage SL upgrade
            if held.lowest_price <= held.entry_price - _STAGE2_PROFIT_ACTIVATION_ATR * atr:
                # Stage 2: lock in profit
                sl_price = min(sl_price, held.entry_price - _STAGE2_PROFIT_LOCK_ATR * atr)
            elif held.lowest_price <= held.entry_price - _STAGE1_BE_ACTIVATION_ATR * atr:
                # Stage 1: breakeven
                sl_price = min(sl_price, held.entry_price)
            sl_hit = bar.high >= sl_price

        # --- Take Profit check ---
        tp_price: float | None = None
        tp_hit = False
        tp_atr_mult = _TP_ATR_MULT.get(strategy)
        if tp_atr_mult is not None:
            if direction == "long":
                tp_price = held.entry_price + tp_atr_mult * atr
                tp_hit = bar.high >= tp_price
            else:
                tp_price = held.entry_price - tp_atr_mult * atr
                tp_hit = bar.low <= tp_price
        else:
            # Indicator-based TP (rsi/bb)
            rsi = indicators.get("RSI_14")
            bb = indicators.get("BBANDS_20")
            pct_b = bb.get("pct_b", 0.5) if isinstance(bb, dict) else None

            if strategy == "rsi_mean_reversion":
                rsi_target = 50.0 if direction == "long" else 50.0
                if direction == "long":
                    tp_hit = (rsi is not None and rsi > rsi_target) or (pct_b is not None and pct_b > 0.50)
                else:
                    tp_hit = (rsi is not None and rsi < rsi_target) or (pct_b is not None and pct_b < 0.50)
            elif strategy == "consecutive_down":
                # TP: close > EMA(5)
                ema_5 = indicators.get("EMA_5")
                if ema_5 is not None and bar.close > ema_5:
                    tp_hit = True

            if tp_hit:
                tp_price = bar.close  # indicator-based TP fills at close

            # Auxiliary ATR TP for rsi_mean_reversion: cap at 2.0 ATR
            if not tp_hit and strategy == "rsi_mean_reversion":
                atr_tp_mult = 2.0
                if direction == "long":
                    atr_tp_price = held.entry_price + atr_tp_mult * atr
                    if bar.high >= atr_tp_price:
                        tp_hit = True
                        tp_price = atr_tp_price
                else:
                    atr_tp_price = held.entry_price - atr_tp_mult * atr
                    if bar.low <= atr_tp_price:
                        tp_hit = True
                        tp_price = atr_tp_price

        # --- Trailing Stop check (for ema_pullback) ---
        # Activation: only after price moved N ATR in our favour (per-strategy).
        # Floor: trailing stop never goes below entry price (no trailing losses).
        trailing_hit = False
        trailing_price: float | None = None
        if strategy in _TRAILING_STRATEGIES and held.bars_held >= 2:
            activation_atr = _TRAILING_ACTIVATION_ATR.get(strategy, 1.5)
            if direction == "long":
                if held.highest_price >= held.entry_price + activation_atr * atr:
                    trail_stop = max(
                        held.entry_price,
                        held.highest_price - _TRAILING_ATR_MULT * atr,
                    )
                    if bar.low <= trail_stop:
                        trailing_hit = True
                        trailing_price = trail_stop
            else:
                if held.lowest_price <= held.entry_price - activation_atr * atr:
                    trail_stop = min(
                        held.entry_price,
                        held.lowest_price + _TRAILING_ATR_MULT * atr,
                    )
                    if bar.high >= trail_stop:
                        trailing_hit = True
                        trailing_price = trail_stop

        # --- Time-based exit ---
        max_hold = self._max_hold_days_override or _MAX_HOLD_DAYS.get(strategy, 5)
        time_hit = held.bars_held >= max_hold

        # --- Determine which exit fires first ---
        # Priority: SL > TP > Trailing > Time
        # TP must be checked before trailing to avoid cutting winners
        # that have already reached take-profit territory.
        if sl_hit and tp_hit and tp_price is not None:
            # Both SL and TP hit: use open proximity to disambiguate
            if direction == "long":
                open_to_sl = abs(bar.open - sl_price)
                open_to_tp = abs(bar.open - tp_price)
            else:
                open_to_sl = abs(bar.open - sl_price)
                open_to_tp = abs(bar.open - tp_price) if tp_price else float("inf")

            if open_to_sl <= open_to_tp:
                exit_p = self._apply_slippage_to_fill(sl_price, direction, is_entry=False)
                return exit_p, "stop_loss"
            else:
                exit_p = self._apply_slippage_to_fill(tp_price, direction, is_entry=False)
                return exit_p, "take_profit"

        if sl_hit:
            exit_p = self._apply_slippage_to_fill(sl_price, direction, is_entry=False)
            return exit_p, "stop_loss"

        if tp_hit and tp_price is not None:
            exit_p = self._apply_slippage_to_fill(tp_price, direction, is_entry=False)
            return exit_p, "take_profit"

        if trailing_hit and trailing_price is not None:
            exit_p = self._apply_slippage_to_fill(trailing_price, direction, is_entry=False)
            return exit_p, "trailing_stop"

        if time_hit:
            exit_p = self._apply_slippage_to_fill(bar.close, direction, is_entry=False)
            return exit_p, "time_exit"

        return None, None

    def _force_close_all(
        self,
        bars_by_date: dict[str, dict[date, Bar]],
        all_dates: list[date],
    ) -> None:
        """Force-close all remaining positions at the last available close price."""
        last_date = all_dates[-1]
        for sym, sim_pos in list(self._positions.items()):
            last_bar = bars_by_date[sym].get(last_date)
            if last_bar is None:
                # Walk backwards to find a bar
                for d in reversed(all_dates):
                    last_bar = bars_by_date[sym].get(d)
                    if last_bar:
                        break

            exit_price = last_bar.close if last_bar else sim_pos.held.entry_price
            exit_price = self._apply_slippage_to_fill(exit_price, sim_pos.held.direction, is_entry=False)
            self._record_trade(sim_pos, exit_price, "forced_close", last_date)

            if sim_pos.held.direction == "long":
                self._cash += exit_price * sim_pos.qty
            else:
                self._cash -= exit_price * sim_pos.qty

        self._positions.clear()

    # ------------------------------------------------------------------
    # Metrics and result building
    # ------------------------------------------------------------------

    def _build_result(self, config: dict) -> BatchBacktestResult:
        """Aggregate all trade records into BacktestResult."""
        trade_pnls = [t.pnl for t in self._trade_records]
        equity_values = [e for _, e in self._equity_curve]

        metrics = self._calculate_portfolio_metrics(
            trade_pnls=trade_pnls,
            equity_curve=equity_values,
            initial_capital=self._initial_capital,
        )

        per_strategy: dict[str, dict] = {}
        all_strategies = {t.strategy for t in self._trade_records}
        for strat in all_strategies:
            strat_trades = [t for t in self._trade_records if t.strategy == strat]
            strat_pnls = [t.pnl for t in strat_trades]
            per_strategy[strat] = self._calculate_strategy_metrics(strat_trades, strat_pnls)

        return BatchBacktestResult(
            trades=list(self._trade_records),
            daily_snapshots=list(self._daily_snapshots),
            equity_curve=list(self._equity_curve),
            metrics=metrics,
            per_strategy_metrics=per_strategy,
            config=config,
        )

    @staticmethod
    def _calculate_portfolio_metrics(
        trade_pnls: list[float],
        equity_curve: list[float],
        initial_capital: float,
    ) -> dict:
        """Calculate comprehensive portfolio performance metrics."""
        if not trade_pnls:
            return {
                "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                "total_return_pct": 0.0, "total_pnl": 0.0,
                "sharpe_ratio": 0.0, "sortino_ratio": 0.0,
                "max_drawdown_pct": 0.0, "calmar_ratio": 0.0,
                "avg_pnl_per_trade": 0.0, "avg_hold_days": 0.0,
            }

        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p < 0]
        total_wins = sum(wins)
        total_losses = abs(sum(losses))

        # Max drawdown from equity curve
        max_dd = 0.0
        peak = equity_curve[0] if equity_curve else initial_capital
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        # Daily returns from equity curve
        daily_returns: list[float] = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] > 0:
                r = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                daily_returns.append(r)

        # Sharpe ratio (annualised, 252 trading days)
        sharpe = 0.0
        if len(daily_returns) > 1:
            mean_r = sum(daily_returns) / len(daily_returns)
            var_r = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
            std_r = math.sqrt(var_r)
            if std_r > 0:
                sharpe = (mean_r / std_r) * math.sqrt(252)

        # Sortino ratio (downside deviation only)
        sortino = 0.0
        if daily_returns:
            mean_r = sum(daily_returns) / len(daily_returns)
            downside_sq = [r ** 2 for r in daily_returns if r < 0]
            if downside_sq:
                downside_std = math.sqrt(sum(downside_sq) / len(downside_sq))
                if downside_std > 0:
                    sortino = (mean_r / downside_std) * math.sqrt(252)

        # Calmar ratio: annualised return / max drawdown
        final_equity = equity_curve[-1] if equity_curve else initial_capital
        total_return = (final_equity - initial_capital) / initial_capital
        num_years = len(equity_curve) / 252.0 if equity_curve else 1.0
        annualised_return = (1 + total_return) ** (1.0 / max(num_years, 0.1)) - 1.0
        calmar = annualised_return / max_dd if max_dd > 0 else 0.0

        return {
            "total_trades": len(trade_pnls),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": len(wins) / len(trade_pnls) if trade_pnls else 0.0,
            "profit_factor": total_wins / total_losses if total_losses > 0 else float("inf"),
            "total_pnl": sum(trade_pnls),
            "total_return_pct": total_return * 100.0,
            "annualised_return_pct": annualised_return * 100.0,
            "avg_pnl_per_trade": sum(trade_pnls) / len(trade_pnls),
            "avg_win": total_wins / len(wins) if wins else 0.0,
            "avg_loss": -total_losses / len(losses) if losses else 0.0,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown_pct": max_dd * 100.0,
            "calmar_ratio": calmar,
            "final_equity": final_equity,
        }

    @staticmethod
    def _calculate_strategy_metrics(
        trades: list[BatchTradeRecord],
        pnls: list[float],
    ) -> dict:
        """Calculate per-strategy metrics."""
        if not trades:
            return {}

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl < 0]
        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in losses))

        consec_loss = 0
        max_consec_loss = 0
        for t in trades:
            if t.pnl < 0:
                consec_loss += 1
                max_consec_loss = max(max_consec_loss, consec_loss)
            else:
                consec_loss = 0

        exit_reasons: dict[str, int] = {}
        for t in trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

        avg_mfe = sum(t.mfe_pct for t in trades) / len(trades) if trades else 0.0
        avg_mae = sum(t.mae_pct for t in trades) / len(trades) if trades else 0.0
        avg_hold = sum(t.bars_held for t in trades) / len(trades) if trades else 0.0

        return {
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": len(wins) / len(trades),
            "total_pnl": sum(pnls),
            "avg_pnl": sum(pnls) / len(pnls),
            "profit_factor": total_wins / total_losses if total_losses > 0 else float("inf"),
            "avg_hold_days": avg_hold,
            "max_consec_loss": max_consec_loss,
            "avg_mfe_pct": avg_mfe * 100.0,
            "avg_mae_pct": avg_mae * 100.0,
            "exit_reasons": exit_reasons,
        }

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _reset(self) -> None:
        """Reset all mutable state for a fresh simulation run."""
        self._cash = self._initial_capital
        self._positions = {}
        self._exit_engine = ExitRuleEngine()
        self._trade_records = []
        self._next_trade_id = 1
        self._daily_snapshots = []
        self._equity_curve = []
        self._closed_today = set()
        self._equity = self._initial_capital
        self._peak_equity = self._initial_capital
        self._equity_history = deque(maxlen=_GDR_ROLLING_WINDOW)
        self._gdr_tier = 0
        self._realized_pnl: float = 0.0  # cumulative realized PnL for DD tracking
        # Per-strategy GDR state
        self._strategy_cumulative_pnl = {s: 0.0 for s in _STRATEGY_NAMES}
        self._strategy_peak_pnl = {s: 0.0 for s in _STRATEGY_NAMES}
        self._strategy_gdr_tier = {s: 0 for s in _STRATEGY_NAMES}
        self._strategy_entries_today = {s: 0 for s in _STRATEGY_NAMES}
        # Portfolio safety net state
        self._portfolio_safety_net_active = False
        # Regime guard state
        self._regime_guard_pending = set()

    def _update_gdr(self) -> None:
        """Update GDR: dispatches to per-strategy or legacy portfolio-level GDR."""
        if self._use_per_strategy_gdr:
            self._update_portfolio_safety_net()
        else:
            self._update_legacy_gdr()

    def _update_legacy_gdr(self) -> None:
        """Update legacy portfolio-level Graduated Drawdown Response tier.

        Appends the current equity to the rolling window, then computes the
        drawdown from the rolling peak.  Tier thresholds:
          Tier 0: DD <= 15%  (normal)
          Tier 1: DD  > 15%  (reduced risk + entries)
          Tier 2: DD  > 25%  (minimal risk + entries)
        """
        self._equity_history.append(self._equity)
        if not self._equity_history:
            self._gdr_tier = 0
            return
        rolling_peak = max(self._equity_history)
        if rolling_peak <= 0:
            self._gdr_tier = 0
            return
        dd = (rolling_peak - self._equity) / rolling_peak
        prev_tier = self._gdr_tier
        if dd > _GDR_TIER2_DD:
            self._gdr_tier = 2
        elif dd > _GDR_TIER1_DD:
            self._gdr_tier = 1
        else:
            self._gdr_tier = 0
        if self._gdr_tier != prev_tier:
            logger.info(
                "GDR tier changed: %d -> %d (rolling DD=%.1f%%, rolling_peak=%.0f, equity=%.0f)",
                prev_tier, self._gdr_tier, dd * 100, rolling_peak, self._equity,
            )

    def _update_per_strategy_gdr(self, strategy: str, pnl: float) -> None:
        """Update per-strategy GDR after a trade closes.

        Tracks cumulative PnL per strategy, computes strategy-specific drawdown
        relative to initial capital, and assigns per-strategy GDR tiers based on
        strategy-specific thresholds.

        Args:
            strategy: Name of the strategy that just closed a trade.
            pnl: Dollar PnL of the closed trade.
        """
        if strategy not in self._strategy_cumulative_pnl:
            # Unknown strategy -- initialize on the fly
            self._strategy_cumulative_pnl[strategy] = 0.0
            self._strategy_peak_pnl[strategy] = 0.0
            self._strategy_gdr_tier[strategy] = 0

        self._strategy_cumulative_pnl[strategy] += pnl

        # Update rolling peak PnL for this strategy
        current_pnl = self._strategy_cumulative_pnl[strategy]
        if current_pnl > self._strategy_peak_pnl[strategy]:
            self._strategy_peak_pnl[strategy] = current_pnl

        # Compute strategy drawdown as fraction of initial capital
        peak_pnl = self._strategy_peak_pnl[strategy]
        dd_dollars = peak_pnl - current_pnl
        dd_pct = dd_dollars / self._initial_capital if self._initial_capital > 0 else 0.0
        dd_pct = max(0.0, dd_pct)

        # Look up strategy-specific thresholds
        thresholds = _STRATEGY_GDR_THRESHOLDS.get(strategy, (0.04, 0.08))
        tier1_dd, tier2_dd = thresholds

        prev_tier = self._strategy_gdr_tier.get(strategy, 0)
        if dd_pct > tier2_dd:
            new_tier = 2
        elif dd_pct > tier1_dd:
            new_tier = 1
        else:
            new_tier = 0

        self._strategy_gdr_tier[strategy] = new_tier
        if new_tier != prev_tier:
            logger.info(
                "Per-strategy GDR [%s]: tier %d -> %d (DD=%.2f%%, peak_pnl=%.0f, cum_pnl=%.0f)",
                strategy, prev_tier, new_tier, dd_pct * 100, peak_pnl, current_pnl,
            )

    def _update_portfolio_safety_net(self) -> None:
        """Check portfolio-level drawdown for safety net activation.

        The portfolio safety net overrides per-strategy GDR when the total
        portfolio drawdown exceeds _PORTFOLIO_SAFETY_NET_DD (20%). It deactivates
        when DD recovers below _PORTFOLIO_SAFETY_NET_RECOVERY (15%).
        """
        realized_eq = self._compute_realized_equity()
        self._equity_history.append(realized_eq)
        if not self._equity_history:
            return

        rolling_peak = max(self._equity_history)
        if rolling_peak <= 0:
            return

        dd = (rolling_peak - realized_eq) / rolling_peak

        if not self._portfolio_safety_net_active:
            if dd > _PORTFOLIO_SAFETY_NET_DD:
                self._portfolio_safety_net_active = True
                logger.warning(
                    "Portfolio safety net ACTIVATED: DD=%.1f%% > %.0f%% threshold "
                    "(realized_eq=%.0f, rolling_peak=%.0f)",
                    dd * 100, _PORTFOLIO_SAFETY_NET_DD * 100,
                    realized_eq, rolling_peak,
                )
        else:
            if dd < _PORTFOLIO_SAFETY_NET_RECOVERY:
                self._portfolio_safety_net_active = False
                logger.info(
                    "Portfolio safety net DEACTIVATED: DD=%.1f%% < %.0f%% recovery "
                    "(realized_eq=%.0f, rolling_peak=%.0f)",
                    dd * 100, _PORTFOLIO_SAFETY_NET_RECOVERY * 100,
                    realized_eq, rolling_peak,
                )

    def _calculate_qty(
        self,
        equity: float,
        fill_price: float,
        stop_distance: float,
        gdr_risk_mult: float = 1.0,
        strategy: str | None = None,
    ) -> int:
        """Calculate position size using ATR-based risk budgeting.

        Risk formula: qty = risk_per_trade_$ / stop_distance_per_share.
        Capped at max_position_pct of equity.  GDR tier reduces effective
        risk percentage via gdr_risk_mult (e.g. 0.5 -> half the normal risk).

        When per-strategy GDR is active and the portfolio safety net is engaged,
        the safety net risk override takes precedence over both the per-strategy
        base risk and the GDR multiplier.

        Args:
            equity: Current portfolio equity.
            fill_price: Entry fill price.
            stop_distance: Dollar distance from entry to stop-loss.
            gdr_risk_mult: GDR-adjusted risk multiplier.
            strategy: Strategy name (for per-strategy base risk lookup).

        Returns:
            Integer number of shares (0 if price or stop_distance is zero).
        """
        if fill_price <= 0 or stop_distance <= 0:
            return 0

        if self._use_per_strategy_gdr and self._portfolio_safety_net_active:
            # Portfolio safety net overrides everything
            effective_risk_pct = _PORTFOLIO_SAFETY_NET_RISK
        elif self._use_per_strategy_gdr and strategy is not None:
            # Per-strategy base risk with per-strategy GDR multiplier
            base_risk = _STRATEGY_BASE_RISK.get(strategy, _DEFAULT_BASE_RISK)
            effective_risk_pct = base_risk * gdr_risk_mult
        else:
            # Legacy portfolio-level GDR
            base_risk = _STRATEGY_BASE_RISK.get(strategy, _RISK_PER_TRADE_PCT) if strategy else _RISK_PER_TRADE_PCT
            effective_risk_pct = base_risk * gdr_risk_mult

        risk_per_trade = equity * effective_risk_pct
        qty_by_risk = int(risk_per_trade / stop_distance)

        max_by_position = int((equity * _MAX_POSITION_PCT) / fill_price)
        qty = min(qty_by_risk, max_by_position)

        return max(0, qty)

    def _apply_slippage_to_fill(
        self,
        price: float,
        direction: str,
        is_entry: bool,
    ) -> float:
        """Apply a simple fixed-bps slippage model to a fill price.

        For long entries and short exits: price goes up (adverse).
        For long exits and short entries: price goes down (adverse).
        """
        if not self._apply_slippage:
            return price
        adverse_direction = 1 if (is_entry == (direction == "long")) else -1
        return price * (1.0 + adverse_direction * _SLIPPAGE_BPS)

    def _compute_equity(self, day_bars: dict[str, Bar]) -> float:
        """Mark-to-market equity using latest close prices."""
        market_value = 0.0
        for sym, sim_pos in self._positions.items():
            bar = day_bars.get(sym)
            price = bar.close if bar else sim_pos.held.entry_price
            if sim_pos.held.direction == "long":
                market_value += price * sim_pos.qty
            else:
                # Short position value: cash received - current cost to cover
                short_value = (sim_pos.held.entry_price - price) * sim_pos.qty
                market_value += short_value
        return self._cash + market_value

    def _compute_realized_equity(self) -> float:
        """Realized equity (cash-based) excluding unrealized MTM.

        Uses initial_capital + cumulative realized PnL to avoid MTM spikes
        contaminating the peak equity tracker for drawdown calculations.
        """
        return self._initial_capital + self._realized_pnl

    def _compute_pnl(self, sim_pos: _SimPosition, exit_price: float) -> float:
        """Calculate dollar PnL for a closed position."""
        ep = sim_pos.held.entry_price
        qty = sim_pos.qty
        if sim_pos.held.direction == "long":
            return (exit_price - ep) * qty
        else:
            return (ep - exit_price) * qty

    def _record_trade(
        self,
        sim_pos: _SimPosition,
        exit_price: float,
        reason: str,
        exit_date: date,
    ) -> None:
        """Append a completed trade to the records list."""
        ep = sim_pos.held.entry_price
        pnl = self._compute_pnl(sim_pos, exit_price)
        if self._apply_commission:
            pnl -= _COMMISSION_PER_SHARE * sim_pos.qty * 2

        pnl_pct = (exit_price - ep) / ep if ep > 0 else 0.0
        if sim_pos.held.direction == "short":
            pnl_pct = -pnl_pct

        self._trade_records.append(BatchTradeRecord(
            trade_id=self._next_trade_id,
            symbol=sim_pos.held.symbol,
            strategy=sim_pos.held.strategy,
            direction=sim_pos.held.direction,
            entry_date=sim_pos.entry_date,
            exit_date=exit_date,
            entry_price=ep,
            exit_price=exit_price,
            qty=sim_pos.qty,
            pnl=pnl,
            pnl_pct=pnl_pct,
            bars_held=sim_pos.held.bars_held,
            exit_reason=reason,
            mfe_pct=sim_pos.mfe_pct,
            mae_pct=sim_pos.mae_pct,
            entry_atr=sim_pos.held.entry_atr,
            signal_strength=sim_pos.signal_strength,
            gap_pct=sim_pos.gap_pct,
            entry_day_skip_applied=self._entry_day_skip,
        ))
        self._next_trade_id += 1

    @staticmethod
    def _collect_indicator_specs() -> list[IndicatorSpec]:
        """Build the union of required indicator specs across all strategies."""
        seen: dict[str, IndicatorSpec] = {}
        for cls in _STRATEGY_CLASSES:
            instance = cls()
            for spec in instance.required_indicators:
                if spec.key not in seen:
                    seen[spec.key] = spec
        return list(seen.values())

    @staticmethod
    def _build_indicator_engine() -> IndicatorEngine:
        """Build and register an IndicatorEngine with all required specs."""
        engine = IndicatorEngine()
        seen: dict[str, IndicatorSpec] = {}
        for cls in _STRATEGY_CLASSES:
            instance = cls()
            for spec in instance.required_indicators:
                if spec.key not in seen:
                    seen[spec.key] = spec
                    engine.register(spec)
        return engine

    @staticmethod
    def _build_strategies(strategy_filter: list[str] | None) -> list:
        """Instantiate strategy objects, optionally filtered by name."""
        strategies = [cls() for cls in _STRATEGY_CLASSES]
        if strategy_filter:
            strategies = [s for s in strategies if s.name in strategy_filter]
        return strategies

    @staticmethod
    def _extract_sorted_dates(bars_by_symbol: dict[str, list[Bar]]) -> list[date]:
        """Extract and sort all unique trading dates across all symbols."""
        date_set: set[date] = set()
        for bars in bars_by_symbol.values():
            for bar in bars:
                date_set.add(bar.timestamp.date())
        return sorted(date_set)

    @staticmethod
    def _index_by_date(bars_by_symbol: dict[str, list[Bar]]) -> dict[str, dict[date, Bar]]:
        """Build a nested dict: symbol -> date -> Bar for O(1) lookups."""
        result: dict[str, dict[date, Bar]] = {}
        for sym, bars in bars_by_symbol.items():
            result[sym] = {bar.timestamp.date(): bar for bar in bars}
        return result

    @staticmethod
    def _has_required_indicators(indicators: dict) -> bool:
        """Check that the minimum required indicators are available (warmup done).

        Only checks core indicators shared by all strategies. Strategy-specific
        indicators (e.g. EMA_10, EMA_21 for ema_cross_trend) are checked within
        each strategy's _extract_indicators method.
        """
        required = ["RSI_14", "ADX_14", "ATR_14", "BBANDS_20"]
        return all(indicators.get(k) is not None for k in required)

    @staticmethod
    def _flatten_indicators(indicators: dict) -> dict:
        """Return indicators dict flattened for storage in ScanResult."""
        flat = {}
        for key, value in indicators.items():
            if isinstance(value, dict):
                flat[key] = {
                    k: round(float(v), 6) if isinstance(v, (int, float)) else v
                    for k, v in value.items()
                }
            elif isinstance(value, (int, float)):
                flat[key] = round(float(value), 6)
            else:
                flat[key] = value
        return flat

    @staticmethod
    def _get_atr(indicators: dict, fallback: float) -> float:
        """Extract ATR from indicators with fallback."""
        atr = indicators.get("ATR_14")
        if isinstance(atr, (int, float)) and atr > 0:
            return float(atr)
        return fallback if fallback > 0 else 1.0

    @staticmethod
    def _loss_pct(held: HeldPosition, current_price: float) -> float:
        """Return unrealized loss fraction (positive = loss)."""
        if held.entry_price <= 0:
            return 0.0
        if held.direction == "long":
            return max(0.0, (held.entry_price - current_price) / held.entry_price)
        else:
            return max(0.0, (current_price - held.entry_price) / held.entry_price)

    @staticmethod
    def _unrealized_loss_dollars(sim_pos: _SimPosition, current_price: float) -> float:
        """Return unrealized loss in dollars (positive = loss)."""
        held = sim_pos.held
        if held.direction == "long":
            return max(0.0, (held.entry_price - current_price) * sim_pos.qty)
        else:
            return max(0.0, (current_price - held.entry_price) * sim_pos.qty)
