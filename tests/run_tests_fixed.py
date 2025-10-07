#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Runner for IB API Integration Components
Provides various test execution modes and reporting
"""

import sys
import os
import argparse
import subprocess
import time
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "autotrading"))
sys.path.insert(0, str(project_root))


def run_command(cmd, cwd=None, timeout=300):
    """Run shell command and return result"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds"


def setup_test_environment():
    """Setup test environment"""
    print("Setting up test environment...")

    # Check if pytest is installed
    returncode, stdout, stderr = run_command("python -m pytest --version")
    if returncode != 0:
        print("Installing pytest...")
        run_command("pip install pytest pytest-asyncio pytest-mock psutil")

    # Create necessary directories
    test_dirs = [
        project_root / "tests" / "reports",
        project_root / "tests" / "coverage",
        project_root / "logs"
    ]

    for test_dir in test_dirs:
        test_dir.mkdir(parents=True, exist_ok=True)

    print("Test environment ready.")


def run_mock_validation():
    """Validate mock implementations"""
    print("\n" + "="*60)
    print("VALIDATING MOCK IMPLEMENTATIONS")
    print("="*60)

    try:
        # Test mock imports
        from tests.mocks.ib_mocks import MockIB, MockTicker, MockTrade
        print("[OK] Mock imports successful")

        # Test basic mock functionality
        mock_ib = MockIB()
        print("[OK] MockIB instantiation successful")

        # Test async mock functionality
        import asyncio

        async def test_mock_async():
            await mock_ib.connectAsync("127.0.0.1", 7497, 1)
            return mock_ib.isConnected()

        connected = asyncio.run(test_mock_async())
        if connected:
            print("[OK] Mock async operations successful")
        else:
            print("[ERROR] Mock async operations failed")
            return False

        mock_ib.disconnect()
        print("[OK] Mock cleanup successful")

        return True

    except Exception as e:
        print(f"[ERROR] Mock validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_unit_tests(verbose=False, coverage=False):
    """Run unit tests"""
    print("\n" + "="*60)
    print("RUNNING UNIT TESTS")
    print("="*60)

    cmd_parts = ["python", "-m", "pytest"]

    # Add test files
    test_files = [
        "tests/test_phase2_ib.py::TestIBConnectionManager",
        "tests/test_phase2_ib.py::TestContractFactory",
        "tests/test_phase2_ib.py::TestIBClient",
    ]
    cmd_parts.extend(test_files)

    # Add flags
    if verbose:
        cmd_parts.extend(["-v", "--tb=short"])
    else:
        cmd_parts.append("-q")

    cmd_parts.extend([
        "--junit-xml=tests/reports/unit_tests.xml",
        "-m", "not slow and not performance"
    ])

    if coverage:
        cmd_parts.extend([
            "--cov=broker",
            "--cov-report=html:tests/coverage/unit",
            "--cov-report=term-missing"
        ])

    cmd = " ".join(cmd_parts)
    print(f"Command: {cmd}")

    start_time = time.time()
    returncode, stdout, stderr = run_command(cmd, cwd=project_root)
    end_time = time.time()

    print(f"\nUnit tests completed in {end_time - start_time:.2f} seconds")
    print(f"Exit code: {returncode}")

    if stdout:
        print("\nSTDOUT:")
        print(stdout)

    if stderr:
        print("\nSTDERR:")
        print(stderr)

    return returncode == 0


def main():
    """Main test runner function"""
    # Set UTF-8 encoding for Windows console
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass

    parser = argparse.ArgumentParser(description="IB API Integration Test Runner")
    parser.add_argument("--unit", action="store_true", help="Run unit tests")
    parser.add_argument("--mock-validation", action="store_true", help="Validate mocks only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--setup-only", action="store_true", help="Setup environment only")

    args = parser.parse_args()

    # If no specific tests requested, run basic suite
    if not any([args.unit, args.mock_validation]):
        args.mock_validation = True

    print("IB API Integration Test Runner")
    print(f"Started at: {datetime.now()}")
    print("-" * 60)

    # Setup test environment
    setup_test_environment()

    if args.setup_only:
        print("Setup completed. Exiting.")
        return 0

    # Validate mocks first
    if not run_mock_validation():
        print("Mock validation failed. Cannot proceed with tests.")
        return 1

    if args.mock_validation and not args.unit:
        print("Mock validation completed successfully.")
        return 0

    # Track results
    results = {}
    overall_success = True

    # Run selected test suites
    if args.unit:
        start_time = time.time()
        success = run_unit_tests(args.verbose, args.coverage)
        end_time = time.time()

        results["unit_tests"] = {
            "passed": success,
            "duration": round(end_time - start_time, 2)
        }
        overall_success = overall_success and success

    # Show final results
    if results:
        print("\n" + "="*60)
        print("FINAL RESULTS")
        print("="*60)

        for suite_name, result in results.items():
            status = "PASSED" if result["passed"] else "FAILED"
            duration = result["duration"]
            print(f"{suite_name:<20} {status:<8} ({duration}s)")

        print("-" * 60)
        final_status = "PASSED" if overall_success else "FAILED"
        print(f"Overall Result: {final_status}")

    return 0 if overall_success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)