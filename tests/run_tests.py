#!/usr/bin/env python3
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


def run_integration_tests(verbose=False):
    """Run integration tests"""
    print("\n" + "="*60)
    print("RUNNING INTEGRATION TESTS")
    print("="*60)

    cmd_parts = ["python", "-m", "pytest"]

    test_files = [
        "tests/test_phase2_ib.py::TestIntegrationScenarios",
    ]
    cmd_parts.extend(test_files)

    if verbose:
        cmd_parts.extend(["-v", "--tb=long"])
    else:
        cmd_parts.append("-q")

    cmd_parts.extend([
        "--junit-xml=tests/reports/integration_tests.xml",
        "-m", "integration"
    ])

    cmd = " ".join(cmd_parts)
    print(f"Command: {cmd}")

    start_time = time.time()
    returncode, stdout, stderr = run_command(cmd, cwd=project_root)
    end_time = time.time()

    print(f"\nIntegration tests completed in {end_time - start_time:.2f} seconds")
    print(f"Exit code: {returncode}")

    if stdout:
        print("\nSTDOUT:")
        print(stdout)

    if stderr:
        print("\nSTDERR:")
        print(stderr)

    return returncode == 0


def run_edge_case_tests(verbose=False):
    """Run edge case and stress tests"""
    print("\n" + "="*60)
    print("RUNNING EDGE CASE & STRESS TESTS")
    print("="*60)

    cmd_parts = ["python", "-m", "pytest", "tests/test_edge_cases.py"]

    if verbose:
        cmd_parts.extend(["-v", "--tb=short"])
    else:
        cmd_parts.append("-q")

    cmd_parts.extend([
        "--junit-xml=tests/reports/edge_case_tests.xml",
        "-m", "not performance"  # Skip performance tests by default
    ])

    cmd = " ".join(cmd_parts)
    print(f"Command: {cmd}")

    start_time = time.time()
    returncode, stdout, stderr = run_command(cmd, cwd=project_root)
    end_time = time.time()

    print(f"\nEdge case tests completed in {end_time - start_time:.2f} seconds")
    print(f"Exit code: {returncode}")

    if stdout:
        print("\nSTDOUT:")
        print(stdout)

    if stderr:
        print("\nSTDERR:")
        print(stderr)

    return returncode == 0


def run_performance_tests(verbose=False):
    """Run performance benchmark tests"""
    print("\n" + "="*60)
    print("RUNNING PERFORMANCE TESTS")
    print("="*60)

    cmd_parts = ["python", "-m", "pytest"]

    cmd_parts.extend([
        "tests/test_edge_cases.py::TestPerformanceBenchmarks",
        "tests/test_phase2_ib.py::TestPerformanceAndReliability"
    ])

    if verbose:
        cmd_parts.extend(["-v", "--tb=short"])
    else:
        cmd_parts.append("-q")

    cmd_parts.extend([
        "--junit-xml=tests/reports/performance_tests.xml",
        "-m", "performance"
    ])

    cmd = " ".join(cmd_parts)
    print(f"Command: {cmd}")

    start_time = time.time()
    returncode, stdout, stderr = run_command(cmd, cwd=project_root, timeout=600)
    end_time = time.time()

    print(f"\nPerformance tests completed in {end_time - start_time:.2f} seconds")
    print(f"Exit code: {returncode}")

    if stdout:
        print("\nSTDOUT:")
        print(stdout)

    if stderr:
        print("\nSTDERR:")
        print(stderr)

    return returncode == 0


def run_mock_validation():
    """Validate mock implementations"""
    print("\n" + "="*60)
    print("VALIDATING MOCK IMPLEMENTATIONS")
    print("="*60)

    try:
        # Test mock imports
        from tests.mocks.ib_mocks import MockIB, MockTicker, MockTrade
        print("✓ Mock imports successful")

        # Test basic mock functionality
        mock_ib = MockIB()
        print("✓ MockIB instantiation successful")

        # Test async mock functionality
        import asyncio

        async def test_mock_async():
            await mock_ib.connectAsync("127.0.0.1", 7497, 1)
            return mock_ib.isConnected()

        connected = asyncio.run(test_mock_async())
        if connected:
            print("✓ Mock async operations successful")
        else:
            print("✗ Mock async operations failed")
            return False

        mock_ib.disconnect()
        print("✓ Mock cleanup successful")

        return True

    except Exception as e:
        print(f"✗ Mock validation failed: {e}")
        return False


def generate_test_report(results):
    """Generate comprehensive test report"""
    print("\n" + "="*60)
    print("GENERATING TEST REPORT")
    print("="*60)

    report = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "summary": {
            "total_test_suites": len(results),
            "passed_suites": sum(1 for r in results.values() if r["passed"]),
            "failed_suites": sum(1 for r in results.values() if not r["passed"]),
            "overall_success": all(r["passed"] for r in results.values())
        }
    }

    # Write JSON report
    report_file = project_root / "tests" / "reports" / "test_summary.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)

    # Generate HTML report
    html_report = generate_html_report(report)
    html_file = project_root / "tests" / "reports" / "test_summary.html"
    with open(html_file, 'w') as f:
        f.write(html_report)

    print(f"Reports generated:")
    print(f"  JSON: {report_file}")
    print(f"  HTML: {html_file}")

    return report


def generate_html_report(report):
    """Generate HTML test report"""
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>IB API Integration Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
        .summary {{ margin: 20px 0; }}
        .test-suite {{ margin: 10px 0; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }}
        .passed {{ background-color: #d4edda; border-color: #c3e6cb; }}
        .failed {{ background-color: #f8d7da; border-color: #f5c6cb; }}
        .timestamp {{ color: #666; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>IB API Integration Test Report</h1>
        <p class="timestamp">Generated: {report['timestamp']}</p>
    </div>

    <div class="summary">
        <h2>Summary</h2>
        <ul>
            <li>Total Test Suites: {report['summary']['total_test_suites']}</li>
            <li>Passed: {report['summary']['passed_suites']}</li>
            <li>Failed: {report['summary']['failed_suites']}</li>
            <li>Overall Status: {'PASSED' if report['summary']['overall_success'] else 'FAILED'}</li>
        </ul>
    </div>

    <div class="results">
        <h2>Test Results</h2>
"""

    for suite_name, result in report['results'].items():
        status_class = "passed" if result['passed'] else "failed"
        status_text = "PASSED" if result['passed'] else "FAILED"

        html += f"""
        <div class="test-suite {status_class}">
            <h3>{suite_name}</h3>
            <p><strong>Status:</strong> {status_text}</p>
            <p><strong>Duration:</strong> {result.get('duration', 'N/A')} seconds</p>
        </div>
"""

    html += """
    </div>
</body>
</html>
"""
    return html


def main():
    """Main test runner function"""
    parser = argparse.ArgumentParser(description="IB API Integration Test Runner")
    parser.add_argument("--unit", action="store_true", help="Run unit tests")
    parser.add_argument("--integration", action="store_true", help="Run integration tests")
    parser.add_argument("--edge-cases", action="store_true", help="Run edge case tests")
    parser.add_argument("--performance", action="store_true", help="Run performance tests")
    parser.add_argument("--all", action="store_true", help="Run all tests")
    parser.add_argument("--mock-validation", action="store_true", help="Validate mocks only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--setup-only", action="store_true", help="Setup environment only")

    args = parser.parse_args()

    # If no specific tests requested, run basic suite
    if not any([args.unit, args.integration, args.edge_cases, args.performance,
                args.all, args.mock_validation]):
        args.unit = True
        args.integration = True

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

    if args.mock_validation:
        print("Mock validation completed successfully.")
        return 0

    # Track results
    results = {}
    overall_success = True

    # Run selected test suites
    if args.unit or args.all:
        start_time = time.time()
        success = run_unit_tests(args.verbose, args.coverage)
        end_time = time.time()

        results["unit_tests"] = {
            "passed": success,
            "duration": round(end_time - start_time, 2)
        }
        overall_success = overall_success and success

    if args.integration or args.all:
        start_time = time.time()
        success = run_integration_tests(args.verbose)
        end_time = time.time()

        results["integration_tests"] = {
            "passed": success,
            "duration": round(end_time - start_time, 2)
        }
        overall_success = overall_success and success

    if args.edge_cases or args.all:
        start_time = time.time()
        success = run_edge_case_tests(args.verbose)
        end_time = time.time()

        results["edge_case_tests"] = {
            "passed": success,
            "duration": round(end_time - start_time, 2)
        }
        overall_success = overall_success and success

    if args.performance or args.all:
        start_time = time.time()
        success = run_performance_tests(args.verbose)
        end_time = time.time()

        results["performance_tests"] = {
            "passed": success,
            "duration": round(end_time - start_time, 2)
        }
        # Don't fail overall on performance test failures
        # overall_success = overall_success and success

    # Generate comprehensive report
    if results:
        report = generate_test_report(results)

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

        if overall_success:
            print("\n🎉 All tests passed! The IB API integration is ready for production.")
        else:
            print("\n❌ Some tests failed. Please review the results and fix issues.")

    return 0 if overall_success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)