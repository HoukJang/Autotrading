"""BB Squeeze Breakout strategy: bidirectional volatility breakout after Bollinger Band squeeze."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy


@dataclass
class _SqueezeState:
    """Per-symbol internal state for BB Squeeze Breakout strategy."""

    bb_width_history: deque = field(default_factory=lambda: deque(maxlen=20))
    prev_adx: float | None = None
    in_position: bool = False
    entry_price: float = 0.0
    entry_direction: str = ""
    bars_since_entry: int = 0


class BbSqueezeBreakout(Strategy):
    """Bidirectional volatility breakout strategy.

    Enters when price breaks out of Bollinger Band after a squeeze
    (low volatility contraction period). Supports both long and short
    entries with ATR-based stops and RSI/BB-middle exits.
    """

    name = "bb_squeeze"

    BB_PERIOD = 20
    BB_STD = 2.0
    ADX_PERIOD = 14
    RSI_PERIOD = 14
    ATR_PERIOD = 14

    SQUEEZE_THRESHOLD = 0.75
    MIN_BB_HISTORY = 5
    ADX_RISE_MIN = 2.0
    ATR_STOP_MULT = 1.5
    MAX_BARS_IN_POSITION = 7

    RSI_LONG_EXIT = 75.0
    RSI_SHORT_EXIT = 25.0

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="BBANDS", params={"period": self.BB_PERIOD, "num_std": self.BB_STD}),
            IndicatorSpec(name="ADX", params={"period": self.ADX_PERIOD}),
            IndicatorSpec(name="RSI", params={"period": self.RSI_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": self.ATR_PERIOD}),
        ]
        self._states: dict[str, _SqueezeState] = {}

    def on_context(self, ctx: MarketContext) -> Signal | None:
        indicators = self._extract_indicators(ctx)
        if indicators is None:
            return None

        symbol = ctx.symbol
        if symbol not in self._states:
            self._states[symbol] = _SqueezeState()
        state = self._states[symbol]

        bb_width = indicators["bb_width"]
        adx = indicators["adx"]

        # Track BB width history
        state.bb_width_history.append(bb_width)

        # Determine squeeze and ADX rising
        is_squeezed = self._is_squeezed(state, bb_width)
        adx_rising = self._is_adx_rising(state, adx)

        signal: Signal | None = None

        if state.in_position:
            state.bars_since_entry += 1
            signal = self._check_exit(ctx, state, indicators)
        else:
            signal = self._check_entry(ctx, state, indicators, is_squeezed, adx_rising)

        # Update prev_adx after processing
        state.prev_adx = adx

        return signal

    def _extract_indicators(self, ctx: MarketContext) -> dict | None:
        bbands = ctx.indicators.get(f"BBANDS_{self.BB_PERIOD}")
        adx = ctx.indicators.get(f"ADX_{self.ADX_PERIOD}")
        rsi = ctx.indicators.get(f"RSI_{self.RSI_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{self.ATR_PERIOD}")

        if any(v is None for v in [bbands, adx, rsi, atr]):
            return None

        if not isinstance(bbands, dict):
            return None

        return {
            "bb_upper": bbands["upper"],
            "bb_middle": bbands["middle"],
            "bb_lower": bbands["lower"],
            "bb_width": bbands["width"],
            "bb_pct_b": bbands["pct_b"],
            "adx": adx,
            "rsi": rsi,
            "atr": atr,
        }

    def _is_squeezed(self, state: _SqueezeState, current_width: float) -> bool:
        if len(state.bb_width_history) < self.MIN_BB_HISTORY:
            return False
        avg_width = sum(state.bb_width_history) / len(state.bb_width_history)
        if avg_width <= 0:
            return False
        return current_width <= avg_width * self.SQUEEZE_THRESHOLD

    def _is_adx_rising(self, state: _SqueezeState, current_adx: float) -> bool:
        if state.prev_adx is None:
            return False
        return (current_adx - state.prev_adx) >= self.ADX_RISE_MIN

    def _check_entry(
        self,
        ctx: MarketContext,
        state: _SqueezeState,
        indicators: dict,
        is_squeezed: bool,
        adx_rising: bool,
    ) -> Signal | None:
        if not is_squeezed or not adx_rising:
            return None

        pct_b = indicators["bb_pct_b"]
        atr = indicators["atr"]
        close = ctx.bar.close

        # Long breakout: price above upper BB
        if pct_b > 1.0:
            strength = min(1.0, pct_b - 1.0 + 0.5)
            stop_loss = close - self.ATR_STOP_MULT * atr

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
                    "sub_strategy": "squeeze_long",
                    "stop_loss": stop_loss,
                },
            )

        # Short breakout: price below lower BB
        if pct_b < 0.0:
            strength = min(1.0, abs(pct_b) + 0.5)
            stop_loss = close + self.ATR_STOP_MULT * atr

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
                    "sub_strategy": "squeeze_short",
                    "stop_loss": stop_loss,
                },
            )

        return None

    def _check_exit(
        self,
        ctx: MarketContext,
        state: _SqueezeState,
        indicators: dict,
    ) -> Signal | None:
        close = ctx.bar.close
        rsi = indicators["rsi"]
        atr = indicators["atr"]
        bb_middle = indicators["bb_middle"]

        reason: str | None = None

        if state.entry_direction == "long":
            if rsi > self.RSI_LONG_EXIT:
                reason = "target"
            elif close <= state.entry_price - self.ATR_STOP_MULT * atr:
                reason = "stop_loss"
            elif close < bb_middle:
                reason = "stop_loss"
        elif state.entry_direction == "short":
            if rsi < self.RSI_SHORT_EXIT:
                reason = "target"
            elif close >= state.entry_price + self.ATR_STOP_MULT * atr:
                reason = "stop_loss"
            elif close > bb_middle:
                reason = "stop_loss"

        if reason is None and state.bars_since_entry >= self.MAX_BARS_IN_POSITION:
            reason = "timeout"

        if reason is None:
            return None

        state.in_position = False

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="close",
            strength=1.0,
            metadata={"reason": reason},
        )
