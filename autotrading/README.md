# 🚀 Automated Futures Trading System

A professional-grade automated trading system for futures markets using Interactive Brokers API, designed for scalping strategies with 1-minute bars.

## 📋 Features

- **Real-time Trading**: High-frequency scalping with sub-second execution
- **Strategy Framework**: Plugin-based architecture for multiple strategies
- **Risk Management**: Comprehensive position limits and emergency protocols
- **Data Pipeline**: Tick-to-bar aggregation with PostgreSQL storage
- **Multi-Symbol Support**: Scalable architecture for multiple futures contracts
- **Backtesting**: Historical strategy validation and optimization
- **Position Management**: Dynamic position sizing with multiple algorithms

## 🛠️ Technology Stack

- **Language**: Python 3.9+
- **Broker API**: ib_async (Interactive Brokers)
- **Database**: PostgreSQL 13+
- **Architecture**: Event-driven, async processing
- **Testing**: pytest with async support

## 📦 Installation

### Prerequisites

1. Python 3.9 or higher
2. PostgreSQL 13 or higher
3. Interactive Brokers TWS or IB Gateway
4. Git

### Setup Steps

1. **Clone the repository**
```bash
git clone <repository-url>
cd autotrading
```

2. **Create virtual environment**
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Setup PostgreSQL database**
```bash
# Create database and user
psql -U postgres
CREATE DATABASE trading_db;
CREATE USER trader WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE trading_db TO trader;
\q

# Run migrations
python scripts/setup_database.py
```

5. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your configuration
```

6. **Configure Interactive Brokers**
- Open TWS or IB Gateway
- Enable API connections in Global Configuration
- Set Trusted IP to 127.0.0.1
- Note the socket port (TWS: 7497, Gateway: 4001)

## 🚀 Quick Start

### Test Connections
```bash
# Test database connection
python scripts/test_db_connection.py

# Test IB API connection
python scripts/test_ib_connection.py
```

### Run the System
```bash
# Development mode
python main.py --env development

# Production mode (with IB Gateway)
python main.py --env production
```

### Run Backtests
```bash
python scripts/backtest.py --strategy ma_crossover --symbol ES --start 2024-01-01 --end 2024-12-31
```

## 📁 Project Structure

```
autotrading/
├── config/                 # Configuration management (singleton pattern)
├── core/                   # Core infrastructure (events, logging, exceptions)
├── database/               # Database models and migrations
├── broker/                 # IB API integration (connection, contracts, client)
├── data/                   # Market data processing (bar builder, collector)
├── strategies/             # Strategy base classes and samples
├── strategy/               # Adaptive strategy management system
├── analysis/               # Market analysis (regime detection, triggers)
│   └── triggers/           # Technical triggers (Bollinger, MA Cross, etc.)
├── backtest/               # Backtesting engine
├── tests/                  # Test suite
├── scripts/                # Utility scripts
└── utils/                  # Helper utilities
```

## 🔧 Configuration

Key configuration options in `.env`:

```bash
# Interactive Brokers
IB_HOST=127.0.0.1
IB_PORT=7497  # TWS: 7497, Gateway: 4001

# Risk Management
MAX_POSITION_SIZE=5
MAX_PORTFOLIO_RISK=0.02
MAX_DRAWDOWN=0.05

# Position Sizing
POSITION_SIZING_METHOD=fixed  # fixed, volatility, kelly
```

## 📊 Database Schema

Core tables:
- `market_data_1min` - 1-minute bar data
- `trading_signals` - Strategy-generated signals
- `orders` - Order tracking
- `positions` - Current positions
- `performance_metrics` - Daily performance

## 🧪 Testing

Run tests:
```bash
# All tests
pytest

# Unit tests only
pytest -m unit

# Integration tests
pytest -m integration

# With coverage
pytest --cov=autotrading
```

## 📈 Strategy Development

Create a new strategy:

```python
from autotrading.strategies.base import Strategy, Bar
from autotrading.backtest.orders import Order, OrderSide, OrderType

class MyStrategy(Strategy):
    def on_bar(self, bar: Bar, context) -> list:
        # Your strategy logic here
        orders = []
        if self.should_buy(bar):
            orders.append(Order(
                symbol=bar.symbol,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=1
            ))
        return orders
```

## ⚠️ Risk Management

The system includes multiple risk controls:
- Position size limits
- Maximum portfolio risk percentage
- Maximum drawdown monitoring
- Emergency liquidation on connection loss
- Real-time P&L tracking

## 📝 Development Workflow

1. Create feature branch
```bash
git checkout -b feature/your-feature
```

2. Make changes and test
```bash
pytest
black autotrading/
pylint autotrading/
```

3. Commit changes
```bash
git add .
git commit -m "feat: your feature description"
```

## 🚨 Production Checklist

Before going live:
- [ ] Complete 2+ weeks paper trading
- [ ] Test all emergency procedures
- [ ] Verify position reconciliation
- [ ] Set up monitoring alerts
- [ ] Document operational procedures
- [ ] Create backup and recovery plan

## 📊 Performance Monitoring

Monitor system health:
```bash
# Check system status
python scripts/health_check.py

# View performance metrics
python scripts/performance_report.py

# Monitor real-time positions
python scripts/position_monitor.py
```

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📚 Documentation

- [Architecture Overview](../architecture.md)
- [Implementation Roadmap](../implementation_roadmap.md)
- [Project Setup Guide](../project_setup.md)

## ⚖️ License

This project is proprietary software. All rights reserved.

## 🆘 Support

For issues and questions:
- Check the [documentation](../docs/)
- Review [common issues](#common-issues)
- Contact the development team

## 🔒 Security

- Never commit `.env` files
- Use strong database passwords
- Keep IB credentials secure
- Enable 2FA on IB account
- Monitor for unusual activity

## 🎯 Roadmap

- [x] Phase 1: Infrastructure Foundation (Config, Logging, Events)
- [x] Phase 2: IB API Integration (Connection, Contracts, Client)
- [x] Phase 3: Data Processing Pipeline (Bar Builder, Collector)
- [x] Phase 4: Adaptive Strategy Framework (Regime Detection, Triggers)
- [ ] Phase 5: Risk Management Enhancement
- [ ] Phase 6: Performance Monitoring Dashboard

---

**Version**: 1.1.0
**Last Updated**: 2026-01-01
**Status**: Active Development