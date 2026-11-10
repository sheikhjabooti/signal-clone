"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, socketUrl } from "@/lib/api";
import type { LiveEvent, Message } from "@/lib/types";

export function useRealtime(uid: number, onEvent: (event: LiveEvent) => void) {
  const client = useQueryClient();
  const callback = useRef(onEvent); callback.current = onEvent;
  const socket = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<"connecting" | "online" | "reconnecting" | "offline">("connecting");
  const lastTyping = useRef({ cid: 0, tick: 0 });

  useEffect(() => {
    let stopped = false, attempts = 0, lastPong = Date.now();
    let retry: ReturnType<typeof setTimeout> | undefined;
    let debounce: ReturnType<typeof setTimeout> | undefined;
    let draining = false, refreshing = false, dirty = false;
    const abort = new AbortController();

    async function drain() {
      if (draining || stopped) return;
      draining = true;
      try {
        while (!stopped) {
          const messages = await api<Message[]>("/deliveries", { signal: abort.signal });
          if (!messages.length) break;
          // Acknowledge actual message payloads, never sidebar previews.
          await api("/receipts", { method: "POST", body: JSON.stringify({ state: "delivered", message_ids: messages.map(m => m.id) }), signal: abort.signal });
          if (messages.length < 100) break;
        }
      } catch { /* A reconnect or foreground refresh will retry. */ }
      finally { draining = false; }
    }

    async function refresh() {
      dirty = true;
      if (refreshing || stopped) return;
      refreshing = true;
      try {
        while (dirty && !stopped) {
          dirty = false;
          // Cancel an initial fetch too. Otherwise a change between its snapshot
          // and socket registration can be hidden by query deduplication.
          await client.cancelQueries({ queryKey: ["messages", uid], type: "active" });
          await Promise.all([
            client.invalidateQueries({ queryKey: ["conversations", uid] }),
            client.invalidateQueries({ queryKey: ["messages", uid], refetchType: "active" }),
          ]);
        }
        await drain();
      } finally { refreshing = false; }
    }
    function schedule() {
      if (stopped) return;
      dirty = true;
      clearTimeout(debounce);
      debounce = setTimeout(() => { void refresh(); }, 90);
    }
    function connect() {
      if (stopped || !navigator.onLine) { setStatus("offline"); return; }
      setStatus(attempts ? "reconnecting" : "connecting");
      const ws = new WebSocket(socketUrl());
      socket.current = ws;
      ws.onmessage = ({ data }) => {
        if (stopped || socket.current !== ws) return;
        let event: LiveEvent;
        try { event = JSON.parse(data); } catch { return; }
        if (event.type === "pong") { lastPong = Date.now(); return; }
        if (event.type === "ready") { attempts = 0; lastPong = Date.now(); setStatus("online"); schedule(); return; }
        callback.current(event);
        if (event.type !== "typing") schedule();
      };
      ws.onclose = event => {
        if (stopped || socket.current !== ws) return;
        socket.current = null;
        if (event.code === 4401) { window.dispatchEvent(new Event("session-expired")); return; }
        setStatus(navigator.onLine ? "reconnecting" : "offline");
        const delay = Math.min(30000, 700 * 2 ** Math.min(attempts++, 6)) + Math.random() * 300;
        retry = setTimeout(connect, delay);
      };
      ws.onerror = () => ws.close();
    }
    const foreground = () => { if (document.visibilityState === "visible") schedule(); };
    const online = () => { clearTimeout(retry); if (!socket.current || socket.current.readyState > 1) connect(); schedule(); };
    const offline = () => { setStatus("offline"); socket.current?.close(); };
    const heartbeat = setInterval(() => {
      if (socket.current?.readyState === WebSocket.OPEN) {
        if (Date.now() - lastPong > 65000) socket.current.close();
        else socket.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 20000);
    const repair = setInterval(foreground, 30000);
    window.addEventListener("focus", foreground);
    window.addEventListener("online", online);
    window.addEventListener("offline", offline);
    document.addEventListener("visibilitychange", foreground);
    connect();
    return () => {
      stopped = true; abort.abort(); clearTimeout(retry); clearTimeout(debounce);
      clearInterval(heartbeat); clearInterval(repair);
      window.removeEventListener("focus", foreground);
      window.removeEventListener("online", online);
      window.removeEventListener("offline", offline);
      document.removeEventListener("visibilitychange", foreground);
      socket.current?.close(); socket.current = null;
    };
  }, [client, uid]);

  const typing = useCallback((cid: number, active: boolean) => {
    const ws = socket.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (active && lastTyping.current.cid === cid && Date.now() - lastTyping.current.tick < 1800) return;
    lastTyping.current = { cid, tick: Date.now() };
    ws.send(JSON.stringify({ type: "typing", conversation_id: cid, active }));
  }, []);
  return { status, typing };
}
