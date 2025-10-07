# 🚀 Project Setup Guide

## 📁 Directory Structure

```
autotrading/
├── config/                 # Configuration management
│   ├── __init__.py
│   ├── config.py          # Configuration loader
│   └── settings.yaml      # Default settings
├── core/                  # Core infrastructure
│   ├── __init__.py
│   ├── events.py          # Event definitions
│   ├── event_bus.py      # Event processing
│   ├── exceptions.py      # Custom exceptions
│   └── logger.py          # Logging setup
├── database/              # Database layer
│   ├── __init__.py
│   ├── models.py          # SQLAlchemy models
│   ├── connection.py      # Connection pooling
│   └── migrations/        # Schema migrations
│       └── 001_initial_schema.sql
├── broker/                # IB API integration
│   ├── __init__.py
│   ├── ib_client.py       # IB client wrapper
│   ├── connection_manager.py
│   └── contracts.py       # Contract definitions
├── data/                  # Market data processing
│   ├── __init__.py
│   ├── market_data.py     # Market data handler
│   ├── tick_handler.py    # Tick processing
│   ├── bar_builder.py     # Bar aggregation
│   └── historical.py      # Historical data
├── strategies/            # Trading strategies
│   ├── __init__.py
│   ├── base_strategy.py   # Strategy interface
│   ├── strategy_manager.py
│   └── samples/           # Sample strategies
│       └── __init__.py
├── execution/             # Order execution
│   ├── __init__.py
│   ├── order_manager.py   # Order management
│   └── execution_handler.py
├── risk/                  # Risk management
│   ├── __init__.py
│   ├── risk_manager.py    # Risk rules
│   ├── position_sizing.py # Position sizing
│   └── emergency.py       # Emergency procedures
├── portfolio/             # Portfolio management
│   ├── __init__.py
│   ├── position_manager.py
│   └── pnl_calculator.py  # P&L calculation
├── monitoring/            # System monitoring
│   ├── __init__.py
│   ├── metrics.py         # Performance metrics
│   └── health_check.py    # Health monitoring
├── tests/                 # Test suite
│   ├── __init__.py
│   ├── conftest.py        # Pytest configuration
│   ├── fixtures/          # Test data
│   └── mocks/             # Mock objects
├── scripts/               # Utility scripts
│   ├── setup_database.py
│   ├── start_trading.py
│   └── backtest.py
├── logs/                  # Log files (auto-created)
├── .env.example           # Environment variables template
├── .gitignore
├── requirements.txt       # Python dependencies
├── pytest.ini             # Pytest configuration
├── README.md              # Project documentation
└── main.py               # Main entry point
```

## 🔧 Installation Steps

### 1. Create Project Directory
```bash
mkdir autotrading
cd autotrading
```

### 2. Initialize Git Repository
```bash
git init
echo "# Automated Futures Trading System" > README.md
git add README.md
git commit -m "Initial commit"
```

### 3. Setup Python Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Setup PostgreSQL Database
```bash
# Install PostgreSQL if not already installed
# Windows: Download from https://www.postgresql.org/download/windows/
# Linux: sudo apt-get install postgresql postgresql-contrib
# Mac: brew install postgresql

# Start PostgreSQL service
# Windows: Use Services app or pg_ctl
# Linux: sudo systemctl start postgresql
# Mac: brew services start postgresql

# Create database and user
psql -U postgres
```

```sql
CREATE DATABASE trading_db;
CREATE USER trader WITH ENCRYPTED PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE trading_db TO trader;
\q
```

### 6. Configure Environment Variables
```bash
# Copy example environment file
cp .env.example .env

# Edit .env file with your settings
# Windows: notepad .env
# Linux/Mac: nano .env
```

### 7. Run Database Migrations
```bash
python scripts/setup_database.py
```

### 8. Test IB Connection
```bash
# Start TWS or IB Gateway
# Enable API connections in TWS/Gateway settings
# Run connection test
python scripts/test_connection.py
```

## 📝 Configuration Files

### requirements.txt
```txt
# Core Dependencies
ib_async>=0.9.86
asyncpg>=0.27.0
asyncio>=3.4.3

# Database
psycopg2-binary>=2.9.6
sqlalchemy>=2.0.0
alembic>=1.11.0

# Data Processing
pandas>=2.0.0
numpy>=1.24.0

# Configuration
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0
PyYAML>=6.0

# Logging & Monitoring
python-json-logger>=2.0.7
psutil>=5.9.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
pytest-mock>=3.11.0

# Development Tools
black>=23.3.0
pylint>=2.17.0
mypy>=1.4.0
ipython>=8.14.0
```

### .env.example
```bash
# Environment
ENVIRONMENT=development

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_db
DB_USER=trader
DB_PASSWORD=your_secure_password

# Interactive Brokers
IB_HOST=127.0.0.1
IB_PORT=7497  # TWS: 7497, Gateway: 4001
IB_CLIENT_ID=1

# Risk Management
MAX_POSITION_SIZE=5
MAX_PORTFOLIO_RISK=0.02
MAX_DRAWDOWN=0.05
EMERGENCY_LIQUIDATE_ON_DISCONNECT=true

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/trading_system.log
LOG_MAX_BYTES=104857600
LOG_BACKUP_COUNT=10

# Performance
TICK_BUFFER_SIZE=10000
DB_POOL_SIZE=10
EVENT_QUEUE_SIZE=10000
```

### pytest.ini
```ini
[tool:pytest]
minversion = 6.0
addopts =
    -ra
    -q
    --strict-markers
    --cov=autotrading
    --cov-report=term-missing
    --cov-report=html
testpaths =
    tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    unit: marks tests as unit tests
```

### .gitignore
```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Project specific
.env
logs/
*.log
data/
backtest_results/

# Database
*.db
*.sqlite
*.sqlite3

# Testing
.coverage
htmlcov/
.pytest_cache/
.tox/

# Distribution
dist/
build/
*.egg-info/

# OS
.DS_Store
Thumbs.db
```

## 🎯 Quick Start Commands

### Development Workflow
```bash
# Activate virtual environment
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Run tests
pytest

# Run with coverage
pytest --cov=autotrading

# Format code
black autotrading/

# Lint code
pylint autotrading/

# Type checking
mypy autotrading/
```

### Running the System
```bash
# Start in development mode
python main.py --env development

# Start in production mode
python main.py --env production

# Run backtest
python scripts/backtest.py --strategy ma_crossover --start 2024-01-01 --end 2024-12-31

# Check system health
python scripts/health_check.py
```

## 🔍 Verification Steps

### 1. Database Connection
```python
# scripts/test_db_connection.py
import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

async def test_db():
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    version = await conn.fetchval('SELECT version()')
    print(f"Connected to: {version}")
    await conn.close()

asyncio.run(test_db())
```

### 2. IB API Connection
```python
# scripts/test_ib_connection.py
import asyncio
from ib_async import IB
from dotenv import load_dotenv
import os

load_dotenv()

async def test_ib():
    ib = IB()
    await ib.connectAsync(
        os.getenv('IB_HOST'),
        int(os.getenv('IB_PORT')),
        clientId=int(os.getenv('IB_CLIENT_ID'))
    )
    print(f"Connected to IB: {ib.isConnected()}")
    print(f"Server Version: {ib.serverVersion()}")
    ib.disconnect()

asyncio.run(test_ib())
```

### 3. Event System Test
```python
# scripts/test_events.py
import asyncio
from core.event_bus import EventBus
from core.events import MarketDataEvent

async def test_events():
    bus = EventBus()

    async def handler(event):
        print(f"Received event: {event}")

    bus.subscribe("MARKET_DATA", handler)

    event = MarketDataEvent({"symbol": "ES", "price": 4500.50})
    await bus.publish(event)

asyncio.run(test_events())
```

## 📊 Development Metrics Targets

| Metric | Target | Description |
|--------|--------|-------------|
| Test Coverage | >80% | Code covered by tests |
| Latency | <100ms | Tick to signal processing |
| Memory Usage | <500MB | Normal operation memory |
| Database Pool | 10 connections | Concurrent DB operations |
| Event Throughput | >1000/sec | Events processed per second |
| Log Rotation | 100MB | Maximum log file size |

## 🚨 Common Issues & Solutions

### Issue: Cannot connect to PostgreSQL
```bash
# Check if PostgreSQL is running
pg_isready

# Check PostgreSQL logs
# Windows: Check Event Viewer
# Linux: sudo journalctl -u postgresql
# Mac: tail -f /usr/local/var/log/postgresql@14.log
```

### Issue: IB API connection refused
```
1. Check TWS/Gateway is running
2. Enable API connections in Global Configuration
3. Check socket port (TWS: 7497, Gateway: 4001)
4. Add 127.0.0.1 to trusted IPs
5. Check firewall settings
```

### Issue: Module import errors
```bash
# Ensure virtual environment is activated
which python  # Should show venv path

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

## 📚 Next Steps

1. **Complete Phase 1**: Set up infrastructure foundation
2. **Test Connectivity**: Verify database and IB connections
3. **Implement Core**: Build event system and logging
4. **Start Data Collection**: Begin collecting tick data
5. **Develop Strategy**: Implement first trading strategy

---

*Setup completed! Ready to start development.*
*For questions, refer to architecture.md and implementation_roadmap.md*