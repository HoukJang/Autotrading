"""Launch the live trading dashboard.

Usage:
    python scripts/run_live_dashboard.py
    python scripts/run_live_dashboard.py --port 8502
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    app_path = (
        Path(__file__).resolve().parent.parent
        / "autotrader"
        / "dashboard"
        / "live_app.py"
    )

    if not app_path.exists():
        print(f"ERROR: Dashboard app not found at {app_path}")
        sys.exit(1)

    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path)]

    # Pass through any extra CLI args (e.g. --port 8502)
    cmd.extend(sys.argv[1:])

    print(f"Starting live dashboard: {' '.join(cmd)}")
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
