import { Router, Request, Response } from 'express';
import { query } from '../db/postgres.js';
import pino from 'pino';

const logger = pino();
export const alertsRouter = Router();

/**
 * GET /api/alerts
 * Get recent alerts
 */
alertsRouter.get('/', async (req: Request, res: Response) => {
  try {
    const { limit = 50, severity } = req.query;

    let whereClause = 'WHERE 1=1';
    const params: any[] = [];

    if (severity) {
      whereClause += ' AND severity = $1';
      params.push(severity);
    }

    const result = await query(
      `SELECT * FROM alerts 
       ${whereClause}
       ORDER BY sent_at DESC 
       LIMIT $${params.length + 1}`,
      [...params, limit]
    );

    res.json({
      count: result.rowCount,
      data: result.rows,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    logger.error('alerts endpoint error:', error);
    res.status(500).json({ error: 'Failed to fetch alerts' });
  }
});

/**
 * POST /api/alerts
 * Create and broadcast a new alert
 */
alertsRouter.post('/', async (req: Request, res: Response) => {
  try {
    const { alert_type, severity, message, channels, user_id } = req.body;

    if (!alert_type || !severity || !message) {
      return res.status(400).json({ error: 'Missing required fields' });
    }

    const result = await query(
      `INSERT INTO alerts 
        (alert_type, severity, message, channels, user_id)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING *`,
      [alert_type, severity, message, JSON.stringify(channels || []), user_id || null]
    );

    // TODO: Broadcast to Discord, Email, WebSocket, etc.

    res.status(201).json({
      success: true,
      data: result.rows[0],
    });
  } catch (error) {
    logger.error('create alert error:', error);
    res.status(500).json({ error: 'Failed to create alert' });
  }
});
