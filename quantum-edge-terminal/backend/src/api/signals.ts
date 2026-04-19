import { Router, Request, Response } from 'express';
import { query } from '../db/postgres.js';
import pino from 'pino';

const logger = pino();
export const signalsRouter = Router();

/**
 * GET /api/signals
 * Get active/recent trade signals
 */
signalsRouter.get('/', async (req: Request, res: Response) => {
  try {
    const { status = 'ACTIVE', limit = 50 } = req.query;

    const result = await query(
      `SELECT * FROM signals 
       WHERE status = $1 
       ORDER BY created_at DESC 
       LIMIT $2`,
      [status, limit]
    );

    res.json({
      count: result.rowCount,
      data: result.rows,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    logger.error('signals endpoint error:', error);
    res.status(500).json({ error: 'Failed to fetch signals' });
  }
});

/**
 * POST /api/signals
 * Create a new trade signal
 */
signalsRouter.post('/', async (req: Request, res: Response) => {
  try {
    const {
      signal_type,
      symbol,
      entry_price,
      stop_loss,
      take_profit,
      confidence,
      confirmations,
    } = req.body;

    if (!signal_type || !symbol || !entry_price) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    const result = await query(
      `INSERT INTO signals 
        (signal_type, symbol, entry_price, stop_loss, take_profit, confidence, confirmations, status)
       VALUES ($1, $2, $3, $4, $5, $6, $7, 'ACTIVE')
       RETURNING *`,
      [signal_type, symbol, entry_price, stop_loss, take_profit, confidence, confirmations]
    );

    res.status(201).json({
      success: true,
      data: result.rows[0],
    });
  } catch (error) {
    logger.error('create signal error:', error);
    res.status(500).json({ error: 'Failed to create signal' });
  }
});

/**
 * PUT /api/signals/:id
 * Update signal status (close position)
 */
signalsRouter.put('/:id', async (req: Request, res: Response) => {
  try {
    const { id } = req.params;
    const { status, pnl, closed_at } = req.body;

    if (!status) {
      return res.status(400).json({ error: 'status required' });
    }

    const result = await query(
      `UPDATE signals 
       SET status = $1, pnl = $2, closed_at = $3
       WHERE id = $4
       RETURNING *`,
      [status, pnl || null, closed_at || new Date().toISOString(), id]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Signal not found' });
    }

    res.json({ success: true, data: result.rows[0] });
  } catch (error) {
    logger.error('update signal error:', error);
    res.status(500).json({ error: 'Failed to update signal' });
  }
});
