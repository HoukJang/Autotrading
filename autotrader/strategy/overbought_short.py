"""Conservative overbought short strategy -- short-only mean reversion.

Enters short when stocks are extremely overbought (RSI > 75, BB %B > 0.95)
in non-trending markets with fading momentum. Exits on target reversion,
stop loss, or timeout.
"""
from __future__ import annotations

from dataclasses import dataclass

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy


@dataclass
class _SymbolState:
    """Per-symbol internal state for position and momentum tracking."""
    in_position: bool = False
    entry_price: float = 0.0
    bars_since_entry: int = 0
    prev_ema_spread: float | None = None


class OverboughtShort(Strategy):
    """Short-only mean reversion strategy targeting overbought conditions.

    Entry requires all four conditions simultaneously:
        - RSI(14) > 75.0  (overbought)
        - BB %B > 0.95    (at upper Bollinger Band)
        - ADX(14) < 25.0  (non-trending / weak trend)
        - EMA(8)-EMA(21) spread narrowing (momentum fading)

    Exit on whichever comes first:
        - RSI < 55 or BB %B < 0.50 (target reached)
        - close >= entry + 2.5*ATR (ATR-based stop loss)
        - close >= entry * 1.05    (absolute 5% max loss)
        - 5 bars since entry       (timeout)
    """

    name = "overbought_short"

    RSI_PERIOD = 14
    BB_PERIOD = 20
    BB_STD = 2.0
    ADX_PERIOD = 14
    EMA_FAST_PERIOD = 8
    EMA_SLOW_PERIOD = 21
    ATR_PERIOD = 14

    RSI_ENTRY = 75.0
    PCT_B_ENTRY = 0.95
    ADX_MAX = 25.0

    RSI_EXIT = 55.0
    PCT_B_EXIT = 0.50
    ATR_STOP_MULT = 2.5
    ABSOLUTE_STOP_PCT = 1.05
    TIMEOUT_BARS = 5

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="RSI", params={"period": self.RSI_PERIOD}),
            IndicatorSpec(
                name="BBANDS",
                params={"period": self.BB_PERIOD, "num_std": self.BB_STD},
            ),
            IndicatorSpec(name="ADX", params={"period": self.ADX_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_FAST_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_SLOW_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": self.ATR_PERIOD}),
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

        # Compute EMA spread and detect momentum fading
        current_spread = indicators["ema_fast"] - indicators["ema_slow"]
        momentum_fading = (
            state.prev_ema_spread is not None
            and current_spread < state.prev_ema_spread
        )
        state.prev_ema_spread = current_spread

        if state.in_position:
            state.bars_since_entry += 1
            return self._check_exit(ctx, state, indicators)

        return self._check_entry(ctx, state, indicators, momentum_fading)

    # ------------------------------------------------------------------
    # Indicator extraction
    # ------------------------------------------------------------------

    def _extract_indicators(self, ctx: MarketContext) -> dict | None:
        rsi = ctx.indicators.get(f"RSI_{self.RSI_PERIOD}")
        bbands = ctx.indicators.get(f"BBANDS_{self.BB_PERIOD}")
        adx = ctx.indicators.get(f"ADX_{self.ADX_PERIOD}")
        ema_fast = ctx.indicators.get(f"EMA_{self.EMA_FAST_PERIOD}")
        ema_slow = ctx.indicators.get(f"EMA_{self.EMA_SLOW_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{self.ATR_PERIOD}")

        if any(v is None for v in [rsi, bbands, adx, ema_fast, ema_slow, atr]):
            return None

        if not isinstance(bbands, dict):
            return None

        return {
            "rsi": rsi,
            "pct_b": bbands["pct_b"],
            "adx": adx,
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "atr": atr,
        }

    # ------------------------------------------------------------------
    # Entry logic (short only)
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        ctx: MarketContext,
        state: _SymbolState,
        indicators: dict,
        momentum_fading: bool,
    ) -> Signal | None:
        rsi = indicators["rsi"]
        pct_b = indicators["pct_b"]
        adx = indicators["adx"]
        atr = indicators["atr"]
        close = ctx.bar.close

        if rsi <= self.RSI_ENTRY:
            return None
        if pct_b <= self.PCT_B_ENTRY:
            return None
        if adx >= self.ADX_MAX:
            return None
        if not momentum_fading:
            return None

        strength = min(1.0, (rsi - 75.0) / 25.0 + (pct_b - 0.95) / 0.05)
        stop_loss = min(close + self.ATR_STOP_MULT * atr,
                        close * self.ABSOLUTE_STOP_PCT)

        state.in_position = True
        state.entry_price = close
        state.bars_since_entry = 0

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="short",
            strength=strength,
            metadata={
                "sub_strategy": "overbought_short",
                "stop_loss": stop_loss,
            },
        )

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self,
        ctx: MarketContext,
        state: _SymbolState,
        indicators: dict,
    ) -> Signal | None:
        rsi = indicators["rsi"]
        pct_b = indicators["pct_b"]
        atr = indicators["atr"]
        close = ctx.bar.close
        entry = state.entry_price

        exit_reason: str | None = None

        # Target exits (price reverting)
        if rsi < self.RSI_EXIT:
            exit_reason = "target"
        elif pct_b < self.PCT_B_EXIT:
            exit_reason = "target"
        # Stop loss exits (price moving against short)
        elif close >= entry * self.ABSOLUTE_STOP_PCT:
            exit_reason = "absolute_stop"
        elif close >= entry + self.ATR_STOP_MULT * atr:
            exit_reason = "stop_loss"
        # Timeout
        elif state.bars_since_entry >= self.TIMEOUT_BARS:
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
