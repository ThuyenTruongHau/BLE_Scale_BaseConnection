import { useEffect } from "react";
import type { BleDevice } from "./types";

export interface WeightReading {
  address?: string;
  kg?: number | null;
  stable?: boolean;
  source?: string;
  raw_hex?: string;
  char_uuid?: string;
  profile?: string;
}

export type BleWsPayload =
  | { type: "device"; device: BleDevice }
  | {
      type: "status";
      scanning?: boolean;
      devices?: BleDevice[];
      scale_connected?: boolean;
      scale_address?: string | null;
      last_reading?: WeightReading | null;
    }
  | {
      type: "weight";
      address?: string;
      kg?: number;
      stable?: boolean;
      source?: string;
      raw_hex?: string;
      char_uuid?: string;
    }
  | { type: "scale_disconnected"; address?: string | null };

const WS_URL = import.meta.env.DEV
  ? "ws://127.0.0.1:8000/ws"
  : `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`;

const DISCONNECT_DELAY_MS = 200;

let socket: WebSocket | null = null;
let refCount = 0;
let reconnectTimer: number | undefined;
let disconnectTimer: number | undefined;
const listeners = new Set<(payload: BleWsPayload) => void>();
const statusListeners = new Set<(connected: boolean) => void>();

function notifyConnected(connected: boolean) {
  statusListeners.forEach((listener) => listener(connected));
}

function dispatch(payload: BleWsPayload) {
  listeners.forEach((listener) => listener(payload));
}

function scheduleReconnect() {
  if (reconnectTimer !== undefined || refCount === 0) return;
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = undefined;
    if (refCount > 0) connectSocket();
  }, 1500);
}

function connectSocket() {
  if (
    socket &&
    (socket.readyState === WebSocket.OPEN ||
      socket.readyState === WebSocket.CONNECTING)
  ) {
    return;
  }

  window.clearTimeout(disconnectTimer);
  disconnectTimer = undefined;

  socket = new WebSocket(WS_URL);

  socket.addEventListener("open", () => {
    notifyConnected(true);
  });

  socket.addEventListener("message", (event) => {
    try {
      dispatch(JSON.parse(event.data) as BleWsPayload);
    } catch {
      // ignore malformed payloads
    }
  });

  socket.addEventListener("close", () => {
    notifyConnected(false);
    socket = null;
    scheduleReconnect();
  });

  socket.addEventListener("error", () => {
    notifyConnected(false);
  });
}

function retainSocket() {
  refCount += 1;
  window.clearTimeout(disconnectTimer);
  disconnectTimer = undefined;
  window.clearTimeout(reconnectTimer);
  reconnectTimer = undefined;
  connectSocket();
}

function releaseSocket() {
  refCount = Math.max(0, refCount - 1);
  if (refCount > 0) return;

  window.clearTimeout(disconnectTimer);
  disconnectTimer = window.setTimeout(() => {
    disconnectTimer = undefined;
    if (refCount > 0) return;
    window.clearTimeout(reconnectTimer);
    reconnectTimer = undefined;
    if (!socket) return;
    const current = socket;
    socket = null;
    if (
      current.readyState === WebSocket.OPEN ||
      current.readyState === WebSocket.CONNECTING
    ) {
      current.close(1000, "client idle");
    }
  }, DISCONNECT_DELAY_MS);
}

export function useBleWebSocket(
  onMessage: (payload: BleWsPayload) => void,
  onConnectionChange?: (connected: boolean) => void
) {
  useEffect(() => {
    listeners.add(onMessage);
    if (onConnectionChange) statusListeners.add(onConnectionChange);
    retainSocket();

    return () => {
      listeners.delete(onMessage);
      if (onConnectionChange) statusListeners.delete(onConnectionChange);
      releaseSocket();
    };
  }, [onMessage, onConnectionChange]);
}
