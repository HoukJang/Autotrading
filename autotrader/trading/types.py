"""Lightweight data types for the unified trading core.

These types are used by GDREngine, EntryConstraintChecker, UnifiedExitEngine,
PositionSizer, ExitRuleEngine, PositionMonitor, and OpenPositionTracker to
decouple from heavy domain objects (Position, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, auto
from typing import Literal


@dataclass(frozen=True, slots=True)
class PositionInfo:
    """Minimal position snapshot for constraint checking.

    Carries only the fields needed by EntryConstraintChecker and heat
    calculation -- no broker handles, no mutable state.
    """

    symbol: str
    strategy: str
    direction: str       # "long" or "short"
    risk_pct: float      # fraction of equity at risk (for heat calculation)


# ---------------------------------------------------------------------------
# PriceMode enum
# ---------------------------------------------------------------------------

class PriceMode(Enum):
    """Determines which price fields are used for SL/TP hit detection.

    BAR_CLOSE: Live mode -- only the bar close price is checked against
        stop-loss and take-profit levels.  This matches the live system
        where ExitRuleEngine evaluates at bar close.

    INTRADAY: Backtest mode -- bar high/low are used for SL/TP checks
        to simulate intraday fills.  When both SL and TP are hit in the
        same bar, open-proximity disambiguation decides which fires first.
    """

    BAR_CLOSE = auto()
    INTRADAY = auto()


# ---------------------------------------------------------------------------
# ExitContext -- position state fed into the exit engine
# ---------------------------------------------------------------------------

@dataclass
class ExitContext:
    """Position state required by the exit engine for evaluation.

    All mutable fields (trailing_high, stage1_done, etc.) are updated
    by the exit engine and returned in ``ExitDecision.updated_context``
    so the caller can persist the state changes.

    Attributes:
        symbol: Ticker symbol.
        strategy: Strategy name that opened the position.
        direction: Trade direction, ``"long"`` or ``"short"``.
        entry_price: Actual fill price at entry.
        entry_date: Calendar date of entry (US/Eastern).
        qty: Number of shares held.
        entry_atr: ATR value at entry time (anchors SL/TP levels).
        bars_held: Number of daily bars since entry (0 on entry day).
        current_sl: Computed stop-loss price (updated by engine).
        current_tp: Computed take-profit price (None for indicator-based).
        trailing_active: Whether the trailing stop has activated.
        trailing_high: Highest price since entry (for long trailing stop).
        trailing_low: Lowest price since entry (for short trailing stop).
        stage1_done: SL has been moved to breakeven.
        stage2_done: SL has locked in profit.
        consecutive_loss_bars: Counter for -7% confirmed emergency exit.
        mfe_price: Max favorable excursion price.
        mae_price: Max adverse excursion price (min for long).
    """

    symbol: str
    strategy: str
    direction: Literal["long", "short"]
    entry_price: float
    entry_date: date
    qty: int
    entry_atr: float
    bars_held: int = 0
    current_sl: float = 0.0
    current_tp: float | None = None
    trailing_active: bool = False
    trailing_high: float = 0.0
    trailing_low: float = float("inf")
    stage1_done: bool = False
    stage2_done: bool = False
    consecutive_loss_bars: int = 0
    mfe_price: float = 0.0
    mae_price: float = float("inf")

    def __post_init__(self) -> None:
        if self.trailing_high == 0.0:
            self.trailing_high = self.entry_price
        if self.trailing_low == float("inf"):
            self.trailing_low = self.entry_price
        if self.mfe_price == 0.0:
            self.mfe_price = self.entry_price
        if self.mae_price == float("inf"):
            self.mae_price = self.entry_price


# ---------------------------------------------------------------------------
# ExitDecision -- result of exit engine evaluation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExitDecision:
    """Result of exit engine evaluation for a single bar.

    Attributes:
        should_exit: True if the position should be closed.
        reason: Exit reason string for logging and trade records.
            Values: ``"sl_hit"``, ``"tp_hit"``, ``"trailing_stop"``,
            ``"time_exit"``, ``"emergency_immediate"``,
            ``"emergency_confirmed"``, or ``""`` for hold.
        exit_price: Price to use for the exit fill.
        updated_context: ExitContext with updated state (MFE/MAE,
            trailing activation, stage upgrades, consecutive_loss_bars).
    """

    should_exit: bool
    reason: str
    exit_price: float
    updated_context: ExitContext


# ---------------------------------------------------------------------------
# HeldPosition -- mutable runtime state for position monitoring
# ---------------------------------------------------------------------------

@dataclass
class HeldPosition:
    """Runtime state for a position being monitored by PositionMonitor.

    This is the primary mutable position representation used across the live
    execution layer (ExitRuleEngine, PositionMonitor, EntryManager) and the
    portfolio tracking layer (OpenPositionTracker).  It unifies the former
    ``HeldPosition`` (execution) and ``TrackedPosition`` (portfolio) types
    into a single class.

    Attributes:
        symbol: Ticker symbol.
        strategy: Strategy that opened the position.
        direction: "long" or "short".
        entry_price: Actual fill price (NOT signal price).
        entry_atr: ATR value at the time of entry (used to anchor SL/TP).
        entry_date_et: Calendar date of entry in US/Eastern timezone.
        bars_held: Number of daily bars elapsed since entry (incremented by
            PositionMonitor on each new daily bar).
        qty: Number of shares held.
        highest_price: Highest price observed since entry (for trailing stop
            and MFE calculation).
        lowest_price: Lowest price observed since entry (for trailing stop
            and MAE calculation).
        consecutive_loss_bars: Counter for emergency -7% confirmation logic.
        entry_adx: ADX value at entry time (for exit guards).
    """

    symbol: str
    strategy: str
    direction: Literal["long", "short"]
    entry_price: float
    entry_atr: float
    entry_date_et: date
    bars_held: int = 0
    qty: float = 0.0
    highest_price: float = 0.0
    lowest_price: float = float("inf")
    consecutive_loss_bars: int = 0
    entry_adx: float = 0.0

    # Optional datetime of entry, stored for backward compat with the
    # former TrackedPosition.entry_time field.  Not required by the exit
    # engine (which uses entry_date_et).  Will be removed in Wave 2.
    _entry_time: datetime | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Initialise price extremes from entry price when not explicitly set.
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price
        if self.lowest_price == float("inf"):
            self.lowest_price = self.entry_price

    def update_price_extremes(self, high: float, low: float) -> None:
        """Update MFE/MAE tracking with new bar high/low."""
        self.highest_price = max(self.highest_price, high)
        self.lowest_price = min(self.lowest_price, low)

    def update(self, high: float, low: float, close: float) -> None:
        """Update with new bar data and increment bar count.

        Backward-compatible method matching the former TrackedPosition
        interface.  Delegates to ``update_price_extremes`` and increments
        ``bars_held``.

        Args:
            high: Bar high price.
            low: Bar low price.
            close: Bar close price (reserved for future use).
        """
        self.update_price_extremes(high, low)
        self.bars_held += 1

    # ------------------------------------------------------------------
    # Backward-compatible aliases (bridge until Wave 2 completes main.py
    # migration from TrackedPosition field names to HeldPosition names).
    # ------------------------------------------------------------------

    @property
    def entry_time(self) -> datetime | None:
        """Alias for ``_entry_time`` (backward compat with TrackedPosition)."""
        return self._entry_time

    @entry_time.setter
    def entry_time(self, value: datetime | None) -> None:
        self._entry_time = value

    @property
    def bar_count(self) -> int:
        """Alias for ``bars_held`` (backward compat with TrackedPosition)."""
        return self.bars_held

    @bar_count.setter
    def bar_count(self, value: int) -> None:
        self.bars_held = value

    @property
    def quantity(self) -> float:
        """Alias for ``qty`` (backward compat with TrackedPosition)."""
        return self.qty

    @quantity.setter
    def quantity(self, value: float) -> None:
        self.qty = value

    @property
    def mfe(self) -> float:
        """Maximum Favorable Excursion (best unrealized profit fraction).

        For long positions: (highest - entry) / entry
        For short positions: (entry - lowest) / entry
        """
        if self.entry_price <= 0:
            return 0.0
        if self.direction == "long":
            return (self.highest_price - self.entry_price) / self.entry_price
        else:  # short
            return (self.entry_price - self.lowest_price) / self.entry_price

    @property
    def mae(self) -> float:
        """Maximum Adverse Excursion (worst unrealized loss fraction).

        For long positions: (entry - lowest) / entry
        For short positions: (highest - entry) / entry
        """
        if self.entry_price <= 0:
            return 0.0
        if self.direction == "long":
            return (self.entry_price - self.lowest_price) / self.entry_price
        else:  # short
            return (self.highest_price - self.entry_price) / self.entry_price


# ---------------------------------------------------------------------------
# TradeMetaSnapshot -- typed metadata for trade records
# ---------------------------------------------------------------------------

@dataclass
class TradeMetaSnapshot:
    """Typed metadata for a trade record.

    Replaces the untyped ``dict`` previously used in ``_trades_meta_cache``
    and similar runtime caches.  Provides explicit field names and types
    so that callers no longer need to guess which keys exist or cast
    values from ``Any``.

    Attributes:
        strategy: Strategy name that generated the trade.
        direction: Trade direction (``"long"`` or ``"short"``).
        entry_atr: ATR value at entry time.
        entry_adx: ADX value at entry time.
        sub_strategy: Sub-strategy identifier (e.g., ``"bb_cross"``).
        timestamp: ISO-8601 timestamp string of the trade event.
    """

    strategy: str = "unknown"
    direction: str = "long"
    entry_atr: float = 0.0
    entry_adx: float = 0.0
    sub_strategy: str = ""
    timestamp: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> TradeMetaSnapshot:
        """Create from an untyped dict (backward compatibility).

        Handles the nested ``metadata`` sub-dict structure used by the
        existing trade record format, with safe defaults for missing keys.

        Args:
            data: Raw trade record dict, optionally containing a nested
                ``metadata`` dict with ``entry_atr``, ``entry_adx``, and
                ``sub_strategy`` fields.

        Returns:
            A fully populated ``TradeMetaSnapshot`` instance.
        """
        metadata = data.get("metadata", {})
        return cls(
            strategy=data.get("strategy", "unknown"),
            direction=data.get("direction", "long"),
            entry_atr=float(metadata.get("entry_atr", 0.0)),
            entry_adx=float(metadata.get("entry_adx", 0.0)),
            sub_strategy=str(metadata.get("sub_strategy", "")),
            timestamp=str(data.get("timestamp", "")),
        )
