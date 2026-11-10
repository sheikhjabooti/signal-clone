"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleDashed, MessageCircle, Moon, PencilLine, Phone, Plus, Search, Settings, Users, X } from "lucide-react";
import { api, ApiError, errorText, setSession } from "@/lib/api";
import { listTime } from "@/lib/format";
import type { Conversation, LiveEvent, Message, MessageCache, PendingMessage, Session, User } from "@/lib/types";
import { mergeMessages } from "@/hooks/use-messages";
import { useRealtime } from "@/hooks/use-realtime";
import { Auth } from "./auth";
import { Avatar, Receipt, SignalMark, Spinner } from "./ui";
import { useTheme, useToast } from "./providers";
import { MessagePane } from "./message-pane";
import { ComposeDialog, ContactDialog, DetailsDialog, GroupDialog, SettingsDialog } from "./dialogs";

export function Application() {
  const client = useQueryClient();
  const toast = useToast();
  const session = useQuery<Session | null>({ queryKey: ["session"], retry: false,
    queryFn: async ({ signal }) => {
      try { const result = await api<Session>("/me", { signal }); setSession(result); return result; }
      catch (e) { if (e instanceof ApiError && e.status === 401) { setSession(null); return null; } throw e; }
    },
  });
  const clearSession = useCallback(async () => {
    setSession(null);
    await client.cancelQueries();
    client.removeQueries({ predicate: query => query.queryKey[0] !== "session" });
    client.setQueryData(["session"], null);
    window.history.replaceState(null, "", "/");
  }, [client]);
  useEffect(() => {
    const expired = () => { toast("Your session ended. Please sign in again.", true); void clearSession(); };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, [clearSession, toast]);
  async function signOut() {
    try { await api("/auth/logout", { method: "POST" }); await clearSession(); }
    catch (e) { toast(errorText(e), true); }
  }
  async function login(result: Session) {
    await client.cancelQueries();
    client.removeQueries({ predicate: query => query.queryKey[0] !== "session" });
    setSession(result);
    client.setQueryData(["session"], result);
  }
  if (session.isPending) return <div className="app-loading"><SignalMark large /><Spinner label="Opening your conversations" /></div>;
  if (session.isError) return <div className="app-loading"><SignalMark large /><h2>Could not reach the server</h2><p className="muted">{errorText(session.error)}</p><button className="button primary" onClick={() => session.refetch()}>Try again</button></div>;
  return session.data ? <ChatApp key={session.data.user.id} session={session.data} onLogout={() => void signOut()} /> : <Auth onLogin={result => { void login(result); }} />;
}

type ModalName = "compose" | "group" | "contact" | "details" | "settings" | null;
function ChatApp({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const { user } = session;
  const client = useQueryClient(), toast = useToast();
  const { theme, setTheme } = useTheme();
  const [selected, setSelected] = useState<number | null>(null);
  const [modal, setModal] = useState<ModalName>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("All");
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [pending, setPending] = useState<PendingMessage[]>([]);
  const [typists, setTypists] = useState<Record<string, number>>({});
  const initialized = useRef(false);
  const searchInput = useRef<HTMLInputElement>(null);
  const conversations = useQuery({ queryKey: ["conversations", user.id], queryFn: ({ signal }) => api<Conversation[]>("/conversations", { signal }) });
  const contacts = useQuery({ queryKey: ["contacts", user.id], queryFn: ({ signal }) => api<User[]>("/contacts", { signal }) });
  const rows = conversations.data || [];
  const current = rows.find(c => c.id === selected) || null;

  function choose(id: number | null) {
    setSelected(id);
    window.history.replaceState(null, "", id ? `/chat/?conversation=${id}` : "/chat/");
  }
  useEffect(() => {
    if (!conversations.data || initialized.current) return;
    initialized.current = true;
    const requested = Number(new URLSearchParams(window.location.search).get("conversation"));
    if (requested && conversations.data.some(c => c.id === requested)) choose(requested);
    else if (window.innerWidth >= 760 && conversations.data.length) choose(conversations.data[0].id);
  }, [conversations.data]);
  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); searchInput.current?.focus(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") { event.preventDefault(); setModal("compose"); }
    }
    window.addEventListener("keydown", shortcut);
    const timer = setInterval(() => setTypists(old => {
      const active = Object.fromEntries(Object.entries(old).filter(([, until]) => until > Date.now()));
      return Object.keys(active).length === Object.keys(old).length ? old : active;
    }), 1000);
    return () => { window.removeEventListener("keydown", shortcut); clearInterval(timer); };
  }, []);

  function liveEvent(event: LiveEvent) {
    if (event.type === "typing" && event.conversation_id && event.user_id) {
      const key = `${event.conversation_id}:${event.user_id}`;
      setTypists(old => ({ ...old, [key]: event.active ? Date.now() + (event.ttl_ms || 5000) : 0 }));
    }
    if (event.type === "membership.changed" && event.removed && event.user_id === user.id) {
      client.removeQueries({ queryKey: ["messages", user.id, event.conversation_id] });
      setPending(old => old.filter(p => p.conversation_id !== event.conversation_id));
      setDrafts(old => { const next = { ...old }; delete next[event.conversation_id!]; return next; });
      if (selected === event.conversation_id) { choose(null); setModal(null); toast("You were removed from this group."); }
    }
    if (event.type === "message.new" && event.sender_id !== user.id) {
      const outside = event.conversation_id !== selected || document.visibilityState !== "visible";
      if (!outside) return;
      const conversation = rows.find(c => c.id === event.conversation_id);
      if (conversation) toast(`New message in ${conversation.name}.`);
      try {
        if (outside && localStorage.getItem("signal-notifications") === "true" && "Notification" in window && Notification.permission === "granted") {
          const notice = new Notification(conversation?.name || "New message", { body: "Open the app to read it.", tag: `conversation-${event.conversation_id}` });
          notice.onclick = () => { window.focus(); if (event.conversation_id) choose(event.conversation_id); notice.close(); };
        }
      } catch { /* In-app notifications still work without browser permission. */ }
    }
  }
  const live = useRealtime(user.id, liveEvent);
  const typingNames = current?.members.filter(m => m.id !== user.id && (typists[`${current.id}:${m.id}`] || 0) > Date.now()).map(m => m.display_name.split(" ")[0]) || [];

  async function start(id: number) {
    const conversation = await api<Conversation>("/conversations/direct", { method: "POST", body: JSON.stringify({ user_id: id }) });
    client.setQueryData<Conversation[]>(["conversations", user.id], old => [...(old || []).filter(c => c.id !== conversation.id), conversation]);
    choose(conversation.id); setModal(null); setSearch("");
    void client.invalidateQueries({ queryKey: ["conversations", user.id] });
  }
  async function transmit(item: PendingMessage) {
    setPending(old => old.map(p => p.client_message_id === item.client_message_id ? { ...p, state: "sending" } : p));
    try {
      const message = await api<Message>(`/conversations/${item.conversation_id}/messages`, { method: "POST", body: JSON.stringify({
        body: item.body, client_message_id: item.client_message_id, reply_to_id: item.reply?.id || null,
      }) });
      client.setQueryData<MessageCache>(["messages", user.id, item.conversation_id], cache => cache ? {
        ...cache, items: mergeMessages(cache.items, [message]),
      } : cache);
      setPending(old => old.filter(p => p.client_message_id !== item.client_message_id));
      void client.invalidateQueries({ queryKey: ["conversations", user.id] });
      void client.invalidateQueries({ queryKey: ["messages", user.id, item.conversation_id] });
    } catch (e) {
      setPending(old => old.map(p => p.client_message_id === item.client_message_id ? { ...p, state: "failed", error: errorText(e) } : p));
      toast(errorText(e), true);
    }
  }
  function send(body: string, reply: Message | null) {
    if (!current) return;
    const item: PendingMessage = { client_message_id: crypto.randomUUID(), conversation_id: current.id,
      body, reply, created_at: new Date().toISOString(), state: "sending" };
    setPending(old => [...old, item]); void transmit(item);
  }
  const filtered = rows.filter(c => {
    const matches = !search || c.name.toLowerCase().includes(search.toLowerCase()) || c.members.some(m => m.username.includes(search.toLowerCase()));
    return matches && (filter !== "Unread" || c.unread_count > 0) && (filter !== "Groups" || c.kind === "group");
  });
  const matchedContacts = search ? (contacts.data || []).filter(person =>
    (person.display_name.toLowerCase().includes(search.toLowerCase()) || person.username.includes(search.toLowerCase())) &&
    !filtered.some(c => c.kind === "direct" && c.peer?.id === person.id)) : [];
  const unread = rows.reduce((sum, c) => sum + c.unread_count, 0);

  return <main className={`workspace ${current ? "has-selection" : ""}`}>
    <nav className="app-rail" aria-label="Main navigation">
      <div className="rail-brand" title="Signal assignment demo"><SignalMark /></div>
      <button className="rail-button active" title="Chats" aria-label="Chats" onClick={() => { setFilter("All"); setSearch(""); }}><MessageCircle size={24} />{unread > 0 && <span className="rail-dot" />}</button>
      <button className="rail-button" title="Calls" aria-label="Calls" onClick={() => toast("Calls are coming soon.")}><Phone size={23} /></button>
      <button className="rail-button" title="Stories" aria-label="Stories" onClick={() => toast("Stories are coming soon.")}><CircleDashed size={25} /></button>
      <span className="rail-spacer" />
      <button className="rail-button theme-toggle" title="Toggle dark mode" aria-label="Toggle dark mode" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}><Moon size={22} /></button>
      <button className="rail-button" title="Settings" aria-label="Settings" onClick={() => setModal("settings")}><Settings size={23} /></button>
      <button className="rail-profile" title="Your profile" aria-label="Your profile" onClick={() => setModal("settings")}><Avatar user={user} size="small" /></button>
    </nav>
    <aside className="sidebar" aria-label="Conversation list">
      <header className="sidebar-heading"><h1>Chats</h1><div><button className="icon-button" title="New group" aria-label="New group" onClick={() => setModal("group")}><Users size={21} /></button><button className="icon-button" title="New message" aria-label="New message" onClick={() => setModal("compose")}><PencilLine size={22} /></button></div></header>
      <div className="sidebar-search search-box"><Search size={17} /><input ref={searchInput} aria-label="Search conversations and contacts" placeholder="Search" value={search} onChange={e => setSearch(e.target.value)} />{search ? <button aria-label="Clear search" onClick={() => setSearch("")}><X size={15} /></button> : <kbd>⌘ K</kbd>}</div>
      <div className="chat-filters" role="group" aria-label="Filter conversations">{["All", "Unread", "Groups"].map(value => <button className={filter === value ? "selected" : ""} key={value} onClick={() => setFilter(value)} aria-pressed={filter === value}>{value}{value === "Unread" && unread > 0 && <span>{unread}</span>}</button>)}</div>
      <div className="conversation-list">
        {conversations.isPending && <Spinner label="Loading chats" />}
        {conversations.isError && <div className="empty-copy"><p>{errorText(conversations.error)}</p><button className="text-button" onClick={() => conversations.refetch()}>Try again</button></div>}
        {filtered.map(conversation => {
          const last = conversation.last_message;
          const own = last?.sender_id === user.id;
          const typing = conversation.members.some(m => m.id !== user.id && (typists[`${conversation.id}:${m.id}`] || 0) > Date.now());
          return <button key={conversation.id} className={`conversation-row ${selected === conversation.id ? "selected" : ""} ${conversation.unread_count ? "unread" : ""}`}
            aria-label={`Open ${conversation.name}`} aria-current={selected === conversation.id ? "true" : undefined} onClick={() => choose(conversation.id)}>
            <span className="list-avatar"><Avatar user={conversation.peer} name={conversation.name} group={conversation.kind === "group"} />{conversation.peer?.online && <span className="online-dot" />}</span>
            <span className="conversation-copy"><span className="conversation-top"><strong>{conversation.name}</strong><time>{listTime(conversation.updated_at)}</time></span>
              <span className="conversation-preview"><span className={typing ? "typing-label" : ""}>{typing ? "Typing…" : <>{own && <Receipt status={last?.status} />}{last ? `${conversation.kind === "group" ? own ? "You: " : `${last.sender.display_name.split(" ")[0]}: ` : ""}${last.body}` : "No messages yet"}</>}</span>
                {conversation.unread_count > 0 && <b className="unread-badge">{conversation.unread_count > 99 ? "99+" : conversation.unread_count}</b>}
              </span></span>
          </button>;
        })}
        {!conversations.isPending && !conversations.isError && !filtered.length && <div className="empty-list"><MessageCircle size={28} /><strong>{search ? "No matching chats" : filter === "Unread" ? "You're all caught up" : "A little quiet here"}</strong><p>{search ? "Try another name, or start a new message." : filter === "Unread" ? "New messages will appear here." : "Start a conversation with someone you know."}</p><button className="text-button" onClick={() => setModal("compose")}><Plus size={15} />New message</button></div>}
        {matchedContacts.length > 0 && <><p className="section-caption contact-results">Contacts</p>{matchedContacts.map(person => <button className="person-row" key={person.id} onClick={() => void start(person.id).catch(e => toast(errorText(e), true))}><Avatar user={person} /><span><strong>{person.display_name}</strong><small>@{person.username}</small></span></button>)}</>}
      </div>
      <footer className="sidebar-footer"><span className={`connection-dot ${live.status === "online" ? "online" : ""}`} /><span>{live.status === "online" ? "Connected" : live.status === "offline" ? "Offline" : "Connecting…"}</span><span className="footer-demo">Demo · @{user.username}</span></footer>
    </aside>
    {current ? <MessagePane key={current.id} conversation={current} user={user} draft={drafts[current.id] || ""}
      onDraft={value => setDrafts(old => ({ ...old, [current.id]: value }))}
      pending={pending.filter(p => p.conversation_id === current.id)} onSend={send} onRetry={item => { void transmit(item); }}
      onDetails={() => setModal("details")} onBack={() => choose(null)} typingNames={typingNames} sendTyping={live.typing} connection={live.status} /> :
      <section className="welcome-pane"><div className="welcome-symbol"><SignalMark large /></div><h2>A space for your conversations.</h2><p>Pick a chat, or start something new.</p><button className="button primary" onClick={() => setModal("compose")}><PencilLine size={18} />New message</button><small>Signal-style assignment · No end-to-end encryption</small></section>}
    {modal === "compose" && <ComposeDialog contacts={contacts.data || []} onClose={() => setModal(null)} onGroup={() => setModal("group")} onContact={() => setModal("contact")} onStart={start} />}
    {modal === "contact" && <ContactDialog onClose={() => setModal(null)} onAdded={() => { void client.invalidateQueries({ queryKey: ["contacts", user.id] }); setModal("compose"); }} />}
    {modal === "group" && <GroupDialog contacts={contacts.data || []} onClose={() => setModal(null)} onCreated={conversation => {
      client.setQueryData<Conversation[]>(["conversations", user.id], old => [conversation, ...(old || [])]);
      choose(conversation.id); setModal(null); void client.invalidateQueries({ queryKey: ["conversations", user.id] }); toast("Group created.");
    }} />}
    {modal === "details" && current && <DetailsDialog conversation={current} user={user} contacts={contacts.data || []} onClose={() => setModal(null)} onChanged={() => { void client.invalidateQueries({ queryKey: ["conversations", user.id] }); }} />}
    {modal === "settings" && <SettingsDialog session={session} onClose={() => setModal(null)} onLogout={onLogout} />}
  </main>;
}
