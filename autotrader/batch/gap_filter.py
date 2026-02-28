"""GapFilter: filters out candidates with large pre-market price gaps.

Runs at 9:25 AM ET (5 minutes before market open) to check pre-market
prices for the 12 ranked candidates from NightlyScanner.

Gap definition:
    gap_pct = (pre_market_price - prev_close) / prev_close

Filter rule:
    - Gap > +3% -> filter out (gapped up excessively, entry too late)
    - Gap < -3% -> filter out (gapped down, potential bad news)
    - |gap| <= 3% -> keep
    - Pre-market data unavailable -> KEEP (conservative default)

The 3% threshold is configurable via the constructor.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from autotrader.batch.types import Candidate, FilteredCandidate

if TYPE_CHECKING:
    from autotrader.data.batch_fetcher import BatchFetcher

logger = logging.getLogger(__name__)

# Default gap threshold (absolute value)
_DEFAULT_GAP_THRESHOLD = 0.03


class GapFilter:
    """Filters ranked candidates based on pre-market price gaps.

    Fetches the latest available quote for each candidate symbol
    and rejects those whose pre-market move exceeds the configured
    threshold against the previous close stored in the ScanResult.

    Usage::

        gap_filter = GapFilter(fetcher, gap_threshold=0.03)
        filtered = await gap_filter.filter(candidates)
    """

    def __init__(
        self,
        fetcher: "BatchFetcher",
        gap_threshold: float = _DEFAULT_GAP_THRESHOLD,
    ) -> None:
        """
        Args:
            fetcher: BatchFetcher instance used to get latest quotes.
            gap_threshold: Maximum absolute gap fraction allowed (default 0.03 = 3%).
        """
        self._fetcher = fetcher
        self._gap_threshold = gap_threshold

    async def filter(self, candidates: list[Candidate]) -> list[FilteredCandidate]:
        """Filter candidates by pre-market gap at ~9:25 AM ET.

        Fetches latest quotes for all candidate symbols concurrently,
        then applies the gap filter to each.

        Args:
            candidates: Ranked list from SignalRanker (up to 12).

        Returns:
            List of FilteredCandidate objects.  Only those with
            passed_filter=True should be used for live trading.
            Candidates with unavailable quotes are included with
            passed_filter=True and gap_pct=None.
        """
        if not candidates:
            return []

        symbols = [c.symbol for c in candidates]
        logger.info("GapFilter: fetching latest quotes for %d candidates", len(symbols))

        # Fetch latest quotes for all candidates in one batch call
        try:
            latest_prices = await self._fetcher.fetch_latest_quotes(symbols)
        except Exception:
            logger.exception("GapFilter: failed to fetch latest quotes; keeping all candidates")
            return [FilteredCandidate(candidate=c, passed_filter=True) for c in candidates]

        filtered: list[FilteredCandidate] = []
        kept = 0
        removed = 0

        for candidate in candidates:
            sym = candidate.symbol
            prev_close = candidate.prev_close
            pre_market_price = latest_prices.get(sym)

            # No quote data available -> keep the candidate
            if pre_market_price is None or pre_market_price <= 0:
                logger.debug(
                    "GapFilter: %s -> no quote data, keeping (prev_close=%.2f)",
                    sym,
                    prev_close,
                )
                filtered.append(
                    FilteredCandidate(
                        candidate=candidate,
                        pre_market_price=None,
                        gap_pct=None,
                        passed_filter=True,
                        filter_reason="no_quote_data",
                    )
                )
                kept += 1
                continue

            # No previous close available (should not happen) -> keep
            if prev_close <= 0:
                logger.warning(
                    "GapFilter: %s has no prev_close, keeping unconditionally", sym
                )
                filtered.append(
                    FilteredCandidate(
                        candidate=candidate,
                        pre_market_price=pre_market_price,
                        gap_pct=None,
                        passed_filter=True,
                        filter_reason="no_prev_close",
                    )
                )
                kept += 1
                continue

            gap_pct = (pre_market_price - prev_close) / prev_close

            if abs(gap_pct) > self._gap_threshold:
                direction_word = "up" if gap_pct > 0 else "down"
                reason = f"gap_{direction_word}_{abs(gap_pct)*100:.1f}pct"
                logger.info(
                    "GapFilter: %s REMOVED -- gapped %s %.2f%% "
                    "(prev_close=%.2f, pre_market=%.2f)",
                    sym,
                    direction_word,
                    abs(gap_pct) * 100,
                    prev_close,
                    pre_market_price,
                )
                filtered.append(
                    FilteredCandidate(
                        candidate=candidate,
                        pre_market_price=pre_market_price,
                        gap_pct=gap_pct,
                        passed_filter=False,
                        filter_reason=reason,
                    )
                )
                removed += 1
            else:
                logger.debug(
                    "GapFilter: %s KEPT -- gap=%.2f%% "
                    "(prev_close=%.2f, pre_market=%.2f)",
                    sym,
                    gap_pct * 100,
                    prev_close,
                    pre_market_price,
                )
                filtered.append(
                    FilteredCandidate(
                        candidate=candidate,
                        pre_market_price=pre_market_price,
                        gap_pct=gap_pct,
                        passed_filter=True,
                    )
                )
                kept += 1

        logger.info(
            "GapFilter complete: %d kept, %d removed (threshold=%.1f%%)",
            kept,
            removed,
            self._gap_threshold * 100,
        )
        return filtered
