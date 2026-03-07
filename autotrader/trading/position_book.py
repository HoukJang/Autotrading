"""PositionBook: single source of truth for all held positions.

Replaces the 4 parallel tracking systems that previously diverged:
- AutoTrader._held_positions
- PositionMonitor._positions
- OpenPositionTracker._positions
- AutoTrader._position_strategy_map
"""
from __future__ import annotations

import logging
from typing import Iterator

from autotrader.trading.types import HeldPosition
from autotrader.trading.constants import MAX_TOTAL_POSITIONS

logger = logging.getLogger("autotrader.trading.position_book")


class PositionBook:
    """Centralized position registry -- single source of truth."""

    def __init__(self) -> None:
        self._positions: dict[str, HeldPosition] = {}

    def add(self, held: HeldPosition) -> bool:
        """Register a new position. Returns False if at capacity or duplicate."""
        if held.symbol in self._positions:
            logger.warning("PositionBook: duplicate add for %s ignored", held.symbol)
            return False
        if len(self._positions) >= MAX_TOTAL_POSITIONS:
            logger.warning(
                "PositionBook: MAX_POSITIONS (%d) reached, cannot add %s",
                MAX_TOTAL_POSITIONS, held.symbol,
            )
            return False
        self._positions[held.symbol] = held
        logger.info(
            "PositionBook: added %s %s (strategy=%s, entry=%.2f, qty=%.0f)",
            held.direction, held.symbol, held.strategy, held.entry_price, held.qty,
        )
        return True

    def remove(self, symbol: str) -> HeldPosition | None:
        """Remove and return a position. Returns None if not found."""
        held = self._positions.pop(symbol, None)
        if held:
            logger.info("PositionBook: removed %s", symbol)
        return held

    def get(self, symbol: str) -> HeldPosition | None:
        """Get a position by symbol (non-destructive)."""
        return self._positions.get(symbol)

    def has(self, symbol: str) -> bool:
        return symbol in self._positions

    @property
    def symbols(self) -> list[str]:
        return list(self._positions.keys())

    @property
    def count(self) -> int:
        return len(self._positions)

    def by_strategy(self, strategy: str) -> list[HeldPosition]:
        """Get all positions for a given strategy."""
        return [p for p in self._positions.values() if p.strategy == strategy]

    def strategy_map(self) -> dict[str, str]:
        """Return symbol -> strategy mapping (replaces _position_strategy_map)."""
        return {sym: p.strategy for sym, p in self._positions.items()}

    def all_positions(self) -> list[HeldPosition]:
        """Return all held positions."""
        return list(self._positions.values())

    def __iter__(self) -> Iterator[HeldPosition]:
        return iter(self._positions.values())

    def __len__(self) -> int:
        return len(self._positions)

    def __contains__(self, symbol: str) -> bool:
        return symbol in self._positions

    # -- Snapshot for RuntimeState persistence --

    def to_snapshot(self) -> dict:
        """Serialize all positions for persistence."""
        result = {}
        for sym, held in self._positions.items():
            result[sym] = {
                "symbol": held.symbol,
                "strategy": held.strategy,
                "direction": held.direction,
                "entry_price": held.entry_price,
                "entry_atr": held.entry_atr,
                "entry_date_et": held.entry_date_et.isoformat(),
                "qty": held.qty,
                "bars_held": held.bars_held,
                "highest_price": held.highest_price,
                "lowest_price": held.lowest_price,
                "consecutive_loss_bars": held.consecutive_loss_bars,
                "entry_adx": held.entry_adx,
                "_entry_time": held._entry_time.isoformat() if held._entry_time else None,
            }
        return result

    def from_snapshot(self, data: dict) -> None:
        """Restore positions from persisted snapshot."""
        from datetime import date, datetime
        self._positions.clear()
        for sym, rec in data.items():
            try:
                held = HeldPosition(
                    symbol=rec["symbol"],
                    strategy=rec.get("strategy", "unknown"),
                    direction=rec.get("direction", "long"),
                    entry_price=float(rec["entry_price"]),
                    entry_atr=float(rec.get("entry_atr", 1.0)),
                    entry_date_et=date.fromisoformat(rec["entry_date_et"]),
                    qty=float(rec.get("qty", 0)),
                )
                held.bars_held = int(rec.get("bars_held", 0))
                held.highest_price = float(rec.get("highest_price", held.entry_price))
                held.lowest_price = float(rec.get("lowest_price", held.entry_price))
                held.consecutive_loss_bars = int(rec.get("consecutive_loss_bars", 0))
                held.entry_adx = float(rec.get("entry_adx", 0.0))
                raw_entry_time = rec.get("_entry_time")
                if raw_entry_time is not None:
                    held._entry_time = datetime.fromisoformat(raw_entry_time)
                self._positions[sym] = held
            except Exception:
                logger.exception("PositionBook: failed to restore position for %s", sym)

    # -- Backward compatibility --

    def update_prices(self, symbol: str, high: float, low: float, close: float) -> None:
        """Update MFE/MAE tracking for a position (compat with OpenPositionTracker)."""
        pos = self._positions.get(symbol)
        if pos:
            pos.update_price_extremes(high, low)

    def close_position(self, symbol: str) -> HeldPosition | None:
        """Alias for remove() (compat with OpenPositionTracker)."""
        return self.remove(symbol)

    def has_position(self, symbol: str) -> bool:
        """Alias for has() (compat with OpenPositionTracker)."""
        return self.has(symbol)

    def get_position(self, symbol: str) -> HeldPosition | None:
        """Alias for get() (compat with OpenPositionTracker)."""
        return self.get(symbol)

    @property
    def open_symbols(self) -> list[str]:
        """Alias for symbols (compat with OpenPositionTracker)."""
        return self.symbols
