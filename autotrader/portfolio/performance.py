from __future__ import annotations


def calculate_metrics(trade_pnls: list[float], initial_equity: float) -> dict:
    if not trade_pnls:
        return {
            "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "total_pnl": 0.0, "max_drawdown": 0.0,
        }

    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]

    total_wins = sum(wins)
    total_losses = abs(sum(losses))

    # Equity curve for drawdown
    equity = initial_equity
    peak = equity
    max_dd = 0.0
    for pnl in trade_pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    return {
        "total_trades": len(trade_pnls),
        "win_rate": len(wins) / len(trade_pnls),
        "profit_factor": total_wins / total_losses if total_losses > 0 else float("inf"),
        "total_pnl": sum(trade_pnls),
        "max_drawdown": max_dd,
    }
