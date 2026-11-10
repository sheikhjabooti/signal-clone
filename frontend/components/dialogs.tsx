"use client";
import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Bell, Camera, Check, ChevronRight, Laptop, LoaderCircle, LockKeyhole, LogOut, Moon, Plus, Search, Shield, Sun, UserPlus, Users, X } from "lucide-react";
import type { Conversation, Session, User } from "@/lib/types";
import { api, errorText } from "@/lib/api";
import { Avatar, Modal } from "./ui";
import { useTheme, useToast } from "./providers";

function usePeople(contacts: User[], query: string) {
  const [debounced, setDebounced] = useState(query);
  useEffect(() => { const t = setTimeout(() => setDebounced(query), 220); return () => clearTimeout(t); }, [query]);
  const remote = useQuery({ queryKey: ["people-search", debounced], enabled: debounced.trim().length >= 2,
    queryFn: ({ signal }) => api<User[]>(`/users?q=${encodeURIComponent(debounced)}`, { signal }) });
  const q = query.toLowerCase();
  const people = new Map(contacts.filter(p => p.display_name.toLowerCase().includes(q) || p.username.includes(q)).map(p => [p.id, p]));
  if (debounced === query) remote.data?.forEach(p => people.set(p.id, p));
  return { people: [...people.values()], searching: remote.isFetching, error: remote.error };
}

export function ComposeDialog({ contacts, onClose, onGroup, onContact, onStart }: {
  contacts: User[]; onClose: () => void; onGroup: () => void; onContact: () => void; onStart: (id: number) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const { people, searching } = usePeople(contacts, query);
  const toast = useToast();
  return <Modal title="New message" onClose={onClose}>
    <div className="modal-body"><div className="search-box"><Search size={18} /><input autoFocus aria-label="Find a person" placeholder="Search by name or username" value={query} onChange={e => setQuery(e.target.value)} />{searching && <LoaderCircle size={16} className="spin" />}</div>
      <div className="compose-actions"><button onClick={onGroup}><span className="action-avatar"><Users size={21} /></span>New group<ChevronRight size={17} /></button><button onClick={onContact}><span className="action-avatar"><UserPlus size={21} /></span>Add a contact<ChevronRight size={17} /></button></div>
      <p className="section-caption">{query ? "People" : "Your contacts"}</p>
      <div className="people-list">{people.map(person => <button className="person-row" key={person.id} disabled={busy !== null} onClick={async () => {
        setBusy(person.id); try { await onStart(person.id); } catch (e) { toast(errorText(e), true); } finally { setBusy(null); }
      }}><Avatar user={person} /><span><strong>{person.display_name}</strong><small>@{person.username}</small></span>{busy === person.id ? <LoaderCircle size={18} className="spin" /> : <ArrowRight size={17} />}</button>)}</div>
      {!people.length && <p className="empty-copy">{query ? "No one found. Try their exact username." : "Search for a username to start your first conversation."}</p>}
    </div>
  </Modal>;
}

export function ContactDialog({ onClose, onAdded }: { onClose: () => void; onAdded: () => void }) {
  const [username, setUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const toast = useToast();
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const person = await api<User>("/contacts", { method: "POST", body: JSON.stringify({ username }) }); toast(`${person.display_name} added to your contacts.`); onAdded(); }
    catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  return <Modal title="Add a contact" onClose={onClose}><form className="modal-body" onSubmit={submit}>
    <p className="muted">Find someone who already has an account in this demo.</p>
    <label>Username<span className="prefixed-input"><span>@</span><input autoFocus value={username} onChange={e => setUsername(e.target.value.toLowerCase())} placeholder="maya" minLength={3} maxLength={32} required /></span></label>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="modal-footer"><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button className="button primary" disabled={busy}>{busy ? "Adding…" : "Add contact"}</button></div>
  </form></Modal>;
}

export function GroupDialog({ contacts, onClose, onCreated }: { contacts: User[]; onClose: () => void; onCreated: (conversation: Conversation) => void }) {
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<User[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { people } = usePeople(contacts, search);
  function toggle(person: User) { setSelected(prev => prev.some(p => p.id === person.id) ? prev.filter(p => p.id !== person.id) : prev.length < 31 ? [...prev, person] : prev); }
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { onCreated(await api<Conversation>("/groups", { method: "POST", body: JSON.stringify({ name, member_ids: selected.map(p => p.id) }) })); }
    catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  return <Modal title="New group" onClose={onClose}><form className="modal-body" onSubmit={submit}>
    <div className="group-form-heading"><Avatar name={name || "New group"} group size="large" /><label>Group name<input autoFocus placeholder="Give your group a name" value={name} onChange={e => setName(e.target.value)} maxLength={80} required /></label></div>
    <div className="selected-people">{selected.map(p => <button type="button" key={p.id} onClick={() => toggle(p)}>{p.display_name.split(" ")[0]}<X size={13} /></button>)}</div>
    <div className="search-box"><Search size={17} /><input aria-label="Find group members" placeholder="Find people to add" value={search} onChange={e => setSearch(e.target.value)} /></div>
    <p className="section-caption">Add members <span>{selected.length}/31 selected</span></p>
    <div className="people-list compact">{people.map(person => <button type="button" className="person-row" key={person.id} onClick={() => toggle(person)} aria-pressed={selected.some(p => p.id === person.id)}>
      <Avatar user={person} /><span><strong>{person.display_name}</strong><small>@{person.username}</small></span><span className={`selection-circle ${selected.some(p => p.id === person.id) ? "selected" : ""}`}>{selected.some(p => p.id === person.id) && <Check size={15} />}</span>
    </button>)}</div>
    {!people.length && <p className="empty-copy">Search for a registered username to add someone.</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="modal-footer"><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button className="button primary" disabled={busy || !selected.length || !name.trim()}>{busy ? "Creating…" : "Create group"}</button></div>
  </form></Modal>;
}

export function DetailsDialog({ conversation, user, contacts, onClose, onChanged }: {
  conversation: Conversation; user: User; contacts: User[]; onClose: () => void; onChanged: () => void;
}) {
  const [name, setName] = useState(conversation.name);
  const [adding, setAdding] = useState(false);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const { people } = usePeople(contacts, search);
  const group = conversation.kind === "group", admin = conversation.role === "admin";
  const available = people.filter(p => !conversation.members.some(m => m.id === p.id));
  async function change(path: string, method: string, body?: object) {
    setBusy(true);
    try { await api(path, { method, ...(body ? { body: JSON.stringify(body) } : {}) }); onChanged(); return true; }
    catch (e) { toast(errorText(e), true); return false; }
    finally { setBusy(false); }
  }
  return <Modal title={adding ? "Add group members" : group ? "Group details" : "Contact details"} onClose={onClose}>
    <div className="modal-body">
      {adding ? <><button className="text-button" onClick={() => setAdding(false)}><ArrowLeft size={16} />Back to group</button>
        <div className="search-box"><Search size={17} /><input autoFocus aria-label="Search new group members" placeholder="Name or username" value={search} onChange={e => setSearch(e.target.value)} /></div>
        <div className="people-list">{available.map(person => <div className="person-row static" key={person.id}><Avatar user={person} /><span><strong>{person.display_name}</strong><small>@{person.username}</small></span><button className="button small secondary" disabled={busy} onClick={async () => {
          if (await change(`/groups/${conversation.id}/members`, "POST", { user_id: person.id })) toast(`${person.display_name} added.`);
        }}>Add</button></div>)}</div>{!available.length && <p className="empty-copy">Search for someone who is not already in this group.</p>}
      </> : <>
        <div className="profile-summary"><Avatar user={conversation.peer} name={conversation.name} group={group} size="large" /><h3>{conversation.name}</h3><p>{group ? `${conversation.members.length} members` : `@${conversation.peer?.username}`}</p></div>
        {group && admin && <form className="rename-form" onSubmit={async e => { e.preventDefault(); if (await change(`/groups/${conversation.id}`, "PATCH", { name })) toast("Group name updated."); }}><label>Group name<input value={name} onChange={e => setName(e.target.value)} maxLength={80} required /></label><button className="button secondary" disabled={busy || name === conversation.name}>Save</button></form>}
        <div className="detail-note"><Shield size={19} /><div><strong>{group ? "Group permissions" : "Demo account"}</strong><p>{group ? "Admins can change the name and manage members. New members only see messages sent during their membership." : "Verification is mocked in this assignment. Do not share private information here."}</p></div></div>
        {group && <><div className="section-caption">Members{admin && <button className="text-button" onClick={() => setAdding(true)}><Plus size={16} />Add members</button>}</div>
          <div className="member-list">{conversation.members.map(member => <div className="person-row static member-row" key={member.id}>
            <Avatar user={member} size="small" /><span><strong>{member.display_name}{member.id === user.id ? " (you)" : ""}</strong><small>{member.role === "admin" ? "Group admin" : `@${member.username}`}</small></span>
            {admin && <div className="member-controls"><button disabled={busy} onClick={() => void change(`/groups/${conversation.id}/members/${member.id}`, "PATCH", { role: member.role === "admin" ? "member" : "admin" })}>{member.role === "admin" ? "Demote" : "Make admin"}</button>
              <button className="danger-text" disabled={busy} onClick={() => { if (window.confirm(`Remove ${member.display_name}? They will lose access to this group.`)) void change(`/groups/${conversation.id}/members/${member.id}`, "DELETE"); }}>Remove</button></div>}
          </div>)}</div>
        </>}
        <div className="detail-note muted-note"><LockKeyhole size={18} /><p>Messages are stored on the server. End-to-end encryption is not implemented.</p></div>
      </>}
    </div>
  </Modal>;
}

export function SettingsDialog({ session, onClose, onLogout }: { session: Session; onClose: () => void; onLogout: () => void }) {
  const [tab, setTab] = useState("Account");
  const [name, setName] = useState(session.user.display_name);
  const [busy, setBusy] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const { theme, setTheme } = useTheme();
  const toast = useToast(), client = useQueryClient();
  useEffect(() => { try { setNotifications(localStorage.getItem("signal-notifications") === "true"); } catch { /* Optional preference. */ } }, []);
  function updated(user: User) {
    client.setQueryData<Session>(["session"], current => current ? { ...current, user } : current);
    void client.invalidateQueries({ queryKey: ["conversations"] });
  }
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true);
    try { updated(await api<User>("/me", { method: "PATCH", body: JSON.stringify({ display_name: name }) })); toast("Profile updated."); }
    catch (e) { toast(errorText(e), true); } finally { setBusy(false); }
  }
  async function upload(file?: File) {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) { toast("Choose an image smaller than 2 MB.", true); return; }
    setBusy(true); const form = new FormData(); form.append("file", file);
    try { updated(await api<User>("/me/avatar", { method: "POST", body: form })); toast("Profile photo updated."); }
    catch (e) { toast(errorText(e), true); } finally { setBusy(false); }
  }
  async function toggleNotifications() {
    if (!("Notification" in window)) { toast("This browser does not support desktop notifications.", true); return; }
    const enabled = !notifications;
    if (enabled && await Notification.requestPermission() !== "granted") { toast("Notifications are blocked in your browser settings.", true); return; }
    setNotifications(enabled);
    try { localStorage.setItem("signal-notifications", String(enabled)); } catch { /* Preference is optional. */ }
  }
  return <Modal title="Settings" onClose={onClose} wide><div className="settings-layout">
    <nav className="settings-nav" aria-label="Settings sections">{[
      ["Account", <Avatar key="a" user={session.user} size="small" />], ["Appearance", <Sun key="s" size={19} />],
      ["Notifications", <Bell key="b" size={19} />], ["Privacy", <LockKeyhole key="l" size={19} />],
    ].map(([label, icon]) => <button key={String(label)} className={tab === label ? "active" : ""} onClick={() => setTab(String(label))}>{icon}{label}</button>)}</nav>
    <section className="settings-content"><h3>{tab}</h3>
      {tab === "Account" && <><div className="settings-avatar"><Avatar user={session.user} size="large" /><label className="avatar-upload" title="Change profile photo"><Camera size={17} /><span className="sr-only">Change profile photo</span><input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={e => void upload(e.target.files?.[0])} /></label></div><p className="centered muted">@{session.user.username}</p>
        <form onSubmit={save}><label>Display name<input value={name} onChange={e => setName(e.target.value)} required maxLength={64} /></label><button className="button primary full" disabled={busy || !name.trim()}>{busy ? "Saving…" : "Save changes"}</button></form>
        <button className="setting-row" onClick={() => toast("Linked devices are coming soon.")}><Laptop size={19} /><span>Linked devices<small>Coming soon</small></span><ChevronRight size={17} /></button>
        <button className="setting-row danger-text" onClick={onLogout}><LogOut size={19} /><span>Sign out</span></button>
      </>}
      {tab === "Appearance" && <><p className="muted">Make yourself comfortable.</p><div className="theme-options">{(["light", "dark", "system"] as const).map(value => <button className={theme === value ? "selected" : ""} key={value} onClick={() => setTheme(value)} aria-pressed={theme === value}>{value === "light" ? <Sun size={26} /> : value === "dark" ? <Moon size={26} /> : <Laptop size={26} />}<span>{value[0].toUpperCase() + value.slice(1)}</span>{theme === value && <Check size={16} />}</button>)}</div><p className="setting-help">System follows your device. This preference stays in this browser.</p></>}
      {tab === "Notifications" && <><p className="muted">A heads-up when someone messages you.</p><button className="setting-row" role="switch" aria-checked={notifications} onClick={() => void toggleNotifications()}><span>Desktop notifications<small>For messages outside the open conversation</small></span><span className={`switch ${notifications ? "on" : ""}`} /></button><p className="setting-help">The app must be open in a tab. Push notifications after the app closes are not included.</p></>}
      {tab === "Privacy" && <><div className="privacy-icon"><LockKeyhole size={32} /></div><h4>A note about this demo</h4><p className="muted">This is an assignment, not a private messaging service. The verification code is shared, and messages are stored on the server without end-to-end encryption.</p><p className="muted">Session cookies, membership checks, and admin permissions are implemented. Anyone who knows a demo username and the code can still sign in as that person.</p><div className="detail-note"><Shield size={21} /><p>Please use fictional names and messages while testing.</p></div></>}
    </section>
  </div></Modal>;
}
