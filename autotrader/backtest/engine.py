from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from autotrader.core.types import Bar, MarketContext
from autotrader.core.config import RiskConfig
from autotrader.indicators.engine import IndicatorEngine
from autotrader.strategy.base import Strategy
from autotrader.risk.manager import RiskManager
from autotrader.backtest.simulator import BacktestSimulator
from autotrader.portfolio.performance import calculate_metrics


@dataclass
class BacktestResult:
    total_trades: int
    final_equity: float
    metrics: dict
    equity_curve: list[float] = field(default_factory=list)


class BacktestEngine:
    def __init__(self, initial_balance: float, risk_config: RiskConfig) -> None:
        self._initial_balance = initial_balance
        self._risk_config = risk_config
        self._strategies: list[Strategy] = []
        self._indicator_engine = IndicatorEngine()

    def add_strategy(self, strategy: Strategy) -> None:
        self._strategies.append(strategy)
        for spec in strategy.required_indicators:
            self._indicator_engine.register(spec)

    def run(self, bars: list[Bar]) -> BacktestResult:
        simulator = BacktestSimulator(self._initial_balance, self._risk_config)
        risk_mgr = RiskManager(self._risk_config)
        history: deque[Bar] = deque(maxlen=500)
        trade_pnls: list[float] = []
        equity_curve: list[float] = [self._initial_balance]
        total_filled = 0

        for bar in bars:
            history.append(bar)
            indicators = self._indicator_engine.compute(history)
            ctx = MarketContext(symbol=bar.symbol, bar=bar, indicators=indicators, history=history)

            for strat in self._strategies:
                try:
                    signal = strat.on_context(ctx)
                except Exception:
                    continue

                if signal is None:
                    continue

                account = simulator._get_account()
                if not risk_mgr.validate(signal, account, positions=[]):
                    continue

                # Calculate PnL before executing close (position gets removed)
                if signal.direction == "close":
                    pnl = simulator.get_pnl(signal.symbol, bar.close)

                result = simulator.execute_signal(signal, bar.close)
                if result and result.status == "filled":
                    total_filled += 1
                    if signal.direction == "close":
                        trade_pnls.append(pnl)

            equity = simulator.get_equity_with_prices({bar.symbol: bar.close})
            equity_curve.append(equity)

        metrics = calculate_metrics(trade_pnls, self._initial_balance)
        return BacktestResult(
            total_trades=total_filled,
            final_equity=equity_curve[-1],
            metrics=metrics,
            equity_curve=equity_curve,
        )
