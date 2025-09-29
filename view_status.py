#!/usr/bin/env python3
"""
Status Viewer CLI

시스템 상태를 확인하는 CLI 명령어입니다.
터미널에서 실시간 상태 모니터링을 제공합니다.
"""

import asyncio
import argparse
import sys
from datetime import datetime
from typing import Optional

from autotrading.core.shared_context import create_shared_context
from autotrading.core.status_handler import AlertLevel


async def view_status(args):
    """상태 조회 메인 함수"""
    try:
        async with create_shared_context() as context:
            if args.command == "dashboard":
                await show_dashboard(context)
            elif args.command == "alerts":
                await show_alerts(context)
            elif args.command == "component":
                await show_component_status(context, args.name)
            elif args.command == "health":
                await show_health_check(context)
            else:
                await show_dashboard(context)  # 기본값

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


async def show_dashboard(context):
    """전체 대시보드 표시"""
    print("🔄 Loading system status...")

    dashboard_data = await context.status_dashboard.get_dashboard_data()
    health_check = dashboard_data["health_check"]

    # 전체 상태 요약
    print(f"\n📊 System Status Dashboard - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    overall_health = health_check["overall_health"]
    health_emoji = {
        "OK": "🟢",
        "WARNING": "⚠️",
        "CRITICAL": "🚨"
    }.get(overall_health, "⚫")

    print(f"{health_emoji} Overall Health: {overall_health}")
    print(f"📈 Components: {health_check['healthy_components']}/{health_check['total_components']} healthy")

    # 컴포넌트별 상태
    print(f"\n📋 Component Status:")
    print("-" * 70)
    print(f"{'Component':<20} {'State':<12} {'Health':<10} {'Last Update':<15}")
    print("-" * 70)

    for component in health_check["components"]:
        state_emoji = {
            "running": "🟢",
            "healthy": "🟢",
            "initialized": "🟡",
            "stopped": "🔴",
            "error": "🚨"
        }.get(component["state"], "⚫")

        health_emoji = {
            "OK": "✅",
            "WARNING": "⚠️",
            "CRITICAL": "🚨",
            "STALE": "⏰"
        }.get(component["health_status"], "❓")

        minutes_ago = int(component["minutes_since_update"])
        time_str = f"{minutes_ago}m ago" if minutes_ago < 60 else f"{minutes_ago//60}h ago"

        print(f"{component['name']:<20} {state_emoji} {component['state']:<10} {health_emoji} {component['health_status']:<8} {time_str:<15}")

        # 중요한 세부사항 표시
        details = component.get("details", {})
        if "error_message" in details:
            print(f"   🚨 Error: {details['error_message']}")
        elif "active_symbols" in details:
            print(f"   📊 Symbols: {details['active_symbols']}")
        elif "last_action" in details:
            print(f"   🔄 Last: {details['last_action']}")

    # 알람 요약
    alerts_summary = dashboard_data["summary"]
    if alerts_summary["total_alerts"] > 0:
        print(f"\n🚨 Active Alerts: {alerts_summary['total_alerts']}")
        if alerts_summary["critical_alerts"] > 0:
            print(f"   🚨 Critical: {alerts_summary['critical_alerts']}")
        if alerts_summary["warning_alerts"] > 0:
            print(f"   ⚠️ Warning: {alerts_summary['warning_alerts']}")
        print("   Use 'view_status.py alerts' for details")
    else:
        print(f"\n✅ No active alerts")


async def show_alerts(context):
    """알람 목록 표시"""
    print("🔄 Loading alerts...")

    alerts = await context.status_handler.get_alerts()

    print(f"\n🚨 Active Alerts - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not alerts:
        print("✅ No active alerts")
        return

    # 레벨별로 그룹화
    critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]
    warning_alerts = [a for a in alerts if a.level == AlertLevel.WARNING]

    if critical_alerts:
        print(f"\n🚨 CRITICAL ALERTS ({len(critical_alerts)}):")
        print("-" * 40)
        for alert in critical_alerts:
            time_str = alert.timestamp.strftime('%H:%M:%S')
            print(f"🚨 {alert.component}: {alert.issue} (at {time_str})")
            if alert.details and "error_message" in alert.details:
                print(f"   └── {alert.details['error_message']}")

    if warning_alerts:
        print(f"\n⚠️ WARNING ALERTS ({len(warning_alerts)}):")
        print("-" * 40)
        for alert in warning_alerts:
            time_str = alert.timestamp.strftime('%H:%M:%S')
            print(f"⚠️ {alert.component}: {alert.issue} (at {time_str})")


async def show_component_status(context, component_name: str):
    """특정 컴포넌트 상태 상세 표시"""
    print(f"🔄 Loading status for {component_name}...")

    status = await context.status_handler.get_status(component_name)

    if not status:
        print(f"❌ Component '{component_name}' not found")
        return

    print(f"\n📊 Component Status: {component_name}")
    print("=" * 50)

    state_emoji = {
        "running": "🟢",
        "healthy": "🟢",
        "initialized": "🟡",
        "stopped": "🔴",
        "error": "🚨"
    }.get(status.state.value, "⚫")

    print(f"{state_emoji} State: {status.state.value}")
    print(f"🕒 Last Updated: {status.record_modified_at.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📅 Created: {status.created_at.strftime('%Y-%m-%d %H:%M:%S')}")

    # 상세 정보
    if status.details:
        print(f"\n📋 Details:")
        print("-" * 30)
        for key, value in status.details.items():
            if key == "error_message":
                print(f"🚨 {key}: {value}")
            elif key == "error_time":
                print(f"⏰ {key}: {value}")
            else:
                print(f"📊 {key}: {value}")


async def show_health_check(context):
    """헬스 체크 결과 표시"""
    print("🔄 Performing health check...")

    health_check = await context.status_handler.health_check_all()

    print(f"\n🏥 System Health Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    overall_health = health_check["overall_health"]
    health_emoji = {
        "OK": "🟢",
        "WARNING": "⚠️",
        "CRITICAL": "🚨"
    }.get(overall_health, "⚫")

    print(f"{health_emoji} Overall Status: {overall_health}")

    if "error" in health_check:
        print(f"🚨 Error: {health_check['error']}")
        return

    # 통계
    total = health_check["total_components"]
    healthy = health_check["healthy_components"]
    unhealthy = total - healthy

    print(f"📊 Total Components: {total}")
    print(f"✅ Healthy: {healthy}")
    print(f"❌ Unhealthy: {unhealthy}")

    if healthy == total:
        print(f"\n🎉 All systems operational!")
    else:
        print(f"\n⚠️ {unhealthy} component(s) need attention")

        # 문제 컴포넌트 표시
        for component in health_check["components"]:
            if component["health_status"] != "OK":
                status_emoji = {
                    "WARNING": "⚠️",
                    "CRITICAL": "🚨",
                    "STALE": "⏰"
                }.get(component["health_status"], "❓")

                print(f"  {status_emoji} {component['name']}: {component['health_status']}")


async def monitor_continuous(context, interval: int = 30):
    """연속 모니터링 모드"""
    print(f"🔄 Starting continuous monitoring (refresh every {interval}s)")
    print("Press Ctrl+C to stop")

    try:
        while True:
            # 화면 클리어 (플랫폼 호환)
            import os
            os.system('cls' if os.name == 'nt' else 'clear')

            await show_dashboard(context)

            print(f"\n⏰ Refreshing in {interval} seconds... (Ctrl+C to stop)")
            await asyncio.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n👋 Monitoring stopped")


def main():
    """CLI 메인 함수"""
    parser = argparse.ArgumentParser(
        description="Autotrading System Status Viewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python view_status.py                    # Show dashboard
  python view_status.py dashboard          # Show dashboard
  python view_status.py alerts             # Show active alerts
  python view_status.py health             # Health check
  python view_status.py component system   # Show specific component
        """
    )

    parser.add_argument(
        "command",
        nargs="?",
        default="dashboard",
        choices=["dashboard", "alerts", "health", "component"],
        help="Command to execute (default: dashboard)"
    )

    parser.add_argument(
        "name",
        nargs="?",
        help="Component name (for component command)"
    )

    parser.add_argument(
        "--monitor",
        "-m",
        action="store_true",
        help="Continuous monitoring mode"
    )

    parser.add_argument(
        "--interval",
        "-i",
        type=int,
        default=30,
        help="Refresh interval for monitoring mode (seconds)"
    )

    args = parser.parse_args()

    # 컴포넌트 명령어인데 이름이 없으면 오류
    if args.command == "component" and not args.name:
        parser.error("component command requires a component name")

    # 비동기 실행
    if args.monitor:
        async def monitor_wrapper():
            async with create_shared_context() as context:
                await monitor_continuous(context, args.interval)
        asyncio.run(monitor_wrapper())
    else:
        asyncio.run(view_status(args))


if __name__ == "__main__":
    main()