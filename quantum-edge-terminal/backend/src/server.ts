import express, { Express, Request, Response } from 'express';
import ws from 'express-ws';
import { config } from 'dotenv';
import pino from 'pino';
import { initializeDatabase } from './db/postgres.js';
import { initializeRedis } from './db/redis.js';
import { setupWebSocket } from './websocket/server.js';
import { marketDataRouter } from './api/market-data.js';
import { signalsRouter } from './api/signals.js';
import { alertsRouter } from './api/alerts.js';
import { healthRouter } from './api/health.js';

config();

const logger = pino();
const PORT = process.env.PORT || 3001;

// Initialize Express app with WebSocket support
const app: Express = express();
const { app: wsApp } = ws(app);

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Logging middleware
app.use((req, res, next) => {
  logger.info({
    method: req.method,
    path: req.path,
    timestamp: new Date().toISOString(),
  });
  next();
});

// CORS
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(200);
  }
  next();
});

// Health check endpoint
app.get('/health', (req: Request, res: Response) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// API Routes
app.use('/api/market-data', marketDataRouter);
app.use('/api/signals', signalsRouter);
app.use('/api/alerts', alertsRouter);
app.use('/api/health', healthRouter);

// WebSocket setup
setupWebSocket(wsApp, logger);

// Error handling
app.use((err: any, req: Request, res: Response, next: Function) => {
  logger.error(err);
  res.status(err.status || 500).json({
    error: err.message || 'Internal Server Error',
    timestamp: new Date().toISOString(),
  });
});

// Startup
async function start() {
  try {
    logger.info('Initializing Quantum Edge Terminal Backend...');

    // Initialize databases
    await initializeDatabase();
    logger.info('✓ PostgreSQL connected');

    await initializeRedis();
    logger.info('✓ Redis connected');

    // Start server
    wsApp.listen(PORT, () => {
      logger.info(`
╔════════════════════════════════════════╗
║  QUANTUM EDGE TERMINAL - Backend      ║
║  Server running at http://localhost:${PORT}║
║  WebSocket: ws://localhost:${PORT}     ║
╚════════════════════════════════════════╝
      `);
    });
  } catch (error) {
    logger.error('Failed to start server:', error);
    process.exit(1);
  }
}

start();

export default app;
