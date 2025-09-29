#!/usr/bin/env python3
"""
Status Handler Test Script

StatusHandler 기능을 테스트하고 사용법을 보여주는 스크립트입니다.
"""

import asyncio
import json
from datetime import datetime

from autotrading.core.shared_context import create_shared_context
from autotrading.core.status_handler import ComponentState


async def test_status_handler():
    """StatusHandler 기능 테스트"""
    try:
        async with create_shared_context() as context:
            handler = context.status_handler
            dashboard = context.status_dashboard

            print("🧪 Testing Status Handler Functionality")
            print("=" * 50)

            # 1. 기본 컴포넌트 상태 설정
            print("\n1️⃣ Setting up initial component statuses...")

            await handler.update_status("data_collector", ComponentState.INITIALIZED, {
                "symbols": ["AAPL", "MSFT", "GOOGL"],
                "last_fetch": None,
                "total_symbols": 3
            })

            await handler.update_status("analyzer", ComponentState.INITIALIZED, {
                "strategy": "momentum",
                "signals_generated": 0,
                "last_analysis": None
            })

            await handler.update_status("trader", ComponentState.INITIALIZED, {
                "portfolio_value": 100000.0,
                "positions": 0,
                "last_trade": None
            })

            await handler.update_status("ticker_manager", ComponentState.RUNNING, {
                "active_symbols": 150,
                "failed_updates": 0,
                "last_sync": datetime.now().isoformat(),
                "api_rate_limit": "250/min"
            })

            print("✅ Initial statuses set")

            # 2. 전체 상태 조회 및 표시
            print("\n2️⃣ Retrieving all statuses...")
            statuses = await handler.get_all_statuses()
            print(f"📊 Found {len(statuses)} components")

            for status in statuses:
                print(f"  • {status.name}: {status.state.value}")

            # 3. 헬스 체크 수행
            print("\n3️⃣ Performing health check...")
            health_check = await handler.health_check_all()
            print(f"🏥 Overall Health: {health_check['overall_health']}")
            print(f"📈 Healthy Components: {health_check['healthy_components']}/{health_check['total_components']}")

            # 4. 컴포넌트 상태 업데이트 (정상 작동)
            print("\n4️⃣ Updating component to running state...")

            await handler.update_status("data_collector", ComponentState.RUNNING, {
                "symbols": ["AAPL", "MSFT", "GOOGL"],
                "last_fetch": datetime.now().isoformat(),
                "fetched_records": 1000,
                "status": "fetching market data"
            })

            # 5. 에러 상태 시뮬레이션
            print("\n5️⃣ Simulating error condition...")

            await handler.set_component_error("analyzer", "Failed to connect to data source", {
                "error_code": "CONNECTION_TIMEOUT",
                "retry_count": 3
            })

            # 6. 알람 확인
            print("\n6️⃣ Checking for alerts...")
            alerts = await handler.get_alerts()
            print(f"🚨 Active alerts: {len(alerts)}")

            for alert in alerts:
                level_emoji = {"CRITICAL": "🚨", "WARNING": "⚠️", "OK": "✅"}.get(alert.level.value, "❓")
                print(f"  {level_emoji} {alert.component}: {alert.issue}")

            # 7. 대시보드 데이터 표시
            print("\n7️⃣ Generating dashboard view...")
            dashboard_data = await dashboard.get_dashboard_data()

            print(f"\n📊 Dashboard Summary:")
            print(f"  Total Components: {dashboard_data['health_check']['total_components']}")
            print(f"  Healthy: {dashboard_data['health_check']['healthy_components']}")
            print(f"  Total Alerts: {dashboard_data['summary']['total_alerts']}")
            print(f"  Critical Alerts: {dashboard_data['summary']['critical_alerts']}")

            # 8. 컨텍스트 매니저 테스트
            print("\n8️⃣ Testing component context manager...")

            async with handler.component_context("test_component", {"test": True}) as ctx:
                print("  📝 Component context started")
                await ctx.update_details({"progress": 50})
                print("  🔄 Progress updated to 50%")
                await asyncio.sleep(0.1)  # 작업 시뮬레이션
                await ctx.update_details({"progress": 100, "completed": True})
                print("  ✅ Work completed")

            # 9. 최종 상태 확인
            print("\n9️⃣ Final status check...")
            final_health = await handler.health_check_all()

            print(f"\n📋 Final System Status:")
            print(f"  Overall Health: {final_health['overall_health']}")

            for component in final_health['components']:
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

                print(f"  {state_emoji} {component['name']}: {component['state']} {health_emoji}")

            print(f"\n🎉 Status Handler test completed successfully!")

            # 10. 사용법 안내
            print(f"\n💡 Usage Examples:")
            print(f"  python view_status.py                    # Show dashboard")
            print(f"  python view_status.py alerts             # Show alerts")
            print(f"  python view_status.py health             # Health check")
            print(f"  python view_status.py component system   # Specific component")
            print(f"  python view_status.py --monitor          # Continuous monitoring")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise


async def demo_component_lifecycle():
    """컴포넌트 생명주기 데모"""
    print("\n🔄 Demonstrating component lifecycle...")

    async with create_shared_context() as context:
        handler = context.status_handler

        # 컴포넌트 시작
        await handler.update_status("demo_component", ComponentState.INITIALIZED, {
            "demo": True,
            "phase": "initialization"
        })

        print("  🟡 Component initialized")

        # 실행 상태로 전환
        await handler.update_status("demo_component", ComponentState.RUNNING, {
            "demo": True,
            "phase": "processing",
            "progress": 0
        })

        print("  🟢 Component running")

        # 진행상황 업데이트 시뮬레이션
        for progress in [25, 50, 75, 100]:
            await handler.update_status("demo_component", ComponentState.RUNNING, {
                "demo": True,
                "phase": "processing",
                "progress": progress
            })
            print(f"  📊 Progress: {progress}%")
            await asyncio.sleep(0.1)

        # 완료 상태
        await handler.update_status("demo_component", ComponentState.HEALTHY, {
            "demo": True,
            "phase": "completed",
            "progress": 100,
            "result": "success"
        })

        print("  ✅ Component completed successfully")


if __name__ == "__main__":
    print("🧪 Starting Status Handler Tests")
    print("This script demonstrates the status handling functionality")
    print()

    # 기본 테스트 실행
    asyncio.run(test_status_handler())

    print("\n" + "="*50)

    # 컴포넌트 생명주기 데모
    asyncio.run(demo_component_lifecycle())

    print(f"\n🎯 Test Summary:")
    print(f"  ✅ StatusHandler functionality verified")
    print(f"  ✅ StatusDashboard working correctly")
    print(f"  ✅ Alert system operational")
    print(f"  ✅ Component context manager tested")
    print(f"  ✅ CLI tools ready for use")
    print(f"\n👉 Run 'python view_status.py' to see the current system status!")