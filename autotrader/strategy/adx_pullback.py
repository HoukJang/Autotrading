"""ADX Trend Pullback strategy.

Enters long on pullbacks during confirmed uptrends detected by ADX strength
and EMA golden cross, using RSI as the pullback indicator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy


@dataclass
class _SymbolState:
    """Per-symbol internal state for tracking position and trailing stop."""

    in_position: bool = False
    entry_price: float = 0.0
    bars_since_entry: int = 0
    highest_since_entry: float = 0.0


class AdxPullback(Strategy):
    """Trend-following strategy that enters long on pullbacks in confirmed uptrends.

    Entry conditions (all must be true):
        - ADX(14) > 25.0 (confirmed trend)
        - EMA(8) > EMA(21) (bullish trend direction)
        - RSI(14) <= 40.0 (pullback / temporarily oversold)
        - close > EMA(21) (price still above slow EMA)

    Exit conditions (checked in priority order):
        1. RSI > 70 (target)
        2. close >= entry + 2.5*ATR (take_profit)
        3. close <= highest_since_entry - 2.0*ATR (trailing_stop)
        4. EMA(8) < EMA(21) (trend_reversal)
        5. close <= entry - 1.5*ATR (stop_loss)
        6. bars_since_entry >= 7 (timeout)
    """

    name = "adx_pullback"

    ADX_PERIOD = 14
    EMA_FAST_PERIOD = 8
    EMA_SLOW_PERIOD = 21
    RSI_PERIOD = 14
    ATR_PERIOD = 14

    ADX_THRESHOLD = 25.0
    RSI_PULLBACK_MAX = 40.0
    RSI_TARGET = 70.0
    TAKE_PROFIT_ATR_MULT = 2.5
    TRAILING_STOP_ATR_MULT = 2.0
    STOP_LOSS_ATR_MULT = 1.5
    TIMEOUT_BARS = 7

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="ADX", params={"period": self.ADX_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_FAST_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_SLOW_PERIOD}),
            IndicatorSpec(name="RSI", params={"period": self.RSI_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": self.ATR_PERIOD}),
        ]
        self._states: dict[str, _SymbolState] = {}

    def _get_state(self, symbol: str) -> _SymbolState:
        if symbol not in self._states:
            self._states[symbol] = _SymbolState()
        return self._states[symbol]

    def _extract_indicators(self, ctx: MarketContext) -> dict[str, float] | None:
        adx = ctx.indicators.get(f"ADX_{self.ADX_PERIOD}")
        ema_fast = ctx.indicators.get(f"EMA_{self.EMA_FAST_PERIOD}")
        ema_slow = ctx.indicators.get(f"EMA_{self.EMA_SLOW_PERIOD}")
        rsi = ctx.indicators.get(f"RSI_{self.RSI_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{self.ATR_PERIOD}")

        if any(v is None for v in [adx, ema_fast, ema_slow, rsi, atr]):
            return None

        return {
            "adx": adx,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "rsi": rsi,
            "atr": atr,
        }

    def on_context(self, ctx: MarketContext) -> Signal | None:
        indicators = self._extract_indicators(ctx)
        if indicators is None:
            return None

        state = self._get_state(ctx.symbol)

        if state.in_position:
            state.bars_since_entry += 1
            if ctx.bar.close > state.highest_since_entry:
                state.highest_since_entry = ctx.bar.close
            if ctx.bar.high > state.highest_since_entry:
                state.highest_since_entry = ctx.bar.high
            return self._check_exit(ctx, state, indicators)

        return self._check_entry(ctx, state, indicators)

    def _check_entry(
        self,
        ctx: MarketContext,
        state: _SymbolState,
        indicators: dict[str, float],
    ) -> Signal | None:
        adx = indicators["adx"]
        ema_fast = indicators["ema_fast"]
        ema_slow = indicators["ema_slow"]
        rsi = indicators["rsi"]
        atr = indicators["atr"]
        close = ctx.bar.close

        if adx <= self.ADX_THRESHOLD:
            return None
        if ema_fast <= ema_slow:
            return None
        if rsi > self.RSI_PULLBACK_MAX:
            return None
        if close <= ema_slow:
            return None

        strength = min(
            1.0,
            (adx - self.ADX_THRESHOLD) / 25.0
            + (self.RSI_PULLBACK_MAX - rsi) / 40.0,
        )
        stop_loss = close - self.STOP_LOSS_ATR_MULT * atr

        state.in_position = True
        state.entry_price = close
        state.bars_since_entry = 0
        state.highest_since_entry = max(close, ctx.bar.high)

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="long",
            strength=strength,
            metadata={
                "sub_strategy": "trend_pullback",
                "stop_loss": stop_loss,
            },
        )

    def _check_exit(
        self,
        ctx: MarketContext,
        state: _SymbolState,
        indicators: dict[str, float],
    ) -> Signal | None:
        rsi = indicators["rsi"]
        atr = indicators["atr"]
        ema_fast = indicators["ema_fast"]
        ema_slow = indicators["ema_slow"]
        close = ctx.bar.close

        reason: str | None = None

        # Priority 1: RSI target
        if rsi > self.RSI_TARGET:
            reason = "target"
        # Priority 2: Take profit
        elif close >= state.entry_price + self.TAKE_PROFIT_ATR_MULT * atr:
            reason = "take_profit"
        # Priority 3: Trailing stop
        elif close <= state.highest_since_entry - self.TRAILING_STOP_ATR_MULT * atr:
            reason = "trailing_stop"
        # Priority 4: Trend reversal (EMA dead cross)
        elif ema_fast < ema_slow:
            reason = "trend_reversal"
        # Priority 5: Stop loss
        elif close <= state.entry_price - self.STOP_LOSS_ATR_MULT * atr:
            reason = "stop_loss"
        # Priority 6: Timeout
        elif state.bars_since_entry >= self.TIMEOUT_BARS:
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
