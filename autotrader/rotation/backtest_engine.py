"""Multi-symbol rotation backtest engine.

Processes bars from multiple symbols with periodic universe rotation,
per-symbol indicator engines, and watchlist-based signal filtering.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from autotrader.backtest.simulator import BacktestSimulator
from autotrader.backtest.trade_collector import TradeCollector, TradeDetail
from autotrader.core.config import RiskConfig, RotationConfig
from autotrader.core.types import Bar, MarketContext, Signal
from autotrader.indicators.engine import IndicatorEngine
from autotrader.portfolio.performance import calculate_metrics
from autotrader.risk.manager import RiskManager
from autotrader.rotation.manager import RotationManager
from autotrader.rotation.types import RotationEvent
from autotrader.strategy.base import Strategy
from autotrader.universe import UniverseResult

logger = logging.getLogger(__name__)


@dataclass
class RotationBacktestResult:
    """Result of a rotation backtest run."""

    total_trades: int
    final_equity: float
    metrics: dict
    equity_curve: list[float] = field(default_factory=list)
    trades: list[TradeDetail] = field(default_factory=list)
    timestamped_equity: list[tuple] = field(default_factory=list)
    rotation_events: list[RotationEvent] = field(default_factory=list)


class RotationBacktestEngine:
    """Multi-symbol backtest engine with weekly rotation support.

    Unlike BacktestEngine which processes a single symbol's bars,
    this engine:
    - Maintains per-symbol IndicatorEngine instances and bar histories
    - Merges bars from all symbols sorted by timestamp
    - Applies rotation at scheduled points
    - Uses RotationManager to filter signals
    """

    def __init__(
        self,
        initial_balance: float,
        risk_config: RiskConfig,
        rotation_config: RotationConfig,
        earnings_cal: object | None = None,
    ) -> None:
        self._initial_balance = initial_balance
        self._risk_config = risk_config
        self._rotation_config = rotation_config
        self._earnings_cal = earnings_cal
        self._strategies: list[Strategy] = []
        self._indicator_specs: list = []

    def add_strategy(self, strategy: Strategy) -> None:
        """Register a strategy and its required indicators."""
        self._strategies.append(strategy)
        for spec in strategy.required_indicators:
            self._indicator_specs.append(spec)

    def _create_indicator_engine(self) -> IndicatorEngine:
        """Create a fresh IndicatorEngine with all registered specs."""
        engine = IndicatorEngine()
        for spec in self._indicator_specs:
            engine.register(spec)
        return engine

    def run(
        self,
        bars: dict[str, list[Bar]],
        initial_universe: list[str],
        rotation_schedule: dict[int, UniverseResult] | None = None,
    ) -> RotationBacktestResult:
        """Run a multi-symbol rotation backtest.

        Args:
            bars: dict mapping symbol -> list of bars (sorted by time).
            initial_universe: Initial set of active symbols.
            rotation_schedule: Optional dict mapping bar_index -> UniverseResult
                for applying rotation at specific points in the timeline.

        Returns:
            RotationBacktestResult with trades, equity curve, and rotation events.
        """
        if rotation_schedule is None:
            rotation_schedule = {}

        # Initialize components
        simulator = BacktestSimulator(self._initial_balance, self._risk_config)
        risk_mgr = RiskManager(self._risk_config)
        collector = TradeCollector()
        rotation_mgr = RotationManager(self._rotation_config, self._earnings_cal)

        # Set initial universe
        rotation_mgr._state.active_symbols = list(initial_universe)
        rotation_mgr._state.weekly_start_equity = self._initial_balance

        # Per-symbol state
        histories: dict[str, deque[Bar]] = {}
        indicator_engines: dict[str, IndicatorEngine] = {}
        for sym in self._all_symbols(bars, initial_universe):
            histories[sym] = deque(maxlen=500)
            indicator_engines[sym] = self._create_indicator_engine()

        # Merge and sort all bars by timestamp
        timeline = self._build_timeline(bars)

        trade_pnls: list[float] = []
        equity_curve: list[float] = [self._initial_balance]
        timestamped_equity: list[tuple] = []
        total_filled = 0
        bar_index = 0
        latest_prices: dict[str, float] = {}

        for ts, bars_at_ts in timeline:
            bar_index += 1

            # Check for rotation at this index
            if bar_index in rotation_schedule:
                universe_result = rotation_schedule[bar_index]
                open_syms = list(simulator._positions.keys())
                rotation_mgr.apply_rotation(
                    universe_result,
                    open_position_symbols=open_syms,
                    new_equity=simulator.get_equity_with_prices(latest_prices),
                )
                # Ensure new symbols have indicator engines
                for sym in universe_result.symbols:
                    if sym not in indicator_engines:
                        histories[sym] = deque(maxlen=500)
                        indicator_engines[sym] = self._create_indicator_engine()

            # Process each bar at this timestamp
            for bar in bars_at_ts:
                sym = bar.symbol
                latest_prices[sym] = bar.close

                # Ensure symbol has state (may be watchlist or new)
                if sym not in histories:
                    histories[sym] = deque(maxlen=500)
                    indicator_engines[sym] = self._create_indicator_engine()

                histories[sym].append(bar)

                # Force close check
                open_syms = list(simulator._positions.keys())
                force_close = rotation_mgr.get_force_close_symbols(
                    bar.timestamp, open_syms,
                )
                for fc_sym in force_close:
                    if fc_sym == sym:
                        pnl = simulator.get_pnl(fc_sym, bar.close)
                        close_sig = Signal(
                            strategy="rotation_manager",
                            symbol=fc_sym,
                            direction="close",
                            strength=1.0,
                            metadata={"exit_reason": "force_close"},
                        )
                        result = simulator.execute_signal(close_sig, bar.close)
                        if result and result.status == "filled":
                            total_filled += 1
                            trade_pnls.append(pnl)
                            collector.on_exit(close_sig, bar, pnl)
                            rotation_mgr.on_position_closed(fc_sym)

                # Compute indicators
                indicators = indicator_engines[sym].compute(histories[sym])
                ctx = MarketContext(
                    symbol=sym,
                    bar=bar,
                    indicators=indicators,
                    history=histories[sym],
                )

                # Run strategies
                signals: list[Signal] = []
                for strat in self._strategies:
                    try:
                        signal = strat.on_context(ctx)
                    except Exception:
                        continue
                    if signal is not None:
                        signals.append(signal)

                # Filter through rotation manager
                signals = rotation_mgr.filter_signals(signals)

                # Execute filtered signals
                for signal in signals:
                    account = simulator._get_account()
                    if not risk_mgr.validate(signal, account, positions=[]):
                        continue

                    if signal.direction == "close":
                        pnl = simulator.get_pnl(signal.symbol, bar.close)

                    exec_result = simulator.execute_signal(signal, bar.close)
                    if exec_result and exec_result.status == "filled":
                        total_filled += 1
                        if signal.direction == "close":
                            trade_pnls.append(pnl)
                            collector.on_exit(signal, bar, pnl)
                            rotation_mgr.on_position_closed(signal.symbol)
                        else:
                            collector.on_entry(signal, bar, exec_result.filled_qty)

            # Weekly loss check
            current_equity = simulator.get_equity_with_prices(latest_prices)
            rotation_mgr.check_weekly_loss_limit(current_equity)

            equity_curve.append(current_equity)
            timestamped_equity.append((ts, current_equity))

        final_equity = equity_curve[-1] if len(equity_curve) > 1 else self._initial_balance
        metrics = calculate_metrics(trade_pnls, self._initial_balance)

        return RotationBacktestResult(
            total_trades=total_filled,
            final_equity=final_equity,
            metrics=metrics,
            equity_curve=equity_curve,
            trades=collector.trades,
            timestamped_equity=timestamped_equity,
            rotation_events=list(rotation_mgr._state.rotation_history),
        )

    @staticmethod
    def _all_symbols(
        bars: dict[str, list[Bar]], initial_universe: list[str]
    ) -> set[str]:
        """Get all unique symbols from bars and initial universe."""
        syms = set(bars.keys())
        syms.update(initial_universe)
        return syms

    @staticmethod
    def _build_timeline(
        bars: dict[str, list[Bar]],
    ) -> list[tuple[datetime, list[Bar]]]:
        """Merge all bars sorted by timestamp, grouping by timestamp."""
        all_bars: list[Bar] = []
        for symbol_bars in bars.values():
            all_bars.extend(symbol_bars)
        all_bars.sort(key=lambda b: (b.timestamp, b.symbol))

        if not all_bars:
            return []

        timeline: list[tuple[datetime, list[Bar]]] = []
        current_ts = all_bars[0].timestamp
        current_group: list[Bar] = []

        for bar in all_bars:
            if bar.timestamp == current_ts:
                current_group.append(bar)
            else:
                timeline.append((current_ts, current_group))
                current_ts = bar.timestamp
                current_group = [bar]

        if current_group:
            timeline.append((current_ts, current_group))

        return timeline
