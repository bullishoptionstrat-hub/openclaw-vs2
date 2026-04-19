# QUANTUM EDGE TERMINAL - API Specification (Phase 1)

**Complete REST API + WebSocket specification for Phase 1 MVP**

---

## Base URLs

| Service | URL | Port | Protocol |
|---------|-----|------|----------|
| Backend API | `http://localhost:3001/api` | 3001 | HTTP |
| WebSocket | `ws://localhost:3001/ws` | 3001 | WS |
| Frontend | `http://localhost:3000` | 3000 | HTTP |
| AI Engine | `http://localhost:8000` | 8000 | HTTP |
| PostgreSQL | `localhost:5432` | 5432 | TCP |
| Redis | `localhost:6379` | 6379 | TCP |

---

## Health & Status

### GET /api/health
**Check if backend is operational**

**Response (200 OK):**
```json
{
  "status": "healthy",
  "uptime": 3600,
  "timestamp": "2026-04-03T12:00:00Z",
  "services": {
    "postgres": "connected",
    "redis": "connected",
    "websocket": "active"
  }
}
```

**Example:**
```bash
curl http://localhost:3001/api/health
```

---

## Market Data API

### GET /api/market-data/candles/:symbol/:timeframe
**Fetch historical OHLCV candles**

**Parameters:**
```
:symbol       - Ticker symbol (ES, NQ, SPY, GC, QQQ, etc.)
:timeframe    - Candle interval (1m, 5m, 15m, 1h, 4h, 1D)

Query:
limit         - Max results to return (default 100, max 1000)
offset        - Pagination offset (default 0)
start         - Unix timestamp (ms) - filter candles >= start
end           - Unix timestamp (ms) - filter candles <= end
```

**Response (200 OK):**
```json
{
  "symbol": "ES",
  "timeframe": "1h",
  "total": 500,
  "count": 100,
  "offset": 0,
  "candles": [
    {
      "timestamp": 1712500800000,
      "open": 5120.50,
      "high": 5135.75,
      "low": 5118.25,
      "close": 5130.00,
      "volume": 450000,
      "vwap": 5127.50,
      "bidAsk": {
        "bid": 5129.75,
        "ask": 5130.25,
        "bidSize": 120,
        "askSize": 85
      }
    },
    {
      "timestamp": 1712504400000,
      "open": 5131.00,
      "high": 5145.50,
      "low": 5125.00,
      "close": 5140.25,
      "volume": 520000,
      "vwap": 5137.80,
      "bidAsk": null
    }
  ]
}
```

**Examples:**
```bash
# Last 100 candles
curl http://localhost:3001/api/market-data/candles/ES/1h

# With pagination
curl "http://localhost:3001/api/market-data/candles/ES/1h?limit=50&offset=100"

# Filter by date range
curl "http://localhost:3001/api/market-data/candles/ES/1h?start=1712400000000&end=1712600000000"
```

**Caching:** 5 minutes (Redis)

---

### GET /api/market-data/latest/:symbol/:timeframe
**Get most recent candle (real-time)**

**Response (200 OK):**
```json
{
  "symbol": "ES",
  "timeframe": "1h",
  "candle": {
    "timestamp": 1712504400000,
    "open": 5131.00,
    "high": 5145.50,
    "low": 5125.00,
    "close": 5140.25,
    "volume": 520000,
    "vwap": 5137.80,
    "bidAsk": {
      "bid": 5140.00,
      "ask": 5140.50
    }
  },
  "changePercent": 0.17,
  "timestamp": "2026-04-03T16:00:00Z"
}
```

**Caching:** 60 seconds (Redis)

**Example:**
```bash
curl http://localhost:3001/api/market-data/latest/ES/1h
```

---

### POST /api/market-data/ingest
**Ingest new candle data (insert or update)**

**Request Body:**
```json
{
  "symbol": "ES",
  "timeframe": "1h",
  "candle": {
    "timestamp": 1712504400000,
    "open": 5131.00,
    "high": 5145.50,
    "low": 5125.00,
    "close": 5140.25,
    "volume": 520000,
    "vwap": 5137.80,
    "bidAsk": {
      "bid": 5140.00,
      "ask": 5140.50,
      "bidSize": 150,
      "askSize": 200
    }
  }
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "candle": {
    "id": 12345,
    "symbol": "ES",
    "timeframe": "1h",
    "timestamp": 1712504400000,
    "close": 5140.25
  },
  "cached": true,
  "action": "INSERT"
}
```

**Errors:**
```json
{
  "success": false,
  "error": "Invalid symbol or timeframe",
  "code": "VALIDATION_ERROR"
}
```

**Example:**
```bash
curl -X POST http://localhost:3001/api/market-data/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ES",
    "timeframe": "1h",
    "candle": {
      "timestamp": 1712504400000,
      "open": 5131.00,
      "high": 5145.50,
      "low": 5125.00,
      "close": 5140.25,
      "volume": 520000
    }
  }'
```

---

## Signals API

### GET /api/signals
**Fetch trade signals (with filtering)**

**Query Parameters:**
```
status        - Filter: PENDING, ACTIVE, CLOSED (default all)
symbol        - Filter by symbol (ES, SPY, etc.)
limit         - Max results (default 20, max 100)
offset        - Pagination offset (default 0)
sort          - Sort by: created_asc, created_desc, confidence_desc (default created_desc)
```

**Response (200 OK):**
```json
{
  "total": 45,
  "count": 20,
  "offset": 0,
  "signals": [
    {
      "id": 1001,
      "signal_type": "BUY",
      "symbol": "ES",
      "entry_price": 5130.00,
      "stop_loss": 5120.00,
      "take_profit": 5150.00,
      "confidence": 0.85,
      "confirmations": 3,
      "status": "ACTIVE",
      "pnl": null,
      "pnl_percent": null,
      "created_at": "2026-04-03T15:30:00Z",
      "closed_at": null
    },
    {
      "id": 1000,
      "signal_type": "SELL",
      "symbol": "SPY",
      "entry_price": 425.50,
      "stop_loss": 430.00,
      "take_profit": 420.00,
      "confidence": 0.72,
      "confirmations": 2,
      "status": "CLOSED",
      "pnl": 150.50,
      "pnl_percent": 0.35,
      "created_at": "2026-04-02T10:00:00Z",
      "closed_at": "2026-04-03T11:45:00Z"
    }
  ]
}
```

**Examples:**
```bash
# All active signals
curl "http://localhost:3001/api/signals?status=ACTIVE"

# ES signals, sorted by confidence
curl "http://localhost:3001/api/signals?symbol=ES&sort=confidence_desc"

# Pagination
curl "http://localhost:3001/api/signals?limit=10&offset=20"
```

---

### POST /api/signals
**Create a new trade signal**

**Request Body:**
```json
{
  "signal_type": "BUY",
  "symbol": "ES",
  "entry_price": 5130.00,
  "stop_loss": 5120.00,
  "take_profit": 5150.00,
  "confidence": 0.85,
  "confirmations": 3,
  "details": {
    "pattern": "BULLISH_FRACTAL",
    "detection_time": "2026-04-03T15:30:00Z",
    "market_state": "ACCUMULATION"
  }
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "signal": {
    "id": 1002,
    "signal_type": "BUY",
    "symbol": "ES",
    "entry_price": 5130.00,
    "confidence": 0.85,
    "status": "PENDING",
    "created_at": "2026-04-03T15:31:00Z"
  },
  "risk_reward": 2.0
}
```

**Example:**
```bash
curl -X POST http://localhost:3001/api/signals \
  -H "Content-Type: application/json" \
  -d '{
    "signal_type": "BUY",
    "symbol": "ES",
    "entry_price": 5130.00,
    "stop_loss": 5120.00,
    "take_profit": 5150.00,
    "confidence": 0.85,
    "confirmations": 3
  }'
```

---

### PUT /api/signals/:id
**Close/update a signal**

**Request Body:**
```json
{
  "status": "CLOSED",
  "exit_price": 5145.00,
  "exit_reason": "TARGET_HIT",
  "timestamp": 1712508600000
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "signal": {
    "id": 1002,
    "status": "CLOSED",
    "exit_price": 5145.00,
    "pnl": 300.00,
    "pnl_percent": 2.32,
    "closed_at": "2026-04-03T16:30:00Z"
  }
}
```

**Example:**
```bash
curl -X PUT http://localhost:3001/api/signals/1002 \
  -H "Content-Type: application/json" \
  -d '{
    "status": "CLOSED",
    "exit_price": 5145.00,
    "exit_reason": "TARGET_HIT"
  }'
```

---

## Alerts API

### GET /api/alerts
**Fetch recent alerts**

**Query Parameters:**
```
severity      - Filter: CRITICAL, HIGH, MEDIUM, LOW (default all)
type          - Filter: TRADE, STRUCTURE, MACRO, VOLUME (default all)
limit         - Max results (default 20, max 100)
read          - Filter: true (read only), false (unread only), none (all)
```

**Response (200 OK):**
```json
{
  "total": 156,
  "count": 20,
  "alerts": [
    {
      "id": 5001,
      "alert_type": "TRADE",
      "severity": "CRITICAL",
      "message": "BUY signal generated on ES 1h fractal with 0.85 confidence",
      "symbol": "ES",
      "threshold": 5130.00,
      "channels": ["websocket", "discord", "email"],
      "read": false,
      "created_at": "2026-04-03T15:31:00Z",
      "sent_at": "2026-04-03T15:31:02Z"
    },
    {
      "id": 5000,
      "alert_type": "STRUCTURE",
      "severity": "HIGH",
      "message": "Break of Structure detected on SPY 15m at 425.50",
      "symbol": "SPY",
      "threshold": 425.50,
      "channels": ["websocket"],
      "read": true,
      "created_at": "2026-04-03T15:15:00Z",
      "sent_at": "2026-04-03T15:15:01Z"
    }
  ]
}
```

**Examples:**
```bash
# Critical alerts only
curl "http://localhost:3001/api/alerts?severity=CRITICAL"

# Unread trade alerts
curl "http://localhost:3001/api/alerts?type=TRADE&read=false"
```

---

### POST /api/alerts
**Create a new alert**

**Request Body:**
```json
{
  "alert_type": "TRADE",
  "severity": "CRITICAL",
  "message": "BUY signal on ES fractal pattern",
  "symbol": "ES",
  "channels": ["websocket", "discord", "email"],
  "metadata": {
    "signal_id": 1002,
    "pattern": "BULLISH_FRACTAL",
    "confidence": 0.85
  }
}
```

**Response (201 Created):**
```json
{
  "success": true,
  "alert": {
    "id": 5002,
    "alert_type": "TRADE",
    "severity": "CRITICAL",
    "created_at": "2026-04-03T15:32:00Z"
  },
  "channels_notified": {
    "websocket": "queued",
    "discord": "pending",
    "email": "pending"
  }
}
```

**Example:**
```bash
curl -X POST http://localhost:3001/api/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "alert_type": "TRADE",
    "severity": "CRITICAL",
    "message": "BUY signal on ES fractal",
    "symbol": "ES",
    "channels": ["websocket"]
  }'
```

---

## WebSocket API

### ws://localhost:3001/ws
**Real-time subscription for candles, signals, alerts**

**Subscribe to Channel:**
```json
{
  "action": "subscribe",
  "channel": "candles",
  "symbol": "ES",
  "timeframe": "1h"
}
```

**Unsubscribe:**
```json
{
  "action": "unsubscribe",
  "channel": "candles",
  "symbol": "ES",
  "timeframe": "1h"
}
```

**Broadcast (Server → Client):**

**New Candle:**
```json
{
  "type": "candle",
  "symbol": "ES",
  "timeframe": "1h",
  "candle": {
    "timestamp": 1712504400000,
    "open": 5131.00,
    "high": 5145.50,
    "low": 5125.00,
    "close": 5140.25,
    "volume": 520000
  }
}
```

**New Signal:**
```json
{
  "type": "signal",
  "signal": {
    "id": 1003,
    "signal_type": "BUY",
    "symbol": "ES",
    "entry_price": 5140.25,
    "confidence": 0.88,
    "created_at": "2026-04-03T16:00:00Z"
  }
}
```

**New Alert:**
```json
{
  "type": "alert",
  "alert": {
    "id": 5003,
    "alert_type": "TRADE",
    "severity": "CRITICAL",
    "message": "Take profit hit on ES BUY signal",
    "created_at": "2026-04-03T16:15:00Z"
  }
}
```

**Example (JavaScript):**
```javascript
const ws = new WebSocket('ws://localhost:3001/ws');

ws.onopen = () => {
  // Subscribe to ES 1h candles
  ws.send(JSON.stringify({
    action: 'subscribe',
    channel: 'candles',
    symbol: 'ES',
    timeframe: '1h'
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

---

## AI Engine API

### GET http://localhost:8000/health
**Check AI engine status**

**Response:**
```json
{
  "status": "healthy",
  "models_loaded": true,
  "uptime": 1200
}
```

---

### POST http://localhost:8000/analyze/structure
**Detect market structure (BOS, CHoCH, FVG, sweeps)**

**Request Body:**
```json
{
  "symbol": "ES",
  "timeframe": "1h",
  "candles": [
    {
      "timestamp": 1712500800,
      "open": 5120.0,
      "high": 5135.0,
      "low": 5118.0,
      "close": 5130.0,
      "volume": 450000
    },
    {
      "timestamp": 1712504400,
      "open": 5131.0,
      "high": 5145.0,
      "low": 5125.0,
      "close": 5140.0,
      "volume": 520000
    }
  ]
}
```

**Response:**
```json
{
  "symbol": "ES",
  "timeframe": "1h",
  "bos": [
    {
      "level": 5135.0,
      "direction": "UP",
      "confidence": 0.85
    }
  ],
  "choch": [
    {
      "level": 5125.0,
      "confidence": 0.75
    }
  ],
  "fvg": [
    {
      "level": 5132.5,
      "gap_size": 2.5,
      "type": "UP"
    }
  ],
  "sweeps": [],
  "order_blocks": [
    {
      "zone": [5128.0, 5132.0],
      "type": "SUPPORT"
    }
  ]
}
```

---

### POST http://localhost:8000/analyze/fractal
**Validate 4-candle fractal pattern**

**Request Body:**
```json
{
  "candles": [
    {"timestamp": 1712500800, "open": 5120, "high": 5135, "low": 5118, "close": 5130, "volume": 450000},
    {"timestamp": 1712504400, "open": 5131, "high": 5145, "low": 5125, "close": 5140, "volume": 520000},
    {"timestamp": 1712508000, "open": 5139, "high": 5150, "low": 5135, "close": 5148, "volume": 480000},
    {"timestamp": 1712511600, "open": 5149, "high": 5160, "low": 5147, "close": 5158, "volume": 510000}
  ]
}
```

**Response:**
```json
{
  "valid": true,
  "pattern": "BULLISH_FRACTAL",
  "confidence": 0.90,
  "entry": 5148.0,
  "stop_loss": 5135.0,
  "take_profit": 5175.6,
  "risk_reward": 1.87,
  "candles": {
    "c1": {"close": 5130},
    "c2": {"close": 5140, "sweep": true},
    "c3": {"close": 5148},
    "c4": {"close": 5158, "expansion": true}
  }
}
```

---

### POST http://localhost:8000/analyze/algo
**Detect algorithmic manipulation and market state**

**Request Body:**
```json
{
  "symbol": "ES",
  "candles": [...]
}
```

**Response:**
```json
{
  "symbol": "ES",
  "market_state": "ACCUMULATION",
  "detections": [
    {
      "type": "FALSE_BREAKOUT",
      "severity": 0.85,
      "description": "Break above 5150 with volume reversal"
    }
  ],
  "risk_level": "HIGH"
}
```

---

### POST http://localhost:8000/score/trade
**Multi-confirmation trade scoring**

**Request Body:**
```json
{
  "symbol": "ES",
  "timeframe": "1h",
  "signal_type": "BUY",
  "structure_confidence": 0.85,
  "fractal_confidence": 0.90,
  "algo_risk": 0.20,
  "volume_confirmation": true
}
```

**Response:**
```json
{
  "overall_confidence": 0.88,
  "recommended_action": "EXECUTE",
  "risk_assessment": "ACCEPTABLE",
  "confirmations": 4,
  "details": {
    "structure": 0.85,
    "fractal": 0.90,
    "volume": 0.95,
    "macro": 0.75
  }
}
```

---

## Error Responses

**400 Bad Request:**
```json
{
  "success": false,
  "error": "Invalid request body",
  "code": "VALIDATION_ERROR",
  "details": {
    "field": "symbol",
    "message": "Symbol must be uppercase"
  }
}
```

**404 Not Found:**
```json
{
  "success": false,
  "error": "Resource not found",
  "code": "NOT_FOUND",
  "resource": "signal",
  "id": 9999
}
```

**500 Internal Server Error:**
```json
{
  "success": false,
  "error": "Internal server error",
  "code": "SERVER_ERROR",
  "timestamp": "2026-04-03T16:00:00Z"
}
```

---

## Rate Limiting

**Phase 1:** No rate limiting (implement in Phase 3)

---

## Authentication

**Phase 1:** No authentication (implement JWT in Phase 3)

---

## Status Codes

| Code | Meaning | Use Case |
|------|---------|----------|
| 200 | OK | Successful GET/PUT |
| 201 | Created | Successful POST (new resource) |
| 400 | Bad Request | Invalid input |
| 404 | Not Found | Resource doesn't exist |
| 500 | Server Error | Unexpected error |

---

**Last Updated:** April 3, 2026
**Status:** Phase 1 Complete
