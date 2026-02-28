"""AutoTrader v3 Watchdog - Process supervision with auto-restart.

Usage:
    python scripts/watchdog.py start   - Start AutoTrader under watchdog supervision
    python scripts/watchdog.py stop    - Stop the supervised AutoTrader process
    python scripts/watchdog.py status  - Print current process status

Restart policy:
    - Exponential backoff: 10s, 30s, 60s, 300s
    - Max 5 restart attempts per hour; stops supervising after that
    - On graceful shutdown (SIGTERM / KeyboardInterrupt), the child is
      terminated cleanly before the watchdog exits.

PID files:
    data/autotrader.pid   - PID of the supervised autotrader child process
    data/watchdog.pid     - PID of this watchdog process itself
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
PID_FILE = DATA_DIR / "autotrader.pid"
WATCHDOG_PID_FILE = DATA_DIR / "watchdog.pid"
LOG_FILE = LOG_DIR / "watchdog.log"

# ---------------------------------------------------------------------------
# Restart policy
# ---------------------------------------------------------------------------
BACKOFF_SCHEDULE = [10, 30, 60, 300]   # seconds between restart attempts
MAX_RESTARTS_PER_HOUR = 5
HEALTH_CHECK_INTERVAL = 30             # seconds between hung-process checks

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | watchdog | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("watchdog")


# ---------------------------------------------------------------------------
# PID helpers
# ---------------------------------------------------------------------------

def _write_pid(pid_file: Path, pid: int) -> None:
    """Write *pid* to *pid_file* atomically."""
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid), encoding="utf-8")


def _read_pid(pid_file: Path) -> int | None:
    """Return the integer PID stored in *pid_file*, or None if unreadable."""
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def _remove_pid(pid_file: Path) -> None:
    try:
        pid_file.unlink(missing_ok=True)
    except OSError:
        pass


def _process_is_alive(pid: int) -> bool:
    """Return True if a process with *pid* is currently running."""
    if pid <= 0:
        return False
    try:
        # os.kill with signal 0 checks existence without sending a signal.
        # On Windows this raises PermissionError (process exists) or
        # ProcessLookupError (process does not exist).
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't have permission to signal it.
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Child process management
# ---------------------------------------------------------------------------

def _start_child() -> subprocess.Popen:
    """Launch the autotrader main process and return the Popen handle."""
    cmd = [sys.executable, "-m", "autotrader.main"]
    logger.info("Launching child: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        # Inherit stdout/stderr so output is visible in the console / captured
        # by the parent process manager.
        stdout=None,
        stderr=None,
    )
    _write_pid(PID_FILE, proc.pid)
    logger.info("Child started with PID %d", proc.pid)
    return proc


def _stop_child(proc: subprocess.Popen, timeout: float = 15.0) -> None:
    """Terminate *proc* gracefully, then force-kill if it does not exit."""
    if proc.poll() is not None:
        return  # already exited

    logger.info("Sending SIGTERM to child PID %d", proc.pid)
    try:
        proc.terminate()   # SIGTERM on Windows via subprocess.terminate()
    except OSError as exc:
        logger.warning("terminate() failed: %s", exc)

    try:
        proc.wait(timeout=timeout)
        logger.info("Child exited gracefully (returncode=%d)", proc.returncode)
    except subprocess.TimeoutExpired:
        logger.warning("Child did not exit within %.0fs; force-killing", timeout)
        try:
            proc.kill()
            proc.wait(timeout=5.0)
        except OSError as exc:
            logger.error("kill() failed: %s", exc)


# ---------------------------------------------------------------------------
# Restart accounting
# ---------------------------------------------------------------------------

class _RestartLimiter:
    """Track restarts; enforce MAX_RESTARTS_PER_HOUR limit."""

    def __init__(self) -> None:
        # Store timestamps (float seconds) of the last N restarts.
        self._times: deque[float] = deque()

    def record(self) -> None:
        """Record a restart event at the current time."""
        now = time.monotonic()
        self._times.append(now)
        # Purge events older than one hour.
        cutoff = now - 3600.0
        while self._times and self._times[0] < cutoff:
            self._times.popleft()

    def exceeded(self) -> bool:
        """Return True if we have hit the max-restart limit for this hour."""
        now = time.monotonic()
        cutoff = now - 3600.0
        recent = sum(1 for t in self._times if t >= cutoff)
        return recent >= MAX_RESTARTS_PER_HOUR

    def count_recent(self) -> int:
        now = time.monotonic()
        cutoff = now - 3600.0
        return sum(1 for t in self._times if t >= cutoff)


# ---------------------------------------------------------------------------
# Main supervisor loop
# ---------------------------------------------------------------------------

def run_supervisor() -> None:
    """Supervise the autotrader process; restart on crash with backoff."""
    # Write our own PID so `stop` can find us.
    _write_pid(WATCHDOG_PID_FILE, os.getpid())
    logger.info("Watchdog started (PID %d)", os.getpid())

    limiter = _RestartLimiter()
    attempt = 0          # index into BACKOFF_SCHEDULE for the next sleep
    proc: subprocess.Popen | None = None

    # Handle graceful shutdown signals.
    _shutdown_requested = [False]

    def _on_signal(signum, frame):  # noqa: ANN001
        logger.info("Watchdog received signal %d; shutting down", signum)
        _shutdown_requested[0] = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    try:
        proc = _start_child()

        while not _shutdown_requested[0]:
            # Poll child status at regular intervals.
            ret = proc.poll()

            if ret is None:
                # Process is still running.  Sleep briefly, then check again.
                time.sleep(HEALTH_CHECK_INTERVAL)
                continue

            # --- Child has exited ---
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.warning(
                "[%s] AutoTrader exited with returncode=%d", ts, ret
            )
            _remove_pid(PID_FILE)

            if _shutdown_requested[0]:
                break

            limiter.record()
            if limiter.exceeded():
                logger.error(
                    "Max restarts per hour (%d) exceeded (%d in last 60 min). "
                    "Watchdog giving up.",
                    MAX_RESTARTS_PER_HOUR,
                    limiter.count_recent(),
                )
                break

            # Determine backoff delay.
            delay = BACKOFF_SCHEDULE[min(attempt, len(BACKOFF_SCHEDULE) - 1)]
            logger.info(
                "Restart attempt %d (backoff=%ds, restarts_this_hour=%d/%d)",
                attempt + 1,
                delay,
                limiter.count_recent(),
                MAX_RESTARTS_PER_HOUR,
            )
            attempt += 1

            # Interruptible sleep so SIGTERM is honoured promptly.
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline and not _shutdown_requested[0]:
                time.sleep(min(1.0, deadline - time.monotonic()))

            if _shutdown_requested[0]:
                break

            proc = _start_child()

    except KeyboardInterrupt:
        logger.info("Watchdog interrupted by keyboard")
    finally:
        if proc is not None and proc.poll() is None:
            _stop_child(proc)
        _remove_pid(PID_FILE)
        _remove_pid(WATCHDOG_PID_FILE)
        logger.info("Watchdog exited cleanly")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_start() -> None:
    """Start the watchdog (and thereby the autotrader)."""
    # Check if watchdog is already running.
    existing_pid = _read_pid(WATCHDOG_PID_FILE)
    if existing_pid and _process_is_alive(existing_pid):
        print(f"Watchdog is already running (PID {existing_pid})")
        sys.exit(1)

    # Remove stale PID files.
    _remove_pid(WATCHDOG_PID_FILE)
    _remove_pid(PID_FILE)

    run_supervisor()


def cmd_stop() -> None:
    """Stop the watchdog and the supervised autotrader."""
    watchdog_pid = _read_pid(WATCHDOG_PID_FILE)
    trader_pid = _read_pid(PID_FILE)

    stopped_any = False

    if watchdog_pid and _process_is_alive(watchdog_pid):
        print(f"Stopping watchdog (PID {watchdog_pid})...")
        try:
            os.kill(watchdog_pid, signal.SIGTERM)
            # Wait for watchdog to clean up (it also terminates the child).
            for _ in range(20):
                time.sleep(0.5)
                if not _process_is_alive(watchdog_pid):
                    break
            if _process_is_alive(watchdog_pid):
                print("Watchdog did not exit; force-killing...")
                os.kill(watchdog_pid, signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM)
        except OSError as exc:
            print(f"Could not signal watchdog: {exc}")
        stopped_any = True
    else:
        print("Watchdog is not running (no PID file or process not alive)")

    # Belt-and-suspenders: also stop the trader directly if still alive.
    if trader_pid and _process_is_alive(trader_pid):
        print(f"Stopping autotrader (PID {trader_pid})...")
        try:
            os.kill(trader_pid, signal.SIGTERM)
            for _ in range(20):
                time.sleep(0.5)
                if not _process_is_alive(trader_pid):
                    break
        except OSError as exc:
            print(f"Could not signal autotrader: {exc}")
        stopped_any = True

    # Clean up stale PID files.
    _remove_pid(PID_FILE)
    _remove_pid(WATCHDOG_PID_FILE)

    if stopped_any:
        print("Done.")
    else:
        print("Nothing was running.")


def cmd_status() -> None:
    """Print current status of watchdog and autotrader."""
    watchdog_pid = _read_pid(WATCHDOG_PID_FILE)
    trader_pid = _read_pid(PID_FILE)

    watchdog_alive = watchdog_pid is not None and _process_is_alive(watchdog_pid)
    trader_alive = trader_pid is not None and _process_is_alive(trader_pid)

    print("AutoTrader v3 Watchdog Status")
    print("=" * 40)
    if watchdog_pid:
        status = "RUNNING" if watchdog_alive else "DEAD (stale PID file)"
        print(f"  Watchdog  : {status} (PID {watchdog_pid})")
    else:
        print("  Watchdog  : NOT RUNNING")

    if trader_pid:
        status = "RUNNING" if trader_alive else "DEAD (stale PID file)"
        print(f"  AutoTrader: {status} (PID {trader_pid})")
    else:
        print("  AutoTrader: NOT RUNNING")

    print(f"  PID files : {PID_FILE}")
    print(f"  Log       : {LOG_FILE}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    commands = {"start": cmd_start, "stop": cmd_stop, "status": cmd_status}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print(f"Usage: python {Path(__file__).name} start|stop|status")
        sys.exit(1)
    commands[sys.argv[1]]()


if __name__ == "__main__":
    main()
