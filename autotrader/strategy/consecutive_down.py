"""Consecutive Down Days strategy (Larry Connors style mean reversion).

Enters long when a stock closes down 3+ consecutive days while remaining
above its long-term trend (EMA-50) and RSI is oversold.  Expects a
short-term bounce back to EMA-5.

Entry:
    Long -- 3+ consecutive down closes + close > EMA(50) + RSI < 50

Exit (strategy-level):
    Target   -- close > EMA(5)
    (SL and time exits handled by ExitRuleEngine)

Direction: Long only.
Entry Group: A (MOO).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy


@dataclass
class _PositionState:
    """Per-symbol internal state for position tracking."""

    in_position: bool = False
    entry_price: float = 0.0
    bars_since_entry: int = 0


class ConsecutiveDown(Strategy):
    """Long-only mean-reversion strategy based on consecutive down days.

    Concept: Stocks that close lower for 3+ consecutive days while still
    above their 50-day EMA tend to bounce.  We enter at the next open and
    exit when the price recovers above the 5-day EMA.
    """

    name = "consecutive_down"

    # Indicator parameters
    RSI_PERIOD = 14
    ATR_PERIOD = 14
    EMA_LONG_PERIOD = 50
    EMA_SHORT_PERIOD = 5

    # Entry thresholds
    MIN_DOWN_DAYS = 3
    RSI_MAX = 45.0

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="RSI", params={"period": self.RSI_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": self.ATR_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_LONG_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_SHORT_PERIOD}),
        ]
        self._states: dict[str, _PositionState] = {}

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

        if state.in_position:
            state.bars_since_entry += 1
            return self._check_exit(ctx, state, indicators)

        return self._check_entry(ctx, state, indicators)

    # ------------------------------------------------------------------
    # Indicator extraction
    # ------------------------------------------------------------------

    def _extract_indicators(self, ctx: MarketContext) -> dict | None:
        rsi = ctx.indicators.get(f"RSI_{self.RSI_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{self.ATR_PERIOD}")
        ema_50 = ctx.indicators.get(f"EMA_{self.EMA_LONG_PERIOD}")
        ema_5 = ctx.indicators.get(f"EMA_{self.EMA_SHORT_PERIOD}")

        if any(v is None for v in [rsi, atr, ema_50, ema_5]):
            return None

        return {
            "rsi": rsi,
            "atr": atr,
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
        atr: float = ind["atr"]
        ema_50: float = ind["ema_50"]
        close = ctx.bar.close

        # Trend filter: only trade above long-term EMA
        if close <= ema_50:
            return None

        # RSI filter
        if rsi >= self.RSI_MAX:
            return None

        # Count consecutive down days from history
        down_days = self._count_consecutive_down(ctx)
        if down_days < self.MIN_DOWN_DAYS:
            return None

        # Signal strength: more down days + lower RSI = stronger signal
        strength = min(
            1.0,
            (down_days - self.MIN_DOWN_DAYS + 1) * 0.15
            + (self.RSI_MAX - rsi) / self.RSI_MAX,
        )

        stop_loss = close - 1.5 * atr

        state.in_position = True
        state.entry_price = close
        state.bars_since_entry = 0

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="long",
            strength=strength,
            metadata={
                "sub_strategy": "consec_down_long",
                "stop_loss": stop_loss,
                "down_days": down_days,
            },
        )

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self, ctx: MarketContext, state: _PositionState, ind: dict,
    ) -> Signal | None:
        ema_5: float = ind["ema_5"]
        close = ctx.bar.close

        exit_reason: str | None = None

        # Target: close above short-term EMA (bounce complete)
        if close > ema_5:
            exit_reason = "target"

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
        If the current bar has not yet been appended to history (some
        callers build the context before appending the bar), it is added
        here to avoid an off-by-one undercount.  When the history already
        ends with the current bar (same timestamp), it is not duplicated.
        """
        count = 0
        history = list(ctx.history)
        # Append current bar only when it is not already the last entry.
        # Identity check first (fast path); fall back to timestamp equality.
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
