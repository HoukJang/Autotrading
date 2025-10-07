# IB API Integration - Test Execution Guide

## Quick Start

### Option 1: Using Batch File (Windows)
```bash
# Run the interactive test menu
run_ib_tests.bat
```

### Option 2: Using Python Script Directly
```bash
# Setup environment
cd C:\Users\linep\Autotrading
python tests/run_tests.py --setup-only

# Run quick validation
python tests/run_tests.py --unit --integration --verbose
```

### Option 3: Using Pytest Directly
```bash
cd C:\Users\linep\Autotrading
python -m pytest tests/ -v --tb=short
```

## Test Categories

### 1. Unit Tests (Fast - ~30 seconds)
Tests individual components in isolation with comprehensive mocking.

```bash
# Run all unit tests
python tests/run_tests.py --unit --verbose

# Run specific component tests
python -m pytest tests/test_phase2_ib.py::TestIBConnectionManager -v
python -m pytest tests/test_phase2_ib.py::TestContractFactory -v
python -m pytest tests/test_phase2_ib.py::TestIBClient -v
```

**Coverage:**
- Connection lifecycle management
- Contract creation and validation
- Order placement and management
- Market data subscription
- Error handling scenarios

### 2. Integration Tests (Medium - ~2 minutes)
Tests component interactions and end-to-end workflows.

```bash
# Run integration tests
python tests/run_tests.py --integration --verbose

# Run specific integration scenarios
python -m pytest tests/test_phase2_ib.py::TestIntegrationScenarios -v
```

**Coverage:**
- Complete trading workflows
- Connection resilience
- Data integrity under stress
- Cross-component communication

### 3. Edge Cases & Stress Tests (Slow - ~5 minutes)
Tests boundary conditions, failure scenarios, and extreme conditions.

```bash
# Run edge case tests
python tests/run_tests.py --edge-cases --verbose

# Run specific edge case categories
python -m pytest tests/test_edge_cases.py::TestConnectionEdgeCases -v
python -m pytest tests/test_edge_cases.py::TestOrderExecutionEdgeCases -v
```

**Coverage:**
- Rapid connect/disconnect cycles
- High-frequency operations
- Memory exhaustion scenarios
- Concurrent operations
- Malformed data handling

### 4. Performance Tests (Slow - ~10 minutes)
Benchmarks and performance validation under load.

```bash
# Run performance tests
python tests/run_tests.py --performance --verbose

# Run specific performance tests
python -m pytest tests/test_edge_cases.py::TestPerformanceBenchmarks -v -m performance
```

**Coverage:**
- Connection establishment speed
- Order throughput benchmarks
- Memory usage stability
- High-frequency data processing

## Test Execution Options

### Comprehensive Test Suite
```bash
# Run everything (recommended for pre-production validation)
python tests/run_tests.py --all --verbose --coverage
```

### Quick Validation (CI/CD)
```bash
# Fast validation for continuous integration
python tests/run_tests.py --unit --mock-validation
```

### Production Readiness Check
```bash
# Comprehensive production readiness validation
python tests/run_tests.py --all --verbose --coverage
```

### Development Testing
```bash
# During development - fast feedback
python -m pytest tests/test_phase2_ib.py -v --tb=short -x
```

## Mock Testing (No TWS Required)

All tests use comprehensive mocks by default, allowing testing without a TWS/IB Gateway connection.

### Mock Validation
```bash
# Validate mock implementations
python tests/run_tests.py --mock-validation --verbose
```

### Mock Features
- **MockIB**: Complete IB API simulation
- **MockTicker**: Real-time market data simulation
- **MockTrade**: Order execution simulation
- **MockContract**: Contract creation simulation
- **Performance Simulation**: Configurable delays and behaviors

## Test Reports and Coverage

### Generated Reports
After running tests, reports are available in:

```
tests/
├── reports/
│   ├── unit_tests.xml          # JUnit XML for CI/CD
│   ├── integration_tests.xml   # Integration test results
│   ├── edge_case_tests.xml     # Edge case test results
│   ├── performance_tests.xml   # Performance test results
│   ├── test_summary.json       # Comprehensive JSON report
│   └── test_summary.html       # HTML dashboard
├── coverage/
│   ├── html/                   # HTML coverage report
│   └── unit/                   # Unit test coverage
└── quality_assessment_report.md # Detailed quality analysis
```

### Viewing Reports
```bash
# Open HTML coverage report
start tests/coverage/html/index.html

# Open test summary dashboard
start tests/reports/test_summary.html

# View quality assessment
notepad tests/quality_assessment_report.md
```

## Test Configuration

### Pytest Configuration
Configuration in `tests/pytest.ini`:
- Test discovery patterns
- Marker definitions
- Logging configuration
- Coverage settings
- Warning filters

### Custom Markers
```bash
# Run only unit tests
python -m pytest -m unit

# Run only fast tests
python -m pytest -m "not slow"

# Run only performance tests
python -m pytest -m performance

# Run reliability tests
python -m pytest -m reliability
```

## Troubleshooting

### Common Issues

#### 1. Import Errors
```bash
# Ensure PYTHONPATH is set correctly
set PYTHONPATH=C:\Users\linep\Autotrading\autotrading;%PYTHONPATH%

# Or use absolute imports
python -m pytest tests/test_phase2_ib.py --tb=short
```

#### 2. Async Test Issues
```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio

# Check asyncio mode in pytest.ini
asyncio_mode = auto
```

#### 3. Mock Import Issues
```bash
# Validate mock implementations first
python tests/run_tests.py --mock-validation
```

#### 4. Test Timeouts
```bash
# Run with increased timeout for slow systems
python -m pytest tests/ --timeout=300
```

### Debug Mode
```bash
# Run with maximum verbosity and debug info
python -m pytest tests/test_phase2_ib.py -vvs --tb=long --log-cli-level=DEBUG
```

### Test Isolation
```bash
# Run single test method
python -m pytest tests/test_phase2_ib.py::TestIBClient::test_market_order_execution -v

# Run with cleanup between tests
python -m pytest tests/ --forked
```

## Continuous Integration

### GitHub Actions Example
```yaml
name: IB API Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: windows-latest
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        pip install pytest pytest-asyncio pytest-mock psutil pytest-cov
    - name: Run tests
      run: |
        python tests/run_tests.py --unit --integration --coverage
    - name: Upload coverage
      uses: codecov/codecov-action@v1
```

### Local CI Simulation
```bash
# Simulate CI environment locally
python tests/run_tests.py --unit --integration --verbose
```

## Performance Monitoring

### Execution Time Tracking
Tests automatically track and report execution times:
- Individual test methods
- Test suite totals
- Performance benchmarks
- Memory usage patterns

### Performance Thresholds
Built-in performance assertions:
- Connection time < 1 second
- Order placement < 100ms
- Memory growth < 50MB per test cycle
- Tick processing > 100 ticks/second

## Quality Gates

### Production Readiness Checklist
- [ ] All unit tests pass (100%)
- [ ] All integration tests pass (100%)
- [ ] Edge case coverage > 90%
- [ ] Performance benchmarks met
- [ ] Memory leak validation passed
- [ ] Error handling comprehensive
- [ ] Mock validation successful

### Quality Metrics
Automated quality scoring based on:
- Test coverage percentage
- Performance benchmark results
- Error handling completeness
- Code complexity metrics
- Documentation coverage

## Next Steps

### After Running Tests
1. **Review Reports**: Check generated HTML and JSON reports
2. **Address Failures**: Fix any failing tests before production
3. **Analyze Coverage**: Ensure adequate test coverage (>90%)
4. **Performance Tuning**: Address any performance bottlenecks
5. **Production Deployment**: Use quality gates for deployment decisions

### Ongoing Testing
- Run quick tests during development
- Full test suite before releases
- Performance tests for optimization
- Regular reliability testing under load

## Support and Documentation

### Additional Resources
- `quality_assessment_report.md` - Detailed quality analysis
- `tests/conftest.py` - Test fixtures and configuration
- `tests/mocks/ib_mocks.py` - Mock implementation details
- Project documentation for architecture overview

### Getting Help
For issues with test execution:
1. Check this guide for common solutions
2. Review test logs in `logs/pytest.log`
3. Validate mock implementations first
4. Run with debug verbosity for detailed output