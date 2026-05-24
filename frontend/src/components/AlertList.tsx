/**
 * AlertList — Real-time alert history panel.
 * Alerts arrive via WebSocket and show the class, confidence, time, and
 * an optional snapshot thumbnail.
 */

"use client";

import type { AlertEvent } from "@/lib/useEvents";

const CLASS_COLORS: Record<string, string> = {
  person: "bg-red-600",
  car: "bg-orange-500",
  motorcycle: "bg-pink-500",
  bus: "bg-cyan-500",
  truck: "bg-purple-500",
};

interface Props {
  alerts: AlertEvent[];
  onClear: () => void;
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function AlertList({ alerts, onClear }: Props) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
          Alertes
          {alerts.length > 0 && (
            <span className="ml-2 px-1.5 py-0.5 text-xs rounded-full bg-red-600 text-white">
              {alerts.length}
            </span>
          )}
        </h2>
        {alerts.length > 0 && (
          <button
            onClick={onClear}
            className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            Effacer
          </button>
        )}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-zinc-600 gap-1">
            <span className="text-2xl">🛡️</span>
            <p className="text-xs">Aucune alerte pour l'instant</p>
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className="flex gap-3 p-2.5 rounded-lg bg-zinc-800/60 border border-zinc-700/50 hover:border-zinc-600 transition-colors"
            >
              {/* Thumbnail */}
              {alert.snapshot ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`data:image/jpeg;base64,${alert.snapshot}`}
                  alt="snapshot"
                  className="w-16 h-12 object-cover rounded flex-shrink-0"
                />
              ) : (
                <div className="w-16 h-12 bg-zinc-700 rounded flex-shrink-0 flex items-center justify-center text-zinc-500 text-xs">
                  N/A
                </div>
              )}

              {/* Info */}
              <div className="flex flex-col justify-between min-w-0">
                <div className="flex items-center gap-1.5">
                  <span
                    className={`px-1.5 py-0.5 text-xs font-semibold rounded text-white ${
                      CLASS_COLORS[alert.class_name] ?? "bg-zinc-600"
                    }`}
                  >
                    {alert.class_name}
                  </span>
                  <span className="text-xs text-zinc-400">
                    {Math.round(alert.confidence * 100)}%
                  </span>
                </div>
                <span className="text-xs text-zinc-500 tabular-nums">
                  {formatTime(alert.timestamp)}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
