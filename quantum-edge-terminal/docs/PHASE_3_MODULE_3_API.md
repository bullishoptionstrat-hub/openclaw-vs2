"""
PHASE 3 - MODULE 3: OPTIONS FLOW API DOCUMENTATION

FastAPI Endpoints for Institutional Options Activity Detection & Integration

Endpoints:
1. POST /ingest/options-trade         - Ingest options trade data
2. GET /options/unusual               - Query unusual options activities
3. GET /options/sentiment/{symbol}    - Get options sentiment for symbol
4. GET /options/summary               - Overall institutional flow bias
5. POST /score/setup/with-options     - Score trade with auto options integration
6. POST /options/reset                - Clear all options data

================================================================================
BASE URL: http://localhost:8200
TARGET PORT: 8200 (AI Trade Decision Engine)

EXAMPLE SETUP
================================================================================

# 1. Start FastAPI server
cd quantum-edge-terminal/services/ai_engine
python main.py

# 2. Run tests
pytest tests/test_options_api.py -v


================================================================================
ENDPOINT 1: POST /ingest/options-trade
================================================================================

PURPOSE: Ingest an options trade and automatically detect unusual activity.

REQUEST BODY (JSON):
{
  "symbol": "SPY",
  "option_type": "call",                    # "call" or "put"
  "strike": 550.0,
  "expiration": "2024-01-19",               # ISO format date
  "size": 2500,                             # Number of contracts
  "premium_per": 2.25,                      # Per contract premium
  "open_interest": 50000,
  "volume": 15000,
  "bid_ask_spread": 0.05,                   # Optional, default 0.0
  "source": "benzinga"                      # benzinga|intrinio|polygon|manual
}

RESPONSE (200 OK):
{
  "status": "ingested",
  "symbol": "SPY",
  "option_type": "call",
  "strike": 550.0,
  "size": 2500,
  "total_premium": 5625000.0,               # size × premium_per × 100
  "timestamp": 1705690800000
}

CURL EXAMPLE:
curl -X POST http://localhost:8200/ingest/options-trade \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "SPY",
    "option_type": "call",
    "strike": 550.0,
    "expiration": "2024-01-19",
    "size": 2500,
    "premium_per": 2.25,
    "open_interest": 50000,
    "volume": 15000,
    "bid_ask_spread": 0.05,
    "source": "benzinga"
  }'

UNUSUAL DETECTION TRIGGERS:
- Premium > $100,000                    → High value activity
- Volume > 1.5× Open Interest           → Unusual volume ratio
- Block size > 500 contracts            → Large institutional trade
- Bid-ask spread > $0.10                → Unusual execution


================================================================================
ENDPOINT 2: GET /options/unusual
================================================================================

PURPOSE: Query unusual options activities with filtering.

QUERY PARAMETERS (optional):
- symbol: str              Filter by symbol (e.g., "SPY", "ES", "TSLA")
- sentiment: str           Filter by sentiment ("bullish", "bearish", "neutral")
- min_score: float         Minimum unusual score (default: 4.0, range: 0-10)

RESPONSE (200 OK):
[
  {
    "symbol": "SPY",
    "option_type": "call",
    "strike": 550.0,
    "expiration": "2024-01-19",
    "size": 2500,
    "total_premium": 5625000.0,
    "unusual_score": 6.0,                   # 0-10 scale
    "sentiment": "bullish",                 # bullish|bearish|neutral
    "reason": "High premium; Volume > OI; Large block trade",
    "timestamp": 1705690800000
  },
  ...
]

CURL EXAMPLES:
# Get all unusual trades with score >= 4.0
curl http://localhost:8200/options/unusual

# Get SPY unusual trades only
curl http://localhost:8200/options/unusual?symbol=SPY

# Get bullish unusual trades
curl http://localhost:8200/options/unusual?sentiment=bullish

# Get high-conviction unusual trades (score >= 7.0)
curl "http://localhost:8200/options/unusual?min_score=7.0"

# Combine filters
curl "http://localhost:8200/options/unusual?symbol=SPY&sentiment=bullish&min_score=5.0"

RESPONSE CODES:
- 200: Success, returns list of unusual activities
- 400: Invalid query parameters


================================================================================
ENDPOINT 3: GET /options/sentiment/{symbol}
================================================================================

PURPOSE: Get options sentiment breakdown for a specific symbol.

PARAMETERS:
- symbol: str (path)       Symbol code (e.g., "SPY", "ES", "TSLA")

RESPONSE (200 OK):
{
  "symbol": "SPY",
  "bullish_count": 1,                       # Number of bullish trades
  "bearish_count": 0,                       # Number of bearish trades
  "neutral_count": 0,
  "total_trades": 1,
  "bullish_premium": 5625000.0,             # $ volume of bullish activity
  "bearish_premium": 0.0,
  "neutral_premium": 0.0,
  "total_premium": 5625000.0,
  "net_bias": "bullish",                    # bullish|bearish|neutral
  "net_bias_strength": 0.71,                # 0.0-1.0 confidence
  "timestamp": 1705690800000
}

CURL EXAMPLE:
curl http://localhost:8200/options/sentiment/SPY
curl http://localhost:8200/options/sentiment/ES
curl http://localhost:8200/options/sentiment/TSLA

INTERPRETATION:
- net_bias_strength > 0.6         → High conviction bias
- net_bias_strength 0.4-0.6       → Moderate bias
- net_bias_strength < 0.4         → Mixed/neutral positioning


================================================================================
ENDPOINT 4: GET /options/summary
================================================================================

PURPOSE: Get overall institutional options flow summary across all symbols.

RESPONSE (200 OK):
{
  "total_unusual_trades": 4,
  "total_unusual_premium": 11635000.0,
  "total_bullish_premium": 8250000.0,
  "total_bearish_premium": 3385000.0,
  "symbols": [
    {
      "symbol": "SPY",
      "count": 1,
      "bullish_premium": 5625000.0,
      "bearish_premium": 0.0,
      "bias": "bullish"
    },
    {
      "symbol": "ES",
      "count": 2,
      "bullish_premium": 2625000.0,
      "bearish_premium": 1680000.0,
      "bias": "neutral"
    },
    {
      "symbol": "TSLA",
      "count": 1,
      "bullish_premium": 0.0,
      "bearish_premium": 1705000.0,
      "bias": "bearish"
    }
  ],
  "net_institutional_bias": "bullish",      # bullish|bearish|neutral
  "net_bias_strength": 0.71,                # 0.0-1.0
  "timestamp": 1705690800000
}

CURL EXAMPLE:
curl http://localhost:8200/options/summary

INTERPRETATION:
- Across all unusual trades, institutional positioning is BULLISH
- 71% of unusual premium is in calls (bullish activity)
- SPY showing pure bullish bias (whale call sweep)
- TSLA showing pure bearish bias (institutional put positioning)
- ES showing mixed (neutral) - balanced long/short


================================================================================
ENDPOINT 5: POST /score/setup/with-options
================================================================================

PURPOSE: Score a trade setup with options flow bias AUTOMATICALLY integrated.

ADVANTAGES OVER /score/setup:
- Automatically queries options sentiment for symbol
- Calculates options bias and strength from flow data
- Integrates into confluence score seamlessly
- Returns combined technical + flow score

QUERY PARAMETERS:
- symbol: str             Symbol (ES, SPY, TSLA, etc.)
- timeframe: str          1m, 5m, 15m, 1h, 4h, 1d
- direction: str          BULLISH or BEARISH
- macro_regime: str       (optional) risk-on, risk-off, neutral

RESPONSE (200 OK):
{
  "symbol": "SPY",
  "timeframe": "1h",
  "direction": "BULLISH",
  "entry_price": 555.0,
  "score": 7.8,                             # 0-10, >= 7.0 = high probability
  "risk_level": "moderate",
  "interpretation": "Strong bullish confluence with institutional support",
  "factors": {
    "market_structure": 2.0,
    "price_action": 1.5,
    "confluence_factor": 1.8,
    "options_aligned": 1.0,                 # Added by this endpoint
    "risk_reward": 0.5
  },
  "options_aligned": true,
  "options_strength": 0.71,                 # 0.0-1.0
  "options_context": {
    "options_bias": "bullish",
    "options_strength": 0.71,
    "options_aligned": true
  },
  "timestamp": 1705690800000
}

CURL EXAMPLE:
curl -X POST "http://localhost:8200/score/setup/with-options?symbol=SPY&timeframe=1h&direction=BULLISH"

WORKFLOW:
1. API receives score request
2. Queries options sentiment for SPY
3. Detects: 71% bullish premium in recent unusual trades
4. Passes options_bias=BULLISH, options_strength=0.71 to confluence engine
5. Confluence engine:
   - Evaluates all technical signals
   - Adds options factor if aligned (scales 0-1.0 by strength)
   - Returns enhanced score with options context

OPTIONS FACTOR LOGIC:
- If direction matches options_bias:
  - Add up to +1.0 to score, scaled by options_strength
  - Example: options_strength=0.71 → add +0.71 to score
- If direction conflicts with options_bias:
  - Reduce up to -1.0, scaled by options_strength
- If options_strength < 0.4 (unclear bias):
  - Institutional flow is mixed, minimal factor contribution


================================================================================
ENDPOINT 6: POST /options/reset
================================================================================

PURPOSE: Clear all ingested options trades and unusual activity.

RESPONSE (200 OK):
{
  "status": "reset",
  "message": "All options trades and unusual activity cleared",
  "timestamp": 1705690800000
}

CURL EXAMPLE:
curl -X POST http://localhost:8200/options/reset

USE CASE:
- Start fresh for new analysis window
- Clear stale/expired options data
- Prepare for new market session


================================================================================
INTEGRATION WITH CONFLUENCE SCORING
================================================================================

TRADITIONAL FLOW (Manual Options Input):
1. Ingest signals from technical analysis
2. Manually specify options_bias via /score/setup?options_bias=BULLISH
3. Get confluence score

NEW FLOW (Automatic Options Integration):
1. POST /ingest/options-trade × N     (ingest options chain)
2. POST /score/setup/with-options     (auto-fetches options sentiment)
3. Confluence engine combines:
   - Technical signals (Market Structure, Price Action, etc.)
   - Options flow (Institutional positioning bias)
   - Options strength (Confidence in positioning)
   - Returns integrated score (0-10)

EXAMPLE SCENARIO:
┌─────────────────────────────────────────────────────┐
│ SPY Call Sweep: 2500 contracts × $2.25 = $5.625M   │
├─────────────────────────────────────────────────────┤
│ ✓ Premium > $100k                                   │
│ ✓ Volume > 1.5× OI                                  │
│ ✓ Block size > 500 contracts                        │
│ → Unusual Score: 6.0/10                             │
│ → Sentiment: BULLISH                                │
│ → Strength: 0.71 (71% bullish)                      │
├─────────────────────────────────────────────────────┤
│ Technical Signals (from Phase 2):                    │
│ • Market Structure: Bullish BOS + CHoCH             │
│ • Price Action: Higher Lows + Fractals             │
│ • Confluence: 3 time frames aligned                │
├─────────────────────────────────────────────────────┤
│ COMBINED SCORE:                                      │
│ Base: 6.5 (technical)                               │
│ + Options: +1.0 × 0.71 = +0.71 (aligned + strong) │
│ = FINAL: 7.21/10 ✅ HIGH PROBABILITY               │
└─────────────────────────────────────────────────────┘


================================================================================
DATA MODEL REFERENCE
================================================================================

OptionsTrade:
- symbol: str
- option_type: OptionType (CALL, PUT)
- strike: float
- expiration: str (ISO date)
- size: int (contracts)
- premium_per: float
- total_premium: float (size × premium_per × 100)
- bid_ask_spread: float
- open_interest: int
- volume: int
- source: str (benzinga, intrinio, polygon, manual)
- timestamp: int (milliseconds)

UnusualActivity:
- trade: OptionsTrade
- unusual_score: float (0-10)
- estimated_sentiment: Sentiment (BULLISH, BEARISH, NEUTRAL)
- reason: str
- timestamp: int

Thresholds:
- MIN_PREMIUM: $100,000
- MIN_VOLUME_OI_RATIO: 1.5
- MIN_LARGE_TRADE_SIZE: 500 contracts
- MAX_SPREAD: $0.10


================================================================================
SAMPLE END-TO-END WORKFLOW
================================================================================

# Terminal 1: Start server
cd quantum-edge-terminal/services/ai_engine
python main.py

# Terminal 2: Make requests
# 1. Ingest options trades
curl -X POST http://localhost:8200/ingest/options-trade \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "SPY",
    "option_type": "call",
    "strike": 550.0,
    "expiration": "2024-01-19",
    "size": 2500,
    "premium_per": 2.25,
    "open_interest": 50000,
    "volume": 15000,
    "bid_ask_spread": 0.05,
    "source": "benzinga"
  }'

# 2. Query unusual activities
curl http://localhost:8200/options/unusual?min_score=5.0

# 3. Get sentiment for SPY
curl http://localhost:8200/options/sentiment/SPY

# 4. Score setup with options integration
curl -X POST "http://localhost:8200/score/setup/with-options?symbol=SPY&timeframe=1h&direction=BULLISH"

# 5. Get overall summary
curl http://localhost:8200/options/summary

# 6. Reset for next session
curl -X POST http://localhost:8200/options/reset


================================================================================
ERROR HANDLING
================================================================================

400 Bad Request:
- Invalid option type (must be "call" or "put")
- Missing required fields
- Invalid sentiment filter
- Invalid symbol format

Example error response:
{
  "detail": "Error ingesting options trade: invalid value for option_type"
}

Mitigation:
- Validate input before POST
- Follow query parameter types exactly
- Use supported values (call/put, bullish/bearish/neutral)


================================================================================
NEXT STEPS
================================================================================

1. ✅ Phase 3 Module 3 Part 1: Data Ingestion (COMPLETE)
2. ✅ Phase 3 Module 3 Part 2: Unusual Detection (COMPLETE)
3. ✅ Phase 3 Module 3 Part 3: Data Source Integration (COMPLETE)
4. ✅ Phase 3 Module 3 Part 4: FastAPI Endpoints (COMPLETE)
5. ✅ Phase 3 Module 3 Part 5: Confluence Integration (COMPLETE)

6. ⏳ Phase 3 Module 4: Macro Filter
   - Add macro regime detection
   - Risk regime classification
   - Fed/economic event monitoring

7. ⏳ Phase 3 Module 5-8: Trade Generation & Risk Management
   - Entry signal generation
   - Stop loss / Take profit calculation
   - Position sizing
   - Risk/reward validation


================================================================================
TESTING YOUR IMPLEMENTATION
================================================================================

Run comprehensive test:
cd quantum-edge-terminal/services/ai_engine
python tests/test_options_api.py

Expected output:
✓ Ingestion: 6 trades
✓ Unusual Detection: 4 flagged
✓ Sentiment Analysis: 3 symbols analyzed
✓ Filter Tests: PASSED
✓ Reset: PASSED
Net Institutional Bias: BULLISH (0.71 strength)
✅ ALL TESTS PASSED
"""
