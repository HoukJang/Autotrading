"""Breakout Momentum strategy: buying 15-day high breakouts with trend confirmation.

Enters long when price closes above the 15-day highest high with strong
momentum (ADX > 28), price above EMA(21), RSI in the 50-80 zone, and
above-average volume participation.  Designed to capture sustained trends
where mean-reversion strategies underperform.

Entry:
    Long -- close > highest high of last 15 bars
          + ADX > 28 (strong trend)
          + close > EMA(21) (uptrend structure)
          + 50 < RSI < 80 (momentum, not overbought)
          + volume > 1.2x SMA(volume, 20) (participation)

Exit (strategy-level):
    Trend loss -- close < EMA(21) for 2 consecutive bars
    (SL and time exits handled by ExitRuleEngine)

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

BREAKOUT_LOOKBACK = 15       # days for highest high (from 10)
ADX_MIN = 28.0               # minimum ADX for entry (from 25.0)
EMA_PERIOD = 21
RSI_PERIOD = 14
ADX_PERIOD = 14
ATR_PERIOD = 14
RSI_MIN = 50.0
RSI_MAX = 80.0
VOL_RATIO_MIN = 1.2          # minimum volume / SMA(20) ratio
VOL_AVG_PERIOD = 20
STOP_ATR_MULT = 2.0          # stop-loss at 2x ATR below close

# Exit: consecutive closes below EMA to trigger trend-loss exit
TREND_LOSS_BARS = 2


@dataclass
class _PositionState:
    """Per-symbol internal state for position tracking."""

    in_position: bool = False
    entry_price: float = 0.0
    bars_since_entry: int = 0
    consecutive_below_ema: int = 0


class BreakoutMomentum(Strategy):
    """Long-only breakout strategy targeting sustained uptrends.

    Concept: Stocks breaking to new 15-day highs with confirmed momentum
    (ADX > 28) and volume participation tend to continue trending.  We
    enter at the next open and exit when the trend structure breaks
    (consecutive closes below EMA-21).
    """

    name = "breakout_momentum"

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="RSI", params={"period": RSI_PERIOD}),
            IndicatorSpec(name="ADX", params={"period": ADX_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": ATR_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": EMA_PERIOD}),
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
        rsi = ctx.indicators.get(f"RSI_{RSI_PERIOD}")
        adx = ctx.indicators.get(f"ADX_{ADX_PERIOD}")
        atr = ctx.indicators.get(f"ATR_{ATR_PERIOD}")
        ema_21 = ctx.indicators.get(f"EMA_{EMA_PERIOD}")

        if any(v is None for v in [rsi, adx, atr, ema_21]):
            return None

        return {
            "rsi": rsi,
            "adx": adx,
            "atr": atr,
            "ema_21": ema_21,
        }

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self, ctx: MarketContext, state: _PositionState, ind: dict,
    ) -> Signal | None:
        rsi: float = ind["rsi"]
        adx: float = ind["adx"]
        atr: float = ind["atr"]
        ema_21: float = ind["ema_21"]
        close = ctx.bar.close

        # Need enough history for breakout lookback and volume average.
        # Exclude the last bar (current bar) -- it is the breakout candidate,
        # not part of the reference window.  Both batch_simulator and the live
        # pipeline append the current bar to history before calling strategies.
        prior_bars = list(ctx.history)[:-1]
        min_history = max(BREAKOUT_LOOKBACK, VOL_AVG_PERIOD)
        if len(prior_bars) < min_history:
            return None

        # 1. ADX filter: trend must be strong
        if adx < ADX_MIN:
            return None

        # 2. Trend structure: price above EMA(21)
        if close <= ema_21:
            return None

        # 3. RSI filter: momentum zone (not overbought)
        if rsi < RSI_MIN or rsi > RSI_MAX:
            return None

        # 4. Breakout check: close above 15-day highest high
        highest_high = self._highest_high(prior_bars, BREAKOUT_LOOKBACK)
        if highest_high is None or close <= highest_high:
            return None

        # 5. Volume confirmation: current volume > 1.2x 20-day average
        vol_ratio = self._volume_ratio(ctx, prior_bars, VOL_AVG_PERIOD)
        if vol_ratio is None or vol_ratio < VOL_RATIO_MIN:
            return None

        # Signal strength: ADX contribution + volume ratio contribution
        # ADX: scale from 28-78 range to 0-0.5 contribution
        adx_score = min(0.5, (adx - ADX_MIN) / 50.0)
        # Volume: scale excess ratio to 0-0.5 contribution
        vol_score = min(0.5, (vol_ratio - 1.0) * 0.5)
        strength = min(1.0, adx_score + vol_score)

        stop_loss = close - STOP_ATR_MULT * atr

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
                "sub_strategy": "breakout_momentum_long",
                "stop_loss": stop_loss,
                "entry_atr": round(atr, 4),
                "adx": round(adx, 2),
                "rsi": round(rsi, 2),
                "volume_ratio": round(vol_ratio, 3),
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

        # Track consecutive closes below EMA(21) for trend-loss detection
        if close < ema_21:
            state.consecutive_below_ema += 1
        else:
            state.consecutive_below_ema = 0

        # Trend loss: 2 consecutive closes below EMA(21)
        if state.consecutive_below_ema >= TREND_LOSS_BARS:
            state.in_position = False
            state.consecutive_below_ema = 0
            return Signal(
                strategy=self.name,
                symbol=ctx.symbol,
                direction="close",
                strength=1.0,
                metadata={"exit_reason": "trend_loss"},
            )

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _highest_high(history: list, lookback: int) -> float | None:
        """Return the highest high over the last *lookback* bars in history.

        Only considers bars already in history (excludes the current bar,
        which is evaluated as the breakout candidate).
        """
        if len(history) < lookback:
            return None
        return max(b.high for b in history[-lookback:])

    @staticmethod
    def _volume_ratio(ctx: MarketContext, history: list, period: int) -> float | None:
        """Return current bar volume divided by the *period*-bar average volume.

        Returns ``None`` when volume data is unavailable or the average is
        zero (illiquid stock).
        """
        current_vol = ctx.bar.volume
        if current_vol is None or current_vol <= 0:
            return None

        if len(history) < period:
            return None

        volumes = [
            b.volume for b in history[-period:]
            if b.volume is not None and b.volume > 0
        ]
        if not volumes:
            return None

        avg_vol = sum(volumes) / len(volumes)
        if avg_vol <= 0:
            return None

        return current_vol / avg_vol


# ---------------------------------------------------------------------------
# Self-registration: declare strategy constants in the metadata registry
# ---------------------------------------------------------------------------

from autotrader.strategy.registry import StrategyMetaRegistry, StrategyMeta  # noqa: E402

StrategyMetaRegistry.register(
    BreakoutMomentum,
    StrategyMeta(
        name="breakout_momentum",
        display_name="Breakout Momentum",
        max_positions=2,
        soft_cap=2,
        base_risk=0.020,
        sl_atr_mult={"long": 2.5},
        tp_atr_mult=4.0,
        max_hold_days=15,
        gdr_thresholds=(0.04, 0.08),
        entry_group="A",
    ),
)
