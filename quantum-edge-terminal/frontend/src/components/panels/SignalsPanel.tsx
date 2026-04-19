'use client';

import React, { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface SignalsPanelProps {
  symbol: string;
}

export default function SignalsPanel({ symbol }: SignalsPanelProps) {
  const [signals, setSignals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSignals = async () => {
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/signals?status=ACTIVE`
        );
        const result = await response.json();
        setSignals(result.data);
      } catch (error) {
        console.error('Failed to fetch signals:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchSignals();
    const interval = setInterval(fetchSignals, 5000); // Update every 5s

    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <div className="text-qt-accent animate-pulse">Loading signals...</div>;
  }

  return (
    <div>
      <h3 className="text-sm text-qt-accent mb-3 font-bold">ACTIVE SIGNALS</h3>
      <div className="space-y-2">
        {signals.length > 0 ? (
          signals.map((signal) => (
            <div
              key={signal.id}
              className="p-2 border border-qt-accent/30 rounded text-xs hover:bg-qt-accent/5 transition"
            >
              <div className="flex justify-between items-center mb-1">
                <span className="flex items-center gap-1">
                  {signal.signal_type === 'BUY' ? (
                    <TrendingUp size={14} className="text-qt-buy" />
                  ) : (
                    <TrendingDown size={14} className="text-qt-sell" />
                  )}
                  {signal.symbol}
                </span>
                <span
                  className={
                    signal.signal_type === 'BUY' ? 'text-qt-buy' : 'text-qt-sell'
                  }
                >
                  {signal.signal_type}
                </span>
              </div>
              <div className="text-qt-accent/60">
                Entry: ${signal.entry_price.toFixed(2)}
              </div>
              <div className="text-qt-accent/60">
                Conf: {(signal.confidence * 100).toFixed(0)}%
              </div>
            </div>
          ))
        ) : (
          <div className="text-qt-accent/50">No active signals</div>
        )}
      </div>
    </div>
  );
}
