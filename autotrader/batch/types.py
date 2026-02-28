"""Shared data types for the nightly batch pipeline.

These types are used across scanner, ranker, gap_filter, and scheduler
modules to pass structured data through the pipeline stages.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ScanResult:
    """Result for a single symbol from the nightly scan.

    Attributes:
        symbol: Trading symbol (e.g., "AAPL").
        strategy: Name of the strategy that generated the signal.
        direction: Trade direction - "long" or "short".
        signal_strength: Signal confidence score in [0.0, 1.0].
        indicators: Key indicator values at scan time.
        prev_close: Previous session closing price.
        scanned_at: UTC timestamp when scan was performed.
        metadata: Additional signal metadata from the strategy.
    """

    symbol: str
    strategy: str
    direction: str  # "long" or "short"
    signal_strength: float
    indicators: dict[str, float | dict | None] = field(default_factory=dict)
    prev_close: float = 0.0
    scanned_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate:
    """A ranked candidate ready for gap-filter and live trading.

    Attributes:
        scan_result: The underlying scan result from NightlyScanner.
        composite_score: Weighted composite score for ranking.
        regime_compatibility: How compatible this signal is with current regime (0-1).
        sector: GICS sector classification for diversification.
        rank: Final rank position (1 = best).
    """

    scan_result: ScanResult
    composite_score: float = 0.0
    regime_compatibility: float = 0.0
    sector: str = "Unknown"
    rank: int = 0

    @property
    def symbol(self) -> str:
        return self.scan_result.symbol

    @property
    def strategy(self) -> str:
        return self.scan_result.strategy

    @property
    def direction(self) -> str:
        return self.scan_result.direction

    @property
    def signal_strength(self) -> float:
        return self.scan_result.signal_strength

    @property
    def prev_close(self) -> float:
        return self.scan_result.prev_close


@dataclass
class BatchResult:
    """Complete result of a nightly batch run, saved to disk for dashboard use.

    Attributes:
        run_at: UTC timestamp when the batch run completed.
        scan_duration_secs: How long the scan took in seconds.
        symbols_scanned: Total number of symbols processed.
        symbols_with_signals: Number of symbols that generated at least one signal.
        candidates: Ranked list of candidates (up to 12).
        errors: List of symbols/errors that failed during scan.
        regime: Detected market regime at scan time.
    """

    run_at: datetime
    scan_duration_secs: float
    symbols_scanned: int
    symbols_with_signals: int
    candidates: list[Candidate] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    regime: str = "UNCERTAIN"

    def to_dict(self) -> dict:
        """Serialize to a JSON-serializable dict for dashboard consumption."""
        return {
            "run_at": self.run_at.isoformat(),
            "scan_duration_secs": round(self.scan_duration_secs, 2),
            "symbols_scanned": self.symbols_scanned,
            "symbols_with_signals": self.symbols_with_signals,
            "regime": self.regime,
            "candidates": [
                {
                    "rank": c.rank,
                    "symbol": c.symbol,
                    "strategy": c.strategy,
                    "direction": c.direction,
                    "signal_strength": round(c.signal_strength, 4),
                    "composite_score": round(c.composite_score, 4),
                    "regime_compatibility": round(c.regime_compatibility, 4),
                    "sector": c.sector,
                    "prev_close": c.prev_close,
                    "indicators": {
                        k: (round(v, 4) if isinstance(v, float) else v)
                        for k, v in c.scan_result.indicators.items()
                        if v is not None
                    },
                    "metadata": c.scan_result.metadata,
                    "scanned_at": c.scan_result.scanned_at.isoformat(),
                }
                for c in self.candidates
            ],
            "errors": self.errors,
        }


@dataclass
class FilteredCandidate:
    """A candidate that passed the 9:25 AM gap filter check.

    Attributes:
        candidate: The underlying ranked candidate.
        pre_market_price: Price observed at gap-filter time (None if unavailable).
        gap_pct: Gap percentage from previous close (None if unavailable).
        passed_filter: Whether the candidate passed the gap filter.
        filter_reason: Human-readable reason if filtered out.
    """

    candidate: Candidate
    pre_market_price: float | None = None
    gap_pct: float | None = None
    passed_filter: bool = True
    filter_reason: str = ""

    @property
    def symbol(self) -> str:
        return self.candidate.symbol
