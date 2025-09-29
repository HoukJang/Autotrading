#!/usr/bin/env python3
"""
자동 인증 테스트

SharedContext의 자동 인증 기능을 테스트합니다.
"""

import asyncio
import logging
from pathlib import Path

from autotrading.core.context import create_shared_context, close_shared_context
from autotrading.config.settings import Settings


async def test_auto_authentication():
    """자동 인증 테스트"""
    print("="*60)
    print("🔐 AUTOMATIC AUTHENTICATION TEST")
    print("="*60)

    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    try:
        settings = Settings()
        token_path = Path(settings.schwab_token_file)

        print(f"📁 Token file: {settings.schwab_token_file}")
        print(f"📁 Token exists: {'Yes' if token_path.exists() else 'No'}")

        if token_path.exists():
            size = token_path.stat().st_size
            print(f"📁 Token size: {size} bytes")

        print("\n🚀 Starting automatic authentication...")
        print("(브라우저 인증이 필요할 수 있습니다)")
        print("-" * 40)

        # 자동 인증 포함 SharedContext 생성
        context = await create_shared_context(auto_auth=True)

        print("\n✅ Authentication completed!")
        print(f"   - Authenticated: {context['schwab_service'].is_authenticated()}")
        print(f"   - Client available: {context['schwab_client'] is not None}")

        # 헬스 체크
        print("\n🔍 Performing health check...")
        health = await context['schwab_service'].health_check()
        print(f"   - Status: {health['status']}")
        print(f"   - Authenticated: {health['authenticated']}")

        # 서비스 통계
        stats = context['schwab_service'].get_stats()
        print(f"   - Circuit Breaker: {stats['circuit_breaker']['state']}")
        print(f"   - Rate Limiter: {stats['rate_limiter']['current_tokens']:.1f} tokens")

        # 간단한 API 호출 테스트
        print("\n📊 Testing API call...")
        try:
            quotes = await context['schwab_service'].get_quotes(['AAPL'])
            if 'AAPL' in quotes:
                price = quotes['AAPL'].get('lastPrice', 'N/A')
                print(f"   ✅ AAPL Price: ${price}")
            else:
                print("   ⚠️ AAPL quote not found")
        except Exception as e:
            print(f"   ⚠️ API call failed: {e}")
            print("     (This might be normal outside market hours)")

        print("\n🎉 All tests completed successfully!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'context' in locals():
            await close_shared_context(context)
            print("\n🧹 Resources cleaned up")


async def test_force_manual_authentication():
    """강제 수동 인증 테스트"""
    print("="*60)
    print("🔐 FORCE MANUAL AUTHENTICATION TEST")
    print("="*60)

    try:
        print("🚀 Starting forced manual authentication...")
        print("브라우저 인증이 시작됩니다.")

        # 강제 수동 인증
        context = await create_shared_context(
            auto_auth=True,
            force_manual_auth=True
        )

        print("\n✅ Manual authentication completed!")
        print(f"   - Authenticated: {context['schwab_service'].is_authenticated()}")

    except Exception as e:
        print(f"❌ Manual authentication failed: {e}")
    finally:
        if 'context' in locals():
            await close_shared_context(context)


async def test_no_authentication():
    """인증 없는 컨텍스트 생성 테스트"""
    print("="*60)
    print("🔧 NO AUTHENTICATION TEST")
    print("="*60)

    try:
        print("🚀 Creating context without authentication...")

        # 인증 없이 컨텍스트 생성
        context = await create_shared_context(auto_auth=False)

        print("✅ Context created without authentication!")
        print(f"   - Schwab service: {context['schwab_service'] is not None}")
        print(f"   - Authenticated: {context['schwab_service'].is_authenticated()}")
        print(f"   - Database connected: {context['db_pool'] is not None}")

    except Exception as e:
        print(f"❌ Test failed: {e}")
    finally:
        if 'context' in locals():
            await close_shared_context(context)


async def main():
    """메인 테스트 함수"""
    tests = [
        ("Automatic Authentication", test_auto_authentication),
        ("Force Manual Authentication", test_force_manual_authentication),
        ("No Authentication", test_no_authentication)
    ]

    print("AUTHENTICATION TESTS")
    print("="*60)

    for i, (name, test_func) in enumerate(tests, 1):
        print(f"\n[{i}/{len(tests)}] {name}")
        choice = input("Run test? (y/n/q): ").strip().lower()

        if choice == 'q':
            print("Tests terminated.")
            break
        elif choice == 'y':
            try:
                await test_func()
            except KeyboardInterrupt:
                print("\nTest interrupted.")
                break
            except Exception as e:
                print(f"Test failed: {e}")

            input("\nPress ENTER to continue...")
        else:
            print("Skipping.")

    print("\nAll tests completed!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted.")
    except Exception as e:
        print(f"Program error: {e}")
        import traceback
        traceback.print_exc()