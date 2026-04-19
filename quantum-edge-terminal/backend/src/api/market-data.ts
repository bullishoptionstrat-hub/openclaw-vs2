import { Router, Request, Response } from 'express';
import { query } from '../db/postgres.js';
import { cacheGet, cacheSet } from '../db/redis.js';
import pino from 'pino';

const logger = pino();
export const marketDataRouter = Router();

/**
 * GET /api/market-data/candles/:symbol/:timeframe
 * Retrieve historical candle data
 */
marketDataRouter.get('/candles/:symbol/:timeframe', async (req: Request, res: Response) => {
  try {
    const { symbol, timeframe } = req.params;
    const { limit = 100, offset = 0 } = req.query;

    // Validate inputs
    if (!symbol || !timeframe) {
      return res.status(400).json({ error: 'symbol and timeframe required' });
    }

    // Check cache first
    const cacheKey = `candles:${symbol}:${timeframe}:${offset}:${limit}`;
    const cached = await cacheGet(cacheKey);
    if (cached) {
      return res.json({ data: cached, source: 'cache' });
    }

    // Query from PostgreSQL
    const result = await query(
      `SELECT * FROM candles 
       WHERE symbol = $1 AND timeframe = $2 
       ORDER BY timestamp DESC 
       LIMIT $3 OFFSET $4`,
      [symbol, timeframe, limit, offset]
    );

    // Cache for 5 minutes
    await cacheSet(cacheKey, result.rows, 300);

    res.json({
      symbol,
      timeframe,
      count: result.rowCount,
      data: result.rows,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    logger.error('candles endpoint error:', error);
    res.status(500).json({ error: 'Failed to fetch candles' });
  }
});

/**
 * GET /api/market-data/latest/:symbol/:timeframe
 * Get the most recent candle
 */
marketDataRouter.get('/latest/:symbol/:timeframe', async (req: Request, res: Response) => {
  try {
    const { symbol, timeframe } = req.params;

    // Check cache first
    const cacheKey = `latest:${symbol}:${timeframe}`;
    const cached = await cacheGet(cacheKey);
    if (cached) {
      return res.json({ data: cached, source: 'cache' });
    }

    // Query latest
    const result = await query(
      `SELECT * FROM candles 
       WHERE symbol = $1 AND timeframe = $2 
       ORDER BY timestamp DESC LIMIT 1`,
      [symbol, timeframe]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found' });
    }

    const candle = result.rows[0];
    await cacheSet(cacheKey, candle, 60); // Cache for 1 minute

    res.json({
      symbol,
      timeframe,
      data: candle,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    logger.error('latest endpoint error:', error);
    res.status(500).json({ error: 'Failed to fetch latest candle' });
  }
});

/**
 * POST /api/market-data/ingest
 * Ingest new candle data (internal use)
 */
marketDataRouter.post('/ingest', async (req: Request, res: Response) => {
  try {
    const { symbol, timeframe, candle } = req.body;

    if (!symbol || !timeframe || !candle) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    // Insert into database
    await query(
      `INSERT INTO candles 
        (symbol, timeframe, timestamp, open, high, low, close, volume, vwap, bidAsk) 
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
       ON CONFLICT (symbol, timeframe, timestamp) DO UPDATE SET
        open = EXCLUDED.open,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        close = EXCLUDED.close,
        volume = EXCLUDED.volume`,
      [
        symbol,
        timeframe,
        candle.timestamp,
        candle.open,
        candle.high,
        candle.low,
        candle.close,
        candle.volume,
        candle.vwap,
        JSON.stringify(candle.bidAsk),
      ]
    );

    // Invalidate cache
    const cacheKey = `latest:${symbol}:${timeframe}`;
    await cacheSet(cacheKey, candle, 60);

    res.json({ success: true, message: 'Candle ingested' });
  } catch (error) {
    logger.error('ingest endpoint error:', error);
    res.status(500).json({ error: 'Failed to ingest candle' });
  }
});
