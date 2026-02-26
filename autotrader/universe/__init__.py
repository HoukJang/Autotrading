from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class StockInfo:
    symbol: str
    sector: str
    sub_industry: str


@dataclass
class StockCandidate:
    symbol: str
    sector: str
    close: float
    avg_dollar_volume: float
    avg_volume: float
    atr_ratio: float
    gap_frequency: float
    trend_pct: float
    range_pct: float
    vol_cycle: float


@dataclass
class ScoredCandidate:
    candidate: StockCandidate
    proxy_score: float
    backtest_score: float
    final_score: float


@dataclass
class UniverseResult:
    symbols: list[str]
    scored: list[ScoredCandidate]
    timestamp: datetime
    rotation_in: list[str] = field(default_factory=list)
    rotation_out: list[str] = field(default_factory=list)
