import { Express, Request, Response } from 'express';
import { Server } from 'ws';
import pino from 'pino';
import { getRedis } from '../db/redis.js';

const logger = pino();

const subscriptions: Map<string, Set<any>> = new Map();

export function setupWebSocket(app: Express, log: any): void {
  // @ts-ignore - express-ws types
  app.ws('/ws', async (ws, req) => {
    logger.info('WebSocket client connected');

    // Handle subscription
    ws.on('message', async (message: string) => {
      try {
        const { action, channel, symbol, timeframe } = JSON.parse(message);

        if (action === 'subscribe') {
          // Handle subscription
          const subscriptionKey = `${channel}:${symbol}:${timeframe || '1m'}`;
          
          if (!subscriptions.has(subscriptionKey)) {
            subscriptions.set(subscriptionKey, new Set());

            // Subscribe to Redis channel
            const redis = await getRedis();
            const subscriber = redis.duplicate();
            await subscriber.connect();
            await subscriber.subscribe(subscriptionKey, (message) => {
              // Broadcast to all subscribers
              const clients = subscriptions.get(subscriptionKey);
              if (clients) {
                clients.forEach((client) => {
                  if (client.readyState === 1) { // OPEN
                    client.send(message);
                  }
                });
              }
            });
          }

          // Add this client to subscription
          subscriptions.get(subscriptionKey)?.add(ws);
          ws.send(JSON.stringify({ action: 'subscribed', channel: subscriptionKey }));
        }

        if (action === 'unsubscribe') {
          const subscriptionKey = `${channel}:${symbol}:${timeframe || '1m'}`;
          subscriptions.get(subscriptionKey)?.delete(ws);
        }
      } catch (error) {
        logger.error('WebSocket message error:', error);
        ws.send(JSON.stringify({ error: 'Invalid message' }));
      }
    });

    ws.on('close', () => {
      // Clean up subscriptions
      subscriptions.forEach((clients) => clients.delete(ws));
      logger.info('WebSocket client disconnected');
    });

    ws.on('error', (error) => {
      logger.error('WebSocket error:', error);
    });
  });
}
