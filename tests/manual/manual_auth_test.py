"""
수동 브라우저 인증 테스트

실제 Schwab 계정으로 브라우저 인증을 수행합니다.
한 번 인증하면 토큰이 저장되어 이후 자동 인증 가능합니다.
"""

import asyncio
import logging
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from autotrading.config.settings import Settings
from autotrading.api.schwab_service import SchwabAPIService


async def manual_authentication_test():
    """수동 브라우저 인증 테스트"""
    print("="*60)
    print("SCHWAB API MANUAL AUTHENTICATION TEST")
    print("="*60)

    try:
        # 설정 로드
        print("Loading settings...")
        settings = Settings()

        print(f"App Key: {settings.schwab_app_key[:8]}...")
        print(f"Callback URL: {settings.schwab_callback_url}")
        print(f"Token File: {settings.schwab_token_file}")
        print()

        # 서비스 생성
        print("Creating Schwab API service...")
        service = SchwabAPIService(
            app_key=settings.schwab_app_key,
            app_secret=settings.schwab_app_secret,
            callback_url=settings.schwab_callback_url,
            token_file=settings.schwab_token_file,
            config=settings.api_config
        )
        print("Service created successfully!")
        print()

        # 기존 토큰 확인
        from pathlib import Path
        token_path = Path(settings.schwab_token_file)

        if token_path.exists():
            print(f"FOUND: Existing token file at {settings.schwab_token_file}")
            print("Will attempt to use existing token first...")
        else:
            print(f"NO TOKEN: Token file not found at {settings.schwab_token_file}")
            print("Will perform new authentication flow...")
        print()

        # 인증 시작
        print("STARTING AUTHENTICATION...")
        print("="*40)
        print("IMPORTANT:")
        print("1. Browser will open automatically")
        print("2. Log in to your Schwab account")
        print("3. Authorize the application")
        print("4. Browser will redirect to callback URL")
        print("5. You may see SSL warning - this is normal")
        print("6. Token will be saved automatically")
        print("="*40)
        print()

        input("Press ENTER to start authentication...")
        print()

        # 인증 실행
        success = await service.initialize()

        if success:
            print("SUCCESS AUTHENTICATION SUCCESSFUL!")
            print(f"OK Authenticated: {service.is_authenticated()}")

            # 토큰 파일 확인
            if token_path.exists():
                print(f"OK Token saved to: {settings.schwab_token_file}")

                # 토큰 파일 크기 확인
                size = token_path.stat().st_size
                print(f"OK Token file size: {size} bytes")

            print()
            print("Testing API connection...")

            # Health check
            health = await service.health_check()
            print(f"OK Health Status: {health['status']}")
            print(f"OK Authenticated: {health['authenticated']}")

            # 서비스 통계
            stats = service.get_stats()
            print(f"OK Circuit Breaker: {stats['circuit_breaker']['state']}")
            print(f"OK Rate Limiter Tokens: {stats['rate_limiter']['current_tokens']:.1f}")

            print()
            print("Testing simple API call...")

            try:
                # 간단한 API 호출 테스트 (AAPL 시세)
                quotes = await service.get_quotes(["AAPL"])

                if "AAPL" in quotes:
                    aapl = quotes["AAPL"]
                    price = aapl.get("lastPrice", "N/A")
                    volume = aapl.get("totalVolume", "N/A")

                    print(f"OK AAPL Quote Retrieved:")
                    print(f"   Price: ${price}")
                    print(f"   Volume: {volume:,}" if isinstance(volume, (int, float)) else f"   Volume: {volume}")
                else:
                    print("WARN AAPL quote not found in response")

            except Exception as e:
                print(f"WARN API call failed: {e}")
                print("This might be normal outside market hours")

            print()
            print("SUCCESS ALL TESTS COMPLETED SUCCESSFULLY!")
            print("Token has been saved for future use.")

        else:
            print("FAIL AUTHENTICATION FAILED!")
            print("Please check:")
            print("1. App Key and Secret are correct")
            print("2. Callback URL matches Schwab app settings")
            print("3. Internet connection is stable")
            print("4. Schwab account credentials are valid")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 정리
        if 'service' in locals():
            await service.close()
            print("\nService closed successfully")

    print("\n" + "="*60)
    print("MANUAL AUTHENTICATION TEST COMPLETED")
    print("="*60)


async def check_existing_token():
    """기존 토큰 상태 확인"""
    print("CHECKING EXISTING TOKEN...")
    print("-"*30)

    try:
        from pathlib import Path
        settings = Settings()
        token_path = Path(settings.schwab_token_file)

        if token_path.exists():
            print(f"OK Token file exists: {settings.schwab_token_file}")

            import json
            with open(token_path, 'r') as f:
                token_data = json.load(f)

            if "token" in token_data:
                token = token_data["token"]
                print(f"OK Access token: {token.get('access_token', 'N/A')[:20]}...")
                print(f"OK Token type: {token.get('token_type', 'N/A')}")
                print(f"OK Expires in: {token.get('expires_in', 'N/A')} seconds")

                # 간단한 인증 테스트
                print("\nTesting existing token...")
                service = SchwabAPIService(
                    app_key=settings.schwab_app_key,
                    app_secret=settings.schwab_app_secret,
                    callback_url=settings.schwab_callback_url,
                    token_file=settings.schwab_token_file,
                    config=settings.api_config
                )

                success = await service.initialize()

                if success:
                    print("OK Existing token is valid!")
                    return True
                else:
                    print("FAIL Existing token is invalid or expired")
                    return False

            else:
                print("FAIL Invalid token file format")
                return False

        else:
            print(f"FAIL No token file found at: {settings.schwab_token_file}")
            return False

    except Exception as e:
        print(f"ERROR checking token: {e}")
        return False


async def main():
    """메인 함수"""
    # 로깅 설정 (조용히)
    logging.basicConfig(level=logging.WARNING)

    print("SCHWAB API AUTHENTICATION SETUP")
    print("="*60)

    # 기존 토큰 확인
    token_valid = await check_existing_token()

    if token_valid:
        print("\nOK You already have a valid token!")
        print("You can skip manual authentication.")

        choice = input("\nDo you want to test with existing token? (y/n): ").strip().lower()
        if choice == 'y':
            print("\nUsing existing token for test...")
        else:
            print("\nPerforming new authentication...")
            token_valid = False

    if not token_valid:
        print("\nStarting manual authentication process...")
        await manual_authentication_test()


if __name__ == "__main__":
    asyncio.run(main())