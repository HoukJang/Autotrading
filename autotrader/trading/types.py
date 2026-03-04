"""Lightweight data types for the unified trading core.

These types are used by GDREngine, EntryConstraintChecker, UnifiedExitEngine,
and PositionSizer to decouple from heavy domain objects (Position,
HeldPosition, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
