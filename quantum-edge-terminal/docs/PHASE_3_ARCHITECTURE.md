# PHASE 3 ARCHITECTURE: MODULES 1-11 BLUEPRINT

**Complete AI Trade Decision Engine**

---

## Module Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                   PHASE 3: AI TRADE DECISION ENGINE                │
│                          (Port 8200)                               │
└─────────────────────────────────────────────────────────────────────┘

↓ Input from Phase 2 (8100)

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 1: SIGNAL INGESTION ✅                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Normalize all Phase 2 outputs to unified NormalizedSignal format  │
│                                                                     │
│  Input:  Heterogeneous Phase 2 signals (varying schemas)          │
│  Output: NormalizedSignal objects (unified format)                 │
│                                                                     │
│  8 signal types:                                                    │
│  - SWING_HIGH, SWING_LOW: Swing detection                         │
│  - BOS, CHOCH: Structure shifts                                   │
│  - LIQUIDITY_SWEEP: Liquidity levels                              │
│  - FVG, ORDER_BLOCK: Reaction zones                               │
│  - FRACTAL: 4-candle patterns with R:R                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ Normalized signals indexed

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 2: CONFLUENCE ENGINE ✅                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Score trade setups using 7-factor confluence analysis            │
│                                                                     │
│  Factors:                                                           │
│  1. Liquidity Sweep          (+1.0)  - Sweep detected             │
│  2. Structure Shift (BOS/CHoCH) (+1.5)  - Confirmed structural    │
│  3. FVG/Order Block Reaction (+1.0)  - Zone present               │
│  4. Fractal Confirmation    (+2.0)  - 4-candle pattern valid      │
│  5. Directional Bias        (+0.5)  - Signals aligned >60%        │
│  6. Options Flow            (+1.0)  - Options align direction     │
│  7. Macro Alignment         (+0.5)  - Risk regime aligned         │
│                                                                     │
│  Output: TradeScore (0-10 with interpretation)                    │
│  0-2:   SKIP | 3-4:  WEAK | 5-6:  VALID | 7+: EXCELLENT         │
│                                                                     │
│  Also outputs:                                                      │
│  - Entry price                                                      │
│  - Stop loss                                                        │
│  - Take profit                                                      │
│  - Risk/Reward ratio                                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ Scored setup (0-10)

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 3: OPTIONS FLOW (Coming - M3)                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Detect bullish/bearish options flow                               │
│                                                                     │
│  Inputs:                                                            │
│  - Options volume data (put/call ratio)                            │
│  - Options implied volatility skew                                 │
│  - Major options order flow                                        │
│                                                                     │
│  Logic:                                                             │
│  IF put_vol > call_vol by X% → BEARISH flow → bearish bias        │
│  IF call_vol > put_vol by X% → BULLISH flow → bullish bias        │
│                                                                     │
│  Output:                                                            │
│  - options_bias: Direction enum (BULLISH, BEARISH, NEUTRAL)       │
│  - options_strength: 0-1 confidence in bias                        │
│  - options_volume_ratio: Float (put/call ratio)                    │
│                                                                     │
│  Integration with Module 2:                                        │
│  - Pass options_bias to confluence scoring                         │
│  - +1.0 points if aligned with trade direction                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ With options confirmation

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 4: MACRO FILTER (Coming - M4)                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Classify overall market regime (risk-on / risk-off / neutral)     │
│                                                                     │
│  Inputs:                                                            │
│  - VIX level (volatility index)                                    │
│  - Bond yields (TLT, IEF ratio)                                    │
│  - Risk sentiment indicators (DXY, commodity prices)               │
│  - New highs / New lows ratio                                      │
│  - Fed sentiment / policy regime                                   │
│                                                                     │
│  Logic:                                                             │
│  IF VIX < 15 AND yields rising AND new_highs > new_lows            │
│     → RISK-ON (favor long trades)                                  │
│  ELSE IF VIX > 25 AND yields falling AND new_lows > new_highs     │
│     → RISK-OFF (favor short trades)                                │
│  ELSE → NEUTRAL (no macro bias)                                    │
│                                                                     │
│  Output:                                                            │
│  - regime: str ("risk-on", "risk-off", "neutral")                 │
│  - regime_strength: 0-1 (confidence)                               │
│  - vix_level: float (current VIX)                                  │
│  - yield_environment: str                                          │
│                                                                     │
│  Integration with Module 2:                                        │
│  - Pass macro_regime to confluence scoring                         │
│  - Filter trades against macro bias                                │
│  - Reject shorts in risk-on, longs in risk-off                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ Macro-validated setup

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 5: TRADE GENERATION (Coming - M5)                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Convert scored signals into executable trade structures           │
│                                                                     │
│  Inputs:                                                            │
│  - TradeScore from Module 2                                        │
│  - Entry/stop/TP already embedded in score                         │
│  - Options bias from Module 3                                      │
│  - Macro regime from Module 4                                      │
│                                                                     │
│  Generate Trade object:                                            │
│  {                                                                  │
│    id: UUID                                                         │
│    symbol: "ES"                                                     │
│    timeframe: "1h"                                                  │
│    direction: BULLISH                                              │
│    entry: 5151.75                                                  │
│    stop_loss: 5148.00                                              │
│    take_profit: 5160.00                                            │
│    risk_amount: 3.75       (entry - stop)                          │
│    reward_amount: 8.25     (TP - entry)                            │
│    risk_reward: 2.6        (reward / risk)                         │
│    position_size: None     (Module 6 calculates)                   │
│    score: 7.5                                                       │
│    reasoning: "5 confluences: sweep, structure, FVG, fractal, bias"│
│    created_at: timestamp                                           │
│    status: "PENDING_EXECUTION"                                     │
│  }                                                                  │
│                                                                     │
│  Output: List[Trade]                                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ Trades created with entry/stop/targets

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 6: RISK MANAGEMENT (Coming - M6)                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Apply risk management filters and position sizing                │
│                                                                     │
│  Filters:                                                           │
│  1. Reject if R:R < 2.0                                            │
│  2. Reject if score < 5.0 (not valid)                              │
│  3. Reject if against macro bias                                   │
│  4. Max positions per symbol: 2                                    │
│  5. Max risk per trade: 1% of account                              │
│  6. Max total open risk: 5% of account                             │
│  7. Time-based filters (trading hours, no news events)             │
│                                                                     │
│  Position Sizing:                                                   │
│  account_size = 100,000                                            │
│  max_risk_per_trade = 1,000 (1%)                                  │
│  position_size = max_risk_per_trade / risk_amount                  │
│  position_size = 1000 / 3.75 = 266.67 contracts                   │
│                                                                     │
│  Output: FilteredTrade (with position_size or rejected reason)     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ Risk-validated, sized trades

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 7: CONFIDENCE SCORING (Coming - M7)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Combine all factors into final confidence score (0-100)           │
│                                                                     │
│  Formula:                                                           │
│  base_score = (Module 2 score / 10) * 40  → 0-40 points          │
│  options_bonus = options_strength * 20    → 0-20 points          │
│  macro_bonus = macro_strength * 15       → 0-15 points          │
│  rr_bonus = MIN(risk_reward / 3, 1) * 15 → 0-15 points          │
│  risk_level_penalty = {LOW: 0, HIGH: -5}                          │
│                                                                     │
│  final_score = base + options + macro + rr + penalty               │
│  capped at 100                                                      │
│                                                                     │
│  Output:                                                            │
│  - confidence: 0-100                                                │
│  - confidence_category: "EXCELLENT" | "STRONG" | "MODERATE" | "WEAK"│
│  - score_breakdown: {base, options, macro, rr, penalty}           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ Final confidence score

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 8: OUTPUT FORMATTING (Coming - M8)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Create unified trade output structure for all downstream systems  │
│                                                                     │
│  Output Format:                                                     │
│  {                                                                  │
│    trade: {                                                         │
│      id, symbol, timeframe, direction, entry, stop, tp, size      │
│    },                                                               │
│    scoring: {                                                       │
│      confluence_score: 7.5,                                        │
│      confidence: 85,                                               │
│      risk_level: "LOW",                                            │
│      factors: {...}                                                │
│    },                                                               │
│    execution: {                                                     │
│      status: "READY",                                              │
│      created_at: timestamp,                                        │
│      expires_at: timestamp + 60 min                                │
│    },                                                               │
│    reasoning: {                                                     │
│      text: "High-confluence setup: liquidity sweep + BOS + FVG + fractal",│
│      confluences: [...]                                            │
│    }                                                                │
│  }                                                                  │
│                                                                     │
│  Supports:                                                          │
│  - JSON serialization (API responses)                              │
│  - WebSocket broadcasts                                            │
│  - Database persistence                                            │
│  - Human-readable logging                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ Formatted, ready to broadcast

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 9: API EXPOSURE (Coming - M9)                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Expose all functions via REST API (FastAPI)                       │
│                                                                     │
│  Endpoints:                                                         │
│  POST   /trades/generate              → Create trade from signals  │
│  GET    /trades                       → List all trades            │
│  GET    /trades/{id}                  → Fetch specific trade       │
│  POST   /trades/{id}/execute          → Mark as executed          │
│  POST   /trades/{id}/close            → Close with P&L            │
│  GET    /trades/high-confidence       → score >= 80               │
│  POST   /analyze                      → Score arbitrary setup     │
│  GET    /status/positions             → Current open positions    │
│                                                                     │
│  Swagger docs: /docs (auto-generated)                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ Via API endpoints

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 10: UI INTEGRATION (Coming - M10)                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Broadcast trades to frontend via WebSocket                        │
│                                                                     │
│  Channels:                                                          │
│  - "trades:new" → New high-confidence trades                       │
│  - "trades:updated" → Trade status changes                         │
│  - "trades:executed" → Trade filled                                │
│  - "trades:closed" → Trade closed with P&L                         │
│  - "dashboard:summary" → Portfolio update                          │
│                                                                     │
│  Frontend display:                                                  │
│  - New trades alert (badge, sound notification)                    │
│  - Trade details panel                                             │
│  - Real-time P&L tracking                                          │
│  - Historical trade log                                            │
│  - Win rate / statistics                                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ Displayed on dashboard

┌─────────────────────────────────────────────────────────────────────┐
│ MODULE 11: LEARNING SYSTEM (Coming - M11)                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Track trade outcomes and optimize confluence weights              │
│                                                                     │
│  Data Collection:                                                   │
│  - Original trade setup info                                       │
│  - Entry time / price                                              │
│  - Exit time / price / P&L                                         │
│  - Win / Loss classification                                       │
│  - Win ratio by factor combination                                 │
│                                                                     │
│  Analysis:                                                          │
│  - Which factors correlate with wins?                              │
│  - Which factor combinations are most profitable?                  │
│  - Are current weights optimal?                                    │
│  - Seasonal/timeframe variations?                                  │
│                                                                     │
│  Optimization:                                                      │
│  - Adjust confluence factor weights based on win rate              │
│  - Use backtesting to validate                                     │
│  - Update Module 2 with new weights                                │
│  - Track performance across markets/timeframes                     │
│                                                                     │
│  Output:                                                            │
│  - win_rate: X% (all trades)                                       │
│  - win_rate_by_factor: {factor: win_rate}                         │
│  - best_factor_combination: [factor1, factor2, ...]               │
│  - suggested_weights: {factor: new_weight}                         │
│  - profitability_metrics: {roi, sharpe, drawdown}                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

↓ Loop back to Module 2

Example: If learning system shows fractals have 85% win rate
but liquidity sweeps only 45%, adjust weights:
  FRACTAL: 2.0 → continue as-is (already working)
  LIQUIDITY_SWEEP: 1.0 → 0.5 (downweight)
```

---

## Data Flow Example

### Scenario: ES 1-hour, BULLISH setup

```
PHASE 2 OUTPUT (Raw Signals)
from structure_engine (port 8100)

swing_high @ 5155.00
liquidity_sweep @ 5162.50
bos @ 5158.00
fvg @ 5150.50-5152.25
fractal (entry: 5151.75, stop: 5148.00, TP: 5160.00)
order_block @ 5152.00-5153.00

        ↓ HTTP to Phase 3

M1: SIGNAL INGESTION
────────────────────
Heterogeneous inputs → NormalizedSignal objects

Output:
[
  NormalizedSignal(type=SWING_HIGH, price=5155, conf=0.95),
  NormalizedSignal(type=LIQUIDITY_SWEEP, price=5162.50, conf=0.88),
  NormalizedSignal(type=BOS, price=5158, conf=0.92),
  NormalizedSignal(type=FVG, price=5150.50, conf=0.85),
  NormalizedSignal(type=FRACTAL, price=5151.75, conf=0.91),
  NormalizedSignal(type=ORDER_BLOCK, price=5152.50, conf=0.80),
]

        ↓ All signals indexed

M2: CONFLUENCE ENGINE
────────────────────
Score the setup

Factors:
✓ Liquidity Sweep      +1.0
✓ BOS                  +1.5
✓ FVG                  +1.0
✓ Fractal              +2.0
✓ Directional Bias     +0.5
✓ Options (bullish)    +1.0
✓ Macro (risk-on)      +0.5
────────────────
TOTAL:             7.5/10

Output:
TradeScore(
  symbol="ES",
  score=7.5,
  entry=5151.75,
  stop=5148.00,
  tp=5160.00,
  rr=2.6,
  risk_level="LOW",
  interpretation="High-probability setup"
)

        ↓ Score >= 7.0 (high confidence)

M3-M4: OPTIONS + MACRO (Coming)
────────────────────────────────
Confirm options flow is bullish ✓
Confirm macro regime is risk-on ✓

        ↓ All filters pass

M5-M7: TRADE GENERATION + SIZING + CONFIDENCE
──────────────────────────────────────────────
Create Trade object:
  Execute ES 1-hour LONG
  Entry: 5151.75 (266 contracts at 1% risk)
  Stop: 5148.00
  Target: 5160.00
  Final Confidence: 85%

        ↓ Ready to execute

M8: OUTPUT FORMATTING
─────────────────────
{
  "trade": {
    "id": "trade_xxx",
    "symbol": "ES",
    "direction": "LONG",
    "entry": 5151.75,
    "size": 266
  },
  "scoring": {
    "confluence": 7.5,
    "confidence": 85,
    "risk_level": "LOW"
  },
  "status": "READY_TO_EXECUTE"
}

        ↓ Via API/WebSocket

M9: API EXPOSURE
────────────────
POST /trades/generate → Creates trade in database

        ↓ Broadcast to frontend

M10: UI INTEGRATION
───────────────────
Frontend receives:
- New trade alert
- Trade details in dashboard
- Real-time entry notification
- P&L tracking

        ↓ Trade executes, track outcome

M11: LEARNING SYSTEM
────────────────────
Trade closes @ 5158 (profit 6.25 per contract = $1,662)

Record:
- Setup: 5 confluences (sweep+BOS+FVG+fractal+bias)
- Win: YES
- P&L: +$1,662
- Duration: 2.5 hours

Analysis:
- This factor combo: 5 confluences → 85% win rate ✓
- Profitable combo verified
- Suggest keeping these weights
```

---

## Integration Points

### Phase 2 → Phase 3
```
POST http://localhost:8100/detect/swings
    + POST http://localhost:8200/ingest/swing
    + POST http://localhost:8200/score/setup
    = Trade score ready
```

### Phase 3 → Backend
```
POST http://localhost:8200/trades/generate
    + PostgreSQL insert (trades table)
    + Redis cache (active trades)
    = Backend updated
```

### Backend → Frontend
```
WebSocket broadcast channel: "trades:new"
    @ 5151.75: BUY ES 266 contracts (confidence 85%)
    = Dashboard notification + alert
```

### Trade Lifecycle
```
PENDING_EXECUTION
    ↓ (manual trigger or auto)
EXECUTING
    ↓ (confirmed filled)
ACTIVE
    ↓ (hit stop or TP)
CLOSED
    ↓ (record P&L, learn)
M11 processes outcome
    ↓ (update weights)
Next trades improve
```

---

## Performance Targets

| Operation | Target | Module |
|-----------|--------|--------|
| Ingest signal | <5ms | M1 |
| Score setup | <50ms | M2 |
| Detect options bias | <100ms | M3 |
| Classify macro regime | <100ms | M4 |
| Generate trade | <20ms | M5 |
| Apply risk filters | <10ms | M6 |
| Calculate confidence | <5ms | M7 |
| Format output | <5ms | M8 |
| API response | <100ms | M9 |
| WebSocket broadcast | <50ms | M10 |
| Learn pattern | <1s | M11 |

---

## Summary

11-module architecture transforms:
```
Phase 2 signals (8 types, heterogeneous)
    ↓ M1: Ingest
    ↓ M2: Score
    ↓ M3-M4: Confirm (options + macro)
    ↓ M5-M7: Generate + Size + Confidence
    ↓ M8: Format
    ↓ M9: Expose (API)
    ↓ M10: Display (WebSocket)
    ↓ M11: Learn (optimize)
    
→ EXECUTABLE HIGH-PROBABILITY TRADES
```

**Modules Built:** 1-2 ✅
**Modules Coming:** 3-11 🔥
