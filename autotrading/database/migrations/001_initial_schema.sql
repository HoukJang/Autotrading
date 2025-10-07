-- Initial Database Schema for Automated Trading System
-- Version: 1.0.0
-- Date: 2025-10-06

-- Enable TimescaleDB extension if available (optional but recommended)
-- CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Market Data Storage (1-minute bars)
CREATE TABLE IF NOT EXISTS market_data_1min (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open_price DECIMAL(10,4) NOT NULL,
    high_price DECIMAL(10,4) NOT NULL,
    low_price DECIMAL(10,4) NOT NULL,
    close_price DECIMAL(10,4) NOT NULL,
    volume BIGINT NOT NULL,
    vwap DECIMAL(10,4),
    tick_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol, timestamp)
);

-- Trading Signals from Strategies
CREATE TABLE IF NOT EXISTS trading_signals (
    id BIGSERIAL PRIMARY KEY,
    strategy_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    signal_type VARCHAR(10) NOT NULL CHECK (signal_type IN ('BUY', 'SELL', 'HOLD')),
    signal_strength DECIMAL(3,2) CHECK (signal_strength >= 0 AND signal_strength <= 1),
    price DECIMAL(10,4) NOT NULL,
    quantity INTEGER NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Order Management and Tracking
CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    order_id VARCHAR(50) UNIQUE NOT NULL,
    parent_signal_id BIGINT REFERENCES trading_signals(id),
    symbol VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL CHECK (action IN ('BUY', 'SELL')),
    order_type VARCHAR(20) NOT NULL CHECK (order_type IN ('MKT', 'LMT', 'STP', 'STP_LMT')),
    quantity INTEGER NOT NULL,
    limit_price DECIMAL(10,4),
    stop_price DECIMAL(10,4),
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    fill_price DECIMAL(10,4),
    fill_quantity INTEGER DEFAULT 0,
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    filled_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    commission DECIMAL(8,2),
    metadata JSONB,
    CONSTRAINT check_status CHECK (status IN ('PENDING', 'SUBMITTED', 'FILLED', 'PARTIAL', 'CANCELLED', 'REJECTED'))
);

-- Position Tracking
CREATE TABLE IF NOT EXISTS positions (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    quantity INTEGER NOT NULL,
    avg_cost DECIMAL(10,4) NOT NULL,
    market_value DECIMAL(12,2),
    unrealized_pnl DECIMAL(12,2),
    realized_pnl DECIMAL(12,2) DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(symbol)
);

-- Daily Performance Metrics
CREATE TABLE IF NOT EXISTS performance_metrics (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    total_pnl DECIMAL(12,2),
    realized_pnl DECIMAL(12,2),
    unrealized_pnl DECIMAL(12,2),
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    max_drawdown DECIMAL(12,2),
    portfolio_value DECIMAL(15,2),
    sharpe_ratio DECIMAL(6,3),
    win_rate DECIMAL(5,2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(date)
);

-- Strategy-specific Performance
CREATE TABLE IF NOT EXISTS strategy_performance (
    id BIGSERIAL PRIMARY KEY,
    strategy_id VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    date DATE NOT NULL,
    signals_generated INTEGER DEFAULT 0,
    trades_executed INTEGER DEFAULT 0,
    pnl DECIMAL(12,2) DEFAULT 0,
    win_rate DECIMAL(5,2),
    sharpe_ratio DECIMAL(6,3),
    max_drawdown DECIMAL(12,2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(strategy_id, symbol, date)
);

-- System Events and Logging
CREATE TABLE IF NOT EXISTS system_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(10) NOT NULL CHECK (severity IN ('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL')),
    component VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    metadata JSONB,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Risk Management Events
CREATE TABLE IF NOT EXISTS risk_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    symbol VARCHAR(20),
    risk_level VARCHAR(20) CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    description TEXT NOT NULL,
    action_taken TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Configuration and Settings (for persistence)
CREATE TABLE IF NOT EXISTS system_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_time ON market_data_1min(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_market_data_timestamp ON market_data_1min(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_strategy_time ON trading_signals(strategy_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON trading_signals(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status_time ON orders(status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_system_events_time ON system_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_system_events_severity ON system_events(severity, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_time ON risk_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_risk_events_level ON risk_events(risk_level, timestamp DESC);

-- Create function to update last_updated timestamp
CREATE OR REPLACE FUNCTION update_last_updated()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for positions table
DROP TRIGGER IF EXISTS update_positions_last_updated ON positions;
CREATE TRIGGER update_positions_last_updated
    BEFORE UPDATE ON positions
    FOR EACH ROW
    EXECUTE FUNCTION update_last_updated();

-- Create function to calculate portfolio statistics
CREATE OR REPLACE FUNCTION calculate_portfolio_stats()
RETURNS TABLE (
    total_value DECIMAL,
    total_pnl DECIMAL,
    position_count INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COALESCE(SUM(market_value), 0) as total_value,
        COALESCE(SUM(unrealized_pnl + realized_pnl), 0) as total_pnl,
        COUNT(*)::INTEGER as position_count
    FROM positions
    WHERE quantity != 0;
END;
$$ LANGUAGE plpgsql;

-- Create view for active positions
CREATE OR REPLACE VIEW active_positions AS
SELECT
    p.*,
    (p.unrealized_pnl + p.realized_pnl) as total_pnl,
    CASE
        WHEN p.avg_cost > 0 THEN ((p.market_value - (p.avg_cost * ABS(p.quantity))) / (p.avg_cost * ABS(p.quantity)) * 100)
        ELSE 0
    END as pnl_percentage
FROM positions p
WHERE p.quantity != 0
ORDER BY ABS(p.quantity) DESC;

-- Create view for today's orders
CREATE OR REPLACE VIEW todays_orders AS
SELECT
    o.*,
    s.strategy_id,
    s.signal_strength
FROM orders o
LEFT JOIN trading_signals s ON o.parent_signal_id = s.id
WHERE DATE(o.submitted_at) = CURRENT_DATE
ORDER BY o.submitted_at DESC;

-- Create view for recent signals
CREATE OR REPLACE VIEW recent_signals AS
SELECT
    s.*,
    COUNT(o.id) as order_count,
    SUM(CASE WHEN o.status = 'FILLED' THEN 1 ELSE 0 END) as filled_count
FROM trading_signals s
LEFT JOIN orders o ON s.id = o.parent_signal_id
WHERE s.timestamp > NOW() - INTERVAL '24 hours'
GROUP BY s.id
ORDER BY s.timestamp DESC;

-- Insert default configuration values
INSERT INTO system_config (key, value, description) VALUES
    ('max_position_size', '5', 'Maximum position size per symbol'),
    ('max_portfolio_risk', '0.02', 'Maximum portfolio risk percentage'),
    ('max_drawdown', '0.05', 'Maximum allowed drawdown'),
    ('emergency_liquidate_on_disconnect', 'true', 'Liquidate all positions on connection loss'),
    ('position_sizing_method', 'fixed', 'Position sizing method: fixed, volatility, kelly'),
    ('default_stop_loss_pct', '0.02', 'Default stop loss percentage'),
    ('default_take_profit_pct', '0.04', 'Default take profit percentage')
ON CONFLICT (key) DO NOTHING;

-- Grant permissions (adjust user as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trader;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trader;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO trader;