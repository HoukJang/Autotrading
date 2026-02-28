"""Universe Selector orchestrator.

Orchestrates the full stock universe selection pipeline:
1. Build StockCandidate objects from bar data (computing metrics)
2. Apply HardFilter to eliminate unsuitable candidates
3. Run BacktestEngine on each filtered candidate (all 5 strategies)
4. Compute hybrid score (proxy_weight * proxy + backtest_weight * backtest)
5. Pass scored candidates to PortfolioOptimizer for final selection
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from statistics import mean, stdev

from autotrader.core.types import Bar
from autotrader.core.config import RiskConfig
from autotrader.universe import (
    StockInfo,
    StockCandidate,
    ScoredCandidate,
    UniverseResult,
)
from autotrader.universe.filters import HardFilter
from autotrader.universe.scorer import ProxyScorer, BacktestScorer
from autotrader.universe.optimizer import PortfolioOptimizer
from autotrader.backtest.engine import BacktestEngine
from autotrader.strategy.rsi_mean_reversion import RsiMeanReversion
from autotrader.strategy.consecutive_down import ConsecutiveDown
from autotrader.strategy.ema_pullback import EmaPullback
from autotrader.strategy.volume_divergence import VolumeDivergence

logger = logging.getLogger(__name__)

_MIN_BARS = 60  # minimum bars needed to compute indicators


class UniverseSelector:
    """Orchestrates full universe selection pipeline with hybrid scoring."""

    def __init__(
        self,
        initial_balance: float = 3000.0,
        target_size: int = 15,
        proxy_weight: float = 0.50,
        backtest_weight: float = 0.50,
    ) -> None:
        self._initial_balance = initial_balance
        self._target_size = target_size
        self._proxy_weight = proxy_weight
        self._backtest_weight = backtest_weight
        self._hard_filter = HardFilter()
        self._proxy_scorer = ProxyScorer()
        self._backtest_scorer = BacktestScorer()
        self._optimizer = PortfolioOptimizer(target_size=target_size)
        self._risk_config = RiskConfig(
            max_position_pct=0.30,
            max_drawdown_pct=0.30,
            max_open_positions=5,
        )

    def select(
        self,
        infos: list[StockInfo],
        bars_by_symbol: dict[str, list[Bar]],
        current_pool: list[str] | None = None,
        open_positions: list[str] | None = None,
    ) -> UniverseResult:
        """Main entry point: run full universe selection pipeline.

        Args:
            infos: List of StockInfo objects (from SP500Provider).
            bars_by_symbol: Historical bar data keyed by symbol.
            current_pool: Symbols currently in the portfolio.
            open_positions: Symbols with open trades (must be preserved).

        Returns:
            UniverseResult with selected symbols, scores, and rotation info.
        """
        current_pool = current_pool or []

        # Stage 1: Build candidates from bar data
        candidates = self._build_candidates(infos, bars_by_symbol)
        logger.info("Built %d candidates from %d infos", len(candidates), len(infos))

        # Stage 2: Apply hard filter
        filtered = self._hard_filter.filter(candidates)
        logger.info(
            "Hard filter: %d -> %d candidates", len(candidates), len(filtered),
        )

        # Stage 3: Run backtest on each filtered candidate
        backtest_scores: dict[str, float] = {}
        for c in filtered:
            bars = bars_by_symbol.get(c.symbol, [])
            if len(bars) >= _MIN_BARS:
                backtest_scores[c.symbol] = self._run_backtest_for_symbol(bars)

        # Stage 4+5: Score, optimize, and return
        return self._score_and_optimize(
            filtered, backtest_scores, current_pool, open_positions,
        )

    def _build_candidates(
        self,
        infos: list[StockInfo],
        bars_by_symbol: dict[str, list[Bar]],
    ) -> list[StockCandidate]:
        """Build StockCandidate objects from bar data.

        Skips symbols with fewer than _MIN_BARS bars.
        """
        candidates: list[StockCandidate] = []
        for info in infos:
            bars = bars_by_symbol.get(info.symbol, [])
            if len(bars) < _MIN_BARS:
                continue
            candidate = self._bars_to_candidate(info, bars)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _bars_to_candidate(
        self, info: StockInfo, bars: list[Bar],
    ) -> StockCandidate | None:
        """Compute all metrics for a single stock from its bar data.

        Metrics computed:
            close: last bar close price
            avg_volume: mean volume of last 20 bars
            avg_dollar_volume: avg_volume * close
            atr_ratio: ATR(14) / close using true range formula
            gap_frequency: fraction of 2%+ overnight gaps in last 60 bars
            trend_pct: fraction of 14-bar windows with directional ratio > 0.30
            range_pct: fraction of 14-bar windows with directional ratio < 0.15
            vol_cycle: CV (stdev/mean) of rolling 20-bar stdev of closes
        """
        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        close = closes[-1]
        avg_volume = mean(volumes[-20:]) if len(volumes) >= 20 else mean(volumes)
        avg_dollar_volume = avg_volume * close

        # ATR ratio (14-period true range)
        trs: list[float] = []
        for i in range(1, min(15, len(bars))):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
        atr = mean(trs) if trs else 0.0
        atr_ratio = atr / close if close > 0 else 0.0

        # Gap frequency (2%+ overnight gaps in last 60 days)
        recent = bars[-60:] if len(bars) >= 60 else bars
        gaps = 0
        for i in range(1, len(recent)):
            gap_pct = abs(recent[i].open - recent[i - 1].close) / recent[i - 1].close
            if gap_pct >= 0.02:
                gaps += 1
        gap_frequency = gaps / max(1, len(recent) - 1)

        # Trend and range percentages using 14-bar directional ratio windows
        lookback = bars[-120:] if len(bars) >= 120 else bars
        trend_count = 0
        range_count = 0
        for i in range(14, len(lookback)):
            window = lookback[i - 14 : i + 1]
            rets = [
                (window[j].close - window[j - 1].close) / window[j - 1].close
                for j in range(1, len(window))
            ]
            directional = abs(sum(rets))
            total = sum(abs(r) for r in rets)
            ratio = directional / total if total > 0 else 0.0
            if ratio > 0.30:
                trend_count += 1
            elif ratio < 0.15:
                range_count += 1
        total_windows = max(1, len(lookback) - 14)
        trend_pct = trend_count / total_windows
        range_pct = range_count / total_windows

        # Vol cycle: CV of rolling 20-bar standard deviation of closes
        if len(closes) >= 20:
            widths: list[float] = []
            for i in range(20, len(closes)):
                window = closes[i - 20 : i]
                sd = stdev(window) if len(window) > 1 else 0.0
                widths.append(sd)
            vol_cycle = (
                stdev(widths) / mean(widths)
                if widths and mean(widths) > 0
                else 0.0
            )
        else:
            vol_cycle = 0.0

        return StockCandidate(
            symbol=info.symbol,
            sector=info.sector,
            close=close,
            avg_dollar_volume=avg_dollar_volume,
            avg_volume=avg_volume,
            atr_ratio=atr_ratio,
            gap_frequency=gap_frequency,
            trend_pct=trend_pct,
            range_pct=range_pct,
            vol_cycle=vol_cycle,
        )

    def _run_backtest_for_symbol(self, bars: list[Bar]) -> float:
        """Run all 5 strategies via BacktestEngine and return backtest score.

        Creates a fresh BacktestEngine with all 4 strategies, runs it on
        the provided bars, and feeds the results to BacktestScorer.

        Returns:
            Float score between 0.0 and 1.0.
        """
        engine = BacktestEngine(self._initial_balance, self._risk_config)
        strategies = [
            RsiMeanReversion(),
            ConsecutiveDown(),
            EmaPullback(),
            VolumeDivergence(),
        ]
        for s in strategies:
            engine.add_strategy(s)

        result = engine.run(bars)
        strategy_names = {t.strategy for t in result.trades}

        return self._backtest_scorer.score_from_metrics(
            total_trades=result.total_trades,
            win_rate=result.metrics.get("win_rate", 0.0),
            profit_factor=result.metrics.get("profit_factor", 0.0),
            strategies_active=len(strategy_names),
        )

    def _score_and_optimize(
        self,
        candidates: list[StockCandidate],
        backtest_scores: dict[str, float],
        current_pool: list[str],
        open_positions: list[str] | None = None,
    ) -> UniverseResult:
        """Compute hybrid scores and run portfolio optimization.

        Combines proxy scores and backtest scores with configured weights,
        then runs the optimizer to select the final portfolio.

        Args:
            candidates: Filtered StockCandidate list.
            backtest_scores: Dict mapping symbol to backtest score.
            current_pool: Symbols currently in the portfolio.
            open_positions: Symbols with open trades (must be preserved).

        Returns:
            UniverseResult with selected symbols and rotation tracking.
        """
        if not candidates:
            return UniverseResult(
                symbols=[],
                scored=[],
                timestamp=datetime.now(tz=timezone.utc),
                rotation_in=[],
                rotation_out=[s for s in current_pool],
            )

        proxy_scores = self._proxy_scorer.score(candidates, current_pool)

        scored: list[ScoredCandidate] = []
        for i, c in enumerate(candidates):
            ps = proxy_scores[i]
            bs = backtest_scores.get(c.symbol, 0.0)
            final = self._proxy_weight * ps + self._backtest_weight * bs
            scored.append(
                ScoredCandidate(
                    candidate=c,
                    proxy_score=ps,
                    backtest_score=bs,
                    final_score=round(final, 6),
                )
            )

        optimized = self._optimizer.optimize(
            scored, current_pool=current_pool, open_positions=open_positions,
        )

        new_symbols = [s.candidate.symbol for s in optimized]
        rotation_in = [s for s in new_symbols if s not in current_pool]
        rotation_out = [s for s in current_pool if s not in new_symbols]

        return UniverseResult(
            symbols=new_symbols,
            scored=optimized,
            timestamp=datetime.now(tz=timezone.utc),
            rotation_in=rotation_in,
            rotation_out=rotation_out,
        )
