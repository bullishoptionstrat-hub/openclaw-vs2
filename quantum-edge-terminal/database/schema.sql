-- Quantum Edge Terminal Database Schema
-- PostgreSQL 15+

-- Candles table (historical OHLCV data)
CREATE TABLE IF NOT EXISTS candles (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  timeframe VARCHAR(10) NOT NULL,  -- 1m, 5m, 15m, 1h, 4h, 1D
  timestamp BIGINT NOT NULL,
  open DECIMAL(18,8) NOT NULL,
  high DECIMAL(18,8) NOT NULL,
  low DECIMAL(18,8) NOT NULL,
  close DECIMAL(18,8) NOT NULL,
  volume BIGINT NOT NULL,
  vwap DECIMAL(18,8),
  bidAsk JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(symbol, timeframe, timestamp),
  INDEX(symbol, timeframe, timestamp)
);

-- Signals table (trade signals)
CREATE TABLE IF NOT EXISTS signals (
  id SERIAL PRIMARY KEY,
  signal_type VARCHAR(50) NOT NULL,  -- BUY, SELL, etc
  symbol VARCHAR(20) NOT NULL,
  entry_price DECIMAL(18,8) NOT NULL,
  stop_loss DECIMAL(18,8),
  take_profit DECIMAL(18,8),
  confidence DECIMAL(5,4) NOT NULL,  -- 0.0 - 1.0
  confirmations INT DEFAULT 0,
  status VARCHAR(20) DEFAULT 'PENDING',  -- PENDING, ACTIVE, CLOSED
  pnl DECIMAL(18,8),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  closed_at TIMESTAMP,
  INDEX(symbol, status, created_at)
);

-- Alerts table
CREATE TABLE IF NOT EXISTS alerts (
  id SERIAL PRIMARY KEY,
  alert_type VARCHAR(50) NOT NULL,  -- TRADE, STRUCTURE, MACRO, VOLUME
  severity VARCHAR(20) NOT NULL,  -- CRITICAL, HIGH, MEDIUM, LOW
  message TEXT NOT NULL,
  channels JSONB DEFAULT '[]'::jsonb,  -- discord, email, websocket, sms
  user_id INT,
  sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  read_at TIMESTAMP,
  INDEX(severity, sent_at)
);

-- Market structure events
CREATE TABLE IF NOT EXISTS structure_events (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  timeframe VARCHAR(10) NOT NULL,
  event_type VARCHAR(50) NOT NULL,  -- BOS, CHoCH, FVG, SWEEP, ORDER_BLOCK
  level DECIMAL(18,8) NOT NULL,
  direction VARCHAR(10) NOT NULL,  -- UP, DOWN
  confidence DECIMAL(5,4) NOT NULL,
  volume BIGINT,
  timestamp BIGINT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX(symbol, timeframe, timestamp)
);

-- User sessions
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  api_key VARCHAR(255) UNIQUE,
  settings JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_login TIMESTAMP
);

-- User preferences
CREATE TABLE IF NOT EXISTS user_settings (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id) ON DELETE CASCADE,
  theme VARCHAR(20) DEFAULT 'dark',  -- dark, light
  alert_channels JSONB,  -- discord, email, sms, etc
  risk_per_trade DECIMAL(5,2) DEFAULT 1.0,  -- percentage
  max_open_positions INT DEFAULT 5,
  auto_trade_enabled BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id)
);

-- Signal execution log (audit trail)
CREATE TABLE IF NOT EXISTS signal_log (
  id SERIAL PRIMARY KEY,
  signal_id INT REFERENCES signals(id) ON DELETE CASCADE,
  user_id INT REFERENCES users(id),
  action VARCHAR(50),  -- GENERATED, ALERTED, ENTERED, EXITED, REJECTED
  details JSONB,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX(signal_id, user_id)
);

-- Create indexes for performance
CREATE INDEX idx_candles_symbol_timeframe ON candles(symbol, timeframe);
CREATE INDEX idx_candles_timestamp ON candles(timestamp DESC);
CREATE INDEX idx_signals_symbol_status ON signals(symbol, status);
CREATE INDEX idx_alerts_severity_date ON alerts(severity, sent_at DESC);
CREATE INDEX idx_structure_symbol_time ON structure_events(symbol, timestamp DESC);

-- Create materialized view for signal statistics
CREATE OR REPLACE VIEW signal_stats AS
SELECT
  symbol,
  COUNT(*) total_signals,
  SUM(CASE WHEN signal_type = 'BUY' THEN 1 ELSE 0 END) buy_signals,
  SUM(CASE WHEN signal_type = 'SELL' THEN 1 ELSE 0 END) sell_signals,
  AVG(confidence) avg_confidence,
  AVG(EXTRACT(EPOCH FROM (closed_at - created_at))) avg_duration_seconds,
  SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) profitable,
  AVG(CASE WHEN pnl IS NOT NULL THEN pnl ELSE 0 END) avg_pnl
FROM signals
WHERE created_at > CURRENT_DATE - INTERVAL '30 days'
GROUP BY symbol;
