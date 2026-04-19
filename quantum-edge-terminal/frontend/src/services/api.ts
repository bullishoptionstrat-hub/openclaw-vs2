import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001';

export const apiClient = axios.create({
  baseURL: `${API_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const marketDataService = {
  getCandles: (symbol: string, timeframe: string, limit: number = 100) =>
    apiClient.get(`/market-data/candles/${symbol}/${timeframe}?limit=${limit}`),
  
  getLatestCandle: (symbol: string, timeframe: string) =>
    apiClient.get(`/market-data/latest/${symbol}/${timeframe}`),
};

export const signalsService = {
  getSignals: (status: string = 'ACTIVE', limit: number = 50) =>
    apiClient.get(`/signals?status=${status}&limit=${limit}`),
  
  createSignal: (payload: any) =>
    apiClient.post('/signals', payload),
  
  updateSignal: (id: number, payload: any) =>
    apiClient.put(`/signals/${id}`, payload),
};

export const alertsService = {
  getAlerts: (limit: number = 50) =>
    apiClient.get(`/alerts?limit=${limit}`),
  
  createAlert: (payload: any) =>
    apiClient.post('/alerts', payload),
};
