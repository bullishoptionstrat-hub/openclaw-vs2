import { Router, Request, Response } from 'express';

export const healthRouter = Router();

healthRouter.get('/', (req: Request, res: Response) => {
  res.json({
    status: 'healthy',
    service: 'quantum-edge-backend',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  });
});
