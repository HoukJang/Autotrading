"""RuntimeState: unified persistence for ephemeral trading state.

Saves/loads snapshots from all stateful components to a single JSON file
using atomic writes (tmp + fsync + replace) for crash safety.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger("autotrader.state.runtime_state")

DEFAULT_PATH = Path("data/state/runtime_state.json")


class Snapshottable(Protocol):
    """Protocol for components that support snapshot persistence."""

    def to_snapshot(self) -> dict: ...
    def from_snapshot(self, data: dict) -> None: ...


class RuntimeState:
    """Unified persistence for all ephemeral runtime state."""

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self._path = path

    def save(self, components: dict[str, Snapshottable]) -> None:
        """Atomically save all component snapshots to disk."""
        payload: dict[str, Any] = {}
        for name, component in components.items():
            try:
                payload[name] = component.to_snapshot()
            except Exception:
                logger.exception("Failed to snapshot component: %s", name)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp_path), str(self._path))
            logger.debug("RuntimeState saved (%d components)", len(payload))
        except Exception:
            logger.exception("Failed to save RuntimeState")

    def load(self) -> dict[str, dict]:
        """Load persisted snapshots from disk.

        Returns:
            dict mapping component name -> snapshot dict.
            Empty dict if file doesn't exist or is corrupted.
        """
        if not self._path.exists():
            logger.info(
                "No RuntimeState file found at %s (first run or bootstrap needed)",
                self._path,
            )
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            logger.info(
                "RuntimeState loaded (%d components) from %s",
                len(data),
                self._path,
            )
            return data
        except Exception:
            logger.exception("Failed to load RuntimeState from %s", self._path)
            return {}

    def restore(
        self,
        components: dict[str, Snapshottable],
        snapshots: dict[str, dict],
    ) -> None:
        """Restore component state from loaded snapshots."""
        for name, component in components.items():
            snap = snapshots.get(name)
            if snap:
                try:
                    component.from_snapshot(snap)
                    logger.info("Restored state for component: %s", name)
                except Exception:
                    logger.exception("Failed to restore component: %s", name)

    @property
    def exists(self) -> bool:
        """Return True if the persisted state file exists on disk."""
        return self._path.exists()


# ---------------------------------------------------------------------------
# Broker state bootstrap (Step 1-6)
# ---------------------------------------------------------------------------

from autotrader.trading.types import HeldPosition


async def bootstrap_from_broker(
    broker: Any,
    ledger: Any = None,
    state_path: Path = DEFAULT_PATH,
) -> dict[str, HeldPosition]:
    """Bootstrap runtime state from broker's actual positions and orders.

    Called on first run or when runtime_state.json is missing.
    Queries broker for current positions and recent orders,
    constructs HeldPosition objects, and optionally populates OrderLedger.

    Args:
        broker: BrokerAdapter instance (must have get_positions, get_account).
        ledger: Optional OrderLedger to populate with recent order history.
        state_path: Path for the runtime state file.

    Returns:
        dict mapping symbol -> HeldPosition for currently held positions.
    """
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    _ET = ZoneInfo("America/New_York")
    today_et = datetime.now(timezone.utc).astimezone(_ET).date()
    positions: dict[str, HeldPosition] = {}

    try:
        broker_positions = await broker.get_positions()
    except Exception:
        logger.exception("Bootstrap: failed to fetch broker positions")
        return positions

    if not broker_positions:
        logger.info("Bootstrap: no positions at broker")
        return positions

    logger.info("Bootstrap: found %d positions at broker", len(broker_positions))

    for pos in broker_positions:
        try:
            held = HeldPosition(
                symbol=pos.symbol,
                strategy="unknown",  # cannot determine from broker data
                direction="long" if pos.side == "long" else "short",
                entry_price=pos.avg_entry_price,
                entry_atr=1.0,  # default; will be updated on next indicator computation
                entry_date_et=today_et,  # approximation
                qty=pos.quantity,
            )
            positions[pos.symbol] = held
            logger.info(
                "Bootstrap: registered %s %s @ %.2f (qty=%.0f)",
                held.direction,
                held.symbol,
                held.entry_price,
                held.qty,
            )
        except Exception:
            logger.exception(
                "Bootstrap: failed to register position for %s", pos.symbol
            )

    # Populate OrderLedger with recent orders if provided
    if ledger is not None:
        try:
            # Note: OrderLedger population from broker orders would require
            # broker.get_recent_orders() which may need to be added to the adapter.
            # For now, positions are registered without historical order records.
            logger.info(
                "Bootstrap: OrderLedger population from broker history not yet implemented"
            )
        except Exception:
            logger.exception("Bootstrap: failed to populate OrderLedger")

    return positions
