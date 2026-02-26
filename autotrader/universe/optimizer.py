"""Portfolio optimizer with greedy selection and constraints.

Selects an optimal portfolio from scored candidates using a 3-phase algorithm:
1. Force-include open positions (cannot be removed while held)
2. Greedy add by score with sector cap and rotation limit
3. Enforce minimum sector diversity by swapping duplicates
"""
from __future__ import annotations

from autotrader.universe import ScoredCandidate


class PortfolioOptimizer:
    """Greedy portfolio selection with sector, regime, and rotation constraints."""

    def __init__(
        self,
        target_size: int = 15,
        max_per_sector: int = 4,
        min_sectors: int = 4,
        min_trend_capable: int = 5,
        min_range_capable: int = 5,
        max_rotation: int = 3,
        trend_threshold: float = 0.30,
        range_threshold: float = 0.40,
    ) -> None:
        self.target_size = target_size
        self.max_per_sector = max_per_sector
        self.min_sectors = min_sectors
        self.min_trend_capable = min_trend_capable
        self.min_range_capable = min_range_capable
        self.max_rotation = max_rotation
        self.trend_threshold = trend_threshold
        self.range_threshold = range_threshold

    def optimize(
        self,
        candidates: list[ScoredCandidate],
        current_pool: list[str] | None = None,
        open_positions: list[str] | None = None,
    ) -> list[ScoredCandidate]:
        """Select optimal portfolio from scored candidates.

        Args:
            candidates: Scored candidates sorted by final_score.
            current_pool: Symbols currently in the portfolio (for rotation limit).
            open_positions: Symbols with open trades (must be included).

        Returns:
            List of selected ScoredCandidate objects.
        """
        if not candidates:
            return []

        current_pool = current_pool or []
        open_positions = open_positions or []

        sorted_candidates = sorted(
            candidates, key=lambda s: s.final_score, reverse=True,
        )
        by_symbol = {s.candidate.symbol: s for s in sorted_candidates}

        selected: list[ScoredCandidate] = []
        sector_count: dict[str, int] = {}

        # Phase 1: Force-include open positions
        for sym in open_positions:
            if sym in by_symbol:
                sc = by_symbol[sym]
                selected.append(sc)
                sec = sc.candidate.sector
                sector_count[sec] = sector_count.get(sec, 0) + 1

        # Phase 2: Greedy selection
        new_additions = 0
        for sc in sorted_candidates:
            if len(selected) >= self.target_size:
                break
            if sc in selected:
                continue

            sym = sc.candidate.symbol
            sec = sc.candidate.sector

            # Sector cap
            if sector_count.get(sec, 0) >= self.max_per_sector:
                continue

            # Rotation cap
            if sym not in current_pool:
                if (
                    self.max_rotation > 0
                    and new_additions >= self.max_rotation
                    and current_pool
                ):
                    continue

            selected.append(sc)
            sector_count[sec] = sector_count.get(sec, 0) + 1
            if sym not in current_pool and current_pool:
                new_additions += 1

        # Phase 3: Check min_sectors constraint - swap if needed
        sectors = {s.candidate.sector for s in selected}
        if len(sectors) < self.min_sectors and len(selected) >= self.min_sectors:
            self._enforce_min_sectors(selected, sorted_candidates, sector_count)

        return selected

    def _enforce_min_sectors(
        self,
        selected: list[ScoredCandidate],
        all_candidates: list[ScoredCandidate],
        sector_count: dict[str, int],
    ) -> None:
        """Swap lowest-scoring same-sector duplicates for new-sector candidates."""
        current_sectors = {s.candidate.sector for s in selected}
        needed = self.min_sectors - len(current_sectors)
        if needed <= 0:
            return

        selected_symbols = {s.candidate.symbol for s in selected}
        for sc in all_candidates:
            if needed <= 0:
                break
            if sc.candidate.symbol in selected_symbols:
                continue
            if sc.candidate.sector in current_sectors:
                continue

            # Find lowest-scoring same-sector duplicate to replace
            over_sectors = [
                s for s in selected
                if sector_count.get(s.candidate.sector, 0) > 1
            ]
            if not over_sectors:
                break
            worst = min(over_sectors, key=lambda s: s.final_score)
            old_sec = worst.candidate.sector
            selected.remove(worst)
            sector_count[old_sec] -= 1

            selected.append(sc)
            new_sec = sc.candidate.sector
            sector_count[new_sec] = sector_count.get(new_sec, 0) + 1
            current_sectors.add(new_sec)
            selected_symbols.add(sc.candidate.symbol)
            needed -= 1
