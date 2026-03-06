"""BatchPipelineOrchestrator: batch scan -> gap filter -> entry pipeline.

Extracted from AutoTrader.main to decompose the god class.
Owns the batch pipeline event handlers that drive the nightly scan
through gap filter and into the EntryManager.

This class reads dependencies from a host context (the AutoTrader
instance) at call time, ensuring tests that monkey-patch attributes
on AutoTrader work transparently.
"""
from __future__ import annotations

import json
import logging
import os
from collections import deque
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from autotrader.batch.types import Candidate as BatchCandidate, FilteredCandidate
from autotrader.core.types import Bar, Signal
from autotrader.execution.entry_manager import Candidate as EntryCandidate
from autotrader.execution.exit_rules import HeldPosition
from autotrader.portfolio.regime_detector import MarketRegime

logger = logging.getLogger("autotrader.orchestration.batch_pipeline")


# ---------------------------------------------------------------------------
# Standalone conversion function (re-exported for backward compat)
# ---------------------------------------------------------------------------


def batch_to_entry_candidate(batch_cand: BatchCandidate) -> EntryCandidate:
    """Convert a batch pipeline Candidate to an EntryManager Candidate.

    The batch pipeline produces ``autotrader.batch.types.Candidate`` objects
    (with a nested ``ScanResult``), while the execution layer expects
    ``autotrader.execution.entry_manager.Candidate`` objects (with a
    ``Signal``).  This helper bridges the two representations.
    """
    sr = batch_cand.scan_result
    atr = sr.indicators.get("ATR_14", 1.0)
    if not isinstance(atr, (int, float)) or atr <= 0:
        atr = 1.0
    atr = float(atr)

    # Merge strategy metadata with entry_atr so that EntryManager can
    # place broker-side stop-loss orders using the actual ATR value.
    merged_metadata = dict(sr.metadata)
    merged_metadata["entry_atr"] = atr

    signal = Signal(
        strategy=sr.strategy,
        symbol=sr.symbol,
        direction=sr.direction,
        strength=sr.signal_strength,
        metadata=merged_metadata,
    )
    return EntryCandidate(
        signal=signal,
        prev_close=sr.prev_close,
        atr=atr,
        indicators=sr.indicators,
    )


# ---------------------------------------------------------------------------
# Host context protocol -- what AutoTrader must expose for the pipeline
# ---------------------------------------------------------------------------

@runtime_checkable
class BatchPipelineHost(Protocol):
    """Protocol describing the attributes the batch pipeline reads from its host.

    The AutoTrader class satisfies this protocol. Using a protocol avoids
    a circular import dependency between main.py and this module.
    """

    _entry_manager: Any
    _gap_filter: Any
    _nightly_scanner: Any
    _held_positions: dict[str, HeldPosition]
    _position_strategy_map: dict[str, str]
    _broker: Any
    _position_monitor: Any
    _open_position_tracker: Any
    _bar_history: dict[str, deque[Bar]]
    _trade_logger: Any
    _current_regime: MarketRegime


# ---------------------------------------------------------------------------
# BatchPipelineOrchestrator
# ---------------------------------------------------------------------------


class BatchPipelineOrchestrator:
    """Drives the batch scan -> gap filter -> entry pipeline.

    Extracted from AutoTrader to give the batch pipeline a single-
    responsibility home. Reads all mutable dependencies from the host
    (AutoTrader) at call time so that test monkey-patching works
    transparently.

    Args:
        host: The AutoTrader instance (or any object satisfying
              BatchPipelineHost protocol).
    """

    def __init__(self, host: Any) -> None:
        self._host = host
        # Batch result from nightly scan (populated by on_nightly_scan or load)
        self._last_batch_result: Any | None = None

    # --- Public property for last batch result ---

    @property
    def last_batch_result(self) -> Any | None:
        return self._last_batch_result

    @last_batch_result.setter
    def last_batch_result(self, value: Any) -> None:
        self._last_batch_result = value

    # ------------------------------------------------------------------
    # Batch pipeline event handlers
    # ------------------------------------------------------------------

    def load_last_batch_result(self) -> None:
        """Load the most recent batch result from disk if still fresh.

        On process restart, the in-memory ``_last_batch_result`` is lost.
        This method reconstructs it from ``data/batch_results.json`` when the
        file exists and was produced within the last 18 hours (nightly scan at
        8 PM, gap filter at 9:25 AM = ~13 h gap; 18 h provides safe margin).
        """
        results_path = os.path.join("data", "batch_results.json")
        if not os.path.exists(results_path):
            logger.debug("No batch_results.json found; skipping load")
            return

        try:
            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read batch_results.json: %s", exc)
            return

        # Check freshness: run_at must be within 18 hours of now
        run_at_str = data.get("run_at")
        if not run_at_str:
            logger.warning("batch_results.json missing run_at; skipping load")
            return

        try:
            run_at = datetime.fromisoformat(run_at_str)
            # Ensure timezone-aware comparison
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - run_at).total_seconds() / 3600
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid run_at in batch_results.json: %s", exc)
            return

        if age_hours > 18:
            logger.info(
                "batch_results.json is %.1f hours old (>18h); not loading stale result",
                age_hours,
            )
            return

        # Reconstruct minimal BatchResult-like object with .candidates
        raw_candidates = data.get("candidates", [])

        class _RestoredBatchResult:
            """Minimal stand-in satisfying the BatchResultProtocol (.candidates)."""

            def __init__(self, candidates: list[BatchCandidate]) -> None:
                self.candidates = candidates

        from autotrader.batch.types import ScanResult as _ScanResult

        candidates: list[BatchCandidate] = []
        for c in raw_candidates:
            try:
                scan_result = _ScanResult(
                    symbol=c["symbol"],
                    strategy=c["strategy"],
                    direction=c["direction"],
                    signal_strength=c.get("signal_strength", 0.0),
                    indicators=c.get("indicators", {}),
                    prev_close=c.get("prev_close", 0.0),
                    scanned_at=datetime.fromisoformat(c["scanned_at"]) if c.get("scanned_at") else datetime.now(timezone.utc),
                    metadata=c.get("metadata", {}),
                )
                candidate = BatchCandidate(
                    scan_result=scan_result,
                    composite_score=c.get("composite_score", 0.0),
                    regime_compatibility=c.get("regime_compatibility", 0.0),
                    sector=c.get("sector", "Unknown"),
                    rank=c.get("rank", 0),
                )
                candidates.append(candidate)
            except (KeyError, TypeError, ValueError) as exc:
                logger.debug("Skipping malformed candidate in batch_results.json: %s", exc)
                continue

        self._last_batch_result = _RestoredBatchResult(candidates)
        gap_statuses = [c.get("gap_filter_status", "N/A") for c in raw_candidates]
        logger.info(
            "[PIPELINE] Loaded %d candidates from batch_results.json (%.1f hours old), "
            "symbols=%s, gap_statuses=%s",
            len(candidates),
            age_hours,
            [c.symbol for c in candidates],
            gap_statuses,
        )

    async def on_gap_filter(self) -> None:
        """Apply gap filter to last batch result at 9:25 AM ET.

        Converts batch pipeline Candidates to EntryManager Candidates and
        loads them into the EntryManager for MOO execution at 9:30 AM.

        When no GapFilter is injected, all raw candidates pass through.
        When a GapFilter is present, only candidates with acceptable
        pre-market gaps are kept.  In both cases the surviving batch
        Candidates are converted to EntryManager Candidates and loaded.
        """
        logger.info(
            "[PIPELINE] on_gap_filter() CALLED -- last_batch_result=%s",
            type(self._last_batch_result).__name__ if self._last_batch_result else "None",
        )

        if self._last_batch_result is None:
            logger.info("[PIPELINE] Gap filter: no nightly batch result; skipping")
            return

        batch_candidates: list[BatchCandidate] = list(self._last_batch_result.candidates)
        if not batch_candidates:
            logger.info("[PIPELINE] Gap filter: no candidates in batch result")
            return

        logger.info(
            "[PIPELINE] Gap filter starting with %d candidates: %s",
            len(batch_candidates),
            [c.symbol for c in batch_candidates],
        )

        gap_filter = self._host._gap_filter
        entry_manager = self._host._entry_manager

        logger.debug(
            "[PIPELINE] gap_filter=%s, entry_manager=%s",
            type(gap_filter).__name__ if gap_filter else "None",
            type(entry_manager).__name__ if entry_manager else "None",
        )

        # Track filtered results for dashboard update
        filtered_results: list[FilteredCandidate] | None = None

        # Apply gap filter if available
        if gap_filter is not None:
            try:
                filtered_results = await gap_filter.filter(batch_candidates)
                passed = [fr.candidate for fr in filtered_results if fr.passed_filter]
                for fr in filtered_results:
                    logger.info(
                        "[PIPELINE] Gap filter result: %s -> %s (gap=%.2f%%, reason=%s)",
                        fr.symbol,
                        "PASSED" if fr.passed_filter else "FILTERED",
                        (fr.gap_pct or 0) * 100,
                        fr.filter_reason or "ok",
                    )
                logger.info(
                    "[PIPELINE] Gap filter summary: %d -> %d passed",
                    len(batch_candidates), len(passed),
                )
            except Exception:
                logger.exception("[PIPELINE] Gap filter execution failed; using all raw candidates")
                passed = batch_candidates
        else:
            logger.info(
                "[PIPELINE] Gap filter: no GapFilter injected; using all %d raw candidates",
                len(batch_candidates),
            )
            passed = batch_candidates

        # Convert batch candidates to entry manager candidates
        entry_candidates: list[EntryCandidate] = []
        for bc in passed:
            try:
                entry_candidates.append(batch_to_entry_candidate(bc))
                logger.debug("[PIPELINE] Converted candidate: %s", bc.symbol)
            except Exception:
                logger.warning("[PIPELINE] Failed to convert candidate %s; skipping", bc.symbol)

        # Load into EntryManager
        if entry_manager is not None and entry_candidates:
            entry_manager.load_candidates(entry_candidates)
            logger.info(
                "[PIPELINE] Gap filter complete: %d candidates loaded into EntryManager: %s",
                len(entry_candidates),
                [ec.signal.symbol for ec in entry_candidates],
            )
        elif not entry_candidates:
            logger.info("[PIPELINE] Gap filter: no candidates survived; nothing to load")

        # Update batch_results.json with gap filter status for dashboard
        passed_syms = {bc.symbol for bc in passed}
        logger.info("[PIPELINE] Updating batch_results.json: passed_symbols=%s", passed_syms)
        self._update_batch_results_gap_status(
            passed_symbols=passed_syms,
            filtered_results=filtered_results,
        )

    def _update_batch_results_gap_status(
        self,
        passed_symbols: set[str],
        filtered_results: list[FilteredCandidate] | None,
    ) -> None:
        """Update gap_filter_status in data/batch_results.json for the dashboard.

        Each candidate entry gets one of:
          - "passed"   -- kept by gap filter or no gap filter injected
          - "filtered" -- removed by gap filter (gap too large)
          - "pending"  -- unchanged (should not happen after this runs)

        If ``filtered_results`` is available (gap filter ran), the
        ``gap_pct`` field is also written for each candidate.
        """
        results_path = os.path.join("data", "batch_results.json")
        if not os.path.exists(results_path):
            logger.warning("[PIPELINE] batch_results.json not found; cannot update gap status")
            return

        try:
            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("[PIPELINE] Could not read batch_results.json for gap status update")
            return

        # Build a lookup from filtered_results for gap_pct info
        gap_info: dict[str, FilteredCandidate] = {}
        if filtered_results is not None:
            for fr in filtered_results:
                gap_info[fr.symbol] = fr

        candidates_list = data.get("candidates", [])

        # Build set of all symbols that went through gap filter (passed or not)
        memory_symbols: set[str] = set(passed_symbols)
        if filtered_results is not None:
            for fr in filtered_results:
                memory_symbols.add(fr.symbol)

        # Safety: if memory_symbols is empty, gap filter didn't actually run --
        # refuse to overwrite disk state to prevent false "filtered" marking
        if not memory_symbols:
            logger.warning(
                "[PIPELINE] ABORT: memory_symbols is empty -- gap filter did not process "
                "any candidates. Refusing to overwrite batch_results.json to prevent "
                "false 'filtered' marking. candidates_on_disk=%d",
                len(candidates_list),
            )
            return

        disk_symbols = {c.get("symbol", "") for c in candidates_list}

        # Check for mismatch between disk and memory candidate lists
        only_in_disk = disk_symbols - memory_symbols
        if only_in_disk:
            logger.warning(
                "[PIPELINE] MISMATCH: symbols in batch_results.json but not in memory: %s "
                "(keeping existing status to prevent false 'filtered' marking)",
                only_in_disk,
            )

        logger.info(
            "[PIPELINE] Updating %d candidates in batch_results.json, passed_symbols=%s",
            len(candidates_list), passed_symbols,
        )
        for cand_dict in candidates_list:
            sym = cand_dict.get("symbol", "")
            old_status = cand_dict.get("gap_filter_status", "unknown")

            # Skip symbols not in memory -- don't overwrite their status
            if sym in only_in_disk:
                logger.info(
                    "[PIPELINE] Gap status: %s: UNCHANGED (not in current memory batch)",
                    sym,
                )
                continue

            if sym in passed_symbols:
                new_status = "passed"
            else:
                new_status = "filtered"
            cand_dict["gap_filter_status"] = new_status
            # Add gap percentage if available
            fr_info = gap_info.get(sym)
            gap_pct_str = "N/A"
            if fr_info is not None and fr_info.gap_pct is not None:
                cand_dict["gap_pct"] = round(fr_info.gap_pct * 100, 2)
                gap_pct_str = f"{fr_info.gap_pct * 100:.2f}%"
                if fr_info.pre_market_price is not None:
                    cand_dict["pre_market_price"] = round(fr_info.pre_market_price, 2)
            logger.info(
                "[PIPELINE] Gap status: %s: %s -> %s (gap=%s)",
                sym, old_status, new_status, gap_pct_str,
            )

        try:
            tmp_path = results_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, results_path)
            logger.info("[PIPELINE] Successfully wrote gap_filter_status to batch_results.json")
        except OSError:
            logger.warning("[PIPELINE] Could not write gap status to batch_results.json")

    def mark_candidates_skipped(self, reason: str = "outside_market_hours") -> None:
        """Mark all candidates in batch_results.json as skipped.

        Called when gap_filter fires outside market hours and cannot fetch
        live pre-market prices.  Updates every candidate's gap_filter_status
        to ``"skipped"`` so the dashboard shows a clear, non-ambiguous state
        instead of leaving them as ``"pending"``.
        """
        results_path = os.path.join("data", "batch_results.json")
        if not os.path.exists(results_path):
            logger.info("[PIPELINE] No batch_results.json to mark as skipped")
            return

        try:
            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning("[PIPELINE] Could not read batch_results.json for skip marking")
            return

        candidates_list = data.get("candidates", [])
        for cand_dict in candidates_list:
            old_status = cand_dict.get("gap_filter_status", "unknown")
            cand_dict["gap_filter_status"] = "skipped"
            cand_dict["gap_filter_reason"] = reason
            logger.info(
                "[PIPELINE] Gap skip: %s: %s -> skipped (%s)",
                cand_dict.get("symbol", "?"), old_status, reason,
            )

        try:
            tmp_path = results_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, results_path)
            logger.info(
                "[PIPELINE] Marked %d candidates as skipped in batch_results.json",
                len(candidates_list),
            )
        except OSError:
            logger.warning("[PIPELINE] Could not write skip status to batch_results.json")

    async def on_moo(self) -> None:
        """Execute Group A market-on-open orders at 9:30 AM ET."""
        logger.info("[PIPELINE] on_moo() CALLED")
        host = self._host
        entry_manager = host._entry_manager
        if entry_manager is None:
            logger.info("[PIPELINE] on_moo(): no entry_manager; skipping")
            return

        # Phase 1: Execute MOO -- if this fails, nothing was opened
        try:
            broker = host._broker
            account = await broker.get_account()
            positions = await broker.get_positions()
            today_et = datetime.now(timezone.utc).astimezone(
                __import__("zoneinfo", fromlist=["ZoneInfo"]).ZoneInfo("America/New_York")
            ).date()

            new_positions = await entry_manager.execute_moo(
                account=account,
                positions=positions,
                regime=host._current_regime,
                current_date_et=today_et,
            )
        except Exception:
            logger.exception("MOO execution failed")
            return

        # Phase 2: Record each position independently -- one failure must
        # not block recording of the remaining positions
        recorded_symbols: list[str] = []
        for held in new_positions:
            # Dedup guard: skip if symbol already tracked (prevents double registration)
            if held.symbol in host._held_positions:
                logger.critical(
                    "DEDUP GUARD: %s already in _held_positions -- skipping "
                    "registration to prevent double tracking (strategy=%s)",
                    held.symbol, held.strategy,
                )
                continue
            try:
                host._held_positions[held.symbol] = held
                host._position_strategy_map[held.symbol] = held.strategy
                if host._position_monitor is not None:
                    host._position_monitor.add_position(held)
                # Register with MFE/MAE tracker
                host._open_position_tracker.open_position(
                    symbol=held.symbol,
                    strategy=held.strategy,
                    direction=held.direction,
                    entry_price=held.entry_price,
                    entry_time=datetime.now(timezone.utc),
                    quantity=held.qty,
                )
                # Log entry trade to live_trades.jsonl
                await self._log_entry_trade(held, account)
                recorded_symbols.append(held.symbol)
            except Exception:
                logger.exception(
                    "Failed to record position for %s "
                    "(BROKER HAS POSITION - manual reconciliation needed)",
                    held.symbol,
                )

        # Phase 3: Post-recording housekeeping
        if recorded_symbols:
            try:
                await broker.add_bar_subscription(recorded_symbols, host._on_bar)
                logger.info(
                    "MOO entries: %d positions opened, subscribed: %s",
                    len(recorded_symbols), recorded_symbols,
                )
                await host._log_equity_snapshot()
            except Exception:
                logger.exception(
                    "Failed post-MOO housekeeping after recording %s",
                    recorded_symbols,
                )

    async def on_confirmation_window(self) -> None:
        """Execute Group B confirmation entries between 9:45 and 10:00 AM ET."""
        host = self._host
        entry_manager = host._entry_manager
        if entry_manager is None:
            return
        try:
            broker = host._broker
            account = await broker.get_account()
            positions = await broker.get_positions()
            today_et = datetime.now(timezone.utc).astimezone(
                __import__("zoneinfo", fromlist=["ZoneInfo"]).ZoneInfo("America/New_York")
            ).date()

            # Fetch current intraday prices for all pending Group B symbols
            current_prices = await host._fetch_current_prices()

            new_positions = await entry_manager.execute_confirmation(
                account=account,
                positions=positions,
                regime=host._current_regime,
                current_date_et=today_et,
                current_prices=current_prices,
            )
        except Exception:
            logger.exception("Confirmation window execution failed")
            return

        # Phase 2: Record each position independently -- one failure must
        # not block recording of the remaining positions
        new_symbols: list[str] = []
        for held in new_positions:
            if held.symbol in host._held_positions:
                logger.critical(
                    "DEDUP GUARD: %s already in _held_positions -- skipping "
                    "confirmation registration to prevent double tracking "
                    "(existing_strategy=%s, new_strategy=%s)",
                    held.symbol,
                    host._held_positions[held.symbol].strategy,
                    held.strategy,
                )
                continue
            try:
                host._held_positions[held.symbol] = held
                host._position_strategy_map[held.symbol] = held.strategy
                new_symbols.append(held.symbol)
                if host._position_monitor is not None:
                    host._position_monitor.add_position(held)
                host._open_position_tracker.open_position(
                    symbol=held.symbol,
                    strategy=held.strategy,
                    direction=held.direction,
                    entry_price=held.entry_price,
                    entry_time=datetime.now(timezone.utc),
                    quantity=held.qty,
                )
                # Log entry trade to live_trades.jsonl
                await self._log_entry_trade(held, account)
            except Exception:
                logger.exception(
                    "Failed to record confirmation position for %s "
                    "(BROKER HAS POSITION - manual reconciliation needed)",
                    held.symbol,
                )

        # Phase 3: Post-recording housekeeping
        if new_symbols:
            try:
                await broker.add_bar_subscription(new_symbols, host._on_bar)
                logger.info("Confirmation entries: %d positions opened, subscribed: %s", len(new_positions), new_symbols)
                await host._log_equity_snapshot()
            except Exception:
                logger.exception(
                    "Failed post-confirmation housekeeping after recording %s",
                    new_symbols,
                )

    async def on_entry_window_close(self) -> None:
        """Discard unconfirmed Group B candidates at 10:00 AM ET."""
        entry_manager = self._host._entry_manager
        if entry_manager is None:
            return
        discarded = entry_manager.close_entry_window()
        if discarded:
            logger.info("Entry window closed: %d candidates discarded", discarded)

    async def on_nightly_scan(self, refresh_daily_bars: Any = None) -> None:
        """Run the nightly batch scan at 8:00 PM ET.

        Args:
            refresh_daily_bars: Optional async callable to refresh bars before scan.
        """
        logger.info("[PIPELINE] on_nightly_scan() CALLED")
        # Refresh daily bars before running the scan for latest data
        if refresh_daily_bars is not None:
            logger.info("[PIPELINE] Refreshing daily bars before scan...")
            await refresh_daily_bars()

        nightly_scanner = self._host._nightly_scanner
        if nightly_scanner is None:
            logger.debug("[PIPELINE] Nightly scan: no NightlyScanner injected; skipping")
            return
        try:
            logger.info("[PIPELINE] Nightly scan starting...")
            result = await nightly_scanner.scan()
            self._last_batch_result = result
            candidate_count = len(result.candidates) if hasattr(result, "candidates") else 0
            candidate_symbols = (
                [c.symbol for c in result.candidates]
                if hasattr(result, "candidates") else []
            )
            logger.info(
                "[PIPELINE] Nightly scan complete: %d candidates -> %s",
                candidate_count, candidate_symbols,
            )
        except Exception:
            logger.exception("[PIPELINE] Nightly scan failed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_entry_metadata(held: Any) -> dict:
        """Build metadata dict for entry trade logging, including SL/TP."""
        from autotrader.trading.constants import SL_ATR_MULT, TP_ATR_MULT
        meta: dict = {"entry_atr": held.entry_atr}
        atr = held.entry_atr or 0
        if atr > 0 and held.entry_price:
            direction = held.direction
            strategy = held.strategy
            sl_mult = SL_ATR_MULT.get(strategy, {}).get(direction, 2.0)
            if direction == "long":
                meta["sl_price"] = round(held.entry_price - sl_mult * atr, 2)
            else:
                meta["sl_price"] = round(held.entry_price + sl_mult * atr, 2)
            tp_mult = TP_ATR_MULT.get(strategy)
            if tp_mult:
                if direction == "long":
                    meta["tp_price"] = round(held.entry_price + tp_mult * atr, 2)
                else:
                    meta["tp_price"] = round(held.entry_price - tp_mult * atr, 2)
        return meta

    async def _log_entry_trade(self, held: Any, account: Any) -> None:
        """Record an entry (open) trade in the trade logger."""
        trade_logger = self._host._trade_logger
        if trade_logger is None:
            return
        try:
            from autotrader.portfolio.trade_logger import LiveTradeRecord
            record = LiveTradeRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                symbol=held.symbol,
                strategy=held.strategy,
                direction=held.direction,
                side="entry",
                quantity=held.qty,
                price=held.entry_price,
                pnl=0.0,
                regime=self._host._current_regime.value,
                equity_after=account.equity,
                metadata=self._build_entry_metadata(held),
            )
            trade_logger.log_trade(record)
        except Exception:
            logger.exception("Trade log write failed for %s entry", held.symbol)
