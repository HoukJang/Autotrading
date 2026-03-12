"""RuntimeState: unified persistence for ephemeral trading state.

Saves/loads snapshots from all stateful components to a single JSON file
using atomic writes (tmp + fsync + replace) for crash safety.

Phase 5 enhancement: dual-write to SQLite component_state table via
StateStore, with JSON kept as backup.  SQLite is tried first on load,
falling back to JSON when the database is empty or unavailable.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from autotrader.data.state_store import StateStore

logger = logging.getLogger("autotrader.state.runtime_state")

DEFAULT_PATH = Path("data/state/runtime_state.json")

# Components that are persisted elsewhere and should NOT go into
# the component_state table (they are already in dedicated tables).
_SQLITE_EXCLUDED_COMPONENTS = frozenset({"position_book"})


class Snapshottable(Protocol):
    """Protocol for components that support snapshot persistence."""

    def to_snapshot(self) -> dict: ...
    def from_snapshot(self, data: dict) -> None: ...


class RuntimeState:
    """Unified persistence for all ephemeral runtime state."""

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self._path = path
        self._store: StateStore | None = None

    def set_state_store(self, store: "StateStore") -> None:
        """Attach a StateStore for SQLite dual-write persistence."""
        self._store = store

    def save(self, components: dict[str, Snapshottable]) -> None:
        """Dual-write: save to SQLite first, then JSON as backup."""
        payload: dict[str, Any] = {}
        for name, component in components.items():
            try:
                payload[name] = component.to_snapshot()
            except Exception:
                logger.exception("Failed to snapshot component: %s", name)

        # --- SQLite write (primary) ---
        if self._store is not None:
            try:
                sqlite_payload = {
                    k: v for k, v in payload.items()
                    if k not in _SQLITE_EXCLUDED_COMPONENTS
                }
                self._store.save_all_component_states(sqlite_payload)
                logger.debug(
                    "RuntimeState saved to SQLite (%d components)",
                    len(sqlite_payload),
                )
            except Exception:
                logger.exception("Failed to save RuntimeState to SQLite")

        # --- JSON write (backup) ---
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp_path), str(self._path))
            logger.debug("RuntimeState saved to JSON (%d components)", len(payload))
        except Exception:
            logger.exception("Failed to save RuntimeState to JSON")

    def load(self) -> dict[str, dict]:
        """Load persisted snapshots: try SQLite first, fallback to JSON.

        Returns:
            dict mapping component name -> snapshot dict.
            Empty dict if no data is available.
        """
        # --- Try SQLite first ---
        if self._store is not None:
            try:
                db_data = self._store.load_component_states()
                if db_data:
                    logger.info(
                        "RuntimeState loaded from SQLite (%d components)",
                        len(db_data),
                    )
                    return db_data
            except Exception:
                logger.exception("Failed to load RuntimeState from SQLite")

        # --- Fallback to JSON ---
        if not self._path.exists():
            logger.info(
                "No RuntimeState file found at %s (first run or bootstrap needed)",
                self._path,
            )
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            logger.info(
                "RuntimeState loaded from JSON (%d components) from %s",
                len(data),
                self._path,
            )
            # Migrate JSON data to SQLite for future loads
            if self._store is not None and data:
                try:
                    sqlite_payload = {
                        k: v for k, v in data.items()
                        if k not in _SQLITE_EXCLUDED_COMPONENTS
                    }
                    self._store.save_all_component_states(sqlite_payload)
                    logger.info(
                        "Migrated %d components from JSON to SQLite",
                        len(sqlite_payload),
                    )
                except Exception:
                    logger.exception("Failed to migrate RuntimeState to SQLite")
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
        """Return True if persisted state exists (SQLite or JSON)."""
        if self._store is not None:
            try:
                db_data = self._store.load_component_states()
                if db_data:
                    return True
            except Exception:
                pass
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
