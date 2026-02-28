"""EMA Pullback strategy: buy the dip to a rising 21-day EMA.

Enters long when price touches or dips below a rising EMA(21) and
then recovers above it, with RSI in the neutral zone (35-55).
This is a trend-continuation pattern for stocks in established uptrends.

Entry:
    Long -- previous close < EMA(21), current close >= EMA(21),
            EMA(21) rising, RSI between 35 and 55

Exit (strategy-level):
    Breakdown -- 2 consecutive closes below EMA(21)
    (SL, TP, trailing, and time exits handled by ExitRuleEngine)

Direction: Long only.
Entry Group: B (confirmation).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy


@dataclass
class _SymbolState:
    """Per-symbol internal state for EMA pullback tracking."""

    in_position: bool = False
    entry_price: float = 0.0
    bars_since_entry: int = 0
    prev_close_below_ema: bool = False
    consecutive_below_ema: int = 0


class EmaPullback(Strategy):
    """Long-only trend-continuation strategy via EMA(21) pullback.

    Concept: In an established uptrend (rising EMA-21), a pullback to the
    EMA is a buying opportunity.  We enter when price recovers above the
    EMA after touching it, and exit if the trend breaks (2 consecutive
    closes below EMA-21).
    """

    name = "ema_pullback"

    # Indicator parameters
    RSI_PERIOD = 14
    ATR_PERIOD = 14
    EMA_PERIOD = 21

    # Entry thresholds
    RSI_MIN = 35.0
    RSI_MAX = 55.0

    # Exit: number of consecutive closes below EMA to trigger breakdown
    BREAKDOWN_BARS = 2

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="RSI", params={"period": self.RSI_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": self.ATR_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_PERIOD}),
        ]
        self._states: dict[str, _SymbolState] = {}

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def on_context(self, ctx: MarketContext) -> Signal | None:
        indicators = self._extract_indicators(ctx)
        if indicators is None:
            return None

        symbol = ctx.symbol
        if symbol not in self._states:
            self._states[symbol] = _SymbolState()
        state = self._states[symbol]

        if state.in_position:
            state.bars_since_entry += 1
            result = self._check_exit(ctx, state, indicators)
            # Update prev_close_below_ema for next bar
            state.prev_close_below_ema = ctx.bar.close < indicators["ema_21"]
            return result

        result = self._check_entry(ctx, state, indicators)
        # Update prev_close_below_ema for next bar
        state.prev_close_below_ema = ctx.bar.close < indicators["ema_21"]
        return result

    # ------------------------------------------------------------------
    # Indicator extraction
    # ------------------------------------------------------------------

    def _extract_indicators(self, ctx: MarketContext) -> dict | None:
        rsi = ctx.indicators.get(f"RSI_{self.RSI_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{self.ATR_PERIOD}")
        ema_21 = ctx.indicators.get(f"EMA_{self.EMA_PERIOD}")

        if any(v is None for v in [rsi, atr, ema_21]):
            return None

        return {
            "rsi": rsi,
            "atr": atr,
            "ema_21": ema_21,
        }

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self, ctx: MarketContext, state: _SymbolState, ind: dict,
    ) -> Signal | None:
        rsi: float = ind["rsi"]
        atr: float = ind["atr"]
        ema_21: float = ind["ema_21"]
        close = ctx.bar.close

        # Must have been below EMA on previous bar (pullback condition)
        if not state.prev_close_below_ema:
            return None

        # Current close must be at or above EMA (recovery)
        if close < ema_21:
            return None

        # EMA must be rising (compare current EMA to EMA a few bars ago)
        if not self._is_ema_rising(ctx):
            return None

        # RSI in neutral zone (not overbought, not deeply oversold)
        if rsi < self.RSI_MIN or rsi > self.RSI_MAX:
            return None

        # Signal strength: lower RSI within range = stronger mean-reversion signal
        strength = min(
            1.0,
            (self.RSI_MAX - rsi) / (self.RSI_MAX - self.RSI_MIN),
        )

        stop_loss = close - 1.5 * atr

        state.in_position = True
        state.entry_price = close
        state.bars_since_entry = 0
        state.consecutive_below_ema = 0

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="long",
            strength=strength,
            metadata={
                "sub_strategy": "ema_pullback_long",
                "stop_loss": stop_loss,
            },
        )

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self, ctx: MarketContext, state: _SymbolState, ind: dict,
    ) -> Signal | None:
        ema_21: float = ind["ema_21"]
        close = ctx.bar.close

        # Track consecutive closes below EMA
        if close < ema_21:
            state.consecutive_below_ema += 1
        else:
            state.consecutive_below_ema = 0

        # Breakdown: 2 consecutive closes below EMA
        if state.consecutive_below_ema >= self.BREAKDOWN_BARS:
            state.in_position = False
            state.consecutive_below_ema = 0
            return Signal(
                strategy=self.name,
                symbol=ctx.symbol,
                direction="close",
                strength=1.0,
                metadata={"exit_reason": "ema_breakdown"},
            )

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_ema_rising(ctx: MarketContext) -> bool:
        """Check if EMA(21) is rising by comparing recent values.

        Note: Individual bar indicator values are not stored in bar history,
        so this method uses close-price moving averages as an EMA direction
        proxy.  Specifically, it compares the average close of the last 5
        bars against the average of the 5 bars before that.  When the recent
        average exceeds the prior average the EMA is considered to be rising.
        """
        history = list(ctx.history)
        if len(history) < 5:
            return False
        # Compare current bar's indicator value to 5 bars ago
        # We approximate by checking that recent closes have a rising trend
        recent = [b.close for b in history[-5:]]
        # Simple check: EMA proxy via average of last 5 > average of prior 5
        if len(history) < 10:
            return recent[-1] > recent[0]
        prior = [b.close for b in history[-10:-5]]
        return sum(recent) / len(recent) > sum(prior) / len(prior)
