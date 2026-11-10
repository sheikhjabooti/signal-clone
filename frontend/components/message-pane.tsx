"use client";
import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowLeft, Check, Copy, CornerUpLeft, Info, LoaderCircle, LockKeyhole, MoreVertical, Phone, Plus, Search, Send, Smile, Video, X } from "lucide-react";
import type { Conversation, Message, MessageCache, PendingMessage, User } from "@/lib/types";
import { api, errorText } from "@/lib/api";
import { dayLabel, lastSeen, time } from "@/lib/format";
import { useMessages } from "@/hooks/use-messages";
import { Avatar, Receipt, Spinner } from "./ui";
import { useToast } from "./providers";

const EMOJI = ["👍", "❤️", "😂", "😮", "😢", "🙏"];

function Highlight({ text, search }: { text: string; search: string }) {
  if (!search) return <>{text}</>;
  const index = text.toLowerCase().indexOf(search.toLowerCase());
  return index < 0 ? <>{text}</> : <>{text.slice(0, index)}<mark>{text.slice(index, index + search.length)}</mark>{text.slice(index + search.length)}</>;
}

export function MessagePane({ conversation, user, draft, onDraft, pending, onSend, onRetry, onDetails, onBack, typingNames, sendTyping, connection }: {
  conversation: Conversation; user: User; draft: string; onDraft: (value: string) => void;
  pending: PendingMessage[]; onSend: (body: string, reply: Message | null) => void;
  onRetry: (message: PendingMessage) => void; onDetails: () => void; onBack: () => void;
  typingNames: string[]; sendTyping: (cid: number, active: boolean) => void; connection: string;
}) {
  const query = useMessages(user.id, conversation.id);
  const client = useQueryClient();
  const toast = useToast();
  const scroll = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const nearBottom = useRef(true);
  const previousLast = useRef(0);
  const loadingEarlier = useRef(false);
  const initialized = useRef(false);
  const readReported = useRef(new Set<number>());
  const [reply, setReply] = useState<Message | null>(null);
  const [menu, setMenu] = useState<number | null>(null);
  const [emojiPicker, setEmojiPicker] = useState(false);
  const [search, setSearch] = useState<string | null>(null);
  const [newCount, setNewCount] = useState(0);
  const messages = query.data?.items || [];
  const pendingVisible = pending.filter(p => !messages.some(m => m.client_message_id === p.client_message_id && m.sender_id === user.id));
  const lastId = messages.at(-1)?.id || 0;

  function bottom(smooth = true) {
    scroll.current?.scrollTo({ top: scroll.current.scrollHeight, behavior: smooth ? "smooth" : "instant" });
    nearBottom.current = true; setNewCount(0);
  }
  useLayoutEffect(() => {
    if (!query.data) return;
    if (!initialized.current || nearBottom.current) { bottom(false); initialized.current = true; }
    else if (lastId > previousLast.current) setNewCount(n => n + 1);
    previousLast.current = lastId;
  }, [lastId, pendingVisible.length, Boolean(query.data)]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (input.current) {
      input.current.style.height = "auto";
      input.current.style.height = `${Math.min(input.current.scrollHeight, 144)}px`;
    }
  }, [draft]);
  useEffect(() => () => sendTyping(conversation.id, false), [conversation.id, sendTyping]);

  // Only visible incoming bubbles in the focused conversation count as read.
  useEffect(() => {
    const root = scroll.current;
    if (!root || !messages.length) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const visible = new Set<number>();
    const candidates = new Set(messages.filter(m => m.sender_id !== user.id && !m.read_at).map(m => m.id));
    async function flush() {
      if (document.visibilityState !== "visible" || !document.hasFocus()) return;
      const ids = [...visible].filter(id => candidates.has(id) && !readReported.current.has(id)).slice(0, 200);
      if (!ids.length) return;
      ids.forEach(id => readReported.current.add(id));
      try {
        await api("/receipts", { method: "POST", body: JSON.stringify({ state: "read", message_ids: ids }) });
        const at = new Date().toISOString();
        client.setQueryData<MessageCache>(["messages", user.id, conversation.id], cache => cache ? {
          ...cache, items: cache.items.map(m => ids.includes(m.id) ? { ...m, read_at: at, delivered_at: m.delivered_at || at } : m),
        } : cache);
        void client.invalidateQueries({ queryKey: ["conversations", user.id] });
      } catch { ids.forEach(id => readReported.current.delete(id)); }
    }
    function schedule() { clearTimeout(timer); timer = setTimeout(() => { void flush(); }, 160); }
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        const id = Number((entry.target as HTMLElement).dataset.messageId);
        if (entry.isIntersecting) visible.add(id); else visible.delete(id);
      }
      schedule();
    }, { root, threshold: 0.15 });
    root.querySelectorAll<HTMLElement>("[data-message-id]").forEach(element => observer.observe(element));
    window.addEventListener("focus", schedule);
    document.addEventListener("visibilitychange", schedule);
    return () => { observer.disconnect(); clearTimeout(timer); window.removeEventListener("focus", schedule); document.removeEventListener("visibilitychange", schedule); };
  }, [messages, user.id, conversation.id, client]);

  async function earlier() {
    if (!scroll.current || loadingEarlier.current || !query.data?.hasOlder) return;
    loadingEarlier.current = true;
    const height = scroll.current.scrollHeight, top = scroll.current.scrollTop;
    try {
      await query.older();
      requestAnimationFrame(() => { if (scroll.current) scroll.current.scrollTop = top + scroll.current.scrollHeight - height; });
    } catch (e) { toast(errorText(e), true); }
    finally { loadingEarlier.current = false; }
  }
  function submit() {
    if (!draft.trim()) return;
    nearBottom.current = true;
    onSend(draft.trim(), reply); onDraft(""); setReply(null); setEmojiPicker(false);
    sendTyping(conversation.id, false); input.current?.focus();
  }
  async function react(mid: number, emoji: string) {
    setMenu(null);
    try {
      await api(`/messages/${mid}/reactions`, { method: "POST", body: JSON.stringify({ emoji }) });
      void client.invalidateQueries({ queryKey: ["messages", user.id, conversation.id] });
    } catch (e) { toast(errorText(e), true); }
  }
  function quote(message: Message) { setReply(message); setMenu(null); input.current?.focus(); }
  const subheading = typingNames.length ? `${typingNames.join(", ")} ${typingNames.length === 1 ? "is" : "are"} typing…` : conversation.kind === "group"
    ? `${conversation.members.length} members` : conversation.peer?.online ? "Online" : lastSeen(conversation.peer?.last_seen || conversation.created_at);

  return <section className="chat-pane" aria-label={`Conversation with ${conversation.name}`}>
    <header className="chat-header">
      <button className="icon-button mobile-back" onClick={onBack} aria-label="Back to chats"><ArrowLeft size={22} /></button>
      <button className="chat-heading" onClick={onDetails} aria-label="Conversation details">
        <Avatar user={conversation.peer} name={conversation.name} group={conversation.kind === "group"} />
        <span><strong>{conversation.name}</strong><small className={typingNames.length ? "typing-label" : ""}>{subheading}</small></span>
      </button>
      <div className="chat-header-actions">
        <button className="icon-button" aria-label="Voice call" title="Voice call" onClick={() => toast("Voice calls are coming soon.")}><Phone size={20} /></button>
        <button className="icon-button" aria-label="Video call" title="Video call" onClick={() => toast("Video calls are coming soon.")}><Video size={23} /></button>
        <span className="header-divider" />
        <button className="icon-button" aria-label="Search loaded messages" onClick={() => setSearch(search === null ? "" : null)}><Search size={20} /></button>
        <button className="icon-button" aria-label="More conversation options" onClick={onDetails}><MoreVertical size={21} /></button>
      </div>
    </header>
    {connection !== "online" && <div className="connection-banner" role="status"><LoaderCircle size={13} className="spin" />{connection === "offline" ? "You're offline. Messages will be here when you're back." : "Reconnecting. Your saved messages are safe."}</div>}
    {search !== null && <div className="message-search"><Search size={17} /><input autoFocus aria-label="Search loaded messages" placeholder="Search loaded messages" value={search} onChange={e => setSearch(e.target.value)} />
      <small>{search ? `${messages.filter(m => m.body.toLowerCase().includes(search.toLowerCase())).length} matches` : "Loaded history only"}</small>
      <button className="icon-button" aria-label="Close message search" onClick={() => setSearch(null)}><X size={17} /></button></div>}
    <div className="message-scroll" ref={scroll} onScroll={() => {
      const element = scroll.current;
      if (!element) return;
      nearBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 100;
      if (nearBottom.current) setNewCount(0);
      if (element.scrollTop < 50 && initialized.current && !nearBottom.current) void earlier();
    }}>
      {query.isPending ? <Spinner label="Loading your conversation" /> : query.isError ? <div className="empty-panel"><Info size={28} /><p>{errorText(query.error)}</p><button className="button secondary" onClick={() => query.refetch()}>Try again</button></div> : <>
        {query.data?.hasOlder ? <button className="load-earlier" disabled={query.loadingOlder} onClick={() => void earlier()}>{query.loadingOlder ? "Loading…" : "Load earlier messages"}</button> :
          <div className="conversation-start"><Avatar user={conversation.peer} name={conversation.name} group={conversation.kind === "group"} size="large" /><h2>{conversation.name}</h2><p>{conversation.kind === "group" ? conversation.members.map(m => m.id === user.id ? "You" : m.display_name.split(" ")[0]).join(", ") : `@${conversation.peer?.username}`}</p></div>}
        <p className="encryption-note"><LockKeyhole size={12} />Assignment demo. End-to-end encryption is not enabled.</p>
        {messages.map((message, index) => {
          const mine = message.sender_id === user.id;
          const day = new Date(message.created_at).toDateString();
          const previousDay = index ? new Date(messages[index - 1].created_at).toDateString() : "";
          const grouped = index > 0 && day === previousDay && messages[index - 1].sender_id === message.sender_id;
          return <Fragment key={message.id}>
            {day !== previousDay && <div className="date-divider"><span>{dayLabel(message.created_at)}</span></div>}
            <div className={`message-row ${mine ? "outgoing" : "incoming"} ${grouped ? "grouped" : ""}`}
              data-message-id={message.id} onContextMenu={event => { event.preventDefault(); setMenu(menu === message.id ? null : message.id); }}>
              {conversation.kind === "group" && !mine && <span className="message-avatar">{!grouped && <Avatar user={message.sender} size="small" />}</span>}
              <div className="bubble-stack">
                <div className={`bubble ${search && message.body.toLowerCase().includes(search.toLowerCase()) ? "search-match" : ""}`}>
                  {conversation.kind === "group" && !mine && !grouped && <span className={`sender-name text-${message.sender.color}`}>{message.sender.display_name}</span>}
                  {message.reply_to_id && <div className="quoted-message"><strong>{message.reply?.sender_name || "Earlier message"}</strong><span>{message.reply?.body || "This message isn't part of your history."}</span></div>}
                  <p className="message-text"><Highlight text={message.body} search={search || ""} /></p>
                  <span className="message-meta" title={mine ? `${message.read_count}/${message.recipient_count} read · ${message.delivered_count}/${message.recipient_count} delivered` : undefined}>
                    <time dateTime={message.created_at}>{time(message.created_at)}</time>{mine && <Receipt status={message.status} />}
                  </span>
                </div>
                {message.reactions.length > 0 && <div className="reaction-list">{message.reactions.map(r => <button key={r.emoji} className={`reaction-chip ${r.mine ? "mine" : ""}`} aria-label={`${r.emoji}: ${r.count} reaction${r.count === 1 ? "" : "s"}`} onClick={() => void react(message.id, r.emoji)}>{r.emoji}{r.count > 1 && <span>{r.count}</span>}</button>)}</div>}
                <div className="message-tools">
                  <button aria-label="Reply to message" title="Reply" onClick={() => quote(message)}><CornerUpLeft size={16} /></button>
                  <button aria-label="React to message" title="React" onClick={() => setMenu(menu === message.id ? null : message.id)}><Smile size={16} /></button>
                </div>
                {menu === message.id && <div className="message-popover"><div className="emoji-options">{EMOJI.map(emoji => <button key={emoji} aria-label={`React ${emoji}`} onClick={() => void react(message.id, emoji)}>{emoji}</button>)}</div>
                  <button className="menu-action" onClick={() => quote(message)}><CornerUpLeft size={16} />Reply</button>
                  <button className="menu-action" onClick={async () => { try { await navigator.clipboard.writeText(message.body); toast("Message copied."); } catch { toast("Your browser couldn't copy that message.", true); } setMenu(null); }}><Copy size={16} />Copy text</button>
                  <button className="menu-action" onClick={() => setMenu(null)}><Check size={16} />Done</button>
                </div>}
              </div>
            </div>
          </Fragment>;
        })}
        {pendingVisible.map(message => <div className="message-row outgoing" key={message.client_message_id}><div className="bubble-stack"><div className={`bubble pending-bubble ${message.state === "failed" ? "failed" : ""}`}>
          {message.reply && <div className="quoted-message"><strong>{message.reply.sender.display_name}</strong><span>{message.reply.body}</span></div>}
          <p className="message-text">{message.body}</p><span className="message-meta"><time>{time(message.created_at)}</time><Receipt pending={message.state === "sending"} status="sent" /></span>
        </div>{message.state === "failed" && <button className="retry-message" onClick={() => onRetry(message)} title={message.error}>Not confirmed. Tap to retry.</button>}</div></div>)}
        {typingNames.length > 0 && <div className="typing-bubble" aria-label="Someone is typing"><i /><i /><i /></div>}
        {!messages.length && <p className="first-message-hint">Say hello to start the conversation.</p>}
      </>}
    </div>
    {newCount > 0 && <button className="new-messages" onClick={() => bottom()}><ArrowDown size={16} />New messages</button>}
    <footer className="composer-area">
      {reply && <div className="reply-preview"><CornerUpLeft size={19} /><div><strong>Replying to {reply.sender_id === user.id ? "yourself" : reply.sender.display_name}</strong><span>{reply.body}</span></div><button className="icon-button" aria-label="Cancel reply" onClick={() => setReply(null)}><X size={18} /></button></div>}
      <div className="composer">
        <button className="icon-button composer-extra" aria-label="Add attachment" onClick={() => toast("File attachments are not included in this demo.")}><Plus size={24} /></button>
        <div className="composer-field"><textarea ref={input} aria-label="Message" placeholder={`Message ${conversation.kind === "group" ? conversation.name : conversation.name.split(" ")[0]}`}
          rows={1} maxLength={4000} value={draft} onChange={e => { onDraft(e.target.value); sendTyping(conversation.id, Boolean(e.target.value.trim())); }}
          onBlur={() => sendTyping(conversation.id, false)} onKeyDown={e => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); }
            if (e.key === "Escape") { setReply(null); setEmojiPicker(false); setMenu(null); }
          }} />
          <button className="icon-button" aria-label="Add emoji" onClick={() => setEmojiPicker(!emojiPicker)}><Smile size={23} /></button>
          {emojiPicker && <div className="composer-emoji">{[...EMOJI, "😊", "🎉", "☀️", "👋", "🤝", "✨"].map(emoji => <button key={emoji} aria-label={`Insert ${emoji}`} onClick={() => { onDraft(draft + emoji); input.current?.focus(); }}>{emoji}</button>)}</div>}
        </div>
        <button className="send-button" aria-label="Send message" disabled={!draft.trim()} onClick={submit}><Send size={21} /></button>
      </div><div className="composer-caption"><span>Enter to send · Shift + Enter for a new line</span><span>{draft.length > 3600 ? `${draft.length}/4000` : ""}</span></div>
    </footer>
  </section>;
}
