from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from autotrader.core.config import RotationConfig, Settings, load_settings
from autotrader.core.event_bus import EventBus
from autotrader.core.logger import setup_logging
from autotrader.core.types import (
    AccountInfo, Bar, MarketContext, Order, OrderResult, Position, Signal,
)
from autotrader.broker.base import BrokerAdapter
from autotrader.broker.paper import PaperBroker
from autotrader.indicators.engine import IndicatorEngine
from autotrader.data.market_sentiment import VIXFetcher
from autotrader.portfolio.allocation_engine import AllocationEngine
from autotrader.portfolio.regime_detector import MarketRegime, RegimeDetector
from autotrader.portfolio.regime_tracker import RegimeTracker
from autotrader.portfolio.tracker import PortfolioTracker
from autotrader.portfolio.position_tracker import OpenPositionTracker
from autotrader.portfolio.regime_position_reviewer import RegimePositionReviewer
from autotrader.portfolio.trade_logger import TradeLogger, LiveTradeRecord, EquitySnapshot
from autotrader.risk.manager import RiskManager
from autotrader.risk.position_sizer import PositionSizer
from autotrader.rotation.event_driven import EventDrivenRotation
from autotrader.rotation.manager import RotationManager
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.bb_squeeze import BbSqueezeBreakout
from autotrader.strategy.adx_pullback import AdxPullback
from autotrader.strategy.overbought_short import OverboughtShort
from autotrader.strategy.regime_momentum import RegimeMomentum
from autotrader.universe.provider import SP500Provider
from autotrader.universe.selector import UniverseSelector
from autotrader.universe.earnings import EarningsCalendar

logger = logging.getLogger(__name__)


class AutoTrader:
    def __init__(
        self,
        settings: Settings,
        rotation_config: RotationConfig | None = None,
        earnings_cal: object | None = None,
    ) -> None:
        self._settings = settings
        self._bus = EventBus()
        self._broker = self._create_broker()
        self._indicator_engine = IndicatorEngine()
        self._strategy_engine = StrategyEngine()
        self._risk_manager = RiskManager(settings.risk)
        self._position_sizer = PositionSizer(settings.risk)
        self._portfolio_tracker: PortfolioTracker | None = None
        self._bar_history: dict[str, deque[Bar]] = defaultdict(
            lambda: deque(maxlen=settings.data.bar_history_size),
        )
        self._running = False
        self._stream_task: asyncio.Task | None = None
        self._rotation_manager: RotationManager | None = None
        if rotation_config is not None:
            self._rotation_manager = RotationManager(rotation_config, earnings_cal)

        # Regime detection and allocation
        self._regime_detector = RegimeDetector()
        self._allocation_engine = AllocationEngine(self._regime_detector)
        self._current_regime: MarketRegime = MarketRegime.UNCERTAIN
        self._spy_bb_width_history: deque[float] = deque(maxlen=20)
        self._regime_proxy_symbol: str = self._settings.scheduler.regime_proxy_symbol
        self._position_strategy_map: dict[str, str] = {}

        # Debounced regime tracking
        self._regime_tracker = RegimeTracker(confirmation_bars=3)

        # Event-driven rotation
        self._event_rotation = EventDrivenRotation(
            cooldown_hours=self._settings.event_rotation.cooldown_hours,
            vix_spike_trigger=self._settings.event_rotation.vix_spike_trigger,
            regime_triggers=self._settings.event_rotation.regime_triggers,
            enabled=self._settings.event_rotation.enable_event_driven,
        )

        # VIX fetcher
        self._vix_fetcher: VIXFetcher | None = None
        if self._settings.sentiment.enable_vix:
            self._vix_fetcher = VIXFetcher(
                symbol=self._settings.sentiment.vix_symbol,
                cache_ttl_seconds=self._settings.sentiment.cache_ttl_seconds,
            )

        # Position lifecycle tracking (MFE/MAE)
        self._open_position_tracker = OpenPositionTracker()
        self._regime_reviewer = RegimePositionReviewer()

        # Scheduler and logging
        self._scheduler_task: asyncio.Task | None = None
        self._bar_count: int = 0

        # Trade logger
        self._trade_logger: TradeLogger | None = None
        if settings.performance.enable_trade_log:
            self._trade_logger = TradeLogger(
                settings.performance.trade_log_path,
                settings.performance.equity_snapshot_path,
            )

    def _create_broker(self) -> BrokerAdapter:
        if self._settings.broker.type == "paper":
            return PaperBroker(self._settings.broker.paper_balance)
        elif self._settings.broker.type == "alpaca":
            from autotrader.broker.alpaca_adapter import AlpacaAdapter
            load_dotenv(Path("config/.env"))
            return AlpacaAdapter(
                api_key=os.environ["ALPACA_API_KEY"],
                secret_key=os.environ["ALPACA_SECRET_KEY"],
                paper=self._settings.alpaca.paper,
                feed=self._settings.alpaca.feed,
            )
        raise ValueError(f"Unknown broker type: {self._settings.broker.type}")

    def _register_strategies(self) -> None:
        strategies = [
            RsiMeanReversion(),
            BbSqueezeBreakout(),
            AdxPullback(),
            OverboughtShort(),
            RegimeMomentum(),
        ]
        registered_keys: set[str] = set(self._indicator_engine._indicators.keys())
        for strategy in strategies:
            self._strategy_engine.add_strategy(strategy)
            for spec in strategy.required_indicators:
                if spec.key not in registered_keys:
                    self._indicator_engine.register(spec)
                    registered_keys.add(spec.key)

    async def start(self) -> None:
        logger.info("Starting %s", self._settings.system.name)
        await self._broker.connect()
        account = await self._broker.get_account()
        logger.info("Account equity: %.2f", account.equity)

        self._portfolio_tracker = PortfolioTracker(account.equity)
        self._register_strategies()
        self._running = True

        symbols = list(set(self._settings.symbols + [self._regime_proxy_symbol]))
        await self._broker.subscribe_bars(symbols, self._on_bar)

        if hasattr(self._broker, "run_stream"):
            self._stream_task = asyncio.create_task(
                asyncio.to_thread(self._broker.run_stream),
            )

        if self._rotation_manager and self._settings.scheduler.enable_rotation_scheduler:
            self._scheduler_task = asyncio.create_task(self._rotation_scheduler())

    async def stop(self) -> None:
        logger.info("Stopping %s", self._settings.system.name)
        self._running = False
        if self._scheduler_task is not None and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except (asyncio.CancelledError, Exception):
                pass
            self._scheduler_task = None
        if self._stream_task is not None and not self._stream_task.done():
            self._stream_task.cancel()
            try:
                await self._stream_task
            except (asyncio.CancelledError, Exception):
                pass
            self._stream_task = None
        await self._broker.disconnect()

    async def _on_bar(self, bar: Bar) -> None:
        history = self._bar_history[bar.symbol]
        history.append(bar)

        # Update MFE/MAE tracking for open positions
        self._open_position_tracker.update_prices(
            bar.symbol, bar.high, bar.low, bar.close,
        )

        indicators = self._indicator_engine.compute(history)

        # Update regime from proxy symbol (SPY)
        if bar.symbol == self._regime_proxy_symbol:
            self._update_regime(indicators)

        ctx = MarketContext(
            symbol=bar.symbol,
            bar=bar,
            indicators=indicators,
            history=history,
        )

        account = await self._broker.get_account()
        positions = await self._broker.get_positions()

        # Rotation manager: force close, weekly loss, signal filtering
        if self._rotation_manager:
            open_syms = [p.symbol for p in positions]
            force_close = self._rotation_manager.get_force_close_symbols(
                bar.timestamp, open_syms,
            )
            for sym in force_close:
                close_sig = Signal(
                    strategy="rotation_manager",
                    symbol=sym,
                    direction="close",
                    strength=1.0,
                    metadata={"exit_reason": "force_close"},
                )
                await self._process_signal(close_sig, account, positions)
                self._rotation_manager.on_position_closed(sym)
                # Refresh positions after close
                positions = await self._broker.get_positions()

            self._rotation_manager.check_weekly_loss_limit(account.equity)

        # Equity snapshot logging
        self._bar_count += 1
        if (
            self._trade_logger is not None
            and self._bar_count % self._settings.performance.equity_snapshot_interval == 0
        ):
            snap = EquitySnapshot(
                timestamp=bar.timestamp.isoformat(),
                equity=account.equity,
                cash=account.cash,
                regime=self._current_regime.value,
                position_count=len(positions),
                open_positions=[p.symbol for p in positions],
            )
            self._trade_logger.log_equity(snap)

        signals = await self._strategy_engine.process(ctx)
        if not signals:
            return

        # Filter signals through rotation manager
        if self._rotation_manager:
            signals = self._rotation_manager.filter_signals(signals)
            if not signals:
                return

        for signal in signals:
            await self._process_signal(signal, account, positions)

    async def _process_signal(
        self, signal: Signal, account: AccountInfo, positions: list[Position],
    ) -> OrderResult | None:
        if not self._risk_manager.validate(signal, account, positions):
            logger.info("Risk rejected signal: %s %s", signal.direction, signal.symbol)
            return None

        order = self._signal_to_order(signal, account, positions)
        if order is None:
            return None

        result = await self._broker.submit_order(order)
        logger.info(
            "Order %s: %s %s %.0f @ %.2f",
            result.status, order.side, order.symbol,
            result.filled_qty, result.filled_price,
        )

        if result.status == "filled":
            # Track position->strategy mapping
            if signal.direction in ("long", "short"):
                self._position_strategy_map[signal.symbol] = signal.strategy
                # Register with position tracker for MFE/MAE
                self._open_position_tracker.open_position(
                    symbol=signal.symbol,
                    strategy=signal.strategy,
                    direction=signal.direction,
                    entry_price=result.filled_price,
                    entry_time=datetime.now(timezone.utc),
                    quantity=result.filled_qty,
                )
            elif signal.direction == "close":
                self._position_strategy_map.pop(signal.symbol, None)

            # Compute PnL for closes and extract MFE/MAE
            pnl = 0.0
            exit_reason = signal.metadata.get("exit_reason", "") if signal.metadata else ""
            mfe = 0.0
            mae = 0.0
            bars_held = 0
            if signal.direction == "close":
                pos = next((p for p in positions if p.symbol == order.symbol), None)
                if pos is not None:
                    if pos.side == "long":
                        pnl = (result.filled_price - pos.avg_entry_price) * result.filled_qty
                    else:  # short
                        pnl = (pos.avg_entry_price - result.filled_price) * result.filled_qty

                # Retrieve MFE/MAE from position tracker
                tracked = self._open_position_tracker.close_position(signal.symbol)
                if tracked is not None:
                    mfe = tracked.mfe
                    mae = tracked.mae
                    bars_held = tracked.bar_count

            if self._portfolio_tracker is not None:
                self._portfolio_tracker.record_trade(
                    symbol=order.symbol,
                    side=order.side,
                    qty=result.filled_qty,
                    price=result.filled_price,
                    pnl=pnl,
                )
            self._risk_manager.record_pnl(pnl)

            # Log trade with MFE/MAE data
            if self._trade_logger is not None:
                account_after = await self._broker.get_account()
                record = LiveTradeRecord(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    symbol=signal.symbol,
                    strategy=signal.strategy,
                    direction=signal.direction,
                    side=order.side,
                    quantity=result.filled_qty,
                    price=result.filled_price,
                    pnl=pnl,
                    regime=self._current_regime.value,
                    equity_after=account_after.equity,
                    metadata=signal.metadata,
                    exit_reason=exit_reason,
                    mfe=mfe,
                    mae=mae,
                    bars_held=bars_held,
                )
                self._trade_logger.log_trade(record)

        return result

    def _signal_to_order(
        self, signal: Signal, account: AccountInfo, positions: list[Position],
    ) -> Order | None:
        if signal.direction == "close":
            pos = next((p for p in positions if p.symbol == signal.symbol), None)
            if pos is None:
                return None
            side = "sell" if pos.side == "long" else "buy"
            return Order(
                symbol=signal.symbol,
                side=side,
                quantity=pos.quantity,
                order_type="market",
            )

        if signal.direction in ("long", "short"):
            # Prevent duplicate positions on same symbol
            if signal.symbol in self._position_strategy_map:
                existing_strategy = self._position_strategy_map[signal.symbol]
                if existing_strategy != signal.strategy:
                    logger.debug(
                        "Skipping %s signal for %s: already has position from %s",
                        signal.strategy, signal.symbol, existing_strategy,
                    )
                    return None

            # Also check broker positions
            existing_pos = next(
                (p for p in positions if p.symbol == signal.symbol), None,
            )
            if existing_pos is not None:
                return None

            strategy_count = sum(
                1 for s in self._position_strategy_map.values()
                if s == signal.strategy
            )
            if not self._allocation_engine.should_enter(
                signal.strategy, self._current_regime, strategy_count,
            ):
                return None
            history = self._bar_history.get(signal.symbol)
            if not history:
                return None
            price = history[-1].close

            # Cash availability check
            position_value = price  # minimum 1 share
            if account.cash < position_value:
                logger.info("Insufficient cash for %s (need %.2f, have %.2f)",
                            signal.symbol, position_value, account.cash)
                return None

            # Get ATR for risk-based sizing
            indicators = self._indicator_engine.compute(history)
            atr = indicators.get("ATR_14")

            qty = self._allocation_engine.get_position_size(
                signal.strategy, price, account.equity, self._current_regime,
                atr=atr, direction=signal.direction,
            )
            if qty <= 0:
                return None
            side = "buy" if signal.direction == "long" else "sell"
            order_type = "market"
            if signal.limit_price is not None:
                order_type = "limit"
            return Order(
                symbol=signal.symbol,
                side=side,
                quantity=qty,
                order_type=order_type,
                limit_price=signal.limit_price,
            )

        return None

    def _update_regime(self, indicators: dict) -> None:
        """Update market regime from proxy symbol indicators."""
        adx = indicators.get("ADX_14")
        bbands = indicators.get("BBANDS_20")
        atr = indicators.get("ATR_14")
        if any(v is None for v in [adx, bbands, atr]):
            return
        bb_width = bbands["width"]
        self._spy_bb_width_history.append(bb_width)
        bb_width_avg = sum(self._spy_bb_width_history) / len(self._spy_bb_width_history)
        history = self._bar_history.get(self._regime_proxy_symbol)
        if not history:
            return
        close = history[-1].close
        atr_ratio = atr / close if close > 0 else 0.0

        raw_regime = self._regime_detector.classify(
            adx=adx,
            bb_width=bb_width,
            bb_width_avg=bb_width_avg,
            atr_ratio=atr_ratio,
        )

        # Use RegimeTracker for debounced transitions
        timestamp = history[-1].timestamp
        transition = self._regime_tracker.update(raw_regime, timestamp)
        if transition is not None:
            logger.info(
                "Regime confirmed: %s -> %s (after %d bars)",
                transition.previous.value,
                transition.current.value,
                transition.bars_in_new_regime,
            )
            self._current_regime = transition.current

            # Review existing positions for regime compatibility
            if self._position_strategy_map:
                reviews = self._regime_reviewer.review(
                    transition.current, self._position_strategy_map,
                )
                close_reviews = [r for r in reviews if r.action == "close"]
                if close_reviews:
                    logger.info(
                        "Regime review: closing %d incompatible positions",
                        len(close_reviews),
                    )
                    for review in close_reviews:
                        close_sig = Signal(
                            strategy=review.strategy,
                            symbol=review.symbol,
                            direction="close",
                            strength=1.0,
                            metadata={"exit_reason": f"regime_{review.reason}"},
                        )
                        asyncio.ensure_future(
                            self._process_regime_close(close_sig),
                        )

            # Check event-driven rotation trigger
            vix_value = None
            if self._vix_fetcher is not None:
                try:
                    sentiment = self._vix_fetcher.get_sentiment()
                    vix_value = sentiment.vix_value
                except Exception:
                    logger.warning("VIX fetch failed during regime transition check")

            should_trigger, reason = self._event_rotation.should_trigger_rotation(
                transition=transition, vix_value=vix_value,
            )
            if should_trigger:
                logger.info("Event-driven rotation triggered: %s", reason)
                self._event_rotation.mark_triggered()
                if self._rotation_manager is not None:
                    asyncio.ensure_future(self._execute_event_rotation(reason))

    async def _process_regime_close(self, signal: Signal) -> None:
        """Process a regime-triggered close signal."""
        try:
            account = await self._broker.get_account()
            positions = await self._broker.get_positions()
            await self._process_signal(signal, account, positions)
        except Exception:
            logger.exception("Regime close failed for %s", signal.symbol)

    async def _run_universe_selection(self) -> None:
        """Run the full universe selection pipeline and apply rotation."""
        logger.info("Starting universe selection pipeline...")

        # Step 1: Fetch S&P 500 list
        provider = SP500Provider()
        infos = await asyncio.to_thread(provider.fetch)
        logger.info("Fetched %d S&P 500 constituents", len(infos))

        # Step 2: Fetch earnings calendar
        earnings_cal = EarningsCalendar()
        all_symbols = [i.symbol for i in infos]
        max_candidates = self._settings.scheduler.universe_max_candidates
        try:
            await asyncio.to_thread(
                earnings_cal.fetch, all_symbols[:max_candidates],
            )
        except Exception:
            logger.warning("Earnings calendar fetch partially failed")

        today = datetime.now(timezone.utc).date()
        blackout = earnings_cal.blackout_symbols(all_symbols, today)
        active_candidates = [s for s in all_symbols if s not in blackout][:max_candidates]
        logger.info(
            "%d candidates after blackout filter (%d in blackout)",
            len(active_candidates), len(blackout),
        )

        # Step 3: Fetch historical bars
        if not hasattr(self._broker, "get_historical_bars"):
            logger.warning("Broker does not support historical bars; skipping rotation")
            return

        days = self._settings.scheduler.universe_history_days
        bars_by_symbol = await self._broker.get_historical_bars(
            active_candidates, days=days,
        )
        logger.info("Fetched history for %d symbols", len(bars_by_symbol))

        if not bars_by_symbol:
            logger.warning("No historical bars received; skipping rotation")
            return

        # Step 4: Run universe selection
        account = await self._broker.get_account()
        positions = await self._broker.get_positions()
        current_pool = list(self._rotation_manager.active_symbols) if self._rotation_manager else []
        open_syms = [p.symbol for p in positions]

        selector = UniverseSelector(
            initial_balance=account.equity,
            target_size=self._settings.risk.max_open_positions * 3,
        )
        result = selector.select(
            infos, bars_by_symbol,
            current_pool=current_pool,
            open_positions=open_syms,
        )
        logger.info(
            "Universe selection complete: %d symbols (in: %s, out: %s)",
            len(result.symbols),
            result.rotation_in or "none",
            result.rotation_out or "none",
        )

        # Step 5: Apply rotation
        await self.apply_rotation(result)

    async def _execute_event_rotation(self, reason: str) -> None:
        """Execute an event-driven mid-week rotation."""
        try:
            logger.info("Executing event-driven rotation: %s", reason)
            await self._run_universe_selection()
        except Exception:
            logger.exception("Event-driven rotation execution failed")

    async def _rotation_scheduler(self) -> None:
        """Background task that checks for weekly rotation day."""
        last_rotation_date = None
        interval = self._settings.scheduler.rotation_check_interval_seconds
        while self._running:
            await asyncio.sleep(interval)
            now = datetime.now(timezone.utc)
            rotation_day = 5  # Saturday by default
            if self._rotation_manager is not None:
                rotation_day = getattr(
                    self._rotation_manager._config, "rotation_day", 5,
                )
            if now.weekday() == rotation_day and last_rotation_date != now.date():
                try:
                    logger.info("Rotation scheduler: triggering weekly rotation")
                    await self._run_universe_selection()
                    last_rotation_date = now.date()
                except Exception:
                    logger.exception("Rotation scheduler failed")

    async def apply_rotation(self, universe_result) -> None:
        """Apply a new universe rotation (called by external scheduler)."""
        if self._rotation_manager is None:
            logger.warning("apply_rotation called but no rotation manager configured")
            return
        account = await self._broker.get_account()
        positions = await self._broker.get_positions()
        open_syms = [p.symbol for p in positions]
        self._rotation_manager.apply_rotation(
            universe_result,
            open_position_symbols=open_syms,
            new_equity=account.equity,
        )
        # Reset peak equity on rotation (breaks drawdown death spiral)
        self._risk_manager.reset_peak_equity(account.equity)
        logger.info(
            "Peak equity reset to %.2f on rotation", account.equity,
        )

        # Update subscribed symbols
        new_symbols = list(
            set(self._rotation_manager.active_symbols)
            | set(self._rotation_manager.watchlist_symbols)
        )
        self._settings.symbols = new_symbols
        logger.info(
            "Rotation applied: %d active, %d watchlist",
            len(self._rotation_manager.active_symbols),
            len(self._rotation_manager.watchlist_symbols),
        )


def main() -> None:
    config_path = Path("config/default.yaml")
    if config_path.exists():
        settings = load_settings(config_path)
    else:
        settings = Settings()

    setup_logging("autotrader", level=settings.system.log_level, log_dir=settings.system.log_dir)
    app = AutoTrader(settings)

    async def run():
        await app.start()
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await app.stop()

    asyncio.run(run())


if __name__ == "__main__":
    main()
