/**
 * StatusBar — Shows backend connection state and AI device info.
 */

"use client";

import type { ConnectionState, ConnectedEvent } from "@/lib/useEvents";

interface Props {
  connectionState: ConnectionState;
  deviceInfo: ConnectedEvent | null;
  alertsTotal: number;
}

const STATE_STYLES: Record<ConnectionState, { dot: string; label: string }> = {
  connecting: { dot: "bg-yellow-400 animate-pulse", label: "Connexion…" },
  open: { dot: "bg-green-400", label: "Connecté" },
  closed: { dot: "bg-red-500 animate-pulse", label: "Déconnecté — reconnexion…" },
};

export default function StatusBar({ connectionState, deviceInfo, alertsTotal }: Props) {
  const { dot, label } = STATE_STYLES[connectionState];

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 rounded-xl bg-zinc-800/60 border border-zinc-700/50 text-xs text-zinc-400">
      {/* Connection */}
      <div className="flex items-center gap-1.5">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${dot}`} />
        <span>{label}</span>
      </div>

      {/* Device */}
      {deviceInfo && (
        <>
          <div className="flex items-center gap-1.5">
            <span className="text-zinc-600">Device</span>
            <span
              className={`font-semibold ${
                deviceInfo.device === "mps"
                  ? "text-green-400"
                  : deviceInfo.device === "cuda"
                  ? "text-blue-400"
                  : "text-zinc-300"
              }`}
            >
              {deviceInfo.device.toUpperCase()}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-zinc-600">Modèle</span>
            <span className="font-medium text-zinc-300">{deviceInfo.model}</span>
          </div>
        </>
      )}

      {/* Total alerts */}
      <div className="flex items-center gap-1.5 ml-auto">
        <span className="text-zinc-600">Alertes totales</span>
        <span className="font-semibold text-white">{alertsTotal}</span>
      </div>
    </div>
  );
}
