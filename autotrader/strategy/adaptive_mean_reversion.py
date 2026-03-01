"""Adaptive Mean Reversion strategy with OR-gate entry architecture.

Combines Bollinger Band / RSI extremes (Gate A) with consecutive down-day
counting (Gate B) to enter mean-reversion trades in non-trending markets.
Uses ADX < 25 and ADX slope filters to avoid trending regimes.
Shorts require close > EMA(50); longs have no EMA(50) gate.

Entry (OR gate -- either gate triggers):
    Long  Gate A -- pct_b < 0.30 AND RSI < 45
    Long  Gate B -- 3+ consecutive down days AND RSI < 40
    Short Gate A -- pct_b > 0.80 AND RSI > 60 AND close > EMA(50)

Exit (strategy-level):
    BB/RSI target -- Long: pct_b > 0.60 OR RSI > 55
                     Short: pct_b < 0.40 OR RSI < 45
    EMA(5) target -- After 2+ bars: Long close > EMA(5), Short close < EMA(5)
    Timeout       -- bars_since_entry >= 7

Direction: Long + Short.
Entry Group: A (MOO).
"""
from __future__ import annotations

from dataclasses import dataclass

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADX_MAX = 25.0
ADX_SLOPE_MAX = 2.0  # max ADX rise over last 3 bars

# Gate A (BB + RSI extreme)
GATE_A_LONG_PCT_B_MAX = 0.30
GATE_A_LONG_RSI_MAX = 45.0
GATE_A_SHORT_PCT_B_MIN = 0.80
GATE_A_SHORT_RSI_MIN = 60.0

# Gate B (consecutive down days)
GATE_B_MIN_DOWN_DAYS = 3
GATE_B_LONG_RSI_MAX = 40.0

# Strategy-level exit targets (emits "close" signal)
LONG_EXIT_PCT_B = 0.60
LONG_EXIT_RSI = 55.0
SHORT_EXIT_PCT_B = 0.40
SHORT_EXIT_RSI = 45.0
EMA_EXIT_MIN_BARS = 2  # min bars in position before EMA(5) exit
MAX_HOLD_DAYS = 7  # timeout exit


@dataclass
class _PositionState:
    """Per-symbol internal state for position tracking."""

    in_position: bool = False
    entry_price: float = 0.0
    entry_direction: str = ""  # "long" or "short"
    bars_since_entry: int = 0


class AdaptiveMeanReversion(Strategy):
    """Bidirectional adaptive mean-reversion strategy with OR-gate entries.

    Uses two independent entry gates (Gate A: BB/RSI extremes, Gate B:
    consecutive down days) filtered by ADX regime and EMA(50) trend direction.
    Exits via BB/RSI target recovery, EMA(5) crossback, or timeout.
    """

    name = "adaptive_mean_reversion"

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="RSI", params={"period": 14}),
            IndicatorSpec(name="BBANDS", params={"period": 20, "num_std": 2.0}),
            IndicatorSpec(name="ADX", params={"period": 14}),
            IndicatorSpec(name="ATR", params={"period": 14}),
            IndicatorSpec(name="EMA", params={"period": 50}),
            IndicatorSpec(name="EMA", params={"period": 5}),
        ]
        self._states: dict[str, _PositionState] = {}
        self._adx_history: dict[str, list[float]] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def on_context(self, ctx: MarketContext) -> Signal | None:
        indicators = self._extract_indicators(ctx)
        if indicators is None:
            return None

        symbol = ctx.symbol
        if symbol not in self._states:
            self._states[symbol] = _PositionState()
        state = self._states[symbol]

        # Track recent ADX values per symbol for slope detection
        adx_val: float = indicators["adx"]
        if symbol not in self._adx_history:
            self._adx_history[symbol] = []
        adx_hist = self._adx_history[symbol]
        adx_hist.append(adx_val)
        if len(adx_hist) > 4:
            self._adx_history[symbol] = adx_hist[-4:]

        if state.in_position:
            state.bars_since_entry += 1
            return self._check_exit(ctx, state, indicators)

        return self._check_entry(ctx, state, indicators)

    # ------------------------------------------------------------------
    # Indicator extraction
    # ------------------------------------------------------------------

    def _extract_indicators(self, ctx: MarketContext) -> dict | None:
        rsi = ctx.indicators.get("RSI_14")
        bbands = ctx.indicators.get("BBANDS_20")
        adx = ctx.indicators.get("ADX_14")
        atr = ctx.indicators.get("ATR_14")
        ema_50 = ctx.indicators.get("EMA_50")
        ema_5 = ctx.indicators.get("EMA_5")

        if any(v is None for v in [rsi, bbands, adx, atr, ema_50, ema_5]):
            return None

        if not isinstance(bbands, dict):
            return None

        return {
            "rsi": rsi,
            "adx": adx,
            "atr": atr,
            "pct_b": bbands["pct_b"],
            "ema_50": ema_50,
            "ema_5": ema_5,
        }

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self, ctx: MarketContext, state: _PositionState, ind: dict,
    ) -> Signal | None:
        rsi: float = ind["rsi"]
        pct_b: float = ind["pct_b"]
        adx: float = ind["adx"]
        atr: float = ind["atr"]
        ema_50: float = ind["ema_50"]
        close = ctx.bar.close

        # Common filter 1: ADX must be below threshold (non-trending)
        if adx >= ADX_MAX:
            return None

        # Common filter 2: ADX slope must not be rising too fast
        adx_hist = self._adx_history.get(ctx.symbol, [])
        if len(adx_hist) >= 4 and (adx_hist[-1] - adx_hist[-4]) > ADX_SLOPE_MAX:
            return None

        # --- LONG entries (Gate A OR Gate B) ---
        # No EMA(50) filter for longs -- removed to avoid selecting
        # only downtrending stocks that continue to fall.
        # Gate A: BB/RSI extreme
        gate_a_long = pct_b < GATE_A_LONG_PCT_B_MAX and rsi < GATE_A_LONG_RSI_MAX
        # Gate B: consecutive down days
        down_days = self._count_consecutive_down(ctx)
        gate_b_long = down_days >= GATE_B_MIN_DOWN_DAYS and rsi < GATE_B_LONG_RSI_MAX

        if gate_a_long:
            strength = min(
                1.0,
                (GATE_A_LONG_PCT_B_MAX - pct_b) / GATE_A_LONG_PCT_B_MAX
                + (GATE_A_LONG_RSI_MAX - rsi) / GATE_A_LONG_RSI_MAX,
            )
            stop_loss = close - 2.5 * atr

            state.in_position = True
            state.entry_price = close
            state.entry_direction = "long"
            state.bars_since_entry = 0

            return Signal(
                strategy=self.name,
                symbol=ctx.symbol,
                direction="long",
                strength=strength,
                metadata={
                    "sub_strategy": "mr_long_gate_a",
                    "stop_loss": stop_loss,
                    "entry_adx": adx,
                },
            )

        if gate_b_long:
            strength = min(
                1.0,
                (GATE_B_LONG_RSI_MAX - rsi) / GATE_B_LONG_RSI_MAX
                + min(down_days, 5) / 5.0,
            )
            stop_loss = close - 2.5 * atr

            state.in_position = True
            state.entry_price = close
            state.entry_direction = "long"
            state.bars_since_entry = 0

            return Signal(
                strategy=self.name,
                symbol=ctx.symbol,
                direction="long",
                strength=strength,
                metadata={
                    "sub_strategy": "mr_long_gate_b",
                    "stop_loss": stop_loss,
                    "entry_adx": adx,
                    "down_days": down_days,
                },
            )

        # --- SHORT entry (Gate A only) ---
        if close > ema_50:
            gate_a_short = (
                pct_b > GATE_A_SHORT_PCT_B_MIN and rsi > GATE_A_SHORT_RSI_MIN
            )
            if gate_a_short:
                strength = min(
                    1.0,
                    (pct_b - GATE_A_SHORT_PCT_B_MIN) / (1.0 - GATE_A_SHORT_PCT_B_MIN)
                    + (rsi - GATE_A_SHORT_RSI_MIN) / (100.0 - GATE_A_SHORT_RSI_MIN),
                )
                stop_loss = close + 2.0 * atr

                state.in_position = True
                state.entry_price = close
                state.entry_direction = "short"
                state.bars_since_entry = 0

                return Signal(
                    strategy=self.name,
                    symbol=ctx.symbol,
                    direction="short",
                    strength=strength,
                    metadata={
                        "sub_strategy": "mr_short_gate_a",
                        "stop_loss": stop_loss,
                        "entry_adx": adx,
                    },
                )

        return None

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self, ctx: MarketContext, state: _PositionState, ind: dict,
    ) -> Signal | None:
        rsi: float = ind["rsi"]
        pct_b: float = ind["pct_b"]
        ema_5: float = ind["ema_5"]
        close = ctx.bar.close

        exit_reason: str | None = None

        # 1. BB/RSI target
        if state.entry_direction == "long":
            if pct_b > LONG_EXIT_PCT_B or rsi > LONG_EXIT_RSI:
                exit_reason = "target"
        elif state.entry_direction == "short":
            if pct_b < SHORT_EXIT_PCT_B or rsi < SHORT_EXIT_RSI:
                exit_reason = "target"

        # 2. EMA(5) target (only after minimum bars)
        if exit_reason is None and state.bars_since_entry >= EMA_EXIT_MIN_BARS:
            if state.entry_direction == "long" and close > ema_5:
                exit_reason = "ema5_exit"
            elif state.entry_direction == "short" and close < ema_5:
                exit_reason = "ema5_exit"

        # 3. Timeout
        if exit_reason is None and state.bars_since_entry >= MAX_HOLD_DAYS:
            exit_reason = "timeout"

        if exit_reason is None:
            return None

        state.in_position = False

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="close",
            strength=1.0,
            metadata={"exit_reason": exit_reason},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_consecutive_down(ctx: MarketContext) -> int:
        """Count how many consecutive days the stock has closed lower.

        Builds a complete sequence that always includes the current bar.
        If the current bar has not yet been appended to history, it is added
        here to avoid an off-by-one undercount.
        """
        count = 0
        history = list(ctx.history)
        # Append current bar only when it is not already the last entry.
        if not history or (
            history[-1] is not ctx.bar
            and history[-1].timestamp != ctx.bar.timestamp
        ):
            history.append(ctx.bar)
        # Walk backwards through history (most recent first)
        for i in range(len(history) - 1, 0, -1):
            if history[i].close < history[i - 1].close:
                count += 1
            else:
                break
        return count
