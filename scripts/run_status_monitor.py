#!/usr/bin/env python3
"""
Autotrading Status Monitor Script

Production-ready script for monitoring system component status with real-time dashboard,
alerting, and comprehensive health checking capabilities.

Usage:
    python scripts/run_status_monitor.py [options]

Examples:
    # Real-time dashboard
    python scripts/run_status_monitor.py --dashboard

    # One-time status check
    python scripts/run_status_monitor.py --check

    # Continuous monitoring with alerts
    python scripts/run_status_monitor.py --monitor --interval 30 --alerts

    # Export status to JSON
    python scripts/run_status_monitor.py --export status.json

    # Filter by component
    python scripts/run_status_monitor.py --dashboard --filter ticker_manager
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import asdict

# Handle curses import for cross-platform compatibility
CURSES_AVAILABLE = False
try:
    import curses
    CURSES_AVAILABLE = True
except ImportError:
    # Windows or other systems without curses support
    curses = None

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from autotrading.core.status_handler import (
        StatusHandler, StatusDashboard, StatusInfo, AlertInfo,
        ComponentState, AlertLevel
    )
    from autotrading.database.connection import create_db_pool, close_db_pool
    from autotrading.config.settings import settings
except ImportError as e:
    print(f"Error importing autotrading modules: {e}")
    print("Make sure you're running from the project root and dependencies are installed.")
    sys.exit(1)


class StatusMonitor:
    """Production-ready status monitoring system"""

    def __init__(self, args: argparse.Namespace):
        """Initialize monitor with CLI arguments"""
        self.args = args
        self.logger = self._setup_logging()
        self.db_pool: Optional[Any] = None
        self.status_handler: Optional[StatusHandler] = None
        self.dashboard: Optional[StatusDashboard] = None
        self.running = True
        self.alert_history: List[Dict[str, Any]] = []

        # Component filtering
        self.component_filter: Optional[Set[str]] = None
        if args.filter:
            self.component_filter = set(f.strip() for f in args.filter.split(','))

        # Alert thresholds
        self.alert_thresholds = {
            "critical_count": 1,  # Alert if any critical issues
            "warning_threshold": 3,  # Alert if 3+ warnings
            "stale_threshold_minutes": 30,  # Alert if component stale for 30+ min
        }

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _setup_logging(self) -> logging.Logger:
        """Configure logging"""
        log_level = logging.DEBUG if self.args.verbose else logging.WARNING

        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        # Only add handlers if they don't exist (avoid duplicate output)
        if not root_logger.handlers:
            # Console handler (only for non-dashboard mode)
            if not self.args.dashboard:
                console_handler = logging.StreamHandler(sys.stderr)
                console_handler.setLevel(log_level)
                console_handler.setFormatter(formatter)
                root_logger.addHandler(console_handler)

            # File handler if specified
            if self.args.log_file:
                file_handler = logging.FileHandler(self.args.log_file)
                file_handler.setLevel(log_level)
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)

        return logging.getLogger(__name__)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    async def _initialize_database(self) -> bool:
        """Initialize database connection"""
        try:
            self.logger.info("Initializing database connection...")

            self.db_pool = await create_db_pool(
                settings.database_url,
                min_size=2,
                max_size=5,
                command_timeout=30
            )

            self.status_handler = StatusHandler(self.db_pool)
            self.dashboard = StatusDashboard(self.status_handler)

            return True

        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            return False

    async def _cleanup(self) -> None:
        """Cleanup resources"""
        try:
            if self.db_pool:
                await close_db_pool(self.db_pool)
            self.logger.info("Cleanup completed")
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")

    def _filter_components(self, statuses: List[StatusInfo]) -> List[StatusInfo]:
        """Filter components based on CLI filter"""
        if not self.component_filter:
            return statuses

        return [s for s in statuses if s.name in self.component_filter]

    def _should_alert(self, alerts: List[AlertInfo]) -> bool:
        """Determine if alerts should be triggered"""
        if not self.args.alerts:
            return False

        critical_count = len([a for a in alerts if a.level == AlertLevel.CRITICAL])
        warning_count = len([a for a in alerts if a.level == AlertLevel.WARNING])

        return (
            critical_count >= self.alert_thresholds["critical_count"] or
            warning_count >= self.alert_thresholds["warning_threshold"]
        )

    def _format_status_simple(self, statuses: List[StatusInfo]) -> str:
        """Format status information for simple output"""
        if not statuses:
            return "No components found."

        lines = ["System Status:"]
        lines.append("=" * 60)

        for status in statuses:
            state_symbol = {
                ComponentState.RUNNING: "[OK]",
                ComponentState.HEALTHY: "[OK]",
                ComponentState.INITIALIZED: "[INIT]",
                ComponentState.STOPPED: "[STOP]",
                ComponentState.ERROR: "[ERR]"
            }.get(status.state, "[UNK]")

            age = datetime.now(timezone.utc) - status.updated_at
            age_str = self._format_timedelta(age)

            lines.append(
                f"{state_symbol} {status.name:<25} | {status.state.value:<12} | {age_str}"
            )

            # Show important details
            if status.details:
                if 'error_message' in status.details:
                    lines.append(f"   └── Error: {status.details['error_message']}")
                if 'last_action' in status.details:
                    lines.append(f"   └── Last: {status.details['last_action']}")

        return "\n".join(lines)

    def _format_alerts_simple(self, alerts: List[AlertInfo]) -> str:
        """Format alerts for simple output"""
        if not alerts:
            return "[OK] No active alerts"

        lines = ["Active Alerts:"]
        lines.append("=" * 40)

        for alert in alerts:
            level_symbol = {
                AlertLevel.CRITICAL: "[CRIT]",
                AlertLevel.WARNING: "[WARN]",
                AlertLevel.OK: "[OK]",
                AlertLevel.STALE: "[STALE]"
            }.get(alert.level, "[UNK]")

            age = datetime.now(timezone.utc) - alert.timestamp
            age_str = self._format_timedelta(age)

            lines.append(f"{level_symbol} {alert.component}: {alert.issue} ({age_str})")

        return "\n".join(lines)

    def _format_timedelta(self, td: timedelta) -> str:
        """Format timedelta for human readability"""
        total_seconds = int(td.total_seconds())
        if total_seconds < 60:
            return f"{total_seconds}s ago"
        elif total_seconds < 3600:
            return f"{total_seconds // 60}m ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m ago"
        else:
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            return f"{days}d {hours}h ago"

    async def _get_status_data(self) -> Dict[str, Any]:
        """Get comprehensive status data"""
        try:
            # Get all statuses
            all_statuses = await self.status_handler.get_all_statuses()
            filtered_statuses = self._filter_components(all_statuses)

            # Get health check
            health_check = await self.status_handler.health_check_all()

            # Get alerts
            alerts = await self.status_handler.get_alerts()

            # Get dashboard data
            dashboard_data = await self.dashboard.get_dashboard_data()

            return {
                "statuses": filtered_statuses,
                "health_check": health_check,
                "alerts": alerts,
                "dashboard_data": dashboard_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "component_count": len(filtered_statuses),
                "total_component_count": len(all_statuses)
            }

        except Exception as e:
            self.logger.error(f"Failed to get status data: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def check_status_once(self) -> int:
        """Perform one-time status check"""
        try:
            if not await self._initialize_database():
                return 1

            status_data = await self._get_status_data()

            if "error" in status_data:
                print(f"Error: {status_data['error']}")
                return 1

            # Print status
            print(self._format_status_simple(status_data["statuses"]))
            print()
            print(self._format_alerts_simple(status_data["alerts"]))

            # Check overall health
            health = status_data["health_check"]
            print(f"\nOverall Health: {health.get('overall_health', 'UNKNOWN')}")
            print(f"Components: {health.get('healthy_components', 0)}/{health.get('total_components', 0)} healthy")

            # Return exit code based on health
            overall_health = health.get('overall_health', 'CRITICAL')
            if overall_health == 'CRITICAL':
                return 2
            elif overall_health == 'WARNING':
                return 1
            else:
                return 0

        except Exception as e:
            print(f"Status check failed: {e}")
            return 1
        finally:
            await self._cleanup()

    async def monitor_continuous(self) -> int:
        """Run continuous monitoring"""
        try:
            if not await self._initialize_database():
                return 1

            print(f"Starting continuous monitoring (interval: {self.args.interval}s)")
            print("Press Ctrl+C to stop")

            while self.running:
                try:
                    status_data = await self._get_status_data()

                    if "error" not in status_data:
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        print(f"\n[{timestamp}] Status Update:")
                        print("-" * 40)

                        # Show summary
                        health = status_data["health_check"]
                        statuses = status_data["statuses"]
                        alerts = status_data["alerts"]

                        print(f"Health: {health.get('overall_health', 'UNKNOWN')}")
                        print(f"Components: {len(statuses)} monitored")
                        print(f"Alerts: {len(alerts)} active")

                        # Show component states summary
                        state_counts = {}
                        for status in statuses:
                            state = status.state.value
                            state_counts[state] = state_counts.get(state, 0) + 1

                        if state_counts:
                            state_summary = ", ".join(f"{state}: {count}"
                                                    for state, count in state_counts.items())
                            print(f"States: {state_summary}")

                        # Show critical alerts
                        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]
                        if critical_alerts:
                            print("[CRITICAL ALERTS]:")
                            for alert in critical_alerts:
                                print(f"   - {alert.component}: {alert.issue}")

                        # Check if should alert
                        if self._should_alert(alerts):
                            self.alert_history.append({
                                "timestamp": timestamp,
                                "alerts": [asdict(a) for a in alerts],
                                "health": health
                            })
                            print("📢 Alert conditions met - logged to alert history")

                    # Wait for next check
                    await asyncio.sleep(self.args.interval)

                except Exception as e:
                    self.logger.error(f"Monitoring error: {e}")
                    await asyncio.sleep(self.args.interval)

            print("\nMonitoring stopped")

            # Show alert summary if any
            if self.alert_history:
                print(f"\nAlert Summary: {len(self.alert_history)} alert events logged")

            return 0

        except Exception as e:
            print(f"Monitoring failed: {e}")
            return 1
        finally:
            await self._cleanup()

    def _draw_dashboard_curses(self, stdscr, status_data: Dict[str, Any]) -> None:
        """Draw real-time dashboard using curses"""
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        try:
            # Header
            header = f"Autotrading System Monitor - {datetime.now().strftime('%H:%M:%S')}"
            stdscr.addstr(0, 0, header[:width-1], curses.A_BOLD)
            stdscr.addstr(1, 0, "=" * min(len(header), width-1))

            line = 3

            # Health summary
            if "health_check" in status_data:
                health = status_data["health_check"]
                health_status = health.get('overall_health', 'UNKNOWN')

                color = curses.A_NORMAL
                if health_status == 'CRITICAL':
                    color = curses.color_pair(1) if curses.has_colors() else curses.A_BOLD
                elif health_status == 'WARNING':
                    color = curses.color_pair(2) if curses.has_colors() else curses.A_BOLD

                stdscr.addstr(line, 0, f"Overall Health: {health_status}", color)
                line += 1

                total = health.get('total_components', 0)
                healthy = health.get('healthy_components', 0)
                stdscr.addstr(line, 0, f"Components: {healthy}/{total} healthy")
                line += 2

            # Component status
            if "statuses" in status_data:
                stdscr.addstr(line, 0, "Component Status:", curses.A_BOLD)
                line += 1

                for status in status_data["statuses"][:height - line - 10]:
                    state_symbol = {
                        ComponentState.RUNNING: "[OK]",
                        ComponentState.HEALTHY: "[OK]",
                        ComponentState.INITIALIZED: "[INIT]",
                        ComponentState.STOPPED: "[STOP]",
                        ComponentState.ERROR: "[ERR]"
                    }.get(status.state, "[UNK]")

                    age = datetime.now(timezone.utc) - status.updated_at
                    age_str = self._format_timedelta(age)

                    status_line = f"{state_symbol} {status.name:<20} {status.state.value:<12} {age_str}"
                    if len(status_line) > width - 1:
                        status_line = status_line[:width-4] + "..."

                    color = curses.A_NORMAL
                    if status.state == ComponentState.ERROR:
                        color = curses.color_pair(1) if curses.has_colors() else curses.A_BOLD
                    elif status.state in [ComponentState.STOPPED, ComponentState.INITIALIZED]:
                        color = curses.color_pair(2) if curses.has_colors() else curses.A_BOLD

                    stdscr.addstr(line, 0, status_line, color)
                    line += 1

            # Alerts
            if "alerts" in status_data and status_data["alerts"]:
                line += 1
                stdscr.addstr(line, 0, "Active Alerts:", curses.A_BOLD)
                line += 1

                for alert in status_data["alerts"][:height - line - 3]:
                    level_symbol = {
                        AlertLevel.CRITICAL: "[CRIT]",
                        AlertLevel.WARNING: "[WARN]",
                        AlertLevel.OK: "[OK]",
                        AlertLevel.STALE: "[STALE]"
                    }.get(alert.level, "[UNK]")

                    alert_line = f"{level_symbol} {alert.component}: {alert.issue}"
                    if len(alert_line) > width - 1:
                        alert_line = alert_line[:width-4] + "..."

                    color = curses.A_NORMAL
                    if alert.level == AlertLevel.CRITICAL:
                        color = curses.color_pair(1) if curses.has_colors() else curses.A_BOLD

                    stdscr.addstr(line, 0, alert_line, color)
                    line += 1

            # Footer
            footer = "Press 'q' to quit, 'r' to refresh"
            stdscr.addstr(height-1, 0, footer[:width-1])

            stdscr.refresh()

        except curses.error:
            # Handle screen too small or other curses errors
            pass

    async def run_dashboard(self) -> int:
        """Run interactive real-time dashboard"""
        if not CURSES_AVAILABLE:
            print("Dashboard mode requires curses library (not available on Windows)")
            print("Use --monitor mode for continuous monitoring instead")
            return 1

        if not await self._initialize_database():
            return 1

        def _dashboard_loop(stdscr):
            # Setup colors
            if curses.has_colors():
                curses.start_color()
                curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)      # Critical
                curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)   # Warning

            # Setup non-blocking input
            stdscr.nodelay(True)
            stdscr.timeout(1000)  # 1 second timeout

            last_update = 0
            refresh_interval = self.args.refresh or 5

            while self.running:
                current_time = time.time()

                # Update data if needed
                if current_time - last_update >= refresh_interval:
                    try:
                        # Run async function in sync context
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        status_data = loop.run_until_complete(self._get_status_data())
                        loop.close()

                        self._draw_dashboard_curses(stdscr, status_data)
                        last_update = current_time

                    except Exception as e:
                        stdscr.clear()
                        stdscr.addstr(0, 0, f"Error: {e}")
                        stdscr.refresh()

                # Handle input
                try:
                    key = stdscr.getch()
                    if key == ord('q') or key == ord('Q'):
                        break
                    elif key == ord('r') or key == ord('R'):
                        last_update = 0  # Force refresh
                except:
                    pass

                time.sleep(0.1)

        try:
            curses.wrapper(_dashboard_loop)
            return 0
        except Exception as e:
            print(f"Dashboard error: {e}")
            return 1
        finally:
            await self._cleanup()

    async def export_status(self) -> int:
        """Export status to JSON file"""
        try:
            if not await self._initialize_database():
                return 1

            status_data = await self._get_status_data()

            if "error" in status_data:
                print(f"Error: {status_data['error']}")
                return 1

            # Convert StatusInfo and AlertInfo objects to dictionaries
            export_data = {
                "timestamp": status_data["timestamp"],
                "health_check": status_data["health_check"],
                "component_count": status_data["component_count"],
                "statuses": [
                    {
                        "name": s.name,
                        "state": s.state.value,
                        "details": s.details,
                        "updated_at": s.updated_at.isoformat(),
                        "created_at": s.created_at.isoformat()
                    }
                    for s in status_data["statuses"]
                ],
                "alerts": [
                    {
                        "level": a.level.value,
                        "component": a.component,
                        "issue": a.issue,
                        "timestamp": a.timestamp.isoformat(),
                        "details": a.details
                    }
                    for a in status_data["alerts"]
                ]
            }

            # Write to file
            output_file = Path(self.args.export)
            with open(output_file, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)

            print(f"Status exported to {output_file}")
            return 0

        except Exception as e:
            print(f"Export failed: {e}")
            return 1
        finally:
            await self._cleanup()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Autotrading Status Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # One-time status check
    python scripts/run_status_monitor.py --check

    # Real-time dashboard
    python scripts/run_status_monitor.py --dashboard

    # Continuous monitoring with alerts
    python scripts/run_status_monitor.py --monitor --interval 30 --alerts

    # Export current status
    python scripts/run_status_monitor.py --export status.json

    # Monitor specific components
    python scripts/run_status_monitor.py --dashboard --filter "ticker_manager,data_collector"
        """
    )

    # Execution modes (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Perform one-time status check and exit"
    )
    mode_group.add_argument(
        "--dashboard",
        action="store_true",
        help="Run interactive real-time dashboard"
    )
    mode_group.add_argument(
        "--monitor",
        action="store_true",
        help="Run continuous monitoring mode"
    )
    mode_group.add_argument(
        "--export",
        type=str,
        metavar="FILE",
        help="Export current status to JSON file"
    )

    # Monitoring options
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        metavar="SECONDS",
        help="Update interval for monitoring/dashboard (default: 10)"
    )

    parser.add_argument(
        "--refresh",
        type=int,
        metavar="SECONDS",
        help="Dashboard refresh interval (default: 5)"
    )

    # Filtering options
    parser.add_argument(
        "--filter",
        type=str,
        metavar="COMPONENTS",
        help="Comma-separated list of components to monitor"
    )

    # Alert options
    parser.add_argument(
        "--alerts",
        action="store_true",
        help="Enable alert notifications in monitoring mode"
    )

    # Logging options
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        "--log-file",
        type=Path,
        metavar="PATH",
        help="Write logs to specified file"
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point"""
    args = parse_arguments()

    # Validate arguments
    if args.interval <= 0:
        print("Error: interval must be positive", file=sys.stderr)
        return 1

    # Run the monitor
    monitor = StatusMonitor(args)

    try:
        if args.check:
            return await monitor.check_status_once()
        elif args.dashboard:
            return await monitor.run_dashboard()
        elif args.monitor:
            return await monitor.monitor_continuous()
        elif args.export:
            return await monitor.export_status()
        else:
            print("No valid mode specified", file=sys.stderr)
            return 1

    except KeyboardInterrupt:
        print("\nMonitoring interrupted by user")
        return 0
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)