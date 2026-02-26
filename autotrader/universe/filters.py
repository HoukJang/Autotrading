from __future__ import annotations

from autotrader.universe import StockCandidate


class HardFilter:
    """Hard filter pipeline for stock universe selection.

    Applies configurable threshold checks to eliminate candidates
    that don't meet minimum liquidity, price, volatility, and
    gap requirements for swing trading.
    """

    def __init__(
        self,
        min_dollar_volume: float = 50e6,
        min_volume: float = 1e6,
        min_price: float = 20.0,
        max_price: float = 200.0,
        min_atr_ratio: float = 0.01,
        max_atr_ratio: float = 0.04,
        max_gap_frequency: float = 0.15,
    ) -> None:
        self.min_dollar_volume = min_dollar_volume
        self.min_volume = min_volume
        self.min_price = min_price
        self.max_price = max_price
        self.min_atr_ratio = min_atr_ratio
        self.max_atr_ratio = max_atr_ratio
        self.max_gap_frequency = max_gap_frequency

    def passes(self, c: StockCandidate) -> bool:
        """Check if a candidate passes all hard filter thresholds."""
        if c.avg_dollar_volume < self.min_dollar_volume:
            return False
        if c.avg_volume < self.min_volume:
            return False
        if c.close < self.min_price or c.close > self.max_price:
            return False
        if c.atr_ratio < self.min_atr_ratio or c.atr_ratio > self.max_atr_ratio:
            return False
        if c.gap_frequency > self.max_gap_frequency:
            return False
        return True

    def filter(self, candidates: list[StockCandidate]) -> list[StockCandidate]:
        """Return candidates that pass all hard filter thresholds."""
        return [c for c in candidates if self.passes(c)]
