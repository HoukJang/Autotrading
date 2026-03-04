"""HistoryManager: historical data loading and regime initialisation.

Extracted from AutoTrader.main to decompose the god class.
Owns the responsibilities of loading historical bars, warming up
indicator history, refreshing daily bars, and initialising the market
regime from daily bar data.

Shared mutable state (daily_bar_history, bar_history) is passed by
reference from AutoTrader.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from autotrader.core.config import Settings
from autotrader.core.types import Bar
from autotrader.indicators.engine import IndicatorEngine
from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector
from autotrader.portfolio.regime_tracker import RegimeTracker

logger = logging.getLogger("autotrader.orchestration.history_manager")


class HistoryManager:
    """Manages historical bar data loading and regime initialisation.

    Extracted from AutoTrader to isolate data-fetching and warmup logic
    from the main orchestrator. Operates on shared mutable dicts so that
    updates are visible to AutoTrader and other components.

    Args:
        broker: BrokerAdapter with get_historical_bars support.
        daily_bar_history: Shared dict[symbol -> deque[Bar]] for daily bars.
        bar_history: Shared dict[symbol -> deque[Bar]] for all bars.
        settings: Application settings.
        indicator_engine: IndicatorEngine for computing indicators.
        regime_detector: RegimeDetector for classification.
        regime_tracker: RegimeTracker for regime state management.
        set_regime: Callable to update the current regime on AutoTrader.
    """

    def __init__(
        self,
        broker: Any,
        daily_bar_history: dict[str, deque[Bar]],
        bar_history: dict[str, deque[Bar]],
        settings: Settings,
        indicator_engine: IndicatorEngine,
        regime_detector: RegimeDetector,
        regime_tracker: RegimeTracker,
        set_regime: Any,
    ) -> None:
        self._broker = broker
        self._daily_bar_history = daily_bar_history
        self._bar_history = bar_history
        self._settings = settings
        self._indicator_engine = indicator_engine
        self._regime_detector = regime_detector
        self._regime_tracker = regime_tracker
        self._set_regime = set_regime

    @property
    def _regime_proxy_symbol(self) -> str:
        return self._settings.scheduler.regime_proxy_symbol

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def warm_up_from_history(self) -> None:
        """Load historical daily bars for regime and indicator warmup."""
        if not hasattr(self._broker, "get_historical_bars"):
            logger.info("Broker does not support historical bars; skipping warmup")
            return

        # Fetch full S&P 500 universe for warmup
        try:
            from autotrader.universe.provider import SP500Provider
            provider = SP500Provider()
            infos = await asyncio.to_thread(provider.fetch)
            all_symbols = [i.symbol for i in infos]
            logger.info("Fetched %d S&P 500 symbols for warmup", len(all_symbols))
        except Exception:
            logger.warning("Failed to fetch S&P 500 list; falling back to config symbols")
            all_symbols = list(self._settings.symbols)

        proxy = self._regime_proxy_symbol
        symbols = list(set(all_symbols + [proxy]))
        logger.info("Loading historical daily bars for %d symbols...", len(symbols))

        try:
            hist = await self._broker.get_historical_bars(
                symbols, days=self._settings.scheduler.universe_history_days,
            )
        except Exception:
            logger.exception("Failed to load historical bars")
            return

        for sym, bars in hist.items():
            for bar in bars:
                self._daily_bar_history[sym].append(bar)
                self._bar_history[sym].append(bar)

        loaded_count = {s: len(b) for s, b in hist.items() if b}
        logger.info("Loaded daily bars for %d symbols (total bars: %d)",
                    len(loaded_count), sum(loaded_count.values()))
        self.initialize_regime_from_daily()

    async def refresh_daily_bars(self) -> None:
        """Fetch latest daily bars for the full S&P 500 universe via REST API.

        Called at 9:00 AM ET (pre-market) and before nightly scan (8:00 PM ET).
        Updates _daily_bar_history and _bar_history with any new bars,
        then refreshes regime classification.
        """
        if not hasattr(self._broker, "get_historical_bars"):
            logger.info("Broker does not support historical bars; skipping daily refresh")
            return

        symbols = list(set(self._settings.symbols + [self._regime_proxy_symbol]))
        logger.info("Refreshing daily bars for %d symbols via REST API...", len(symbols))

        try:
            hist = await self._broker.get_historical_bars(symbols, days=5)
        except Exception:
            logger.exception("Daily bar refresh failed")
            return

        new_bar_count = 0
        for sym, bars in hist.items():
            if not bars:
                continue
            existing_ts = {b.timestamp for b in self._daily_bar_history[sym]}
            for bar in bars:
                if bar.timestamp not in existing_ts:
                    self._daily_bar_history[sym].append(bar)
                    self._bar_history[sym].append(bar)
                    new_bar_count += 1

        if new_bar_count > 0:
            self.initialize_regime_from_daily()
            logger.info("Daily bar refresh complete: %d new bars added", new_bar_count)
        else:
            logger.info("Daily bar refresh: no new bars (already up to date)")

    def initialize_regime_from_daily(self) -> None:
        """Walk SPY daily bars to classify regime using SPY-based 5-regime system."""
        proxy = self._regime_proxy_symbol
        spy_history = self._daily_bar_history.get(proxy)
        if not spy_history or len(spy_history) < 50:
            logger.warning(
                "Insufficient %s daily bars for regime init (%d bars)",
                proxy, len(spy_history) if spy_history else 0,
            )
            return

        indicators = self._indicator_engine.compute(list(spy_history))
        adx = indicators.get("ADX_14")
        ema_50 = indicators.get("EMA_50")
        bbands = indicators.get("BBANDS_20")

        if any(v is None for v in [adx, ema_50, bbands]):
            logger.warning("Indicators still None after warmup")
            return

        close = list(spy_history)[-1].close
        bb_upper = bbands.get("upper", 0)
        bb_lower = bbands.get("lower", 0)
        bb_middle = bbands.get("middle", 1.0)
        if bb_middle <= 0:
            bb_middle = 1.0
        bb_ratio = (bb_upper - bb_lower) / bb_middle

        regime = self._regime_detector.update(
            adx=adx, close=close, ema_50=ema_50, bb_ratio=bb_ratio,
        )
        self._set_regime(regime)
        self._regime_tracker._confirmed_regime = regime
        logger.info(
            "Regime initialised: %s (ADX=%.1f, BB_ratio=%.2f, %d bars)",
            regime.value, adx, bb_ratio, len(spy_history),
        )
