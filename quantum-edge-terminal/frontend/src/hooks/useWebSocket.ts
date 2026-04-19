'use client';

import { useEffect, useState, useCallback } from 'react';

export function useWebSocket() {
  const [isConnected, setIsConnected] = useState(false);
  const [ws, setWs] = useState<WebSocket | null>(null);

  useEffect(() => {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:3001/ws';
    const websocket = new WebSocket(wsUrl);

    websocket.onopen = () => {
      setIsConnected(true);
      console.log('WebSocket connected');
    };

    websocket.onclose = () => {
      setIsConnected(false);
      console.log('WebSocket disconnected');
    };

    websocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };

    setWs(websocket);

    return () => {
      websocket.close();
    };
  }, []);

  const subscribe = useCallback(
    (channel: string, options: any) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(
          JSON.stringify({
            action: 'subscribe',
            channel,
            ...options,
          })
        );
      }
    },
    [ws]
  );

  return { isConnected, subscribe };
}
