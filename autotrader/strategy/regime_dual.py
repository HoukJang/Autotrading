"""Regime-aware dual strategy combining trend-following and mean-reversion."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy


@dataclass
class _SymbolState:
    regime: str = "UNCERTAIN"
    regime_score: float = 0.0
    prev_regime: str = "UNCERTAIN"
    regime_bars: int = 0
    bb_width_history: deque = field(default_factory=lambda: deque(maxlen=20))
    prev_ema_fast: float | None = None
    prev_ema_slow: float | None = None
    in_position: bool = False
    entry_price: float = 0.0
    entry_regime: str = "UNCERTAIN"
    bars_since_entry: int = 0
    highest_since_entry: float = 0.0
    prev_rsi: float | None = None


class RegimeDualStrategy(Strategy):
    name = "regime_dual"

    EMA_FAST_PERIOD = 8
    EMA_SLOW_PERIOD = 21

    ADX_PERIOD = 14
    RSI_PERIOD = 14
    ATR_PERIOD = 14
    BB_PERIOD = 20
    BB_STD = 2.0

    ADX_STRONG_TREND = 30.0
    ADX_MODERATE_TREND = 25.0
    ADX_NO_TREND = 20.0
    BB_WIDTH_EXPANDING = 1.3
    BB_WIDTH_CONTRACTING = 0.8
    REGIME_TREND_THRESHOLD = 1.0
    REGIME_MR_THRESHOLD = -1.0
    MIN_REGIME_BARS = 2

    TREND_RSI_LONG_MIN = 45.0
    TREND_RSI_LONG_MAX = 75.0
    TREND_PROFIT_ATR_MULT = 2.5
    TREND_STOP_ATR_MULT = 1.5
    TREND_TRAILING_ATR_MULT = 2.0
    TREND_MAX_BARS = 60

    MR_BB_ENTRY_PCT_B = 0.05
    MR_BB_EXIT_PCT_B = 0.50
    MR_RSI_OVERSOLD = 30.0
    MR_RSI_NEUTRAL = 50.0
    MR_PROFIT_ATR_MULT = 1.5
    MR_STOP_ATR_MULT = 2.0
    MR_MAX_BARS = 30

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="EMA", params={"period": self.EMA_FAST_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_SLOW_PERIOD}),
            IndicatorSpec(name="ADX", params={"period": self.ADX_PERIOD}),
            IndicatorSpec(name="RSI", params={"period": self.RSI_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": self.ATR_PERIOD}),
            IndicatorSpec(
                name="BBANDS",
                params={"period": self.BB_PERIOD, "num_std": self.BB_STD},
            ),
        ]
        self._states: dict[str, _SymbolState] = {}

    def on_context(self, ctx: MarketContext) -> Signal | None:
        indicators = self._extract_indicators(ctx)
        if indicators is None:
            return None

        symbol = ctx.symbol
        if symbol not in self._states:
            self._states[symbol] = _SymbolState()
        state = self._states[symbol]

        self._update_regime(state, indicators)

        signal: Signal | None = None

        if state.in_position:
            state.bars_since_entry += 1
            state.highest_since_entry = max(
                state.highest_since_entry, ctx.bar.high
            )
            signal = self._check_exit(ctx, state, indicators)
        elif state.regime_bars >= self.MIN_REGIME_BARS:
            signal = self._check_entry(ctx, state, indicators)

        state.prev_ema_fast = indicators["ema_fast"]
        state.prev_ema_slow = indicators["ema_slow"]
        state.prev_rsi = indicators["rsi"]

        return signal

    def _extract_indicators(self, ctx: MarketContext) -> dict | None:
        ema_fast = ctx.indicators.get(f"EMA_{self.EMA_FAST_PERIOD}")
        ema_slow = ctx.indicators.get(f"EMA_{self.EMA_SLOW_PERIOD}")
        adx = ctx.indicators.get(f"ADX_{self.ADX_PERIOD}")
        rsi = ctx.indicators.get(f"RSI_{self.RSI_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{self.ATR_PERIOD}")
        bbands = ctx.indicators.get(f"BBANDS_{self.BB_PERIOD}")

        if any(v is None for v in [ema_fast, ema_slow, adx, rsi, atr, bbands]):
            return None

        if not isinstance(bbands, dict):
            return None

        return {
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "adx": adx,
            "rsi": rsi,
            "atr": atr,
            "bb_upper": bbands["upper"],
            "bb_middle": bbands["middle"],
            "bb_lower": bbands["lower"],
            "bb_width": bbands["width"],
            "bb_pct_b": bbands["pct_b"],
        }

    def _update_regime(self, state: _SymbolState, indicators: dict) -> None:
        adx = indicators["adx"]
        bb_width = indicators["bb_width"]

        if adx >= self.ADX_STRONG_TREND:
            adx_score = 1.0
        elif adx >= self.ADX_MODERATE_TREND:
            adx_score = 0.5
        elif adx < self.ADX_NO_TREND:
            adx_score = -1.0
        else:
            adx_score = 0.0

        state.bb_width_history.append(bb_width)

        if len(state.bb_width_history) >= 5:
            avg_width = sum(state.bb_width_history) / len(state.bb_width_history)
            if avg_width > 0:
                ratio = bb_width / avg_width
            else:
                ratio = 1.0

            if ratio > self.BB_WIDTH_EXPANDING:
                bbw_score = 0.5
            elif ratio < self.BB_WIDTH_CONTRACTING:
                bbw_score = -0.5
            else:
                bbw_score = 0.0
        else:
            bbw_score = 0.0

        regime_score = adx_score + bbw_score
        state.regime_score = regime_score

        if regime_score >= self.REGIME_TREND_THRESHOLD:
            new_regime = "TREND"
        elif regime_score <= self.REGIME_MR_THRESHOLD:
            new_regime = "MEAN_REVERSION"
        else:
            new_regime = "UNCERTAIN"

        if new_regime != state.regime:
            state.prev_regime = state.regime
            state.regime = new_regime
            state.regime_bars = 1
        else:
            state.regime_bars += 1

    def _check_entry(
        self, ctx: MarketContext, state: _SymbolState, indicators: dict
    ) -> Signal | None:
        if state.regime == "TREND":
            return self._check_trend_entry(ctx, state, indicators)
        if state.regime == "MEAN_REVERSION":
            return self._check_mr_entry(ctx, state, indicators)
        return None

    def _check_trend_entry(
        self, ctx: MarketContext, state: _SymbolState, indicators: dict
    ) -> Signal | None:
        if state.prev_ema_fast is None or state.prev_ema_slow is None:
            return None

        ema_fast = indicators["ema_fast"]
        ema_slow = indicators["ema_slow"]
        rsi = indicators["rsi"]
        adx = indicators["adx"]
        atr = indicators["atr"]

        crossed = (
            state.prev_ema_fast <= state.prev_ema_slow and ema_fast > ema_slow
        )
        if not crossed:
            return None

        if not (self.TREND_RSI_LONG_MIN <= rsi <= self.TREND_RSI_LONG_MAX):
            return None

        if ctx.bar.close <= ema_slow:
            return None

        adx_component = min(adx / 50.0, 1.0)
        spread_component = min((ema_fast - ema_slow) / ema_slow * 100, 1.0)
        rsi_component = max(0.0, 1.0 - abs(rsi - 60) / 30)
        strength = 0.4 * adx_component + 0.3 * spread_component + 0.3 * rsi_component

        stop_loss = ctx.bar.close - self.TREND_STOP_ATR_MULT * atr
        take_profit = ctx.bar.close + self.TREND_PROFIT_ATR_MULT * atr

        state.in_position = True
        state.entry_price = ctx.bar.close
        state.entry_regime = state.regime
        state.bars_since_entry = 0
        state.highest_since_entry = ctx.bar.high

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="long",
            strength=strength,
            metadata={
                "sub_strategy": "trend_following",
                "regime": state.regime,
                "regime_score": state.regime_score,
                "adx": adx,
                "rsi": rsi,
                "atr": atr,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            },
        )

    def _check_mr_entry(
        self, ctx: MarketContext, state: _SymbolState, indicators: dict
    ) -> Signal | None:
        bb_pct_b = indicators["bb_pct_b"]
        rsi = indicators["rsi"]
        adx = indicators["adx"]
        atr = indicators["atr"]

        if bb_pct_b >= self.MR_BB_ENTRY_PCT_B:
            return None

        if rsi >= self.MR_RSI_OVERSOLD:
            return None

        if state.prev_rsi is not None and (state.prev_rsi - rsi) >= 5.0:
            return None

        rsi_component = (30.0 - rsi) / 30.0
        bb_component = min(1.0, (0.05 - bb_pct_b) / 0.05)
        adx_component = max(0.0, 1.0 - adx / 30.0)
        strength = 0.4 * rsi_component + 0.4 * bb_component + 0.2 * adx_component

        stop_loss = ctx.bar.close - self.MR_STOP_ATR_MULT * atr
        take_profit = indicators["bb_middle"]

        state.in_position = True
        state.entry_price = ctx.bar.close
        state.entry_regime = state.regime
        state.bars_since_entry = 0
        state.highest_since_entry = ctx.bar.high

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="long",
            strength=strength,
            metadata={
                "sub_strategy": "mean_reversion",
                "regime": state.regime,
                "regime_score": state.regime_score,
                "bb_pct_b": bb_pct_b,
                "rsi": rsi,
                "atr": atr,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            },
        )

    def _check_exit(
        self, ctx: MarketContext, state: _SymbolState, indicators: dict
    ) -> Signal | None:
        price = ctx.bar.close
        atr = indicators["atr"]
        pnl_pct = (price - state.entry_price) / state.entry_price if state.entry_price else 0.0

        is_trend_entry = state.entry_regime == "TREND"
        max_bars = self.TREND_MAX_BARS if is_trend_entry else self.MR_MAX_BARS
        stop_mult = self.TREND_STOP_ATR_MULT if is_trend_entry else self.MR_STOP_ATR_MULT
        profit_mult = self.TREND_PROFIT_ATR_MULT if is_trend_entry else self.MR_PROFIT_ATR_MULT

        exit_reason: str | None = None

        if state.bars_since_entry >= max_bars:
            exit_reason = "max_bars"
        elif price <= state.entry_price - stop_mult * atr:
            exit_reason = "stop_loss"
        elif price >= state.entry_price + profit_mult * atr:
            exit_reason = "take_profit"
        elif is_trend_entry and state.bars_since_entry > 3:
            if price <= state.highest_since_entry - self.TREND_TRAILING_ATR_MULT * atr:
                exit_reason = "trailing_stop"
        if exit_reason is None and not is_trend_entry:
            bb_pct_b = indicators["bb_pct_b"]
            rsi = indicators["rsi"]
            if bb_pct_b >= self.MR_BB_EXIT_PCT_B or rsi >= self.MR_RSI_NEUTRAL:
                exit_reason = "mr_target"

        if exit_reason is None:
            if state.regime == "UNCERTAIN" and state.regime_bars >= 3:
                exit_reason = "regime_uncertain"

        if exit_reason is None:
            return None

        strength = max(0.1, min(1.0, 0.5 + pnl_pct * 10))

        state.in_position = False

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="close",
            strength=strength,
            metadata={
                "exit_reason": exit_reason,
                "bars_held": state.bars_since_entry,
                "entry_price": state.entry_price,
                "exit_price": price,
                "pnl_pct": pnl_pct,
            },
        )
