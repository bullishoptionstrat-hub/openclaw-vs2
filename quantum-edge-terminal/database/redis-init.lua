-- Redis initialization script
-- Run with: redis-cli < redis-init.lua

-- Key prefixes and structures
-- qt:latest_candle:{symbol}:{timeframe} - Current candle (expires in 60s)
-- qt:signals:{symbol} - Active signals for symbol
-- qt:alerts:queue - Alert message queue
-- qt:user:{userId}:settings - User preferences
-- qt:circuit_breaker - Trading halt flags
-- qt:rate_limiter:{userId} - Rate limit counters

-- Initialize empty structures
DEL qt:signals:*
DEL qt:alerts:queue
DEL qt:circuit_breaker
DEL qt:rate_limiter:*

-- Set default circuit breaker to 'OFF'
SET qt:circuit_breaker OFF

-- Create Redis streams for audit logging
XGROUP CREATE qt:signal_log signal_group $ MKSTREAM
XGROUP CREATE qt:alert_log alert_group $ MKSTREAM
XGROUP CREATE qt:trade_log trade_group $ MKSTREAM

-- Create channels for pub/sub
PUBLISH qt:initialized "Redis initialized successfully"
