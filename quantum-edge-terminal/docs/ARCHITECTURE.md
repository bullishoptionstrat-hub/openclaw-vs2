# QUANTUM EDGE TERMINAL - System Architecture

## System Design Philosophy

**Modular. Scalable. Real-time. Institutional-grade.**

The system is built on the principle that trade validation requires **multi-confirmation consensus**. No single indicator or module is trusted alone; all trade signals must pass through a confluence filter before execution.

---

## Core Data Flow

```
Market Data Sources
    ↓
Data Normalization Pipeline
    ↓
Real-time Signal Stream (Redis)
    ↓
8 Parallel Detection Modules
    ↓
Confidence Scoring Engine
    ↓
Multi-Confirmation Validation
    ↓
AI Trade Scoring (Python)
    ↓
Signal Output (Discord, Email, WebSocket)
    ↓
Trader Action
```

---

## Module Specifications

### MODULE 1: Market Data Engine

**Responsibility:** Ingest, normalize, and distribute live market feeds.

**Data Sources:**
- Binance (crypto)
- Alpaca (stocks)
- CBOE (options data)
- FRED API (macro data)

**Pipeline:**
1. Connect to exchange WebSocket
2. Normalize OHLCV candles to 1m, 5m, 15m, 1h timeframes
3. Calculate volume profile, bid/ask imbalance
4. Stream to Redis with 50ms latency guarantee
5. Store to PostgreSQL for historical backtesting

**Key Data Points:**
```javascript
{
  timestamp: 1712500800000,
  symbol: "ES",
  open: 5120.50,
  high: 5135.75,
  low: 5118.25,
  close: 5130.00,
  volume: 450000,
  vwap: 5127.30,
  bidAsk: {
    bid: 5129.75,
    ask: 5130.25,
    bidVol: 250000,
    askVol: 280000
  }
}
```

**Confidence Score:** 100% (if data is valid)

---

### MODULE 2: Market Structure Engine

**Responsibility:** Detect institutional-grade market structure patterns.

**Detections:**
1. **Swing High/Low**
   - Identify local peaks and troughs
   - Threshold: 2+ candles of lower highs/higher lows
   
2. **Break of Structure (BOS)**
   - Previous swing high/low breached
   - Requires volume confirmation
   - Confidence: 85% if volume > 1.2x MA(20)

3. **Change of Character (CHoCH)**
   - Directional shift (uptrend → downtrend)
   - Occurs at market structure
   - Confidence: 75%

4. **Liquidity Sweep**
   - Price touches swing + reverses
   - False breakout pattern
   - Confidence: 80%

5. **Fair Value Gap (FVG)**
   - Unmitigated price gap in market
   - Reversion target
   - Confidence: 70%

6. **Order Block**
   - Institutional accumulation/distribution zone
   - Previous candle body where reversal occurred
   - Confidence: 65%

**Output:**
```javascript
{
  type: "BOS | CHoCH | FVG | SWEEP | ORDER_BLOCK",
  level: 5135.50,
  direction: "UP | DOWN",
  timeframe: "1h | 4h | 1D",
  confidence: 0.85,
  timestamp: 1712500800000,
  volume: 450000
}
```

---

### MODULE 3: Fractal Engine (TTrades Logic)

**Responsibility:** Validate 4-candle fractal patterns.

**Candle Rules:**

```
Candle 1: Trend establishment
  - If uptrend: close > open
  - If downtrend: close < open
  
Candle 2: Reversal swing
  - Opposite polarity of Candle 1
  - MUST sweep liquidity (previous candle high/low)
  
Candle 3: Confirmation
  - Returns to Candle 1 direction
  - Close must exceed Candle 1 close
  
Candle 4: Expansion
  - Continuation of Candle 3
  - New higher high/lower low
  - Volume confirmation required
```

**Validation Logic:**
```
Valid Fractal = (C1 valid) AND (C2 sweep) AND (C3 confirm) AND (C4 expand) AND (structure POI)
```

**Confidence Scoring:**
- All 4 candles + structure POI: 90%
- 3 candles + structure POI: 75%
- 3 candles, no POI: 60%

**Output:**
```javascript
{
  pattern: "BULLISH_FRACTAL | BEARISH_FRACTAL",
  confidence: 0.90,
  c1: { open, close, high, low },
  c2: { open, close, high, low, sweepLevel },
  c3: { open, close, high, low },
  c4: { open, close, high, low },
  entryLevel: 5130.00,
  stopLoss: 5120.00,
  profitTarget: 5150.00,
  riskReward: 2.0,
  timeframe: "1h"
}
```

---

### MODULE 4: Algo Detection Engine

**Responsibility:** Identify manipulation, false breakouts, and traps.

**Detection Types:**

1. **False Breakout**
   - Price breaks resistance/support
   - Reverses within 2-5 candles
   - Confidence: 85%

2. **Stop Hunt**
   - Price tags swing high/low
   - Reverses sharply
   - Volume spike on reversal
   - Confidence: 80%

3. **OTE Retracement Trap** (0.618–0.705)
   - Retraces to Golden Ratio zone
   - Bounces from OTE level
   - Confidence: 75%

4. **Deep Liquidity Sweep** (0.786)
   - Price sweeps to 0.786 retracement
   - Kills stops below market structure
   - Confidence: 80%

5. **Judas Swing Behavior**
   - Initial move in one direction
   - Sharp reversal to opposite direction
   - Confidence: 70%

**Market State Classification:**
```
ACCUMULATION = price consolidating, volume declining
MANIPULATION = whipsaws, false breaks, high volatility
DISTRIBUTION = volume increasing, price stalling at resistance
TRENDING = directional, consistent volume, smooth extension
```

**Output:**
```javascript
{
  detectionType: "FALSE_BREAKOUT | STOP_HUNT | OTE_TRAP | DEEP_SWEEP | JUDAS",
  marketState: "ACCUMULATION | MANIPULATION | DISTRIBUTION | TRENDING",
  severity: 0.85,  // 0-1, higher = more likely to move
  expectedNextMove: "UP | DOWN | CONSOLIDATION",
  trapLiquidityLevel: 5135.50,
  timestamp: 1712500800000
}
```

---

### MODULE 5: Options Flow Engine

**Responsibility:** Track institutional options positioning and delta imbalance.

**Data Points:**
- Large block trades (>100 contracts)
- Implied volatility skew
- Put/call ratio
- Delta-weighted open interest

**Signals:**
1. **Delta Imbalance**
   - Unusual call/put ratio shift
   - Indicates directional bias
   
2. **Gamma Zone**
   - Price level where gamma peak occurs
   - Market makers delta-hedge aggressively here
   - Often acts as support/resistance

3. **Institutional Positioning**
   - Flow analysis from large blocks
   - Unusual volume in specific strikes
   - Expirations with concentration

**Output:**
```javascript
{
  bias: "BULLISH_INSTITUTIONAL | BEARISH_INSTITUTIONAL | NEUTRAL",
  confidence: 0.80,
  deltaImbalance: 1.35,  // calls/puts ratio
  gammaZone: [5130, 5140],
  putCall: 0.75,
  unusualVolume: true,
  volumeLevel: "VERY_HIGH",
  sessionExpiration: "2024-04-19"
}
```

---

### MODULE 6: Macro Engine

**Responsibility:** Classify market regime based on macro conditions.

**Macro Indicators:**
- PCE Inflation
- GDP Growth
- Unemployment Rate
- Fed Funds Rate
- QE/QT Status
- Treasury Yields

**Regime Classification:**
```
RISK_ON = Low inflation, growing GDP, positive sentiment, QE
RISK_OFF = High inflation, recession signals, uncertainty, QT
LIQUIDITY_EXPANSION = QE active, rates falling, volatility declining
LIQUIDITY_CONTRACTION = QT active, rates rising, volatility rising
STAGNATION = No growth, high inflation, policy uncertainty
```

**Logic:**
```
if PCE > 3% AND unemployment < 4% → Inflation pressure (RISK_OFF bias)
if GDP growth > 2.5% AND Fed rate > 5% → Growth + Tightening (mixed)
if QE active → Liquidity expansion (RISK_ON bias)
if QT active AND yields rising → Contraction (RISK_OFF bias)
```

**Output:**
```javascript
{
  regime: "RISK_ON | RISK_OFF | LIQUIDITY_EXPANSION | CONTRACTION | STAGNATION",
  confidence: 0.75,
  inflation: 2.8,
  gdpGrowth: 2.5,
  unemploymentRate: 4.1,
  fedRate: 5.25,
  qeStatus: "ACTIVE | INACTIVE",
  lastUpdate: 1712500800000,
  nextMacroEvent: "FOMC 2024-05-01",
  eventsForecast: {
    bullish: 2,
    bearish: 1,
    neutral: 2
  }
}
```

---

### MODULE 7: AI Trade Engine

**Responsibility:** Multi-confirmation trade validation and scoring.

**Validation Requirements:**
```
Trade Valid IF (Confirmations >= 3) AND (Confidence >= 0.70)

Confirmation Sources:
  1. Market Structure (BOS/CHoCH/FVG) ✓
  2. Fractal Pattern (4-candle) ✓
  3. Algorithm Detection (not a trap) ✓
  4. Options Flow (directional bias match) ✓
  5. Macro Regime (supports direction) ✓
  6. Volume Profile (supports move) ✓
  7. Technical (MACD, RSI, moving avg) ✓
```

**Trade Scoring Algorithm:**
```
Score = (
  StructureWeight(0.25) * structureScore +
  FractalWeight(0.20) * fractalScore +
  AlgoWeight(0.15) * algoScore +
  OptionsWeight(0.15) * optionsScore +
  MacroWeight(0.15) * macroScore +
  VolumeWeight(0.10) * volumeScore
)

if Score >= 0.70 → Generate Trade Signal
```

**Position Sizing:**
```
PositionSize = (
  AccountRisk(1%) / (Exit - EntryPrice) in pips
)

MaxPosition = min(
  CalculatedSize,
  AccountEquity * 0.05,  // Max 5% per trade
  20% of average daily volume
)

StopLoss = StructureLow - Buffer(20 pips for ES)
TakeProfit = FractalTarget or NextStructure
RiskReward = (TP - Entry) / (Entry - SL)

Valid if RiskReward >= 1.5
```

**Output:**
```javascript
{
  signal: "BUY | SELL | NEUTRAL",
  confidence: 0.82,
  confirmations: 4,
  entry: 5130.00,
  stopLoss: 5120.00,
  takeProfit1: 5145.00,
  takeProfit2: 5160.00,
  positionSize: 2,  // contracts or shares
  riskReward: 2.15,
  expirity: "2024-04-10T15:30:00Z",
  reasoning: [
    "BOS at 4h structure",
    "Bullish fractal complete",
    "Not a false breakout",
    "Institutional call bias",
    "Risk-on macro regime"
  ],
  scoringDetails: {
    structure: 0.95,
    fractal: 0.90,
    algo: 0.85,
    options: 0.75,
    macro: 0.80,
    volume: 0.88
  }
}
```

---

### MODULE 8: Alert System

**Responsibility:** Route alerts to traders via multiple channels.

**Alert Types:**
- Market Structure Changes (BOS, CHoCH)
- Trade Signals (entry, exit, alerts)
- Risk Alerts (liquidation risk, drawdown)
- Macro Events (NFP, FOMC, CPI)
- Institutional Flows (unusual options activity)

**Routing Pipeline:**
```
Signal Generated
    ↓
    ├→ Check Notification Preferences
    ├→ Format for each channel
    ├→ Rate limit (no spam)
    └→ Deliver
        ├→ Discord (real-time)
        ├→ Email (summaries)
        ├→ WebSocket (in-app)
        ├→ SMS (critical only)
        └→ Telegram (optional)
```

**Alert Severity Levels:**
```
CRITICAL (Immediate):
  - Trade generated with 85%+ confidence
  - Liquidation risk detected
  - Circuit breaker triggered

HIGH (Soon):
  - Market structure shift
  - Macro event in <1 hour
  - unusual volume spike

MEDIUM (Reference):
  - Structure patterns forming
  - Macro event in >1 hour
  - Analysis updates

LOW (archive):
  - Pattern confirmations
  - Session summaries
  - Backtesting results
```

**Output:**
```javascript
{
  alertId: "ALT_20240403_001",
  type: "TRADE_SIGNAL | STRUCTURE | MACRO | VOLUME",
  severity: "CRITICAL | HIGH | MEDIUM | LOW",
  message: "BUY ES @ 5130 | SL 5120 | TP 5145 | R:R 2.15",
  channels: ["discord", "email", "websocket"],
  timestamp: 1712500800000,
  expiresAt: 1712504400000,
  actionRequired: true
}
```

---

## Data Storage Architecture

### PostgreSQL (Historical Data)
```sql
-- Candles table
CREATE TABLE candles (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20),
  timeframe VARCHAR(10),  -- 1m, 5m, 15m, 1h, 4h, 1D
  timestamp BIGINT,
  open DECIMAL(18,8),
  high DECIMAL(18,8),
  low DECIMAL(18,8),
  close DECIMAL(18,8),
  volume BIGINT,
  vwap DECIMAL(18,8),
  bidAsk JSONB,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(symbol, timeframe, timestamp)
);

-- Signals table
CREATE TABLE signals (
  id SERIAL PRIMARY KEY,
  signal_type VARCHAR(50),  -- BUY, SELL, etc
  symbol VARCHAR(20),
  entry_price DECIMAL(18,8),
  stop_loss DECIMAL(18,8),
  take_profit DECIMAL(18,8),
  confidence DECIMAL(5,4),
  confirmations INT,
  status VARCHAR(20),  -- PENDING, ACTIVE, CLOSED
  pnl DECIMAL(18,8),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  closed_at TIMESTAMP
);

-- Alerts table
CREATE TABLE alerts (
  id SERIAL PRIMARY KEY,
  alert_type VARCHAR(50),
  severity VARCHAR(20),
  message TEXT,
  channels JSONB,
  user_id INT,
  sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  read_at TIMESTAMP
);
```

### Redis (Real-time)
```
Keys:
  qt:latest_candle:{symbol}:{timeframe} → Current candle JSON
  qt:signals:{symbol} → Active signals for symbol
  qt:alerts:queue → Alert message queue
  qt:user:{userId}:settings → User preferences
  qt:circuit_breaker → Trading halt flags
  qt:rate_limiter:{userId} → Rate limit counters
```

---

## API Specification (Phase 1)

### REST Endpoints
```
GET    /api/candles/:symbol/:timeframe  → Historical OHLCV
GET    /api/signals                     → Active signals
GET    /api/alerts                      → Recent alerts
POST   /api/trade/validate              → Test trade idea
GET    /api/health                      → System status
```

### WebSocket Events
```
subscribe:candles:{symbol}:{timeframe}  → Real-time candles
subscribe:signals                       → Trade signals
subscribe:alerts                        → Alerts
subscribe:structure:{symbol}            → Market structure updates
```

---

## Security & Safety

**Production Checklist:**
- [ ] All inputs validated (SQL injection, XSS prevention)
- [ ] JWT authentication on all API endpoints
- [ ] Rate limiting (100 req/min per user)
- [ ] Circuit breakers for algo detection
- [ ] Audit logging for all trades
- [ ] PII encryption (user data)
- [ ] HTTPS/WSS only
- [ ] Regular security audits
- [ ] Paper trading isolation from live trading

---

## Performance Targets

- **Candle latency:** <50ms from exchange to Redis
- **Signal generation:** <200ms from data ingestion
- **API response time:** <100ms p95
- **WebSocket update frequency:** 50ms for candles, 100ms for signals
- **Historical backtesting:** 1 year of data in <5 seconds

---

## Deployment Topology (Production)

```
AWS ECS Cluster
├── Frontend (Load Balanced)
│   ├── Next.js Container x3
│   └── CloudFront CDN
├── Backend (Auto-scaled)
│   ├── Express Container x5
│   └── ALB Load Balancer
├── AI Engine (GPU instances)
│   ├── Python Workers x2
│   └── Model serving via FastAPI
├── Data Layer
│   ├── RDS PostgreSQL (multi-AZ)
│   ├── ElastiCache Redis (cluster)
│   └── S3 (historical data backups)
└── Message Queue
    └── SQS (alert queue)
```

---

End of Architecture Document.
