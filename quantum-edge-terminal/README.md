# QUANTUM EDGE TERMINAL

**Bloomberg-level quantitative trading platform for institutional-grade analysis.**

A production-grade, modular, real-time trading intelligence system designed to detect liquidity manipulation, institutional order flow, algorithmic traps, and high-probability trade setups.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│          FRONTEND (Next.js + Tailwind)              │
│  Bloomberg-style dark theme multi-panel UI          │
│  Real-time WebSocket updates, drag-drop panels      │
└────────────────┬──────────────────────────────────┘
                 │ WebSocket / REST API
┌────────────────▼──────────────────────────────────┐
│          BACKEND (Express + Node.js)               │
│  • Market Data Aggregation                         │
│  • Signal Processing & Routing                     │
│  • User Sessions & Alerts                          │
│  • API Gateway                                     │
└────────────────┬──────────────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
   PostgreSQL         Redis
   (Historical)    (Real-time Signals)
   
┌─────────────────────────────────────────────────────┐
│          PYTHON AI ENGINE                           │
│  • Market Structure Detection (ICT/SMC)             │
│  • Pattern Recognition                             │
│  • Multi-Confirmation Trade Validation             │
│  • Signal Scoring                                  │
└─────────────────────────────────────────────────────┘
```

## 8 Core Modules

| Module | Purpose | Output |
|--------|---------|--------|
| **Market Data Engine** | Aggregates live market feeds (ES, NQ, GC, SPY, QQQ) | Normalized price/volume |
| **Market Structure** | Detects BOS, CHoCH, sweeps, FVG, order blocks | Structure events |
| **Fractal Engine (TTrades)** | 4-candle fractal pattern validation | Candle confluence |
| **Algo Detection** | Identifies false breakouts, stop hunts, traps | Manipulation state |
| **Options Flow** | Tracks institutional positioning & delta imbalance | Institutional bias |
| **Macro Engine** | GDP, inflation, QE tracking, regime classification | Macro regime |
| **AI Trade Engine** | Multi-confirmation trade validation | Trade signals |
| **Alert System** | Discord, email, web notifications | Real-time alerts |

## Phase 1: Market Data + UI (MVP Foundation)

✅ **Phase 1 Scope:**
- Market data aggregation pipeline
- PostgreSQL schema for historical data
- Redis setup for real-time signals
- Next.js dashboard UI (dark theme)
- WebSocket server for live updates
- Basic API routes

## Phase 2: Market Structure Detection

- Swing high/low detection
- BOS (Break of Structure) alerts
- CHoCH (Change of Character) recognition
- Liquidity sweep identification
- Fair value gap (FVG) detection
- Order block mapping

## Phase 3: AI + Trade Validation

- Multi-confirmation scoring
- Fractal pattern validation
- Entry/exit generation
- Position sizing
- Risk/reward calculations

## Phase 4: Options + Macro Integration

- Options flow analysis
- Institutional positioning
- Macro regime correlation
- Advanced alert routing

---

## Quick Start

### Prerequisites
- Node.js 20+
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (optional)

### Installation

1. **Clone & Install**
```bash
cd quantum-edge-terminal
npm install  # root dependencies
cd backend && npm install
cd ../frontend && npm install
cd ../ai-engine && pip install -r requirements.txt
```

2. **Setup Environment**
```bash
# backend/.env
DATABASE_URL=postgresql://user:pass@localhost:5432/quantum-edge
REDIS_URL=redis://localhost:6379
JWT_SECRET=your-secret-key

# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:3001
NEXT_PUBLIC_WS_URL=ws://localhost:3001
```

3. **Database Migrations**
```bash
cd database
psql -U postgres < schema.sql
redis-cli < redis-init.lua
```

4. **Start Services**
```bash
# Terminal 1: Backend
cd backend && npm run dev

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: AI Engine
cd ai-engine && python main.py
```

5. **Access Terminal**
- Open `http://localhost:3000`
- Login with demo credentials
- Markets will start loading in real-time

---

## Project Structure

```
quantum-edge-terminal/
├── frontend/                 # Next.js UI
│   ├── src/
│   │   ├── components/      # Dashboard panels, charts
│   │   ├── hooks/           # WebSocket, API hooks
│   │   ├── services/        # API client, WebSocket client
│   │   └── styles/          # Tailwind config
│   └── package.json
│
├── backend/                 # Express API
│   ├── src/
│   │   ├── modulesdetect/    # 8 core modules
│   │   ├── api/              # REST routes
│   │   ├── db/               # Database clients
│   │   ├── services/         # Business logic
│   │   ├── websocket/        # WebSocket server
│   │   └── utils/            # Helpers
│   └── package.json
│
├── ai-engine/               # Python signal processing
│   ├── src/
│   │   ├── modules/         # Detection algorithms
│   │   ├── models/          # ML/scoring models
│   │   └── utils/           # Data processing
│   └── requirements.txt
│
├── database/                # PostgreSQL + Redis
│   ├── schema.sql
│   ├── migrations/
│   └── redis-init.lua
│
├── docker-compose.yml       # Full stack deployment
└── docs/                    # Architecture & guides

```

---

## Production Deployment

### Docker
```bash
docker-compose up -d
```

### AWS/GCP
- Backend → ECS/Cloud Run
- Frontend → CloudFront/CDN
- PostgreSQL → RDS
- Redis → ElastiCache
- Python workers → Lambda/Cloud Functions

---

## Testing & Backtesting

### Unit Tests
```bash
cd backend && npm test
cd ai-engine && pytest
```

### Backtesting
```bash
python backtester.py --strategy market_structure --symbols ES,NQ,SPY
```

---

## Safety & Reliability

- **Multi-confirmation logic** — No trade without 3+ signals
- **Signal logging** — All trades/signals recorded
- **Paper trading mode** — Test before live
- **Rate limiting** — Prevent over-trading
- **Circuit breakers** — Auto-stop on anomalies

---

## API Reference

See [docs/API.md](docs/API.md) for full REST/WebSocket API specification.

---

## Contributing

- Follow TypeScript strict mode
- All modules have unit tests
- Signal quality gates before merge
- Code review for algo changes

---

## License

Proprietary. For authorized users only.

---

## Support

- Discord: [Quantum Edge Trading]
- Email: support@quantumedge.io
- Docs: https://docs.quantumedge.io

---

**Built for professional traders who demand institutional-grade analysis.**

*Real-time market structure. Institutional order flow. Algorithmic precision.*
