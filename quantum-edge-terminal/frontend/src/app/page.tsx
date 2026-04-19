'use client';

import React, { useState, useEffect } from 'react';
import { TrendingUp, Settings, Menu } from 'lucide-react';
import ChartPanel from '@/components/panels/ChartPanel';
import SignalsPanel from '@/components/panels/SignalsPanel';
import AlertsPanel from '@/components/panels/AlertsPanel';
import { useWebSocket } from '@/hooks/useWebSocket';

export default function Dashboard() {
  const [selectedSymbol, setSelectedSymbol] = useState('ES');
  const [selectedTimeframe, setSelectedTimeframe] = useState('1h');
  const { isConnected, subscribe } = useWebSocket();

  useEffect(() => {
    if (isConnected) {
      subscribe('candles', {
        symbol: selectedSymbol,
        timeframe: selectedTimeframe,
      });
    }
  }, [selectedSymbol, selectedTimeframe, isConnected, subscribe]);

  return (
    <div className="min-h-screen bg-qt-darker text-white p-4">
      {/* Header */}
      <div className="border-b border-qt-accent/20 pb-4 mb-4 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <TrendingUp className="text-qt-accent" size={24} />
          <h1 className="text-2xl font-bold text-qt-accent">
            QUANTUM EDGE TERMINAL
          </h1>
        </div>
        <div className="flex gap-2">
          <button className="p-2 hover:bg-qt-accent/10 rounded">
            <Menu size={20} />
          </button>
          <button className="p-2 hover:bg-qt-accent/10 rounded">
            <Settings size={20} />
          </button>
        </div>
      </div>

      {/* Symbol Selector */}
      <div className="mb-4 flex gap-2 flex-wrap">
        {['ES', 'NQ', 'GC', 'SPY', 'QQQ'].map((sym) => (
          <button
            key={sym}
            onClick={() => setSelectedSymbol(sym)}
            className={`px-4 py-2 rounded border transition ${
              selectedSymbol === sym
                ? 'border-qt-accent bg-qt-accent/20'
                : 'border-qt-accent/30 hover:border-qt-accent/50'
            }`}
          >
            {sym}
          </button>
        ))}
      </div>

      {/* Timeframe Selector */}
      <div className="mb-6 flex gap-2 flex-wrap">
        {['1m', '5m', '15m', '1h', '4h', '1D'].map((tf) => (
          <button
            key={tf}
            onClick={() => setSelectedTimeframe(tf)}
            className={`px-3 py-1 text-sm rounded border transition ${
              selectedTimeframe === tf
                ? 'border-qt-accent-alt bg-qt-accent-alt/20'
                : 'border-qt-accent-alt/30 hover:border-qt-accent-alt/50'
            }`}
          >
            {tf}
          </button>
        ))}
      </div>

      {/* Main Dashboard Grid */}
      <div className="grid grid-cols-12 gap-4">
        {/* Chart Panel */}
        <div className="col-span-8 bg-qt-dark border border-qt-accent/20 rounded p-4">
          <ChartPanel symbol={selectedSymbol} timeframe={selectedTimeframe} />
        </div>

        {/* Right Sidebar */}
        <div className="col-span-4 flex flex-col gap-4">
          {/* Signals Panel */}
          <div className="flex-1 bg-qt-dark border border-qt-accent/20 rounded p-4 overflow-auto">
            <SignalsPanel symbol={selectedSymbol} />
          </div>

          {/* Alerts Panel */}
          <div className="flex-1 bg-qt-dark border border-qt-accent/20 rounded p-4 overflow-auto">
            <AlertsPanel />
          </div>
        </div>
      </div>

      {/* Connection Status */}
      <div className="fixed bottom-4 right-4 flex items-center gap-2 text-sm">
        <div
          className={`w-2 h-2 rounded-full ${
            isConnected ? 'bg-qt-buy animate-pulse' : 'bg-qt-sell'
          }`}
        />
        <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
      </div>
    </div>
  );
}
