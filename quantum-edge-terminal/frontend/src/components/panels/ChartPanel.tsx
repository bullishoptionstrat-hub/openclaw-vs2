'use client';

import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface ChartPanelProps {
  symbol: string;
  timeframe: string;
}

export default function ChartPanel({ symbol, timeframe }: ChartPanelProps) {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/market-data/candles/${symbol}/${timeframe}?limit=50`
        );
        const result = await response.json();
        
        // Transform data for Recharts
        const chartData = result.data.map((candle: any) => ({
          time: new Date(candle.timestamp).toLocaleTimeString(),
          close: candle.close,
          high: candle.high,
          low: candle.low,
          volume: candle.volume,
        }));

        setData(chartData);
      } catch (error) {
        console.error('Failed to fetch chart data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [symbol, timeframe]);

  if (loading) {
    return <div className="text-qt-accent animate-pulse">Loading chart...</div>;
  }

  return (
    <div className="h-full w-full">
      <h3 className="text-sm text-qt-accent mb-4">
        {symbol} {timeframe}
      </h3>
      
      {data.length > 0 ? (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#00d9ff20" />
            <XAxis stroke="#00d9ff40" />
            <YAxis stroke="#00d9ff40" />
            <Tooltip 
              contentStyle={{
                backgroundColor: '#050814',
                border: '1px solid #00d9ff',
              }}
            />
            <Line 
              type="monotone" 
              dataKey="close" 
              stroke="#00d9ff" 
              dot={false}
              strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="text-qt-accent/50">No data available</div>
      )}
    </div>
  );
}
