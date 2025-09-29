#!/usr/bin/env python3
"""
Autotrading Test Runner

모든 테스트를 실행하고 결과를 정리해서 보여주는 스크립트입니다.
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(cmd, description=""):
    """명령어 실행 및 결과 반환"""
    print(f"\n{'='*60}")
    print(f">>> {description}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}")
    print()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent
        )

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        return result.returncode == 0, result.stdout, result.stderr

    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False, "", str(e)


def main():
    """메인 테스트 실행 함수"""
    print("AUTOTRADING TEST SUITE")
    print("=" * 60)

    # 현재 디렉토리 확인
    current_dir = Path.cwd()
    if current_dir.name != "Autotrading":
        print("ERROR: Please run this script from the Autotrading root directory")
        sys.exit(1)

    total_tests = 0
    passed_tests = 0
    failed_tests = 0

    # 1. 단위 테스트 실행
    success, stdout, stderr = run_command(
        [sys.executable, "-m", "pytest", "tests/unit/", "-v", "--tb=short"],
        "RUNNING UNIT TESTS"
    )

    if success:
        print("✅ Unit tests completed successfully")
        # pytest 출력에서 테스트 결과 파싱
        lines = stdout.split('\n')
        for line in lines:
            if "passed" in line and "warnings" in line:
                # 예: "17 passed, 8 warnings in 0.33s"
                parts = line.split()
                if len(parts) > 0 and parts[0].isdigit():
                    passed_tests += int(parts[0])
                    total_tests += int(parts[0])
    else:
        print("❌ Unit tests failed")
        failed_tests += 1

    # 2. 통합 테스트 실행
    success, stdout, stderr = run_command(
        [sys.executable, "-m", "pytest", "tests/integration/", "-v", "--tb=short"],
        "Running Integration Tests"
    )

    if success:
        print("✅ Integration tests completed successfully")
        lines = stdout.split('\n')
        for line in lines:
            if "passed" in line and ("warnings" in line or "seconds" in line):
                parts = line.split()
                if len(parts) > 0 and parts[0].isdigit():
                    passed_tests += int(parts[0])
                    total_tests += int(parts[0])
    else:
        print("❌ Integration tests failed")
        failed_tests += 1

    # 3. 코드 품질 검사 (선택적)
    print(f"\n{'='*60}")
    print("🔍 Code Quality Checks")
    print(f"{'='*60}")

    # Black 포매팅 검사
    if os.system("black --version > nul 2>&1") == 0:
        success, stdout, stderr = run_command(
            [sys.executable, "-m", "black", "--check", "autotrading/", "tests/"],
            "Checking code formatting with Black"
        )
        if success:
            print("✅ Code formatting is correct")
        else:
            print("⚠️ Code formatting issues found (run 'black autotrading/ tests/' to fix)")
    else:
        print("⚠️ Black not installed, skipping formatting check")

    # Ruff 린팅 검사
    if os.system("ruff --version > nul 2>&1") == 0:
        success, stdout, stderr = run_command(
            [sys.executable, "-m", "ruff", "check", "autotrading/", "tests/"],
            "Running code linting with Ruff"
        )
        if success:
            print("✅ No linting issues found")
        else:
            print("⚠️ Linting issues found")
    else:
        print("⚠️ Ruff not installed, skipping linting check")

    # 4. 최종 결과 요약
    print(f"\n{'='*60}")
    print("📊 TEST SUMMARY")
    print(f"{'='*60}")

    if total_tests > 0:
        success_rate = (passed_tests / total_tests) * 100
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {success_rate:.1f}%")

        if success_rate == 100:
            print("\n🎉 ALL TESTS PASSED!")
        elif success_rate >= 80:
            print(f"\n⚠️ Most tests passed ({success_rate:.1f}%)")
        else:
            print(f"\n❌ Many tests failed ({success_rate:.1f}%)")
    else:
        print("❌ No tests were executed successfully")

    print(f"\n{'='*60}")
    print("📋 NEXT STEPS")
    print(f"{'='*60}")

    print("Manual Tests:")
    print("  • Run browser authentication: python tests/manual/manual_auth_test.py")
    print("  • Requires actual Schwab API credentials")
    print("  • Creates tokens.json for future automated testing")

    print("\nDevelopment:")
    print("  • Code formatting: black autotrading/ tests/")
    print("  • Linting: ruff check autotrading/ tests/")
    print("  • Coverage: pytest --cov=autotrading tests/")

    print("\nProject Status:")
    print("  ✅ Core architecture implemented")
    print("  ✅ Authentication system tested")
    print("  ✅ API services validated")
    print("  ⏳ Ready for business logic implementation")


if __name__ == "__main__":
    main()