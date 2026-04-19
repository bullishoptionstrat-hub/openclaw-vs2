#!/bin/bash

# Ports
PostgreSQL: 5432
Redis: 6379
Backend (Node.js): 3001
Frontend (Next.js): 3000
AI Engine (FastAPI): 8000

# Default Credentials
PostgreSQL:
  User: qe_user
  Password: qe_password
  Database: quantum-edge

# API Endpoints

## Frontend
http://localhost:3000

## Backend API
http://localhost:3001/api/

### Market Data
GET  /api/market-data/candles/:symbol/:timeframe
GET  /api/market-data/latest/:symbol/:timeframe
POST /api/market-data/ingest

### Signals
GET  /api/signals
POST /api/signals
PUT  /api/signals/:id

### Alerts
GET  /api/alerts
POST /api/alerts

### Health
GET  /api/health

## WebSocket
ws://localhost:3001/ws

## AI Engine (FastAPI)
http://localhost:8000

### AI Endpoints
GET  /health
POST /analyze/structure
POST /analyze/fractal
POST /analyze/algo
POST /score/trade

# Tech Stack
- Frontend: Next.js 14, React 18, TypeScript, Tailwind CSS
- Backend: Express.js, TypeScript, PostgreSQL, Redis
- AI: Python 3.11, FastAPI, Pandas, NumPy, scikit-learn
- Deployment: Docker, Docker Compose
- Testing: Vitest (TS), Pytest (Python)

# MongoDB
# Optional: For time-series data and signal logging
# docker run -d -p 27017:27017 mongo:7

# InfluxDB
# Optional: For high-frequency time-series market data
# docker run -d -p 8086:8086 influxdb:2
