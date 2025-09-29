# Autotrading Scripts

Production-ready command-line tools for the Autotrading system administration and monitoring.

## Scripts Overview

### 1. run_ticker_update.py
**Purpose**: Updates ticker information with integrated delisting detection
**Use Cases**: Cron jobs, scheduled updates, system administration

**Key Features**:
- Batch processing with configurable size
- Integrated delisting detection and ticker deactivation
- Comprehensive error handling and logging
- Continuous monitoring mode
- Dry-run capability for testing
- Production-ready exit codes and status reporting

### 2. run_status_monitor.py
**Purpose**: Real-time system status monitoring and health checking
**Use Cases**: System monitoring, troubleshooting, health dashboards

**Key Features**:
- Interactive real-time dashboard
- Continuous monitoring with alerts
- Component filtering and status export
- JSON export for integration with monitoring systems
- Curses-based UI for terminal dashboard
- Health check summaries and alert notifications

## Prerequisites

### System Requirements
- Python 3.10+
- PostgreSQL 17.4+ with autotrading database
- Valid Schwab API credentials
- Configured environment variables or auth.py

### Dependencies
All dependencies are managed through pyproject.toml:
```bash
# Install in development mode with all dependencies
pip install -e ".[dev]"

# Or install just the core dependencies
pip install -e .
```

### Configuration
Ensure your environment is properly configured:

1. **Database Configuration**:
   ```bash
   # Via environment variable
   export DATABASE_URL="postgresql://user:password@localhost:5432/autotrading"

   # Or via autotrading/config/auth.py
   DATABASE_CONFIG = {
       'url': 'postgresql://user:password@localhost:5432/autotrading'
   }
   ```

2. **Schwab API Configuration**:
   ```bash
   # Via environment variables
   export SCHWAB_APP_KEY="your_app_key"
   export SCHWAB_APP_SECRET="your_app_secret"

   # Or via autotrading/config/auth.py
   SCHWAB_CONFIG = {
       'app_key': 'your_app_key',
       'app_secret': 'your_app_secret',
       'callback_url': 'https://localhost:8080/callback',
       'token_file': 'tokens.json'
   }
   ```

## Usage Examples

### Ticker Update Script

#### Basic Operations
```bash
# One-time ticker update with default batch size (50)
python scripts/run_ticker_update.py

# Large batch update with verbose logging
python scripts/run_ticker_update.py --batch-size 200 --verbose

# Test run without making actual changes
python scripts/run_ticker_update.py --dry-run --verbose

# Check configuration without running updates
python scripts/run_ticker_update.py --config-check
```

#### Continuous Operations
```bash
# Run continuously with 1-hour intervals
python scripts/run_ticker_update.py --continuous --interval 3600

# Continuous mode with custom batch size and logging
python scripts/run_ticker_update.py --continuous --interval 1800 --batch-size 100 --log-file ticker_updates.log
```

#### Production Deployment
```bash
# Cron job example (runs every hour)
0 * * * * cd /path/to/autotrading && python scripts/run_ticker_update.py --batch-size 100 >> /var/log/autotrading/ticker_updates.log 2>&1

# Systemd service for continuous operation
[Unit]
Description=Autotrading Ticker Update Service
After=postgresql.service

[Service]
Type=simple
User=autotrading
WorkingDirectory=/opt/autotrading
ExecStart=/opt/autotrading/.venv/bin/python scripts/run_ticker_update.py --continuous --interval 3600
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

### Status Monitor Script

#### One-time Checks
```bash
# Quick system health check
python scripts/run_status_monitor.py --check

# Export status to JSON file
python scripts/run_status_monitor.py --export system_status.json

# Check specific components only
python scripts/run_status_monitor.py --check --filter "ticker_manager,data_collector"
```

#### Interactive Monitoring
```bash
# Real-time dashboard (press 'q' to quit, 'r' to refresh)
python scripts/run_status_monitor.py --dashboard

# Dashboard with custom refresh rate
python scripts/run_status_monitor.py --dashboard --refresh 3

# Dashboard monitoring specific components
python scripts/run_status_monitor.py --dashboard --filter "ticker_manager,analyzer,trader"
```

#### Continuous Monitoring
```bash
# Continuous monitoring with console output
python scripts/run_status_monitor.py --monitor --interval 30

# Monitoring with alerts enabled
python scripts/run_status_monitor.py --monitor --interval 30 --alerts

# Background monitoring with logging
python scripts/run_status_monitor.py --monitor --interval 60 --verbose --log-file monitor.log
```

## Script Options Reference

### run_ticker_update.py

| Option | Description | Default |
|--------|-------------|---------|
| `--batch-size N` | Number of tickers per batch | 50 |
| `--continuous` | Run continuously with intervals | False |
| `--interval SECONDS` | Interval between runs | 3600 |
| `--dry-run` | Simulate without making changes | False |
| `--verbose` | Enable verbose logging | False |
| `--log-file PATH` | Write logs to file | None |
| `--config-check` | Check configuration and exit | False |

### run_status_monitor.py

| Option | Description | Default |
|--------|-------------|---------|
| `--check` | One-time status check | - |
| `--dashboard` | Interactive real-time dashboard | - |
| `--monitor` | Continuous monitoring mode | - |
| `--export FILE` | Export status to JSON | - |
| `--interval SECONDS` | Update interval | 10 |
| `--refresh SECONDS` | Dashboard refresh interval | 5 |
| `--filter COMPONENTS` | Comma-separated component filter | None |
| `--alerts` | Enable alert notifications | False |
| `--verbose` | Enable verbose logging | False |
| `--log-file PATH` | Write logs to file | None |

## Exit Codes

Both scripts follow standard Unix exit code conventions:

| Code | Meaning | Description |
|------|---------|-------------|
| 0 | Success | Operation completed successfully |
| 1 | General Error | Configuration, database, or runtime error |
| 2 | Partial Failure | Some operations failed (ticker_update only) |

For status_monitor.py specifically:
- **0**: System healthy
- **1**: System has warnings
- **2**: System has critical issues

## Integration Examples

### Monitoring System Integration
```bash
# Nagios/Icinga check
python scripts/run_status_monitor.py --check --filter "critical_components"
if [ $? -eq 2 ]; then
    echo "CRITICAL: System has critical issues"
    exit 2
elif [ $? -eq 1 ]; then
    echo "WARNING: System has warnings"
    exit 1
else
    echo "OK: System healthy"
    exit 0
fi

# Prometheus metrics export
python scripts/run_status_monitor.py --export /tmp/autotrading_status.json
# Process JSON for Prometheus node_exporter textfile collector
```

### Automated Operations
```bash
# Pre-deployment health check
echo "Checking system health before deployment..."
python scripts/run_status_monitor.py --check
if [ $? -ne 0 ]; then
    echo "System not healthy, aborting deployment"
    exit 1
fi

# Post-deployment verification
echo "Running ticker update to verify system..."
python scripts/run_ticker_update.py --batch-size 10 --verbose
if [ $? -eq 0 ]; then
    echo "Deployment verification successful"
else
    echo "Deployment verification failed"
    exit 1
fi
```

## Troubleshooting

### Common Issues

1. **ImportError: No module named 'autotrading'**
   - Ensure you're running from the project root directory
   - Install the package: `pip install -e .`

2. **Database Connection Failed**
   - Check `DATABASE_URL` environment variable
   - Verify PostgreSQL is running and accessible
   - Check auth.py configuration

3. **Schwab API Authentication Errors**
   - Verify `SCHWAB_APP_KEY` and `SCHWAB_APP_SECRET`
   - Check token file permissions and validity
   - Ensure callback URL is correct

4. **Permission Denied**
   - Make scripts executable: `chmod +x scripts/*.py`
   - Check file permissions and ownership

### Debug Mode
Enable verbose logging for troubleshooting:
```bash
# Ticker update debug
python scripts/run_ticker_update.py --verbose --log-file debug.log

# Status monitor debug
python scripts/run_status_monitor.py --check --verbose --log-file status_debug.log
```

### Configuration Validation
```bash
# Check if configuration is valid
python scripts/run_ticker_update.py --config-check

# Verify database connectivity
python -c "
import asyncio
from autotrading.database.connection import create_db_pool
from autotrading.config.settings import settings

async def test():
    pool = await create_db_pool(settings.database_url)
    print('Database connection successful')
    await pool.close()

asyncio.run(test())
"
```

## Performance Considerations

### Ticker Update Script
- **Batch Size**: Larger batches (100-200) are more efficient but use more memory
- **API Rate Limits**: Schwab API allows ~120 requests/minute
- **Database Connections**: Uses connection pooling for efficiency
- **Continuous Mode**: Suitable for production with appropriate intervals (1-4 hours)

### Status Monitor Script
- **Dashboard Mode**: Low resource usage, suitable for continuous operation
- **Refresh Intervals**: 3-10 seconds recommended for dashboard
- **Component Filtering**: Reduces query complexity and display clutter
- **Export Mode**: Efficient for integration with external monitoring systems

## Security Considerations

- **Credentials**: Never commit API keys or passwords to version control
- **File Permissions**: Ensure log files and token files have appropriate permissions
- **Network Security**: Use SSL/TLS for database connections in production
- **Process Isolation**: Run scripts with dedicated service accounts in production

## Development and Testing

### Running Tests
```bash
# Test ticker update logic
pytest tests/test_ticker_manager.py -v

# Test status handler functionality
pytest tests/test_status_handler.py -v

# Integration testing
python scripts/run_ticker_update.py --dry-run --batch-size 5 --verbose
python scripts/run_status_monitor.py --check --verbose
```

### Contributing
When modifying scripts:
1. Follow the existing code style (Black formatting, line length 100)
2. Add appropriate logging and error handling
3. Update CLI help text and this README
4. Test with both valid and invalid configurations
5. Ensure graceful handling of interrupts (Ctrl+C)

## Support
For issues or questions:
1. Check the troubleshooting section above
2. Review system logs and script output
3. Verify configuration with `--config-check`
4. Test with `--dry-run` mode first