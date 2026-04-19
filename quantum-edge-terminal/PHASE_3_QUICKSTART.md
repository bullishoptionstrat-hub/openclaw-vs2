# PHASE 3 QUICKSTART

**AI Trade Decision Engine - Get Running in 5 Minutes**

---

## Installation

```bash
cd quantum-edge-terminal/services/ai_engine

# Install dependencies
pip install -r requirements.txt
# or
python -m pip install fastapi uvicorn pydantic python-dateutil

# Or with conda
conda create -n ai_engine python=3.11
conda activate ai_engine
pip install -r requirements.txt
```

---

## Run Tests

### Module 1: Signal Ingestion

```bash
cd tests
python test_signal_ingestion.py
```

**Output:**
```
Phase 2 raw signals (6 types)
    → Normalized to NormalizedSignal format
    → Indexed for O(1) queries
    → Summary stats
```

### Module 2: Confluence Engine

```bash
cd tests
python test_confluence_scoring.py
```

**Output:**
```
✅ CONFLUENCE SCORE: 7.5 / 10.0

📈 FACTOR BREAKDOWN:

   ✓ Liquidity Sweep            Weight: 1.0
   ✓ Structure Shift (BOS/CHoCH) Weight: 1.5
   ✓ FVG/OB Reaction            Weight: 1.0
   ✓ Fractal Confirmation       Weight: 2.0
   ✓ Directional Bias           Weight: 0.5
   ✓ Options Flow               Weight: 1.0
   ✓ Macro Alignment            Weight: 0.5

🎯 TRADE SUMMARY:

   Direction      : BULLISH
   Entry Price    : $5151.75
   Stop Loss      : $5148.00
   Take Profit    : $5160.00
   Risk/Reward    : 2.6:1
   Risk Level     : LOW
```

---

## Start Server

```bash
python main.py
```

**Output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8200
INFO:     Application startup complete
```

---

## Test Endpoints (Terminal/Postman)

### Health Check

```bash
curl http://localhost:8200/health
```

```json
{
  "status": "healthy",
  "version": "3.0.0",
  "timestamp": 1712500000000
}
```

---

### Ingest Signals

**Ingest a swing:**

```bash
curl -X POST http://localhost:8200/ingest/swing \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ES",
    "timeframe": "1h",
    "direction": "BULLISH",
    "price": 5155.50,
    "confidence": 0.95,
    "signal_type": "SWING_HIGH",
    "details": {"index": 5}
  }'
```

**Ingest a fractal:**

```bash
curl -X POST http://localhost:8200/ingest/fractal \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ES",
    "timeframe": "1h",
    "direction": "BULLISH",
    "price": 5151.75,
    "confidence": 0.91,
    "signal_type": "FRACTAL",
    "details": {
      "entry": 5151.75,
      "stop_loss": 5148.00,
      "take_profit": 5160.00,
      "pattern": "bullish_dip",
      "rr": 2.6
    }
  }'
```

**Ingest BOS:**

```bash
curl -X POST http://localhost:8200/ingest/bos \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "ES",
    "timeframe": "1h",
    "direction": "BULLISH",
    "price": 5158.00,
    "confidence": 0.92,
    "signal_type": "BOS"
  }'
```

---

### Query Signals

**Get all signals:**

```bash
curl http://localhost:8200/signals/all
```

```json
{
  "count": 3,
  "signals": [...]
}
```

**Get summary:**

```bash
curl http://localhost:8200/signals/summary
```

```json
{
  "total": 3,
  "bullish": 3,
  "bearish": 0,
  "avg_confidence": 0.926,
  "by_type": {
    "SWING_HIGH": 1,
    "FRACTAL": 1,
    "BOS": 1
  }
}
```

---

### Score Setup

**Score a single setup:**

```bash
curl -X POST "http://localhost:8200/score/setup?symbol=ES&timeframe=1h&direction=BULLISH&options_bias=BULLISH&macro_regime=risk-on"
```

```json
{
  "symbol": "ES",
  "timeframe": "1h",
  "direction": "BULLISH",
  "score": 7.5,
  "base_price": 5151.75,
  "risk_level": "LOW",
  "stop_loss": 5148.00,
  "take_profit": 5160.00,
  "risk_reward_ratio": 2.6,
  "interpretation": "High-probability trade setup (7.5/10). Multiple confluences present."
}
```

**Score multiple setups (batch):**

```bash
curl -X POST http://localhost:8200/score/batch \
  -H "Content-Type: application/json" \
  -d '{
    "setups": [
      {
        "symbol": "ES",
        "timeframe": "1h",
        "direction": "BULLISH"
      },
      {
        "symbol": "ES",
        "timeframe": "5m",
        "direction": "BEARISH"
      }
    ]
  }'
```

**Get high-probability trades:**

```bash
curl http://localhost:8200/score/high-probability
```

---

### Reset

```bash
curl -X POST http://localhost:8200/signals/reset
```

```json
{
  "status": "reset",
  "timestamp": 1712500000000
}
```

---

## Integration with Phase 2

**From Phase 2 structure_engine (port 8100), forward signals:**

```python
import requests

# After detecting a swing in Phase 2
swing_data = {
    "symbol": "ES",
    "timeframe": "1h",
    "direction": "BULLISH",
    "price": 5155.50,
    "confidence": 0.95,
    "signal_type": "SWING_HIGH"
}

# Send to Phase 3
response = requests.post(
    "http://localhost:8200/ingest/swing",
    json=swing_data
)

print(response.json())
# {"status": "ingested", "signal_type": "SWING_HIGH", ...}

# Score the setup
response = requests.post(
    "http://localhost:8200/score/setup",
    params={
        "symbol": "ES",
        "timeframe": "1h",
        "direction": "BULLISH",
        "options_bias": "BULLISH",
        "macro_regime": "risk-on"
    }
)

trade_score = response.json()
print(f"Trade Score: {trade_score['score']}/10")
print(f"Risk Level: {trade_score['risk_level']}")
```

---

## Docker Deployment

```bash
# Build
docker build -t ai-engine:latest .

# Run
docker run -p 8200:8200 ai-engine:latest

# Or with docker-compose from root
docker-compose up ai_engine
```

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────┐
│ Frontend (port 3000)                                │
│ ├─ Dashboard                                        │
│ ├─ Trade signals panel                              │
│ └─ Real-time alerts                                 │
└──────────────────────────────────────────────────────┘
           ↑ WebSocket
           
┌──────────────────────────────────────────────────────┐
│ Backend (port 3001)                                 │
│ ├─ API routes                                       │
│ ├─ PostgreSQL (trades table)                        │
│ └─ Redis (caching)                                  │
└──────────────────────────────────────────────────────┘
           ↑ HTTP
           
┌──────────────────────────────────────────────────────┐
│ AI Engine (port 8200) ← YOU ARE HERE                │
│ ├─ M1: Signal Ingestion ✅                          │
│ ├─ M2: Confluence Engine ✅                         │
│ ├─ M3-11: (Coming)                                  │
│ └─ FastAPI + Pydantic                               │
└──────────────────────────────────────────────────────┘
           ↑ HTTP
           
┌──────────────────────────────────────────────────────┐
│ Phase 2: Structure Engine (port 8100)               │
│ ├─ M1: Swing Detection ✅                           │
│ ├─ M2-7: (Coming)                                   │
│ └─ FastAPI + Python                                 │
└──────────────────────────────────────────────────────┘
```

---

## Common Patterns

### Pattern 1: Score a New Setup Each Hour

```python
import requests
from datetime import datetime

while True:
    # Get current signals
    signals = requests.get("http://localhost:8200/signals/all").json()
    
    # Score for each symbol/timeframe
    score = requests.post(
        "http://localhost:8200/score/setup",
        params={
            "symbol": "ES",
            "timeframe": "1h",
            "direction": "BULLISH"
        }
    ).json()
    
    if score['score'] >= 7.0:
        print(f"🟢🟢 HIGH PROBABILITY: {score['interpretation']}")
        # Execute trade, alert user, etc.
    
    time.sleep(3600)  # Next hour
```

### Pattern 2: Monitor All Symbols

```python
symbols = ["ES", "SPY", "QQQ", "TSLA"]

for symbol in symbols:
    for timeframe in ["1m", "5m", "15m"]:
        score = requests.post(
            "http://localhost:8200/score/setup",
            params={
                "symbol": symbol,
                "timeframe": timeframe,
                "direction": "BULLISH"
            }
        ).json()
        
        if score['score'] >= 5.0:
            print(f"{symbol} {timeframe}: {score['score']:.1f}/10")
```

### Pattern 3: Batch Score Everything

```python
setups = [
    {"symbol": "ES", "timeframe": "1h", "direction": "BULLISH"},
    {"symbol": "ES", "timeframe": "1h", "direction": "BEARISH"},
    {"symbol": "SPY", "timeframe": "15m", "direction": "BULLISH"},
]

response = requests.post(
    "http://localhost:8200/score/batch",
    json={"setups": setups}
).json()

# Results sorted highest score first
for result in response['results']:
    print(f"{result['score']:.1f}/10: {result['symbol']} {result['direction']}")
```

---

## Troubleshooting

**Error: Connection refused (port 8200)**
```
→ Make sure you ran: python main.py
→ Check it's listening: lsof -i :8200
```

**Error: ModuleNotFoundError: fastapi**
```
→ Install dependencies: pip install -r requirements.txt
```

**Error: InvalidRequestModel**
```
→ Check JSON payload format
→ All required fields present (symbol, timeframe, direction, etc.)
```

**Slow API response**
```
→ Too many signals ingested
→ Run: POST /signals/reset
→ Re-ingest necessary signals
```

---

## Next Steps

1. ✅ Run tests to verify M1 and M2 work
2. ✅ Test API endpoints with curl
3. 🔥 Build Module 3: Options Flow detection
4. 🔥 Build Module 4: Macro Filter
5. 🔥 Build Module 5: Trade Generation
6. 🔥 Integrate with backend (port 3001)
7. 🔥 Add WebSocket broadcasting to frontend

---

## Files

**Core Modules:**
- `modules/signal_ingestion.py` - M1 (320 lines)
- `modules/confluence_engine.py` - M2 (370 lines)

**Server:**
- `main.py` - FastAPI server (400+ lines)

**Tests:**
- `tests/test_signal_ingestion.py` - M1 test
- `tests/test_confluence_scoring.py` - M2 test

**Docs:**
- `README.md` - Complete documentation
- `../docs/PHASE_3_ARCHITECTURE.md` - Full blueprint

---

## Status

✅ Phase 3 Modules 1-2: COMPLETE
🔥 Ready for Module 3
