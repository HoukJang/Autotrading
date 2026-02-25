"""Regime-aware momentum strategy for TREND regime with volatility filter."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from autotrader.core.types import MarketContext, Signal
from autotrader.indicators.base import IndicatorSpec
from autotrader.strategy.base import Strategy


@dataclass
class _SymbolState:
    """Internal per-symbol state for the RegimeMomentum strategy."""

    bb_width_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=20)
    )
    in_position: bool = False
    entry_price: float = 0.0
    bars_since_entry: int = 0
    highest_since_entry: float = 0.0
    current_regime: str = "UNCERTAIN"


class RegimeMomentum(Strategy):
    """Adaptive momentum strategy that enters long during TREND regime.

    Entry requires:
    - TREND regime (ADX >= 25 AND expanding Bollinger Band width)
    - Positive 20-bar momentum
    - RSI between 50 and 70 (healthy, not overheated)
    - Bullish EMA alignment (EMA_8 > EMA_21)
    - Volatility filter (ATR/close < 3%)

    Exit triggers:
    - Regime change away from TREND
    - RSI > 75 (overheated target)
    - Trailing stop (close <= highest - 2.0*ATR)
    - Stop loss (close <= entry - 1.5*ATR)
    - Timeout (10 bars)
    """

    name = "regime_momentum"

    # Indicator parameters
    ADX_PERIOD = 14
    BB_PERIOD = 20
    BB_STD = 2.0
    EMA_FAST_PERIOD = 8
    EMA_SLOW_PERIOD = 21
    RSI_PERIOD = 14
    ATR_PERIOD = 14

    # Regime thresholds
    ADX_TREND_THRESHOLD = 25.0
    ADX_RANGING_THRESHOLD = 20.0
    BB_WIDTH_EXPANDING = 1.3
    BB_WIDTH_CONTRACTING = 0.8
    MIN_BB_WIDTH_BARS = 5

    # Entry thresholds
    RSI_ENTRY_MIN = 50.0
    RSI_ENTRY_MAX = 70.0
    VOLATILITY_MAX = 0.03
    MIN_HISTORY_BARS = 21  # need at least 21 bars (20 ago + current)
    MOMENTUM_LOOKBACK = 20

    # Exit thresholds
    RSI_EXIT = 75.0
    TRAILING_STOP_ATR_MULT = 2.0
    STOP_LOSS_ATR_MULT = 1.5
    TIMEOUT_BARS = 10

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="ADX", params={"period": self.ADX_PERIOD}),
            IndicatorSpec(
                name="BBANDS",
                params={"period": self.BB_PERIOD, "num_std": self.BB_STD},
            ),
            IndicatorSpec(name="EMA", params={"period": self.EMA_FAST_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_SLOW_PERIOD}),
            IndicatorSpec(name="RSI", params={"period": self.RSI_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": self.ATR_PERIOD}),
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

        # Update BB width history and regime
        self._update_regime(state, indicators)

        if state.in_position:
            state.bars_since_entry += 1
            state.highest_since_entry = max(
                state.highest_since_entry, ctx.bar.high
            )
            return self._check_exit(ctx, state, indicators)

        return self._check_entry(ctx, state, indicators)

    # ------------------------------------------------------------------
    # Indicator extraction
    # ------------------------------------------------------------------

    def _extract_indicators(self, ctx: MarketContext) -> dict | None:
        """Extract and validate all required indicators from context."""
        adx = ctx.indicators.get(f"ADX_{self.ADX_PERIOD}")
        bbands = ctx.indicators.get(f"BBANDS_{self.BB_PERIOD}")
        ema_fast = ctx.indicators.get(f"EMA_{self.EMA_FAST_PERIOD}")
        ema_slow = ctx.indicators.get(f"EMA_{self.EMA_SLOW_PERIOD}")
        rsi = ctx.indicators.get(f"RSI_{self.RSI_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{self.ATR_PERIOD}")

        if any(v is None for v in [adx, bbands, ema_fast, ema_slow, rsi, atr]):
            return None

        if not isinstance(bbands, dict):
            return None

        return {
            "adx": adx,
            "bb_width": bbands["width"],
            "bb_pct_b": bbands["pct_b"],
            "ema_fast": ema_fast,
            "ema_slow": ema_slow,
            "rsi": rsi,
            "atr": atr,
        }

    # ------------------------------------------------------------------
    # Regime detection
    # ------------------------------------------------------------------

    def _update_regime(self, state: _SymbolState, indicators: dict) -> None:
        """Classify the current market regime based on ADX and BB width."""
        adx: float = indicators["adx"]
        bb_width: float = indicators["bb_width"]

        state.bb_width_history.append(bb_width)

        if len(state.bb_width_history) < self.MIN_BB_WIDTH_BARS:
            state.current_regime = "UNCERTAIN"
            return

        avg_width = sum(state.bb_width_history) / len(state.bb_width_history)
        if avg_width > 0:
            ratio = bb_width / avg_width
        else:
            ratio = 1.0

        if adx >= self.ADX_TREND_THRESHOLD and ratio >= self.BB_WIDTH_EXPANDING:
            state.current_regime = "TREND"
        elif adx < self.ADX_RANGING_THRESHOLD and ratio <= self.BB_WIDTH_CONTRACTING:
            state.current_regime = "RANGING"
        else:
            state.current_regime = "UNCERTAIN"

    # ------------------------------------------------------------------
    # 20-bar return
    # ------------------------------------------------------------------

    def _calc_return_20(self, ctx: MarketContext) -> float | None:
        """Calculate 20-bar return from history. Returns None if insufficient data."""
        if len(ctx.history) < self.MIN_HISTORY_BARS:
            return None

        close_20_ago = ctx.history[-(self.MOMENTUM_LOOKBACK + 1)].close
        current_close = ctx.bar.close

        if close_20_ago == 0:
            return None

        return (current_close - close_20_ago) / close_20_ago

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        ctx: MarketContext,
        state: _SymbolState,
        indicators: dict,
    ) -> Signal | None:
        """Check all entry conditions for a long position."""
        # Regime must be TREND
        if state.current_regime != "TREND":
            return None

        # Need enough BB width history
        if len(state.bb_width_history) < self.MIN_BB_WIDTH_BARS:
            return None

        # 20-bar return must be positive
        return_20 = self._calc_return_20(ctx)
        if return_20 is None or return_20 <= 0:
            return None

        rsi: float = indicators["rsi"]
        ema_fast: float = indicators["ema_fast"]
        ema_slow: float = indicators["ema_slow"]
        atr: float = indicators["atr"]
        adx: float = indicators["adx"]
        close = ctx.bar.close

        # RSI between 50 and 70
        if not (self.RSI_ENTRY_MIN <= rsi <= self.RSI_ENTRY_MAX):
            return None

        # EMA bullish alignment
        if ema_fast <= ema_slow:
            return None

        # Volatility filter
        if close == 0:
            return None
        atr_ratio = atr / close
        if atr_ratio >= self.VOLATILITY_MAX:
            return None

        # Strength calculation
        strength = min(1.0, return_20 * 10 + (adx - 25) / 25)
        strength = max(0.0, strength)

        # Calculate stop loss
        stop_loss = close - self.STOP_LOSS_ATR_MULT * atr

        # Update state
        state.in_position = True
        state.entry_price = close
        state.bars_since_entry = 0
        state.highest_since_entry = ctx.bar.high

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="long",
            strength=strength,
            metadata={
                "sub_strategy": "regime_momentum",
                "stop_loss": stop_loss,
                "regime": state.current_regime,
                "adx": adx,
                "rsi": rsi,
                "atr": atr,
                "return_20": return_20,
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
        """Check all exit conditions for an open position."""
        close = ctx.bar.close
        atr: float = indicators["atr"]
        rsi: float = indicators["rsi"]

        reason: str | None = None

        # Priority order of exit checks:
        # 1. Stop loss
        if close <= state.entry_price - self.STOP_LOSS_ATR_MULT * atr:
            reason = "stop_loss"
        # 2. Trailing stop
        elif close <= state.highest_since_entry - self.TRAILING_STOP_ATR_MULT * atr:
            reason = "trailing_stop"
        # 3. RSI target
        elif rsi > self.RSI_EXIT:
            reason = "target"
        # 4. Regime change
        elif state.current_regime != "TREND":
            reason = "regime_change"
        # 5. Timeout
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
            metadata={
                "reason": reason,
                "bars_held": state.bars_since_entry,
                "entry_price": state.entry_price,
                "exit_price": close,
            },
        )
