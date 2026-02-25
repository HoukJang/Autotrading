from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv

from autotrader.core.config import Settings, load_settings
from autotrader.core.event_bus import EventBus
from autotrader.core.logger import setup_logging
from autotrader.core.types import (
    AccountInfo, Bar, MarketContext, Order, OrderResult, Position, Signal,
)
from autotrader.broker.base import BrokerAdapter
from autotrader.broker.paper import PaperBroker
from autotrader.indicators.engine import IndicatorEngine
from autotrader.portfolio.tracker import PortfolioTracker
from autotrader.risk.manager import RiskManager
from autotrader.risk.position_sizer import PositionSizer
from autotrader.strategy.engine import StrategyEngine
from autotrader.strategy.sma_crossover import SmaCrossover

logger = logging.getLogger(__name__)


class AutoTrader:
    def __init__(self, settings: Settings) -> None:
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

    def _create_broker(self) -> BrokerAdapter:
        if self._settings.broker.type == "paper":
            return PaperBroker(self._settings.broker.paper_balance)
        elif self._settings.broker.type == "alpaca":
            from autotrader.broker.alpaca_adapter import AlpacaAdapter
            load_dotenv()
            return AlpacaAdapter(
                api_key=os.environ["ALPACA_API_KEY"],
                secret_key=os.environ["ALPACA_SECRET_KEY"],
                paper=self._settings.alpaca.paper,
                feed=self._settings.alpaca.feed,
            )
        raise ValueError(f"Unknown broker type: {self._settings.broker.type}")

    def _register_strategies(self) -> None:
        strategy = SmaCrossover()
        self._strategy_engine.add_strategy(strategy)
        registered_keys: set[str] = set(self._indicator_engine._indicators.keys())
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

        await self._broker.subscribe_bars(self._settings.symbols, self._on_bar)

        if hasattr(self._broker, "run_stream"):
            self._stream_task = asyncio.create_task(
                asyncio.to_thread(self._broker.run_stream),
            )

    async def stop(self) -> None:
        logger.info("Stopping %s", self._settings.system.name)
        self._running = False
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

        indicators = self._indicator_engine.compute(history)

        ctx = MarketContext(
            symbol=bar.symbol,
            bar=bar,
            indicators=indicators,
            history=history,
        )

        signals = await self._strategy_engine.process(ctx)
        if not signals:
            return

        account = await self._broker.get_account()
        positions = await self._broker.get_positions()

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

        if result.status == "filled" and self._portfolio_tracker is not None:
            pnl = 0.0
            if order.side == "sell":
                pos = next((p for p in positions if p.symbol == order.symbol), None)
                if pos is not None:
                    pnl = (result.filled_price - pos.avg_entry_price) * result.filled_qty
            self._portfolio_tracker.record_trade(
                symbol=order.symbol,
                side=order.side,
                qty=result.filled_qty,
                price=result.filled_price,
                pnl=pnl,
            )
            self._risk_manager.record_pnl(pnl)

        return result

    def _signal_to_order(
        self, signal: Signal, account: AccountInfo, positions: list[Position],
    ) -> Order | None:
        if signal.direction == "close":
            pos = next((p for p in positions if p.symbol == signal.symbol), None)
            if pos is None:
                return None
            return Order(
                symbol=signal.symbol,
                side="sell",
                quantity=pos.quantity,
                order_type="market",
            )

        if signal.direction == "long":
            price = account.equity  # fallback
            # Use last bar close if available
            history = self._bar_history.get(signal.symbol)
            if history:
                price = history[-1].close
            qty = self._position_sizer.calculate(price, account)
            if qty <= 0:
                return None
            return Order(
                symbol=signal.symbol,
                side="buy",
                quantity=qty,
                order_type="market",
            )

        return None


def main() -> None:
    config_path = Path("config/default.yaml")
    if config_path.exists():
        settings = load_settings(config_path)
    else:
        settings = Settings()

    setup_logging("autotrader", level=settings.system.log_level)
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
