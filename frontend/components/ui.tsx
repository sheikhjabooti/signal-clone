"use client";
import { useEffect, useRef, type ReactNode } from "react";
import { Check, CheckCheck, LoaderCircle, Users, X } from "lucide-react";
import type { User } from "@/lib/types";
import { assetUrl } from "@/lib/api";
import { initials } from "@/lib/format";

export function SignalMark({ large = false }: { large?: boolean }) {
  return <span className={`signal-mark ${large ? "large" : ""}`} aria-hidden="true"><span /></span>;
}
export function Avatar({ user, name, group = false, size = "normal" }: {
  user?: User | null; name?: string; group?: boolean; size?: "small" | "normal" | "large";
}) {
  return <span className={`avatar ${size} ${group ? "group-avatar" : user?.color || "blue"}`} aria-hidden="true">
    {user?.avatar_url ? <img src={assetUrl(user.avatar_url)} alt="" /> : group ? <Users size={size === "large" ? 32 : 22} /> : initials(name || user?.display_name || "?")}
  </span>;
}
export function Receipt({ status, pending = false }: { status?: string; pending?: boolean }) {
  if (pending) return <LoaderCircle size={13} className="spin" aria-label="Sending" />;
  if (status === "sent") return <Check size={15} aria-label="Sent" />;
  return <CheckCheck size={17} className={status === "read" ? "read-receipt" : ""} aria-label={status === "read" ? "Read" : "Delivered"} />;
}
export function Spinner({ label = "Loading" }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle size={24} className="spin" /><span>{label}</span></div>;
}
export function Modal({ title, children, onClose, wide = false }: {
  title: string; children: ReactNode; onClose: () => void; wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return <dialog ref={ref} className={`modal ${wide ? "wide" : ""}`} aria-label={title}
    onCancel={event => { event.preventDefault(); onClose(); }}
    onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="modal-inner"><header className="modal-header"><h2>{title}</h2>
      <button className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={21} /></button>
    </header>{children}</section>
  </dialog>;
}
