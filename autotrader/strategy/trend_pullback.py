"""Trend Pullback strategy: buying pullbacks to EMA(21) in moderate trends.

Fills the ADX 15-35 dead zone where neither Breakout Momentum (ADX > 28)
nor RSI Mean Reversion (ADX < 20) can trade. Captures pullback-to-support
entries in developing or moderate trends.

Entry (Long only):
    1. close > EMA(50)                          -- above medium-term trend
    2. EMA(21) > EMA(21) from 5 bars ago        -- rising short-term trend
    3. 15 <= ADX <= 35                           -- moderate trend strength
    4. 0.97 <= close / EMA(21) <= 1.02           -- price near EMA(21) support
    5. 35 <= RSI <= 60                           -- not oversold, not overbought
    6. Green candle (close > open) OR hammer      -- reversal confirmation

Exit (strategy-level):
    EMA structure break -- close < EMA(21) for 2 consecutive bars
    (SL/TP/trailing/time exits handled by ExitRuleEngine)

Direction: Long only.
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

EMA_SHORT_PERIOD = 21
EMA_LONG_PERIOD = 50
ADX_PERIOD = 14
RSI_PERIOD = 14
ATR_PERIOD = 14

# ADX range for moderate trend
ADX_MIN = 15.0
ADX_MAX = 35.0

# Price proximity to EMA(21)
PROXIMITY_LOWER = 0.97   # max 3% below EMA(21)
PROXIMITY_UPPER = 1.02   # max 2% above EMA(21)

# RSI pullback zone
RSI_MIN = 35.0
RSI_MAX = 60.0

# EMA slope lookback
SLOPE_LOOKBACK = 5

# Hammer pattern: lower wick > 1.5x body
HAMMER_WICK_RATIO = 1.5

# Exit: consecutive closes below EMA to trigger structure break
STRUCTURE_BREAK_BARS = 2


@dataclass
class _PositionState:
    """Per-symbol internal state for position tracking."""

    in_position: bool = False
    entry_price: float = 0.0
    bars_since_entry: int = 0
    consecutive_below_ema: int = 0


class TrendPullback(Strategy):
    """Long-only pullback strategy targeting EMA(21) support in moderate trends.

    Concept: In markets with ADX between 15 and 35, price often pulls back
    to the EMA(21) before resuming the trend. We enter on confirmation
    of a reversal (green candle or hammer) near the EMA(21) level when the
    overall trend structure (close > EMA(50), EMA(21) rising) is intact.
    """

    name = "trend_pullback"

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="EMA", params={"period": EMA_SHORT_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": EMA_LONG_PERIOD}),
            IndicatorSpec(name="ADX", params={"period": ADX_PERIOD}),
            IndicatorSpec(name="RSI", params={"period": RSI_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": ATR_PERIOD}),
        ]
        self._states: dict[str, _PositionState] = {}
        # Track recent EMA(21) values per symbol for slope detection
        self._ema_history: dict[str, list[float]] = {}

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

        # Track recent EMA(21) values per symbol for slope check
        ema_21 = indicators["ema_21"]
        if symbol not in self._ema_history:
            self._ema_history[symbol] = []
        ema_hist = self._ema_history[symbol]
        ema_hist.append(ema_21)
        # Keep last SLOPE_LOOKBACK + 1 values (current + 5 bars ago)
        if len(ema_hist) > SLOPE_LOOKBACK + 1:
            self._ema_history[symbol] = ema_hist[-(SLOPE_LOOKBACK + 1):]

        if state.in_position:
            state.bars_since_entry += 1
            return self._check_exit(ctx, state, indicators)

        return self._check_entry(ctx, state, indicators)

    # ------------------------------------------------------------------
    # Indicator extraction
    # ------------------------------------------------------------------

    def _extract_indicators(self, ctx: MarketContext) -> dict | None:
        ema_21 = ctx.indicators.get(f"EMA_{EMA_SHORT_PERIOD}")
        ema_50 = ctx.indicators.get(f"EMA_{EMA_LONG_PERIOD}")
        adx = ctx.indicators.get(f"ADX_{ADX_PERIOD}")
        rsi = ctx.indicators.get(f"RSI_{RSI_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{ATR_PERIOD}")

        if any(v is None for v in [ema_21, ema_50, adx, rsi, atr]):
            return None

        return {
            "ema_21": ema_21,
            "ema_50": ema_50,
            "adx": adx,
            "rsi": rsi,
            "atr": atr,
        }

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self, ctx: MarketContext, state: _PositionState, ind: dict,
    ) -> Signal | None:
        ema_21: float = ind["ema_21"]
        ema_50: float = ind["ema_50"]
        adx: float = ind["adx"]
        rsi: float = ind["rsi"]
        atr: float = ind["atr"]
        close = ctx.bar.close

        # 1. Trend confirmation: price above medium-term trend
        if close <= ema_50:
            return None

        # 2. EMA(21) slope positive (5-bar lookback)
        ema_hist = self._ema_history.get(ctx.symbol, [])
        if len(ema_hist) < SLOPE_LOOKBACK + 1:
            return None
        ema_5_bars_ago = ema_hist[-(SLOPE_LOOKBACK + 1)]
        if ema_21 <= ema_5_bars_ago:
            return None

        # 3. ADX in target range (moderate trend)
        if adx < ADX_MIN or adx > ADX_MAX:
            return None

        # 4. Price near EMA(21) (pullback to support)
        if ema_21 <= 0:
            return None
        ratio = close / ema_21
        if ratio < PROXIMITY_LOWER or ratio > PROXIMITY_UPPER:
            return None

        # 5. RSI in pullback zone
        if rsi < RSI_MIN or rsi > RSI_MAX:
            return None

        # 6. Reversal candle confirmation
        bar = ctx.bar
        is_green = bar.close > bar.open
        body = abs(bar.close - bar.open)
        lower_wick = min(bar.open, bar.close) - bar.low
        is_hammer = body > 0 and lower_wick > body * HAMMER_WICK_RATIO

        if not is_green and not is_hammer:
            return None

        # Signal strength: ADX-based scaling
        strength = 0.5 + (adx - ADX_MIN) / 40.0
        strength = max(0.0, min(1.0, strength))

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
                "sub_strategy": "trend_pullback_long",
                "stop_loss": stop_loss,
                "adx": round(adx, 2),
                "rsi": round(rsi, 2),
                "ema_slope": round(ema_21 - ema_5_bars_ago, 4),
            },
        )

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self, ctx: MarketContext, state: _PositionState, ind: dict,
    ) -> Signal | None:
        ema_21: float = ind["ema_21"]
        close = ctx.bar.close

        # Track consecutive closes below EMA(21) for structure break
        if close < ema_21:
            state.consecutive_below_ema += 1
        else:
            state.consecutive_below_ema = 0

        # Structure break: 2 consecutive closes below EMA(21)
        if state.consecutive_below_ema >= STRUCTURE_BREAK_BARS:
            state.in_position = False
            state.consecutive_below_ema = 0
            return Signal(
                strategy=self.name,
                symbol=ctx.symbol,
                direction="close",
                strength=1.0,
                metadata={"exit_reason": "structure_break"},
            )

        return None
