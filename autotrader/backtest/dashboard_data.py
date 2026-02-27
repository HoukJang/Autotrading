"""Dashboard data aggregation and JSON serialization for backtest results."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from autotrader.backtest.engine import BacktestResult
from autotrader.backtest.trade_collector import TradeDetail


@dataclass
class BacktestDashboardData:
    config: dict
    trades: list[dict]
    equity_curves: dict[str, list[dict]]
    per_symbol_metrics: dict[str, dict]
    per_substrategy_metrics: dict[str, dict]
    aggregate_metrics: dict

    @classmethod
    def from_results(
        cls, results: dict[str, BacktestResult], config: dict
    ) -> BacktestDashboardData:
        all_trades: list[dict] = []
        equity_curves: dict[str, list[dict]] = {}
        per_symbol_metrics: dict[str, dict] = {}

        # Sub-strategy accumulators
        sub_strat_pnls: dict[str, list[float]] = {}

        for symbol, result in results.items():
            # Trades
            for t in result.trades:
                td = _trade_detail_to_dict(t)
                all_trades.append(td)

                ss = td["sub_strategy"]
                sub_strat_pnls.setdefault(ss, []).append(td["pnl"])

            # Equity curve
            equity_curves[symbol] = [
                {"timestamp": ts.isoformat(), "equity": eq}
                for ts, eq in result.timestamped_equity
            ]

            # Per-symbol metrics
            per_symbol_metrics[symbol] = {
                **result.metrics,
                "final_equity": result.final_equity,
            }

        # Per-substrategy metrics
        per_substrategy_metrics: dict[str, dict] = {}
        for ss, pnls in sub_strat_pnls.items():
            wins = [p for p in pnls if p > 0]
            per_substrategy_metrics[ss] = {
                "trade_count": len(pnls),
                "win_rate": len(wins) / len(pnls) if pnls else 0.0,
                "total_pnl": sum(pnls),
                "avg_pnl": sum(pnls) / len(pnls) if pnls else 0.0,
            }

        # Aggregate
        all_pnls = [t["pnl"] for t in all_trades]
        all_wins = [p for p in all_pnls if p > 0]
        all_losses_sum = abs(sum(p for p in all_pnls if p < 0))
        total_pnl = sum(all_pnls)

        aggregate_metrics = {
            "total_trades": len(all_trades),
            "win_rate": len(all_wins) / len(all_pnls) if all_pnls else 0.0,
            "total_pnl": total_pnl,
            "profit_factor": (
                sum(all_wins) / all_losses_sum if all_losses_sum > 0 else float("inf")
            ),
            "initial_balance": config.get("initial_balance", 0),
            "final_equity": sum(
                m.get("final_equity", 0) for m in per_symbol_metrics.values()
            ),
        }

        return cls(
            config=config,
            trades=all_trades,
            equity_curves=equity_curves,
            per_symbol_metrics=per_symbol_metrics,
            per_substrategy_metrics=per_substrategy_metrics,
            aggregate_metrics=aggregate_metrics,
        )

    def to_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._to_serializable(), f, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, path: str | Path) -> BacktestDashboardData:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            config=data["config"],
            trades=data["trades"],
            equity_curves=data["equity_curves"],
            per_symbol_metrics=data["per_symbol_metrics"],
            per_substrategy_metrics=data["per_substrategy_metrics"],
            aggregate_metrics=data["aggregate_metrics"],
        )

    def _to_serializable(self) -> dict:
        return {
            "config": self.config,
            "trades": self.trades,
            "equity_curves": self.equity_curves,
            "per_symbol_metrics": self.per_symbol_metrics,
            "per_substrategy_metrics": self.per_substrategy_metrics,
            "aggregate_metrics": _make_json_safe(self.aggregate_metrics),
        }


def _trade_detail_to_dict(t: TradeDetail) -> dict:
    return {
        "trade_id": t.trade_id,
        "symbol": t.symbol,
        "strategy": t.strategy,
        "sub_strategy": t.sub_strategy,
        "direction": t.direction,
        "entry_time": t.entry_time.isoformat(),
        "exit_time": t.exit_time.isoformat(),
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "quantity": t.quantity,
        "pnl": t.pnl,
        "pnl_pct": t.pnl_pct,
        "bars_held": t.bars_held,
        "exit_reason": t.exit_reason,
        "entry_indicators": t.entry_indicators,
    }


def _make_json_safe(d: dict) -> dict:
    result = {}
    for k, v in d.items():
        if isinstance(v, float) and (v == float("inf") or v == float("-inf")):
            result[k] = str(v)
        else:
            result[k] = v
    return result
