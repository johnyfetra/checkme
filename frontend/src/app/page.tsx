/**
 * Dashboard principal CheckMe.
 *
 * Layout:
 *   ┌─────────────────────────────────┐
 *   │  Header (titre + StatusBar)     │
 *   ├──────────────────┬──────────────┤
 *   │  VideoFeed       │  AlertList   │
 *   │  (aspect-video)  │  (scrollable)│
 *   └──────────────────┴──────────────┘
 */

"use client";

import { useEvents } from "@/lib/useEvents";
import VideoFeed from "@/components/VideoFeed";
import AlertList from "@/components/AlertList";
import StatusBar from "@/components/StatusBar";

export default function DashboardPage() {
  const { connectionState, deviceInfo, status, alerts, clearAlerts } = useEvents();

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col p-4 gap-4">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">
            Check<span className="text-red-500">Me</span>
          </h1>
          <p className="text-xs text-zinc-500">Surveillance intelligente · YOLOv8 · M1 MPS</p>
        </div>
      </header>

      {/* ── Status bar ──────────────────────────────────────────────────────── */}
      <StatusBar
        connectionState={connectionState}
        deviceInfo={deviceInfo}
        alertsTotal={status?.alerts_total ?? deviceInfo?.alerts_total ?? 0}
      />

      {/* ── Main content ────────────────────────────────────────────────────── */}
      <div className="flex flex-col lg:flex-row gap-4 flex-1">
        {/* Video feed — takes 2/3 of the width on large screens */}
        <div className="lg:flex-[2]">
          <VideoFeed
            hasMotion={status?.motion ?? false}
            detectionCount={status?.detections ?? 0}
          />

          {/* Quick stats below the video */}
          <div className="mt-3 grid grid-cols-3 gap-3">
            <StatCard
              label="Mouvement"
              value={status?.motion ? "OUI" : "NON"}
              accent={status?.motion ? "red" : "zinc"}
            />
            <StatCard label="Détections" value={String(status?.detections ?? 0)} accent="orange" />
            <StatCard label="Alertes session" value={String(alerts.length)} accent="purple" />
          </div>
        </div>

        {/* Alert panel — takes 1/3 on large screens */}
        <div className="lg:flex-[1] lg:max-h-[calc(100vh-220px)] overflow-hidden">
          <AlertList alerts={alerts} onClear={clearAlerts} />
        </div>
      </div>
    </main>
  );
}

// ── Small helper component ────────────────────────────────────────────────────
type Accent = "red" | "orange" | "purple" | "zinc";

const ACCENT_MAP: Record<Accent, string> = {
  red: "text-red-400",
  orange: "text-orange-400",
  purple: "text-purple-400",
  zinc: "text-zinc-400",
};

function StatCard({ label, value, accent }: { label: string; value: string; accent: Accent }) {
  return (
    <div className="rounded-xl bg-zinc-800/60 border border-zinc-700/50 px-4 py-3">
      <p className="text-xs text-zinc-500 mb-0.5">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${ACCENT_MAP[accent]}`}>{value}</p>
    </div>
  );
}
