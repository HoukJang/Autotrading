"""SignalRanker: ranks scan results and selects the top N candidates.

Composite scoring formula:
    composite = signal_strength * 0.6
              + regime_compatibility * 0.3
              + sector_diversity_bonus * 0.1

Sector diversification:
    Candidates from sectors already well-represented in the top-N receive
    a lower sector_diversity_bonus so that the final list covers multiple
    GICS sectors rather than clustering in a single hot sector.

Strategy diversity bonus (added on top of composite):
    Strategies with 0 open positions: +0.25
    Strategies with 1 open position:  +0.10
    Strategies with 2+ open positions: no bonus

Tie-breaking:
    When composite scores are equal, higher signal_strength wins.
    When signal_strength is also equal, alphabetical symbol order wins
    (deterministic output regardless of map iteration order).
"""
from __future__ import annotations

import logging
from collections import Counter

from autotrader.batch.types import Candidate, ScanResult

logger = logging.getLogger(__name__)

# Weights for composite score components (must sum to 1.0)
_WEIGHT_SIGNAL = 0.6
_WEIGHT_REGIME = 0.3
_WEIGHT_SECTOR = 0.1

# Maximum candidates returned by rank()
_DEFAULT_TOP_N = 12

# Sector penalty: each additional candidate from the same sector reduces
# the sector_diversity_bonus by this fraction (clamped to 0).
_SECTOR_PENALTY_STEP = 0.25

# Regime compatibility scores per strategy/direction combination
# (strategy, direction) -> float in [0.0, 1.0]
_REGIME_COMPAT: dict[tuple[str, str], float] = {
    # Mean-reversion strategies
    ("rsi_mean_reversion", "long"): 0.80,
    ("rsi_mean_reversion", "short"): 0.80,
    ("consecutive_down", "long"): 0.80,
    # Trend-continuation
    ("ema_pullback", "long"): 0.90,
}

# Default compatibility score for unknown (strategy, direction) combinations
_DEFAULT_COMPAT = 0.60


def _regime_compatibility(scan_result: ScanResult) -> float:
    """Return a regime compatibility score in [0.0, 1.0] for a scan result.

    Uses the strategy name and direction to look up a preset compatibility
    score. ADX value from indicators can boost the score for trend strategies.
    """
    base = _REGIME_COMPAT.get(
        (scan_result.strategy, scan_result.direction), _DEFAULT_COMPAT
    )

    # Boost ema_pullback when ADX is strong (> 25) -- trend continuation
    if scan_result.direction == "long" and scan_result.strategy == "ema_pullback":
        adx = scan_result.indicators.get("ADX_14")
        if isinstance(adx, (int, float)) and adx > 25:
            boost = min(0.05, (adx - 25) / 200)  # up to +5% boost
            base = min(1.0, base + boost)

    return base


class SignalRanker:
    """Ranks ScanResult objects and returns top-N Candidate instances.

    Usage::

        ranker = SignalRanker(top_n=12)
        candidates = ranker.rank(scan_results, sector_map)
    """

    def __init__(self, top_n: int = _DEFAULT_TOP_N) -> None:
        self._top_n = top_n

    def rank(
        self,
        scan_results: list[ScanResult],
        sector_map: dict[str, str] | None = None,
        current_positions: list | None = None,
    ) -> list[Candidate]:
        """Rank scan results and return the top-N candidates.

        Args:
            scan_results: List of scan results from NightlyScanner.
            sector_map: Optional mapping of symbol -> GICS sector name.
                        Missing symbols default to "Unknown".
            current_positions: Optional list of objects with a ``strategy``
                attribute representing currently held positions.  Used to
                compute the strategy diversity bonus: strategies with fewer
                open positions receive a higher composite score bonus.

        Returns:
            List of Candidate objects sorted by composite_score descending,
            length <= top_n, with rank attribute set (1 = best).
        """
        if not scan_results:
            return []

        sm = sector_map or {}

        # Step 1: Build initial Candidate objects with regime compatibility
        candidates: list[Candidate] = []
        for sr in scan_results:
            compat = _regime_compatibility(sr)
            sector = sm.get(sr.symbol, "Unknown")
            cand = Candidate(
                scan_result=sr,
                regime_compatibility=compat,
                sector=sector,
            )
            candidates.append(cand)

        # Step 2: Pre-sort by signal_strength descending (needed for sector penalty)
        candidates.sort(
            key=lambda c: (-c.signal_strength, c.symbol)
        )

        # Step 3: Assign sector diversity bonuses.
        # Walk candidates in signal_strength order; track how many from each
        # sector have already been assigned a bonus to compute penalties.
        sector_counts: Counter[str] = Counter()
        for cand in candidates:
            sector_count = sector_counts[cand.sector]
            # Bonus decreases as more candidates from the same sector appear
            sector_bonus = max(0.0, 1.0 - sector_count * _SECTOR_PENALTY_STEP)
            sector_counts[cand.sector] += 1

            composite = (
                _WEIGHT_SIGNAL * cand.signal_strength
                + _WEIGHT_REGIME * cand.regime_compatibility
                + _WEIGHT_SECTOR * sector_bonus
            )
            cand.composite_score = composite

        # Step 4: Apply strategy diversity bonus based on current open positions.
        # Strategies with no open positions get +0.25; strategies with one
        # open position get +0.10; strategies with two or more get no bonus.
        # This encourages diversification across strategies.
        if current_positions is not None:
            strategy_position_counts: dict[str, int] = {}
            for pos in current_positions:
                strat = getattr(pos, "strategy", None)
                if strat is not None:
                    strategy_position_counts[strat] = strategy_position_counts.get(strat, 0) + 1
            for cand in candidates:
                pos_count = strategy_position_counts.get(cand.strategy, 0)
                if pos_count == 0:
                    cand.composite_score += 0.25
                elif pos_count == 1:
                    cand.composite_score += 0.10

        # Step 5: Final sort by composite score, tie-break on signal_strength,
        # then symbol for determinism.
        candidates.sort(
            key=lambda c: (-c.composite_score, -c.signal_strength, c.symbol)
        )

        # Step 6: Select top-N and assign ranks
        top = candidates[: self._top_n]
        for i, cand in enumerate(top, start=1):
            cand.rank = i

        logger.info(
            "SignalRanker: %d scan results -> %d candidates (top_n=%d)",
            len(scan_results),
            len(top),
            self._top_n,
        )
        for cand in top:
            logger.debug(
                "  Rank %2d: %-6s %-22s %-5s strength=%.3f compat=%.3f composite=%.4f sector=%s",
                cand.rank,
                cand.symbol,
                cand.strategy,
                cand.direction,
                cand.signal_strength,
                cand.regime_compatibility,
                cand.composite_score,
                cand.sector,
            )

        return top
