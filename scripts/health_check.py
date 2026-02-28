"""AutoTrader v3 Health Check - Verify system health at any point.

Performs 6 checks and outputs a JSON summary.

Checks:
    1. Process     - Is the autotrader process running? (PID file)
    2. Batch scan  - Did the nightly batch scan run? (batch_results.json < 12h old)
    3. Entries     - Did entries execute today during market hours?
    4. Equity      - Is equity snapshot being written? (< 30 min old)
    5. Errors      - Any ERROR-level log entries in the last hour?
    6. Disk        - At least 1 GB free on the data drive?

Usage:
    python scripts/health_check.py

Exit codes:
    0  - All checks passed
    1  - One or more checks failed
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (resolved relative to this script's location)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"

PID_FILE = DATA_DIR / "autotrader.pid"
BATCH_RESULTS_FILE = DATA_DIR / "batch_results.json"
LIVE_TRADES_FILE = DATA_DIR / "live_trades.jsonl"
EQUITY_SNAPSHOTS_FILE = DATA_DIR / "equity_snapshots.jsonl"
LOG_FILE = LOG_DIR / "autotrader.log"

# Thresholds
BATCH_MAX_AGE_HOURS = 12
EQUITY_MAX_AGE_MINUTES = 30
DISK_MIN_FREE_BYTES = 1 * 1024 ** 3     # 1 GB
ERROR_LOOKBACK_SECONDS = 3600           # 1 hour

# Market hours (ET) used to determine whether entries are expected today.
MARKET_OPEN_HOUR_ET = 9
MARKET_OPEN_MINUTE_ET = 30
MARKET_CLOSE_HOUR_ET = 16

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _read_pid(pid_file: Path) -> int | None:
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def _file_mtime_utc(path: Path) -> datetime | None:
    """Return the UTC mtime of *path*, or None if it does not exist."""
    try:
        mtime = path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    except FileNotFoundError:
        return None


def _last_line(path: Path) -> str | None:
    """Return the last non-empty line of a file, or None."""
    try:
        with open(path, "rb") as fh:
            # Seek backward to find the last line efficiently.
            fh.seek(0, 2)
            size = fh.tell()
            if size == 0:
                return None
            buf = b""
            pos = size - 1
            while pos >= 0:
                fh.seek(pos)
                ch = fh.read(1)
                if ch == b"\n" and buf.strip():
                    break
                buf = ch + buf
                pos -= 1
            line = buf.decode("utf-8", errors="replace").strip()
            return line if line else None
    except (FileNotFoundError, OSError):
        return None


def _disk_free_bytes(path: Path) -> int:
    """Return free bytes on the filesystem containing *path*."""
    try:
        stat = os.statvfs(str(path)) if hasattr(os, "statvfs") else None
        if stat:
            return stat.f_bavail * stat.f_frsize
        # Windows fallback via shutil
        import shutil
        usage = shutil.disk_usage(str(path.anchor))
        return usage.free
    except Exception:
        import shutil
        try:
            usage = shutil.disk_usage(str(path.anchor))
            return usage.free
        except Exception:
            return -1


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_process() -> dict:
    """Check 1: Is the autotrader process running?"""
    pid = _read_pid(PID_FILE)
    if pid is None:
        return {
            "name": "process",
            "passed": False,
            "detail": f"PID file not found: {PID_FILE}",
        }
    alive = _process_is_alive(pid)
    return {
        "name": "process",
        "passed": alive,
        "detail": (
            f"Process running (PID {pid})"
            if alive
            else f"PID {pid} found in {PID_FILE} but process is not alive"
        ),
    }


def check_batch_scan() -> dict:
    """Check 2: Did the nightly batch scan run within the last 12 hours?"""
    mtime = _file_mtime_utc(BATCH_RESULTS_FILE)
    if mtime is None:
        return {
            "name": "batch_scan",
            "passed": False,
            "detail": f"Batch results file not found: {BATCH_RESULTS_FILE}",
        }
    age = _utcnow() - mtime
    hours = age.total_seconds() / 3600
    passed = hours < BATCH_MAX_AGE_HOURS
    return {
        "name": "batch_scan",
        "passed": passed,
        "detail": (
            f"Last batch scan {hours:.1f}h ago (limit: {BATCH_MAX_AGE_HOURS}h)"
        ),
    }


def check_entries_today() -> dict:
    """Check 3: Did at least one entry execute today during market hours?

    This check only flags a failure when:
      - We are past 10:00 AM ET (entry window has closed), AND
      - No trades were recorded for today.
    Outside market hours the check is informational (passes with a note).
    """
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

    et = ZoneInfo("US/Eastern")
    now_et = datetime.now(tz=et)
    today_et = now_et.date()

    # Determine if we are past the entry window.
    entry_window_closed = now_et.hour > 10 or (now_et.hour == 10 and now_et.minute >= 0)
    is_trading_hours = (
        (now_et.hour > MARKET_OPEN_HOUR_ET or
         (now_et.hour == MARKET_OPEN_HOUR_ET and now_et.minute >= MARKET_OPEN_MINUTE_ET))
        and now_et.hour < MARKET_CLOSE_HOUR_ET
    )

    if not is_trading_hours and not entry_window_closed:
        # Outside market hours entirely — don't require entries.
        return {
            "name": "entries_today",
            "passed": True,
            "detail": "Outside market hours; entry check skipped",
        }

    if not LIVE_TRADES_FILE.exists():
        detail = "live_trades.jsonl not found"
        # Only fail if the entry window has already passed.
        return {
            "name": "entries_today",
            "passed": not entry_window_closed,
            "detail": detail,
        }

    # Scan trades file for today's entries.
    entries_today: list[str] = []
    try:
        with open(LIVE_TRADES_FILE, encoding="utf-8") as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    rec = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                ts_str = rec.get("timestamp", "")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    trade_date_et = ts.astimezone(et).date()
                    if trade_date_et == today_et:
                        entries_today.append(rec.get("symbol", "?"))
                except (ValueError, AttributeError):
                    continue
    except OSError as exc:
        return {
            "name": "entries_today",
            "passed": False,
            "detail": f"Could not read live_trades.jsonl: {exc}",
        }

    if entries_today:
        return {
            "name": "entries_today",
            "passed": True,
            "detail": f"{len(entries_today)} entry/entries today: {', '.join(entries_today[:5])}",
        }

    # No entries yet — only fail after the entry window has closed.
    if entry_window_closed:
        return {
            "name": "entries_today",
            "passed": False,
            "detail": "Entry window has closed and no entries were recorded today",
        }
    return {
        "name": "entries_today",
        "passed": True,
        "detail": "Entry window still open; no entries yet",
    }


def check_equity_snapshot() -> dict:
    """Check 4: Is the equity snapshot being written (< 30 min old)?"""
    mtime = _file_mtime_utc(EQUITY_SNAPSHOTS_FILE)
    if mtime is None:
        return {
            "name": "equity_snapshot",
            "passed": False,
            "detail": f"Equity snapshots file not found: {EQUITY_SNAPSHOTS_FILE}",
        }
    age_minutes = (_utcnow() - mtime).total_seconds() / 60
    passed = age_minutes < EQUITY_MAX_AGE_MINUTES
    return {
        "name": "equity_snapshot",
        "passed": passed,
        "detail": (
            f"Last equity snapshot {age_minutes:.1f} min ago "
            f"(limit: {EQUITY_MAX_AGE_MINUTES} min)"
        ),
    }


def check_recent_errors() -> dict:
    """Check 5: Any ERROR-level entries in the log in the last hour?"""
    if not LOG_FILE.exists():
        return {
            "name": "recent_errors",
            "passed": True,
            "detail": f"Log file not found: {LOG_FILE} (treating as no errors)",
        }

    cutoff = _utcnow() - timedelta(seconds=ERROR_LOOKBACK_SECONDS)
    error_lines: list[str] = []

    try:
        with open(LOG_FILE, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.rstrip()
                if " | ERROR | " not in line and " | CRITICAL | " not in line:
                    continue
                # Try to parse the timestamp at the start of the line.
                # Expected format: "2026-02-27 18:04:12,123 | module | LEVEL | msg"
                parts = line.split(" | ", maxsplit=3)
                if len(parts) < 3:
                    continue
                ts_str = parts[0].strip()
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
                    ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= cutoff:
                        error_lines.append(line[:120])
                except ValueError:
                    # Could not parse timestamp; include conservatively.
                    error_lines.append(line[:120])
    except OSError as exc:
        return {
            "name": "recent_errors",
            "passed": False,
            "detail": f"Could not read log file: {exc}",
        }

    if error_lines:
        sample = error_lines[-3:]  # Show last 3 errors
        return {
            "name": "recent_errors",
            "passed": False,
            "detail": (
                f"{len(error_lines)} error(s) in last hour. "
                f"Most recent: {sample[-1][:100]}"
            ),
        }
    return {
        "name": "recent_errors",
        "passed": True,
        "detail": "No errors in the last hour",
    }


def check_disk_space() -> dict:
    """Check 6: At least 1 GB free on the data drive?"""
    check_path = DATA_DIR if DATA_DIR.exists() else PROJECT_ROOT
    free = _disk_free_bytes(check_path)
    if free < 0:
        return {
            "name": "disk_space",
            "passed": False,
            "detail": "Could not determine free disk space",
        }
    free_gb = free / (1024 ** 3)
    passed = free >= DISK_MIN_FREE_BYTES
    return {
        "name": "disk_space",
        "passed": passed,
        "detail": f"{free_gb:.2f} GB free (minimum: 1.00 GB)",
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_health_check() -> dict:
    """Execute all checks and return aggregated result dict."""
    checks = [
        check_process(),
        check_batch_scan(),
        check_entries_today(),
        check_equity_snapshot(),
        check_recent_errors(),
        check_disk_space(),
    ]

    all_passed = all(c["passed"] for c in checks)
    failed_names = [c["name"] for c in checks if not c["passed"]]

    result = {
        "timestamp": _utcnow().isoformat(),
        "overall": "HEALTHY" if all_passed else "UNHEALTHY",
        "all_passed": all_passed,
        "failed_checks": failed_names,
        "checks": checks,
    }
    return result


def main() -> None:
    result = run_health_check()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["all_passed"] else 1)


if __name__ == "__main__":
    main()
