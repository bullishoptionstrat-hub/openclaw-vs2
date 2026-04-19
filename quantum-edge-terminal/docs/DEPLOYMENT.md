# QUANTUM EDGE TERMINAL - Deployment Guide

**Complete deployment guide for Phase 1 MVP across development, staging, and production environments.**

---

## Table of Contents

1. [Local Development Setup](#local-development-setup)
2. [Docker Compose Deployment](#docker-compose-deployment)
3. [Production Deployment](#production-deployment)
4. [Monitoring & Logging](#monitoring--logging)
5. [Backup & Disaster Recovery](#backup--disaster-recovery)
6. [Troubleshooting](#troubleshooting)

---

## Local Development Setup

### Prerequisites

```
- Node.js 20+ (verify: node --version)
- Python 3.11+ (verify: python --version)
- npm or yarn (verify: npm --version)
- PostgreSQL 15+ (brew install postgresql@15)
- Redis 7+ (brew install redis)
- Git (verify: git --version)
```

### Installation Steps

**1. Clone Repository**
```bash
cd ~/projects
git clone https://github.com/openclaw/openclaw.git
cd openclaw/quantum-edge-terminal
```

**2. Backend Setup**
```bash
cd backend

# Install dependencies
npm install

# Copy environment file
cp .env.example .env

# Edit .env with local credentials
nano .env
# DB_HOST=localhost
# DB_USER=postgres
# DB_PASSWORD=yourpassword
# REDIS_URL=redis://localhost:6379

# Run database migrations (Phase 2)
npm run db:migrate

# Start development server
npm run dev
# Server running on http://localhost:3001
```

**3. Frontend Setup**
```bash
cd ../frontend

# Install dependencies
npm install

# Copy environment file
cp .env.example .env

# Edit .env
nano .env
# NEXT_PUBLIC_API_URL=http://localhost:3001
# NEXT_PUBLIC_WS_URL=ws://localhost:3001

# Start Next.js development server
npm run dev
# Frontend running on http://localhost:3000
```

**4. AI Engine Setup**
```bash
cd ../ai-engine

# Create Python virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run FastAPI server
python main.py
# AI Engine running on http://localhost:8000
```

**5. Database Setup**
```bash
# Start PostgreSQL (if not running)
brew services start postgresql@15

# Create database
psql -U postgres -c "CREATE DATABASE quantum_edge;"

# Run schema
psql -U postgres -d quantum_edge < database/schema.sql

# Verify
psql -U postgres -d quantum_edge -c "\dt"
```

**6. Redis Setup**
```bash
# Start Redis (if not running)
brew services start redis

# Verify connection
redis-cli ping
# Output: PONG

# Initialize streams
redis-cli < database/redis-init.lua
```

### Development Workflow

```bash
# Terminal 1: Backend
cd backend && npm run dev

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: AI Engine
cd ai-engine && source venv/bin/activate && python main.py

# Terminal 4: Watch logs
tail -f /tmp/quantum-edge.log
```

---

## Docker Compose Deployment

### Quick Start (5 minutes)

```bash
cd quantum-edge-terminal

# Start all services
docker-compose up -d

# Verify services
docker-compose ps

# Check logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Service Architecture

```
┌─────────────────────────────────────────────────┐
│         Docker Compose (quantum-edge)           │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────┐  ┌──────────────┐            │
│  │  Frontend    │  │  Backend     │            │
│  │  Port: 3000  │  │  Port: 3001  │            │
│  │  (Next.js)   │  │  (Express)   │            │
│  └──────────────┘  └──────────────┘            │
│         ↓                  ↓                    │
│  ┌──────────────────────────────────┐          │
│  │   PostgreSQL (Port 5432)         │          │
│  │   Redis (Port 6379)              │          │
│  └──────────────────────────────────┘          │
│                                                 │
│  ┌──────────────────────────────────┐          │
│  │  AI Engine (Port 8000)           │          │
│  │  (FastAPI)                       │          │
│  └──────────────────────────────────┘          │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Environment Configuration

**Create .env file:**
```bash
cd quantum-edge-terminal

# Copy example
cp .env.example .env

# Edit with your credentials
cat .env
```

**.env contents:**
```
# PostgreSQL
DATABASE_URL=postgresql://qe_user:qe_password@postgres:5432/quantum-edge
DB_HOST=postgres
DB_USER=qe_user
DB_PASSWORD=qe_password
DB_NAME=quantum-edge

# Redis
REDIS_URL=redis://redis:6379
REDIS_HOST=redis
REDIS_PORT=6379

# Backend
BACKEND_PORT=3001
BACKEND_ENV=development
LOG_LEVEL=info

# Frontend
FRONTEND_PORT=3000
NEXT_PUBLIC_API_URL=http://localhost:3001
NEXT_PUBLIC_WS_URL=ws://localhost:3001

# AI Engine
AI_ENGINE_PORT=8000
AI_MODEL=gpt-4

# Security (Phase 3)
JWT_SECRET=your-secret-key-here
API_KEY=your-api-key-here
```

### Docker Compose Commands

```bash
# Start services in background
docker-compose up -d

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f ai-engine

# Stop services
docker-compose stop

# Remove services and volumes
docker-compose down -v

# Rebuild images
docker-compose build --no-cache

# Scale service (Phase 2)
docker-compose up -d --scale backend=3

# Execute command in container
docker-compose exec backend npm run db:migrate
docker-compose exec postgres psql -U qe_user -d quantum-edge -c "\dt"
```

### Monitoring Docker Services

```bash
# Resource usage
docker stats

# View container logs with timestamps
docker-compose logs --timestamps -f

# Inspect service
docker-compose ps
docker inspect <container-name>

# Network diagnostics
docker network ls
docker inspect quantum-edge-terminal_default
```

---

## Production Deployment

### AWS ECS Deployment (Phase 2+)

#### Architecture
```
┌─────────────────────────────────────┐
│        Application Load Balancer    │
└────────────────┬────────────────────┘
                 │
         ┌──────┴──────┐
         │             │
    ┌────▼────┐   ┌───▼────┐
    │  ECS    │   │  ECS   │
    │Frontend │   │Backend │
    └────┬────┘   └───┬────┘
         │            │
    ┌────▼────────────▼────┐
    │   RDS PostgreSQL     │
    │   (Multi-AZ)         │
    └──────────────────────┘
    
    ┌──────────────────────┐
    │  ElastiCache Redis   │
    │  (Cluster mode)      │
    └──────────────────────┘
```

#### ECS Task Definitions

**backend-task-definition.json:**
```json
{
  "family": "quantum-edge-backend",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "YOUR_ACCOUNT.dkr.ecr.us-east-1.amazonaws.com/quantum-edge:backend-latest",
      "portMappings": [
        {
          "containerPort": 3001,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {
          "name": "DATABASE_URL",
          "value": "postgresql://user:pass@rds-endpoint:5432/quantum-edge"
        },
        {
          "name": "REDIS_URL",
          "value": "redis://elasticache-endpoint:6379"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/quantum-edge-backend",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:3001/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
```

#### Deployment Script

```bash
#!/bin/bash
# deploy.sh

set -e

REGION="us-east-1"
ACCOUNT_ID="123456789012"
ECR_REPO="quantum-edge"
CLUSTER_NAME="prod-cluster"
FAMILY="quantum-edge-backend"

# Build and push Docker image
docker build -t ${ECR_REPO}:backend-latest backend/
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com
docker tag ${ECR_REPO}:backend-latest ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}:backend-latest
docker push ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}:backend-latest

# Update ECS service
aws ecs update-service \
  --cluster ${CLUSTER_NAME} \
  --service quantum-edge-backend \
  --force-new-deployment \
  --region ${REGION}

# Wait for deployment
aws ecs wait services-stable \
  --cluster ${CLUSTER_NAME} \
  --services quantum-edge-backend \
  --region ${REGION}

echo "✅ Deployment complete!"
```

#### Database Migration (RDS)

```bash
# Connect to RDS
psql -h quantum-edge-db.123456789012.us-east-1.rds.amazonaws.com \
     -U qe_admin \
     -d quantum_edge < database/schema.sql

# Verify
psql -h quantum-edge-db.123456789012.us-east-1.rds.amazonaws.com \
     -U qe_admin \
     -d quantum_edge -c "\dt"
```

### Kubernetes Deployment (Phase 3+)

#### Helm Chart Structure
```
helm/quantum-edge/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── backend-deployment.yaml
│   ├── frontend-deployment.yaml
│   ├── ai-engine-deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── configmap.yaml
```

#### Deploy with Helm
```bash
helm repo add quantum-edge https://helm.openclaw.ai
helm install quantum-edge quantum-edge/quantum-edge \
  --namespace prod \
  --values values-prod.yaml

# Verify
kubectl get pods -n prod
kubectl logs -f pod/quantum-edge-backend-0 -n prod
```

---

## Monitoring & Logging

### Application Monitoring

#### Health Checks

```bash
# Backend
curl http://localhost:3001/health
# {"status": "healthy", "uptime": 3600}

# AI Engine
curl http://localhost:8000/health
# {"status": "healthy", "models_loaded": true}

# Frontend (Next.js)
curl http://localhost:3000
# HTML response
```

#### Metrics Collection (Phase 2+)

```javascript
// backend/src/middleware/metrics.ts
import prom from 'prom-client';

const httpDuration = new prom.Histogram({
  name: 'http_request_duration_ms',
  help: 'Duration of HTTP requests in ms',
  labelNames: ['method', 'route', 'status_code'],
  buckets: [0.1, 5, 15, 50, 100, 500]
});

export const metricsMiddleware = (req, res, next) => {
  const start = Date.now();
  res.on('finish', () => {
    const duration = Date.now() - start;
    httpDuration
      .labels(req.method, req.route?.path, res.statusCode)
      .observe(duration);
  });
  next();
};

// Prometheus metrics endpoint
app.get('/metrics', (req, res) => {
  res.set('Content-Type', prom.register.contentType);
  res.end(prom.register.metrics());
});
```

#### Logging Strategy

```bash
# Log levels
DEBUG    - Detailed execution flow
INFO     - Important events
WARN     - Potential issues
ERROR    - Error conditions
FATAL    - System failures

# Log files
/var/log/quantum-edge/backend.log
/var/log/quantum-edge/frontend.log
/var/log/quantum-edge/ai-engine.log
/var/log/quantum-edge/postgres.log
/var/log/quantum-edge/redis.log
```

#### CloudWatch Setup (AWS)

```bash
# Create log group
aws logs create-log-group --log-group-name /quantum-edge/backend

# Stream logs
aws logs tail /quantum-edge/backend --follow

# Query logs
aws logs filter-log-events \
  --log-group-name /quantum-edge/backend \
  --filter-pattern "ERROR"
```

### Performance Monitoring

#### Key Metrics

| Metric | Target | Alert |
|--------|--------|-------|
| API Response Time (p95) | <100ms | >500ms |
| Database Query (p95) | <50ms | >200ms |
| Error Rate | <0.1% | >1% |
| CPU Usage | <70% | >85% |
| Memory Usage | <80% | >90% |
| Disk Usage | <80% | >90% |

#### New Relic/Datadog Setup

```javascript
// backend/src/server.ts
const newrelic = require('newrelic');

const app = express();
app.use(newrelic.middleware.express());

// All requests now automatically tracked
```

---

## Backup & Disaster Recovery

### Database Backups

#### PostgreSQL Backups

```bash
# Full backup
pg_dump -U qe_user quantum_edge > backup-$(date +%Y%m%d-%H%M%S).sql

# Compress backup
pg_dump -U qe_user quantum_edge | gzip > backup-$(date +%Y%m%d-%H%M%S).sql.gz

# S3 backup
pg_dump -U qe_user quantum_edge | gzip | aws s3 cp - s3://quantum-edge-backups/postgres-$(date +%Y%m%d-%H%M%S).sql.gz

# Automated daily backup (cron)
0 2 * * * pg_dump -U qe_user quantum_edge | gzip | aws s3 cp - s3://quantum-edge-backups/postgres-$(date +\%Y\%m\%d-\%H\%M\%S).sql.gz
```

#### Restore from Backup

```bash
# From file
psql -U qe_user quantum_edge < backup-20260403-120000.sql

# From S3
aws s3 cp s3://quantum-edge-backups/postgres-20260403-120000.sql.gz - | gunzip | psql -U qe_user quantum_edge
```

#### AWS RDS Backups (Production)

```bash
# Enable automated backups (30-day retention)
aws rds modify-db-instance \
  --db-instance-identifier quantum-edge-db \
  --backup-retention-period 30 \
  --preferred-backup-window "02:00-03:00"

# Create manual snapshot
aws rds create-db-snapshot \
  --db-instance-identifier quantum-edge-db \
  --db-snapshot-identifier quantum-edge-snapshot-$(date +%Y%m%d)

# Restore from snapshot
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier quantum-edge-db-restored \
  --db-snapshot-identifier quantum-edge-snapshot-20260403
```

### Redis Backup

```bash
# Save current dataset
redis-cli BGSAVE

# Background snapshot (async)
redis-cli BGREWRITEAOF

# Copy to S3
aws s3 cp /var/lib/redis/dump.rdb s3://quantum-edge-backups/redis-$(date +%Y%m%d).rdb
```

### Disaster Recovery Plan

#### RTO/RPO Targets

| Scenario | RTO | RPO |
|----------|-----|-----|
| Single service crash | 5 min | 1 min |
| Database corruption | 30 min | 5 min |
| Region failure | 1 hour | 15 min |
| Total system failure | 4 hours | 1 hour |

#### Recovery Procedures

**1. Backend Service Down**
```bash
# Check health
curl http://localhost:3001/health

# Restart container
docker-compose restart backend

# Or restart ECS task
aws ecs update-service \
  --cluster prod-cluster \
  --service quantum-edge-backend \
  --force-new-deployment
```

**2. Database Down**
```bash
# Check connection
psql -h localhost -U qe_user -c "SELECT 1"

# Restore from backup
psql -U qe_user quantum_edge < backup-latest.sql

# Verify data
psql -U qe_user quantum_edge -c "SELECT COUNT(*) FROM signals;"
```

**3. Complete System Failure**
```bash
# Provision new infrastructure (terraform/CloudFormation)
terraform apply

# Restore from latest backup
psql -U qe_user quantum_edge < s3://backups/latest.sql

# Restore Redis
redis-cli SHUTDOWN
cp s3://backups/redis-latest.rdb /var/lib/redis/dump.rdb
redis-server

# Deploy services
docker-compose up -d
# or
helm install quantum-edge quantum-edge/quantum-edge
```

---

## Troubleshooting

### Common Issues & Solutions

#### 1. PostgreSQL Connection Failed

**Symptom:** `Error: connect ECONNREFUSED 127.0.0.1:5432`

**Solution:**
```bash
# Check if PostgreSQL is running
ps aux | grep postgres
# or
brew services list | grep postgresql

# Start PostgreSQL
brew services start postgresql@15

# Verify port
lsof -i :5432

# Test connection
psql -U postgres -h localhost -c "SELECT 1"
```

#### 2. Redis Connection Refused

**Symptom:** `Error: Connection refused 127.0.0.1:6379`

**Solution:**
```bash
# Start Redis
redis-server

# Verify connection
redis-cli ping
# Output: PONG

# Check port
lsof -i :6379

# Clear cache (if corrupted)
redis-cli FLUSHALL
```

#### 3. WebSocket Connection Timeout

**Symptom:** `WebSocket connection failed after 30s`

**Solution:**
```bash
# Check backend is running
curl http://localhost:3001/health

# Verify WebSocket port
lsof -i :3001

# Test connection
wscat -c ws://localhost:3001/ws

# Check backend logs
docker-compose logs backend | grep -i websocket
```

#### 4. Frontend Build Fails

**Symptom:** `Error: Cannot find module 'next'`

**Solution:**
```bash
cd frontend

# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install

# Rebuild
npm run build

# Start
npm run dev
```

#### 5. AI Engine Model Loading Fails

**Symptom:** `Error loading detection models`

**Solution:**
```bash
cd ai-engine

# Verify Python environment
python --version
python -c "import fastapi; import pydantic; print('OK')"

# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Start with debug output
python main.py --debug
```

#### 6. Out of Memory

**Symptom:** `Container killed: OOMKilled`

**Solution:**
```bash
# Increase Docker memory limit
docker update --memory 4g container-name

# Or in docker-compose.yml
services:
  backend:
    mem_limit: 4g
    memswap_limit: 6g

# Monitor memory usage
docker stats

# Check logs for memory leaks
docker-compose logs backend | grep -i memory
```

#### 7. High CPU Usage

**Symptom:** Service consuming 100% CPU

**Solution:**
```bash
# Identify hot function
# Use profiling tools (Phase 2)

# Temporary mitigation: restart service
docker-compose restart backend

# Scale horizontally
docker-compose up -d --scale backend=3

# Profile CPU
py-spy record -o profile.svg --pid <PID>
```

### Debug Commands

```bash
# Backend logs with timestamps
docker-compose logs --timestamps backend

# Follow real-time logs
docker-compose logs -f

# Filter errors only
docker-compose logs backend | grep ERROR

# Database query log
SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;

# Redis memory usage
redis-cli INFO memory

# Frontend build debug
NEXT_DEBUG=true npm run build

# Network debugging
netstat -an | grep ESTABLISHED
ss -ltnp | grep 3001
```

---

## Scaling (Phase 2+)

### Horizontal Scaling

```bash
# Scale backend to 3 instances
docker-compose up -d --scale backend=3

# With load balancer
docker-compose -f docker-compose.prod.yml up -d

# Kubernetes scaling
kubectl scale deployment backend --replicas=3 -n prod
```

### Performance Optimization Checklist

- [ ] Enable PostgreSQL query caching
- [ ] Compress API responses (gzip)
- [ ] Enable Redis cluster mode
- [ ] CDN for static assets (Phase 2+)
- [ ] Database connection pooling increment
- [ ] Add read replicas for database (Phase 3+)
- [ ] Implement candle compression (Phase 2+)

---

**Last Updated:** April 3, 2026
**Status:** Phase 1 Complete
**Next:** Production monitoring setup (Phase 2)
