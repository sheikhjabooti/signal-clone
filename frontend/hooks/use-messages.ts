"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import type { History, Message, MessageCache } from "@/lib/types";

const rank = { sent: 0, delivered: 1, read: 2 };
export function mergeMessages(existing: Message[], incoming: Message[]): Message[] {
  const rows = new Map(existing.map(m => [m.id, m]));
  for (const message of incoming) {
    const previous = rows.get(message.id);
    rows.set(message.id, previous ? {
      ...message,
      status: rank[previous.status] > rank[message.status] ? previous.status : message.status,
      delivered_at: message.delivered_at || previous.delivered_at,
      read_at: message.read_at || previous.read_at,
      delivered_count: Math.max(message.delivered_count, previous.delivered_count),
      read_count: Math.max(message.read_count, previous.read_count),
    } : message);
  }
  return [...rows.values()].sort((a, b) => a.id - b.id);
}

export function useMessages(uid: number, cid: number | null) {
  const client = useQueryClient();
  const [loadingOlder, setLoadingOlder] = useState(false);
  const key = ["messages", uid, cid];
  const query = useQuery<MessageCache>({
    queryKey: key,
    enabled: cid !== null,
    queryFn: async ({ signal }) => {
      const existing = client.getQueryData<MessageCache>(key);
      if (!existing?.items.length) {
        const page = await api<History>(`/conversations/${cid}/messages`, { signal });
        return { items: page.messages, through: page.through_id, older: page.next_before_id, hasOlder: page.has_more };
      }
      // Refresh the loaded suffix, not just the latest 50. This repairs receipts,
      // reactions and missed inserts without leaving holes during reconnects.
      // A fixed upper bound makes pagination finish even while messages arrive.
      let after = existing.items[0].id - 1;
      let through: number | undefined;
      let incoming: Message[] = [];
      for (;;) {
        const params = new URLSearchParams({ after_id: String(after), limit: "100" });
        if (through !== undefined) params.set("through_id", String(through));
        const page = await api<History>(`/conversations/${cid}/messages?${params}`, { signal });
        through = page.through_id;
        incoming = mergeMessages(incoming, page.messages);
        if (!page.has_more) break;
        if (page.next_after_id <= after) throw new Error("Message synchronization did not advance.");
        after = page.next_after_id;
      }
      const current = client.getQueryData<MessageCache>(key) || existing;
      return { ...current, items: mergeMessages(current.items, incoming), through: through ?? existing.through };
    },
  });

  async function older() {
    const current = client.getQueryData<MessageCache>(key);
    if (!cid || !current?.hasOlder || !current.older || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const page = await api<History>(`/conversations/${cid}/messages?before_id=${current.older}`);
      // The key includes the account and conversation. A late result cannot land
      // in another account's chat, and logout removes the query altogether.
      if (!client.getQueryData(key)) return;
      client.setQueryData<MessageCache>(key, data => data ? {
        ...data, items: mergeMessages(page.messages, data.items),
        older: page.next_before_id, hasOlder: page.has_more,
      } : data);
    } finally { setLoadingOlder(false); }
  }
  function accept(message: Message) {
    client.setQueryData<MessageCache>(key, data => data ? {
      ...data, items: mergeMessages(data.items, [message]),
      // HTTP success is not evidence that the range before this ID was synced.
    } : data);
  }
  return { ...query, older, loadingOlder, accept };
}
