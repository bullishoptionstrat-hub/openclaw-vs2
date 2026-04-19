import { createClient, RedisClientType } from 'redis';
import pino from 'pino';

const logger = pino();

let redisClient: RedisClientType;

export async function initializeRedis(): Promise<void> {
  try {
    redisClient = createClient({
      url: process.env.REDIS_URL || 'redis://localhost:6379',
    });

    redisClient.on('error', (err) => logger.error('Redis error:', err));
    redisClient.on('connect', () => logger.info('Redis connected'));

    await redisClient.connect();
  } catch (error) {
    logger.error('Redis connection failed:', error);
    throw error;
  }
}

export async function getRedis(): Promise<RedisClientType> {
  if (!redisClient) {
    throw new Error('Redis not initialized');
  }
  return redisClient;
}

// Helper functions
export async function cacheSet(key: string, value: any, ttl: number = 3600): Promise<void> {
  const client = await getRedis();
  await client.setEx(key, ttl, JSON.stringify(value));
}

export async function cacheGet(key: string): Promise<any> {
  const client = await getRedis();
  const value = await client.get(key);
  return value ? JSON.parse(value) : null;
}

export async function cacheDel(key: string): Promise<void> {
  const client = await getRedis();
  await client.del(key);
}

export async function cachePublish(channel: string, message: any): Promise<void> {
  const client = await getRedis();
  await client.publish(channel, JSON.stringify(message));
}
