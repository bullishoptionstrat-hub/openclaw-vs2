'use client';

import React, { useEffect, useState } from 'react';
import { AlertCircle, Info } from 'lucide-react';

export default function AlertsPanel() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAlerts = async () => {
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/alerts?limit=20`
        );
        const result = await response.json();
        setAlerts(result.data);
      } catch (error) {
        console.error('Failed to fetch alerts:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAlerts();
    const interval = setInterval(fetchAlerts, 3000);

    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <div className="text-qt-accent animate-pulse">Loading alerts...</div>;
  }

  return (
    <div>
      <h3 className="text-sm text-qt-accent mb-3 font-bold">ALERTS</h3>
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {alerts.length > 0 ? (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className={`p-2 border rounded text-xs transition ${
                alert.severity === 'CRITICAL'
                  ? 'border-qt-sell bg-qt-sell/5'
                  : alert.severity === 'HIGH'
                  ? 'border-qt-accent/50 bg-qt-accent/5'
                  : 'border-qt-accent/20'
              }`}
            >
              <div className="flex gap-2">
                {alert.severity === 'CRITICAL' ? (
                  <AlertCircle size={14} className="text-qt-sell flex-shrink-0 mt-0.5" />
                ) : (
                  <Info size={14} className="text-qt-accent flex-shrink-0 mt-0.5" />
                )}
                <div>
                  <div className="text-qt-accent font-mono">
                    [{alert.alert_type}]
                  </div>
                  <div className="text-qt-accent/70">{alert.message}</div>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="text-qt-accent/50">No alerts</div>
        )}
      </div>
    </div>
  );
}
