#!/bin/bash

# Quantum Edge Terminal - Setup & Deployment Script

set -e

echo "╔════════════════════════════════════════╗"
echo "║  QUANTUM EDGE TERMINAL - Setup         ║"
echo "║  Bloomberg-level Trading Platform      ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check prerequisites
echo "✓ Checking prerequisites..."

if ! command -v node &> /dev/null; then
    echo "✗ Node.js not found. Install Node.js 20+ first."
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 not found. Install Python 3.11+ first."
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "✗ Docker not found. Install Docker first."
    exit 1
fi

echo "✓ All prerequisites met"
echo ""

# Backend setup
echo "📦 Setting up Backend..."
cd backend
npm install
cd ..
echo "✓ Backend ready"
echo ""

# Frontend setup
echo "📦 Setting up Frontend..."
cd frontend
npm install
cd ..
echo "✓ Frontend ready"
echo ""

# AI Engine setup
echo "📦 Setting up AI Engine..."
cd ai-engine
pip install -r requirements.txt
cd ..
echo "✓ AI Engine ready"
echo ""

# Docker Compose
echo "🐳 Starting Docker containers..."
docker-compose up -d

echo ""
echo "╔════════════════════════════════════════╗"
echo "║  Setup Complete!                       ║"
echo "╠════════════════════════════════════════╣"
echo "║  Frontend:   http://localhost:3000     ║"
echo "║  Backend:    http://localhost:3001     ║"
echo "║  WebSocket:  ws://localhost:3001/ws    ║"
echo "║  PostgreSQL: localhost:5432            ║"
echo "║  Redis:      localhost:6379            ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "1. Open http://localhost:3000 in browser"
echo "2. Check logs: docker-compose logs -f"
echo "3. Read docs: https://docs.quantumedge.io"
echo ""
