/**
 * useEvents — WebSocket hook for real-time backend events.
 *
 * Event types emitted by the backend:
 *   connected  → initial handshake with device / model info
 *   alert      → a real detection has passed the debounce threshold
 *   status     → periodic camera / detection stats
 */

"use client";

import { useEffect, useRef, useState, useCallback } from "react";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/events";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const RECONNECT_DELAY_MS = 3000;

export interface AlertEvent {
  id: number;
  timestamp: string;
  class_name: string;
  confidence: number;
  event_type?: string;
  zone_name?: string;
  snapshot: string | null;
}

export interface StatusEvent {
  motion: boolean;
  detections: number;
  events_total: number;
  recording: boolean;
}

export interface ConnectedEvent {
  device: string;
  model: string;
  events_total: number;
}

export type ConnectionState = "connecting" | "open" | "closed";

interface UseEventsReturn {
  connectionState: ConnectionState;
  deviceInfo: ConnectedEvent | null;
  status: StatusEvent | null;
  alerts: AlertEvent[];
  clearAlerts: () => void;
}

export function useEvents(): UseEventsReturn {
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [deviceInfo, setDeviceInfo] = useState<ConnectedEvent | null>(null);
  const [status, setStatus] = useState<StatusEvent | null>(null);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmounted = useRef(false);

  const connect = useCallback(() => {
    if (unmounted.current) return;
    setConnectionState("connecting");

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!unmounted.current) setConnectionState("open");
    };

    ws.onmessage = (e) => {
      if (unmounted.current) return;
      try {
        const msg = JSON.parse(e.data as string) as { type: string; data: unknown };
        if (msg.type === "connected") {
          setDeviceInfo(msg.data as ConnectedEvent);
        } else if (msg.type === "status") {
          setStatus(msg.data as StatusEvent);
        } else if (msg.type === "alert") {
          const alert = msg.data as AlertEvent;
          setAlerts((prev) => [alert, ...prev].slice(0, 50));

          // Browser notification (if permission granted)
          if (typeof window !== "undefined" && Notification.permission === "granted") {
            new Notification(`⚠ CheckMe — ${alert.class_name} detected`, {
              body: `Confidence: ${Math.round(alert.confidence * 100)}%`,
            });
          }
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      if (!unmounted.current) {
        setConnectionState("closed");
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    unmounted.current = false;

    // Request browser notification permission once
    if (typeof window !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission();
    }

    connect();

    // Load persisted events from DB on first mount
    fetch(`${API_URL}/api/events?limit=50`)
      .then((r) => r.json())
      .then((events: AlertEvent[]) => {
        if (!unmounted.current && events.length) {
          setAlerts((prev) =>
            prev.length === 0
              ? events.map((e: Record<string, unknown>) => ({
                  id: e.id as number,
                  timestamp: (e as { timestamp?: string }).timestamp ?? "",
                  class_name: (e as { class_name?: string }).class_name ?? "",
                  confidence: (e as { confidence?: number }).confidence ?? 0,
                  event_type: (e as { event_type?: string }).event_type,
                  zone_name: (e as { zone_name?: string }).zone_name,
                  snapshot: (e as { snapshot_b64?: string }).snapshot_b64 ?? null,
                }))
              : prev,
          );
        }
      })
      .catch(() => {}); // backend may not be running yet

    // Keep-alive ping every 20 s
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send("ping");
      }
    }, 20_000);

    return () => {
      unmounted.current = true;
      clearInterval(pingInterval);
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const clearAlerts = useCallback(() => setAlerts([]), []);

  return { connectionState, deviceInfo, status, alerts, clearAlerts };
}
