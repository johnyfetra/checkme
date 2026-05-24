/**
 * VideoFeed — MJPEG live stream component.
 *
 * The backend streams MJPEG over GET /api/video.
 * A plain <img> with that URL is the simplest, most compatible approach.
 * No WebRTC, no WebSocket, no canvas — just multipart/x-mixed-replace.
 */

"use client";

import { useState } from "react";

const STREAM_URL =
  process.env.NEXT_PUBLIC_API_URL
    ? `${process.env.NEXT_PUBLIC_API_URL}/api/video`
    : "http://localhost:8000/api/video";

interface Props {
  hasMotion: boolean;
  detectionCount: number;
  isRecording?: boolean;
}

export default function VideoFeed({ hasMotion, detectionCount, isRecording }: Props) {
  const [streamError, setStreamError] = useState(false);

  return (
    <div className="relative w-full aspect-video bg-zinc-900 rounded-xl overflow-hidden border border-zinc-700">
      {streamError ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-zinc-500 gap-2">
          <span className="text-4xl">📷</span>
          <p className="text-sm">Impossible de se connecter au backend.</p>
          <p className="text-xs">Démarrez le serveur Python sur le port 8000.</p>
          <button
            className="mt-2 px-4 py-1.5 text-xs bg-zinc-700 hover:bg-zinc-600 rounded-lg transition-colors"
            onClick={() => setStreamError(false)}
          >
            Réessayer
          </button>
        </div>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={STREAM_URL}
          alt="Flux vidéo en direct"
          className="w-full h-full object-cover"
          onError={() => setStreamError(true)}
        />
      )}

      {/* Top-right: Motion / Detection badge */}
      <div className="absolute top-3 right-3 flex gap-2">
        {hasMotion && (
          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-yellow-500/90 text-black animate-pulse">
            MOUVEMENT
          </span>
        )}
        {detectionCount > 0 && (
          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-red-600/90 text-white">
            {detectionCount} détecté{detectionCount > 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Bottom-left: LIVE badge */}
      {!streamError && (
        <div className="absolute bottom-3 left-3 flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            <span className="text-xs font-bold text-white tracking-widest">LIVE</span>
          </div>
          {isRecording && (
            <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-red-700/80">
              <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
              <span className="text-xs font-bold text-white">REC</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
