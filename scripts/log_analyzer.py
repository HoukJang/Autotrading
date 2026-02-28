"""AutoTrader v3 Log Analyzer - Daily log analysis and summary.

Parses logs/autotrader.log for a given date and produces a structured
summary of system activity, trades, errors, and uptime.

Usage:
    python scripts/log_analyzer.py
    python scripts/log_analyzer.py --date 2026-02-27
    python scripts/log_analyzer.py --save
    python scripts/log_analyzer.py --date 2026-02-27 --save

Output:
    - Text report to stdout.
    - If --save is specified, also writes to logs/daily_summary_YYYY-MM-DD.txt.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "autotrader.log"


# ---------------------------------------------------------------------------
# Log line parser
# ---------------------------------------------------------------------------

# Log format: "2026-02-27 18:04:12,123 | module_name | LEVEL | message"
_LOG_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)"
    r"\s*\|\s*(?P<module>[^|]+)"
    r"\s*\|\s*(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)"
    r"\s*\|\s*(?P<message>.*)$"
)


def _parse_line(line: str) -> dict | None:
    """Parse a single log line.  Returns None if it does not match the format."""
    m = _LOG_RE.match(line.rstrip())
    if not m:
        return None
    ts_str = m.group("ts")
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None
    return {
        "ts": ts,
        "module": m.group("module").strip(),
        "level": m.group("level").strip(),
        "message": m.group("message").strip(),
    }


# ---------------------------------------------------------------------------
# Pattern matchers for interesting events
# ---------------------------------------------------------------------------

# Nightly batch scan
_SCAN_START_RE = re.compile(r"nightly.?scan|batch.?scan|NightlyScanner", re.IGNORECASE)
_SCAN_SYMBOLS_RE = re.compile(r"scanned?[:\s]+(\d+)\s+symbol", re.IGNORECASE)
_SCAN_CANDIDATES_RE = re.compile(r"(\d+)\s+candidate", re.IGNORECASE)

# Entry / exit events
_ENTRY_RE = re.compile(r"\b(BUY|SELL|entry|entered|filled|order.?submit)", re.IGNORECASE)
_EXIT_RE = re.compile(r"\b(exit|closed|stop.?loss|take.?profit|TP|SL|emergency|force.?close)", re.IGNORECASE)
_SYMBOL_IN_MSG_RE = re.compile(r"\b([A-Z]{1,5})\b")

# Strategy names (from known list; extend as needed)
_STRATEGY_NAMES = {
    "rsi_mean_reversion", "overbought_short", "adx_pullback",
    "bb_squeeze", "regime_momentum",
}

# Error category keywords
_ERROR_CATEGORIES = {
    "network": re.compile(r"HTTPError|ConnectionError|Timeout|requests|APIError", re.IGNORECASE),
    "alpaca": re.compile(r"alpaca|broker", re.IGNORECASE),
    "data": re.compile(r"data|bars?|historical|feed", re.IGNORECASE),
    "order": re.compile(r"order|fill|submit|trade", re.IGNORECASE),
    "regime": re.compile(r"regime|detector", re.IGNORECASE),
    "other": re.compile(r".*"),  # catch-all; keep last
}

# Startup marker
_STARTUP_RE = re.compile(r"Starting AutoTrader", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

class DayStats:
    """Accumulates statistics for a single calendar day."""

    def __init__(self, target_date: date) -> None:
        self.target_date = target_date

        # Level counts
        self.level_counts: dict[str, int] = defaultdict(int)

        # Uptime: list of (start_ts, end_ts_or_None)
        self.startup_times: list[datetime] = []
        self.last_seen_ts: datetime | None = None

        # Nightly scan
        self.scan_time: datetime | None = None
        self.symbols_scanned: int = 0
        self.candidates_selected: int = 0
        self.scan_lines: list[str] = []

        # Entries
        self.entry_events: list[dict] = []   # {ts, symbol, strategy, direction}

        # Exits
        self.exit_events: list[dict] = []    # {ts, symbol, reason}

        # Errors
        self.error_lines: list[dict] = []    # {ts, module, message}
        self.error_categories: dict[str, int] = defaultdict(int)

    # -----------------------------------------------------------------------

    def ingest(self, parsed: dict, raw_line: str) -> None:
        """Process a single parsed log entry."""
        ts: datetime = parsed["ts"]

        # Only count entries for the target date.
        if ts.date() != self.target_date:
            return

        self.last_seen_ts = ts
        level = parsed["level"]
        module = parsed["module"]
        msg = parsed["message"]

        self.level_counts[level] += 1

        # --- Startup ---
        if _STARTUP_RE.search(msg):
            self.startup_times.append(ts)

        # --- Nightly scan ---
        if _SCAN_START_RE.search(msg):
            if self.scan_time is None:
                self.scan_time = ts
            self.scan_lines.append(msg)
            m = _SCAN_SYMBOLS_RE.search(msg)
            if m:
                self.symbols_scanned = max(self.symbols_scanned, int(m.group(1)))
            m = _SCAN_CANDIDATES_RE.search(msg)
            if m:
                self.candidates_selected = max(self.candidates_selected, int(m.group(1)))

        # --- Entry events (INFO level only to avoid noise) ---
        if level in ("INFO",) and _ENTRY_RE.search(msg):
            strategy = next(
                (s for s in _STRATEGY_NAMES if s in msg.lower()), None
            )
            symbols = _SYMBOL_IN_MSG_RE.findall(msg)
            # Filter obvious non-symbols (level words, module names, etc.)
            _SKIP = {"INFO", "ERROR", "WARNING", "DEBUG", "CRITICAL", "ET", "PID", "AM", "PM"}
            symbols = [s for s in symbols if s not in _SKIP and len(s) >= 2]
            self.entry_events.append({
                "ts": ts.strftime("%H:%M:%S"),
                "symbol": symbols[0] if symbols else "?",
                "strategy": strategy or "unknown",
                "message": msg[:100],
            })

        # --- Exit events ---
        if level in ("INFO", "WARNING") and _EXIT_RE.search(msg):
            reason = "unknown"
            msg_lower = msg.lower()
            if "stop" in msg_lower and "loss" in msg_lower:
                reason = "stop_loss"
            elif "take" in msg_lower and "profit" in msg_lower:
                reason = "take_profit"
            elif "tp" in msg_lower:
                reason = "take_profit"
            elif "sl" in msg_lower:
                reason = "stop_loss"
            elif "emergency" in msg_lower:
                reason = "emergency"
            elif "force" in msg_lower:
                reason = "force_close"
            elif "time" in msg_lower or "hold" in msg_lower:
                reason = "time_based"
            symbols = _SYMBOL_IN_MSG_RE.findall(msg)
            _SKIP = {"INFO", "ERROR", "WARNING", "DEBUG", "CRITICAL", "ET", "TP", "SL", "AM", "PM"}
            symbols = [s for s in symbols if s not in _SKIP and len(s) >= 2]
            self.exit_events.append({
                "ts": ts.strftime("%H:%M:%S"),
                "symbol": symbols[0] if symbols else "?",
                "reason": reason,
                "message": msg[:100],
            })

        # --- Errors ---
        if level in ("ERROR", "CRITICAL"):
            cat = "other"
            for category, pattern in _ERROR_CATEGORIES.items():
                if pattern.search(module + " " + msg):
                    cat = category
                    break
            self.error_categories[cat] += 1
            self.error_lines.append({
                "ts": ts.strftime("%H:%M:%S"),
                "module": module,
                "message": msg[:120],
            })

    # -----------------------------------------------------------------------

    def compute_uptime(self) -> str:
        """Estimate uptime from first startup to last seen event."""
        if not self.startup_times:
            return "N/A"
        first = self.startup_times[0]
        last = self.last_seen_ts or first
        delta = last - first
        hours, rem = divmod(int(delta.total_seconds()), 3600)
        minutes = rem // 60
        return f"{hours}h {minutes}m"


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def _format_report(stats: DayStats) -> str:
    lines: list[str] = []
    sep = "=" * 60

    lines.append(sep)
    lines.append(f"  AutoTrader v3 Daily Log Summary - {stats.target_date}")
    lines.append(sep)
    lines.append("")

    # --- System uptime ---
    lines.append("[ System Uptime ]")
    if stats.startup_times:
        for st in stats.startup_times:
            lines.append(f"  Startup : {st.strftime('%H:%M:%S')}")
    else:
        lines.append("  Startup : not detected in log")
    lines.append(f"  Uptime  : {stats.compute_uptime()}")
    lines.append("")

    # --- Message counts ---
    lines.append("[ Log Message Counts ]")
    for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        count = stats.level_counts.get(level, 0)
        lines.append(f"  {level:<10}: {count}")
    lines.append("")

    # --- Nightly batch scan ---
    lines.append("[ Nightly Batch Scan ]")
    if stats.scan_time:
        lines.append(f"  Time             : {stats.scan_time.strftime('%H:%M:%S')}")
        lines.append(f"  Symbols scanned  : {stats.symbols_scanned or 'N/A'}")
        lines.append(f"  Candidates found : {stats.candidates_selected or 'N/A'}")
    else:
        lines.append("  No batch scan detected in log for this date")
    lines.append("")

    # --- Entries ---
    lines.append("[ Entry Events ]")
    lines.append(f"  Count : {len(stats.entry_events)}")
    if stats.entry_events:
        by_strategy: dict[str, int] = defaultdict(int)
        symbols_entered: list[str] = []
        for ev in stats.entry_events:
            by_strategy[ev["strategy"]] += 1
            symbols_entered.append(ev["symbol"])
        lines.append(f"  Symbols   : {', '.join(symbols_entered)}")
        lines.append("  Strategies:")
        for strat, cnt in sorted(by_strategy.items()):
            lines.append(f"    {strat}: {cnt}")
        lines.append("  Detail (up to 10):")
        for ev in stats.entry_events[:10]:
            lines.append(f"    {ev['ts']}  {ev['symbol']:<6} [{ev['strategy']}]  {ev['message'][:60]}")
    lines.append("")

    # --- Exits ---
    lines.append("[ Exit Events ]")
    lines.append(f"  Count : {len(stats.exit_events)}")
    if stats.exit_events:
        by_reason: dict[str, int] = defaultdict(int)
        for ev in stats.exit_events:
            by_reason[ev["reason"]] += 1
        lines.append("  Reasons:")
        for reason, cnt in sorted(by_reason.items()):
            lines.append(f"    {reason}: {cnt}")
        lines.append("  Detail (up to 10):")
        for ev in stats.exit_events[:10]:
            lines.append(f"    {ev['ts']}  {ev['symbol']:<6} [{ev['reason']}]  {ev['message'][:60]}")
    lines.append("")

    # --- Errors ---
    lines.append("[ Errors ]")
    total_errors = stats.level_counts.get("ERROR", 0) + stats.level_counts.get("CRITICAL", 0)
    lines.append(f"  Total   : {total_errors}")
    if stats.error_categories:
        lines.append("  By category:")
        for cat, cnt in sorted(stats.error_categories.items()):
            lines.append(f"    {cat}: {cnt}")
    if stats.error_lines:
        lines.append("  Most recent (up to 5):")
        for ev in stats.error_lines[-5:]:
            lines.append(f"    {ev['ts']}  [{ev['module']}]  {ev['message'][:80]}")
    lines.append("")

    lines.append(sep)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def analyze(target_date: date) -> tuple[DayStats, str]:
    """Parse the log file and return (DayStats, formatted_report)."""
    stats = DayStats(target_date)

    if not LOG_FILE.exists():
        report = (
            f"Log file not found: {LOG_FILE}\n"
            "Cannot generate summary."
        )
        return stats, report

    pending_continuation: str | None = None  # multi-line traceback accumulation

    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                parsed = _parse_line(raw_line)
                if parsed is None:
                    # Continuation line (e.g., traceback body).
                    # Attach to the previous error entry if present.
                    if stats.error_lines and raw_line.strip():
                        stats.error_lines[-1]["message"] = (
                            stats.error_lines[-1]["message"][:80]
                        )  # already capped; ignore continuation detail
                    continue
                stats.ingest(parsed, raw_line)
    except OSError as exc:
        return stats, f"ERROR reading log file: {exc}"

    report = _format_report(stats)
    return stats, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AutoTrader v3 daily log analyzer"
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Date to analyze (default: today)",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save report to logs/daily_summary_YYYY-MM-DD.txt",
    )
    args = parser.parse_args()

    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"ERROR: Invalid date format '{args.date}'. Use YYYY-MM-DD.", file=sys.stderr)
            sys.exit(1)
    else:
        target_date = date.today()

    _stats, report = analyze(target_date)
    print(report)

    if args.save:
        save_path = LOG_DIR / f"daily_summary_{target_date}.txt"
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        save_path.write_text(report, encoding="utf-8")
        print(f"Report saved to: {save_path}")


if __name__ == "__main__":
    main()
