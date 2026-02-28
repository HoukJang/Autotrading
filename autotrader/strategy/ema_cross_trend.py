"""EMA Cross Trend strategy for trending markets.

Enters long when EMA(10) crosses above EMA(21) and enters short when
EMA(10) crosses below EMA(21).  Only trades when ADX > 28 (trending),
ADX has risen by at least +2.0 over the last 3 bars, 2 consecutive
closes confirm the direction, and RSI is in a healthy range.

Entry:
    Long  -- EMA(10) crosses above EMA(21), ADX > 28, ADX rising +2.0/3bars,
             2 consecutive up closes, RSI 40-70
    Short -- EMA(10) crosses below EMA(21), ADX > 28, ADX rising +2.0/3bars,
             2 consecutive down closes, RSI 30-60

Exit (handled by ExitRuleEngine):
    SL 3.0 ATR, TP 5.0 ATR, Trailing 2.0 ATR (activate at 1.5 ATR), Max Hold 10 days

Direction: Long and Short.
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
    entry_direction: str = ""  # "long" or "short"
    bars_since_entry: int = 0


@dataclass
class _EmaState:
    """Per-symbol EMA tracking for crossover detection."""

    prev_ema10: float = 0.0
    prev_ema21: float = 0.0
    has_prev: bool = False


class EmaCrossTrend(Strategy):
    """Bidirectional trend-following strategy based on EMA crossovers.

    Concept: When EMA(10) crosses above EMA(21) in a trending market
    (ADX > 28), enter long. When EMA(10) crosses below EMA(21) in a
    trending market, enter short. Requires ADX to be rising (+2.0 over
    3 bars) and 2 consecutive closes in the direction. RSI filters
    prevent entries in overbought/oversold conditions.
    """

    name = "ema_cross_trend"

    # Indicator parameters
    RSI_PERIOD = 14
    ATR_PERIOD = 14
    ADX_PERIOD = 14
    EMA_FAST_PERIOD = 10
    EMA_SLOW_PERIOD = 21

    # Entry thresholds
    ADX_MIN = 28.0
    RSI_LONG_MIN = 40.0
    RSI_LONG_MAX = 70.0
    RSI_SHORT_MIN = 30.0
    RSI_SHORT_MAX = 60.0

    # ADX rising confirmation
    ADX_RISE_THRESHOLD = 2.0    # ADX must rise by at least 2.0 over 3 bars
    MIN_MOMENTUM_BARS = 2       # require 2 consecutive bars in direction

    # Stop loss ATR multiplier (used in signal metadata)
    SL_ATR_MULT = 3.0

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="RSI", params={"period": self.RSI_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": self.ATR_PERIOD}),
            IndicatorSpec(name="ADX", params={"period": self.ADX_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_FAST_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_SLOW_PERIOD}),
        ]
        self._states: dict[str, _PositionState] = {}
        self._ema_states: dict[str, _EmaState] = {}
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
        if symbol not in self._ema_states:
            self._ema_states[symbol] = _EmaState()
        state = self._states[symbol]
        ema_state = self._ema_states[symbol]

        # Track recent ADX values per symbol for rising confirmation
        adx_val: float = indicators["adx"]
        if symbol not in self._adx_history:
            self._adx_history[symbol] = []
        adx_hist = self._adx_history[symbol]
        adx_hist.append(adx_val)
        if len(adx_hist) > 4:
            self._adx_history[symbol] = adx_hist[-4:]

        ema_10: float = indicators["ema_10"]
        ema_21: float = indicators["ema_21"]

        # Generate signal (or None) before updating EMA state
        signal: Signal | None = None

        if state.in_position:
            state.bars_since_entry += 1
            # No internal exit logic; ExitRuleEngine handles everything
            signal = None
        else:
            signal = self._check_entry(ctx, state, ema_state, indicators)

        # Update EMA state for next bar's crossover detection
        ema_state.prev_ema10 = ema_10
        ema_state.prev_ema21 = ema_21
        ema_state.has_prev = True

        return signal

    # ------------------------------------------------------------------
    # Indicator extraction
    # ------------------------------------------------------------------

    def _extract_indicators(self, ctx: MarketContext) -> dict | None:
        rsi = ctx.indicators.get(f"RSI_{self.RSI_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{self.ATR_PERIOD}")
        adx = ctx.indicators.get(f"ADX_{self.ADX_PERIOD}")
        ema_10 = ctx.indicators.get(f"EMA_{self.EMA_FAST_PERIOD}")
        ema_21 = ctx.indicators.get(f"EMA_{self.EMA_SLOW_PERIOD}")

        if any(v is None for v in [rsi, atr, adx, ema_10, ema_21]):
            return None

        return {
            "rsi": rsi,
            "atr": atr,
            "adx": adx,
            "ema_10": ema_10,
            "ema_21": ema_21,
        }

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        ctx: MarketContext,
        state: _PositionState,
        ema_state: _EmaState,
        ind: dict,
    ) -> Signal | None:
        rsi: float = ind["rsi"]
        atr: float = ind["atr"]
        adx: float = ind["adx"]
        ema_10: float = ind["ema_10"]
        ema_21: float = ind["ema_21"]
        close = ctx.bar.close

        # Need previous EMA values for crossover detection
        if not ema_state.has_prev:
            return None

        prev_ema10 = ema_state.prev_ema10
        prev_ema21 = ema_state.prev_ema21

        # Trend confirmation: ADX must be above threshold
        if adx <= self.ADX_MIN:
            return None

        # ADX must be rising: current ADX > 3-bars-ago ADX + threshold
        adx_hist = self._adx_history.get(ctx.symbol, [])
        if len(adx_hist) >= 4:
            if (adx_hist[-1] - adx_hist[-4]) < self.ADX_RISE_THRESHOLD:
                return None

        # Detect crossover
        long_cross = prev_ema10 <= prev_ema21 and ema_10 > ema_21
        short_cross = prev_ema10 >= prev_ema21 and ema_10 < ema_21

        # Long entry: EMA10 crosses above EMA21
        if long_cross:
            if rsi < self.RSI_LONG_MIN or rsi > self.RSI_LONG_MAX:
                return None

            # Momentum: require 2 consecutive up closes
            if not self._has_momentum(ctx, "long"):
                return None

            strength = min(
                1.0,
                (adx - 28.0) / 22.0 + abs(ema_10 - ema_21) / ema_21 * 10.0,
            )
            stop_loss = close - self.SL_ATR_MULT * atr

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
                    "sub_strategy": "ema_cross_long",
                    "stop_loss": stop_loss,
                    "entry_adx": adx,
                },
            )

        # Short entry: EMA10 crosses below EMA21
        if short_cross:
            if rsi < self.RSI_SHORT_MIN or rsi > self.RSI_SHORT_MAX:
                return None

            # Momentum: require 2 consecutive down closes
            if not self._has_momentum(ctx, "short"):
                return None

            strength = min(
                1.0,
                (adx - 28.0) / 22.0 + abs(ema_10 - ema_21) / ema_21 * 10.0,
            )
            stop_loss = close + self.SL_ATR_MULT * atr

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
                    "sub_strategy": "ema_cross_short",
                    "stop_loss": stop_loss,
                    "entry_adx": adx,
                },
            )

        return None

    # ------------------------------------------------------------------
    # Momentum helper
    # ------------------------------------------------------------------

    @staticmethod
    def _has_momentum(ctx: MarketContext, direction: str) -> bool:
        """Check for consecutive closes in the expected direction."""
        history = list(ctx.history)
        if len(history) < 3:  # Need at least 3 bars (current + 2 previous)
            return False
        # Include current bar if not already in history
        if not history or (
            history[-1] is not ctx.bar
            and history[-1].timestamp != ctx.bar.timestamp
        ):
            history.append(ctx.bar)
        if len(history) < 3:
            return False
        if direction == "long":
            # Last 2 closes must be up: bar[-1].close > bar[-2].close AND bar[-2].close > bar[-3].close
            return history[-1].close > history[-2].close and history[-2].close > history[-3].close
        else:  # short
            # Last 2 closes must be down
            return history[-1].close < history[-2].close and history[-2].close < history[-3].close
