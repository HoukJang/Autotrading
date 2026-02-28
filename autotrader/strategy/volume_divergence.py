"""Volume-Price Divergence strategy: fading selling exhaustion.

Enters long when price has declined over the past 5 days but volume
has also declined, indicating that selling pressure is drying up.
Requires the stock to remain above its long-term EMA(50) and RSI < 45.

Entry:
    Long -- close < close[5] (5-day price decline)
          + avg volume (last 3 bars) < avg volume (bars 6-8 ago)
          + RSI < 45
          + close > EMA(50)

Exit (strategy-level):
    Volume spike -- volume > 1.5x * SMA(volume, 20) AND positive close
    (SL and time exits handled by ExitRuleEngine)

Direction: Long only.
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
    bars_since_entry: int = 0


class VolumeDivergence(Strategy):
    """Long-only strategy based on volume-price divergence.

    Concept: When price declines but volume also declines, the selling
    pressure is exhausting.  We enter expecting a reversal, and exit
    when a volume spike with a positive close confirms the reversal
    is underway.
    """

    name = "volume_divergence"

    # Indicator parameters
    RSI_PERIOD = 14
    ATR_PERIOD = 14
    EMA_PERIOD = 50

    # Entry thresholds
    PRICE_LOOKBACK = 5      # days of price decline
    VOL_RECENT_BARS = 3     # recent volume window
    VOL_PRIOR_BARS = 3      # prior volume window (starts after recent)
    RSI_MAX = 45.0

    # Exit thresholds
    VOL_SPIKE_MULT = 1.5    # 1.5x average volume = spike
    VOL_AVG_PERIOD = 20     # volume SMA period for spike detection

    def __init__(self) -> None:
        self.required_indicators = [
            IndicatorSpec(name="RSI", params={"period": self.RSI_PERIOD}),
            IndicatorSpec(name="ATR", params={"period": self.ATR_PERIOD}),
            IndicatorSpec(name="EMA", params={"period": self.EMA_PERIOD}),
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
        atr = ctx.indicators.get(f"ATR_{self.ATR_PERIOD}")
        ema_50 = ctx.indicators.get(f"EMA_{self.EMA_PERIOD}")

        if any(v is None for v in [rsi, atr, ema_50]):
            return None

        return {
            "rsi": rsi,
            "atr": atr,
            "ema_50": ema_50,
        }

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self, ctx: MarketContext, state: _PositionState, ind: dict,
    ) -> Signal | None:
        rsi: float = ind["rsi"]
        atr: float = ind["atr"]
        ema_50: float = ind["ema_50"]
        close = ctx.bar.close
        history = list(ctx.history)

        # Need enough history for volume comparison
        if len(history) < self.PRICE_LOOKBACK + self.VOL_RECENT_BARS + self.VOL_PRIOR_BARS:
            return None

        # Trend filter: above long-term EMA
        if close <= ema_50:
            return None

        # RSI filter
        if rsi >= self.RSI_MAX:
            return None

        # Price decline check: current close < close N days ago
        past_close = history[-(self.PRICE_LOOKBACK + 1)].close
        if close >= past_close:
            return None

        # Volume divergence check: recent avg volume < prior avg volume
        recent_vols = [
            b.volume for b in history[-self.VOL_RECENT_BARS:]
            if b.volume is not None and b.volume > 0
        ]
        prior_start = -(self.VOL_RECENT_BARS + self.VOL_PRIOR_BARS)
        prior_end = -self.VOL_RECENT_BARS
        prior_vols = [
            b.volume for b in history[prior_start:prior_end]
            if b.volume is not None and b.volume > 0
        ]

        if not recent_vols or not prior_vols:
            return None

        avg_recent = sum(recent_vols) / len(recent_vols)
        avg_prior = sum(prior_vols) / len(prior_vols)

        if avg_recent >= avg_prior:
            return None

        # Signal strength: bigger volume divergence + lower RSI = stronger
        vol_ratio = 1.0 - (avg_recent / avg_prior) if avg_prior > 0 else 0.0
        strength = min(
            1.0,
            vol_ratio * 0.5 + (self.RSI_MAX - rsi) / self.RSI_MAX * 0.5,
        )

        stop_loss = close - 1.5 * atr

        state.in_position = True
        state.entry_price = close
        state.bars_since_entry = 0

        return Signal(
            strategy=self.name,
            symbol=ctx.symbol,
            direction="long",
            strength=strength,
            metadata={
                "sub_strategy": "vol_div_long",
                "stop_loss": stop_loss,
                "vol_ratio": round(vol_ratio, 3),
            },
        )

    # ------------------------------------------------------------------
    # Exit logic
    # ------------------------------------------------------------------

    def _check_exit(
        self, ctx: MarketContext, state: _PositionState, ind: dict,
    ) -> Signal | None:
        close = ctx.bar.close
        history = list(ctx.history)

        exit_reason: str | None = None

        # Volume spike with positive close: reversal confirmed, take profit
        if len(history) >= self.VOL_AVG_PERIOD:
            volumes = [
                b.volume for b in history[-self.VOL_AVG_PERIOD:]
                if b.volume is not None and b.volume > 0
            ]
            if volumes:
                avg_vol = sum(volumes) / len(volumes)
                current_vol = ctx.bar.volume
                if (
                    current_vol is not None
                    and current_vol > self.VOL_SPIKE_MULT * avg_vol
                    and ctx.bar.close > ctx.bar.open  # positive/green candle
                ):
                    exit_reason = "volume_spike_tp"

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
