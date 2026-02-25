from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from autotrader.core.config import Settings, load_settings
from autotrader.core.event_bus import EventBus
from autotrader.core.logger import setup_logging
from autotrader.broker.base import BrokerAdapter
from autotrader.broker.paper import PaperBroker
from autotrader.indicators.engine import IndicatorEngine
from autotrader.strategy.engine import StrategyEngine
from autotrader.risk.manager import RiskManager

logger = logging.getLogger(__name__)


class AutoTrader:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bus = EventBus()
        self._broker = self._create_broker()
        self._indicator_engine = IndicatorEngine()
        self._strategy_engine = StrategyEngine()
        self._risk_manager = RiskManager(settings.risk)

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

    async def start(self) -> None:
        logger.info("Starting %s", self._settings.system.name)
        await self._broker.connect()
        account = await self._broker.get_account()
        logger.info("Account equity: %.2f", account.equity)

    async def stop(self) -> None:
        logger.info("Stopping %s", self._settings.system.name)
        await self._broker.disconnect()


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
