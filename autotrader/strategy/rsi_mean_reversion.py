"""RSI Mean Reversion strategy for non-trending (low ADX) markets.

Enters long when RSI oversold + BB %B near lower band, and enters short when
RSI overbought + BB %B near upper band.  Only trades when ADX < 25 (non-trending).
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


class RsiMeanReversion(Strategy):
    """Bidirectional mean-reversion strategy using RSI, Bollinger Bands, and ADX.

    Entry:
        Long  -- RSI < 30, BB %B < 0.05, ADX < 25
        Short -- RSI > 75, BB %B > 0.95, ADX < 25

    Exit:
        Long target  -- RSI > 50 OR pct_b > 0.50
        Short target -- RSI < 50 OR pct_b < 0.50
        Long stop    -- close <= entry - 2.0 * ATR
        Short stop   -- close >= entry + 2.5 * ATR
        Timeout      -- bars_since_entry >= 5
    """

    name = "rsi_mean_reversion"

    # Indicator parameters
    RSI_PERIOD = 14
    BB_PERIOD = 20
    BB_STD = 2.0
    ADX_PERIOD = 14
    ATR_PERIOD = 14

    # Entry thresholds
    RSI_OVERSOLD = 30.0
    RSI_OVERBOUGHT = 75.0
    BB_LONG_ENTRY_PCT_B = 0.05
    BB_SHORT_ENTRY_PCT_B = 0.95
    ADX_MAX = 25.0

    # Exit thresholds
    RSI_LONG_EXIT = 50.0
    RSI_SHORT_EXIT = 50.0
    BB_LONG_EXIT_PCT_B = 0.50
    BB_SHORT_EXIT_PCT_B = 0.50

    # Stop loss ATR multipliers
    LONG_STOP_ATR_MULT = 2.0
    SHORT_STOP_ATR_MULT = 2.5

    # Timeout
    MAX_BARS_IN_POSITION = 5

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="RSI", params={"period": self.RSI_PERIOD}),
            IndicatorSpec(
                name="BBANDS",
                params={"period": self.BB_PERIOD, "num_std": self.BB_STD},
            ),
            IndicatorSpec(name="ADX", params={"period": self.ADX_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": self.ATR_PERIOD}),
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
        bbands = ctx.indicators.get(f"BBANDS_{self.BB_PERIOD}")
        adx = ctx.indicators.get(f"ADX_{self.ADX_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{self.ATR_PERIOD}")

        if any(v is None for v in [rsi, bbands, adx, atr]):
            return None

        if not isinstance(bbands, dict):
            return None

        return {
            "rsi": rsi,
            "adx": adx,
            "atr": atr,
            "pct_b": bbands["pct_b"],
        }

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self, ctx: MarketContext, state: _PositionState, ind: dict
    ) -> Signal | None:
        rsi: float = ind["rsi"]
        pct_b: float = ind["pct_b"]
        adx: float = ind["adx"]
        atr: float = ind["atr"]

        # Regime filter: only trade in non-trending markets
        if adx >= self.ADX_MAX:
            return None

        # Long entry
        if rsi < self.RSI_OVERSOLD and pct_b < self.BB_LONG_ENTRY_PCT_B:
            strength = min(
                1.0,
                (self.RSI_OVERSOLD - rsi) / self.RSI_OVERSOLD
                + (self.BB_LONG_ENTRY_PCT_B - pct_b) / self.BB_LONG_ENTRY_PCT_B,
            )
            stop_loss = ctx.bar.close - self.LONG_STOP_ATR_MULT * atr

            state.in_position = True
            state.entry_price = ctx.bar.close
            state.entry_direction = "long"
            state.bars_since_entry = 0

            return Signal(
                strategy=self.name,
                symbol=ctx.symbol,
                direction="long",
                strength=strength,
                metadata={
                    "sub_strategy": "mr_long",
                    "stop_loss": stop_loss,
                },
            )

        # Short entry
        if rsi > self.RSI_OVERBOUGHT and pct_b > self.BB_SHORT_ENTRY_PCT_B:
            strength = min(
                1.0,
                (rsi - self.RSI_OVERBOUGHT) / (100.0 - self.RSI_OVERBOUGHT)
                + (pct_b - self.BB_SHORT_ENTRY_PCT_B)
                / (1.0 - self.BB_SHORT_ENTRY_PCT_B),
            )
            stop_loss = ctx.bar.close + self.SHORT_STOP_ATR_MULT * atr

            state.in_position = True
            state.entry_price = ctx.bar.close
            state.entry_direction = "short"
            state.bars_since_entry = 0

            return Signal(
                strategy=self.name,
                symbol=ctx.symbol,
                direction="short",
                strength=strength,
                metadata={
                    "sub_strategy": "mr_short",
                    "stop_loss": stop_loss,
                },
            )

        return None

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self, ctx: MarketContext, state: _PositionState, ind: dict
    ) -> Signal | None:
        rsi: float = ind["rsi"]
        pct_b: float = ind["pct_b"]
        atr: float = ind["atr"]
        close = ctx.bar.close

        exit_reason: str | None = None

        # Stop loss (checked first -- highest priority)
        if state.entry_direction == "long":
            if close <= state.entry_price - self.LONG_STOP_ATR_MULT * atr:
                exit_reason = "stop_loss"
        elif state.entry_direction == "short":
            if close >= state.entry_price + self.SHORT_STOP_ATR_MULT * atr:
                exit_reason = "stop_loss"

        # Target conditions
        if exit_reason is None:
            if state.entry_direction == "long":
                if rsi > self.RSI_LONG_EXIT or pct_b > self.BB_LONG_EXIT_PCT_B:
                    exit_reason = "target"
            elif state.entry_direction == "short":
                if rsi < self.RSI_SHORT_EXIT or pct_b < self.BB_SHORT_EXIT_PCT_B:
                    exit_reason = "target"

        # Timeout
        if exit_reason is None:
            if state.bars_since_entry >= self.MAX_BARS_IN_POSITION:
                exit_reason = "timeout"

        if exit_reason is None:
            return None

        state.in_position = False

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="close",
            strength=1.0,
            metadata={
                "exit_reason": exit_reason,
            },
        )
