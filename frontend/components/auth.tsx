"use client";
import { useState, type FormEvent } from "react";
import { ArrowRight, ChevronLeft, LockKeyhole, LoaderCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api, errorText } from "@/lib/api";
import type { Session } from "@/lib/types";
import { SignalMark } from "./ui";

export function Auth({ onLogin }: { onLogin: (session: Session) => void }) {
  const [register, setRegister] = useState(false);
  const [step, setStep] = useState<"username" | "code">("username");
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const config = useQuery({ queryKey: ["config"], queryFn: () => api<{ demo_otp: string; demo_accounts: string[] }>("/config") });
  async function submit(event: FormEvent) {
    event.preventDefault(); setError("");
    if (step === "username") { setStep("code"); return; }
    setBusy(true);
    try {
      const result = await api<Session>(`/auth/${register ? "register" : "login"}`, {
        method: "POST", body: JSON.stringify({ username, otp, ...(register ? { display_name: displayName } : {}) }),
      });
      onLogin(result);
    } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); }
  }
  function switchMode() { setRegister(!register); setStep("username"); setError(""); setOtp(""); }
  return <main className="auth-screen">
    <div className="auth-brand"><SignalMark /><span>Signal</span><span className="demo-pill">Assignment demo</span></div>
    <section className="auth-card">
      {step === "code" && <button className="back-button icon-button" aria-label="Back to username" onClick={() => { setStep("username"); setError(""); }}><ChevronLeft /></button>}
      <SignalMark large />
      <h1>{step === "code" ? "One small step." : register ? "Your conversations start here." : "Good to see you."}</h1>
      <p className="auth-subtitle">{step === "code" ? `Enter the demo code to continue as @${username}.` : register ? "Pick a username and make yourself at home." : "Sign in to pick up where you left off."}</p>
      <form onSubmit={submit}>
        {step === "username" ? <>
          {register && <label>Display name<input autoFocus value={displayName} onChange={e => setDisplayName(e.target.value)} placeholder="How people know you" maxLength={64} required autoComplete="name" /></label>}
          <label>Username<span className="prefixed-input"><span>@</span><input autoFocus={!register} value={username}
            onChange={e => setUsername(e.target.value.toLowerCase())} placeholder="your_username" minLength={3} maxLength={32}
            pattern="[a-z0-9_]{3,32}" title="3–32 letters, numbers, or underscores" required autoComplete="username" /></span></label>
        </> : <label>Verification code<input className="otp-input" autoFocus value={otp} onChange={e => setOtp(e.target.value)}
          placeholder="000000" inputMode="numeric" autoComplete="one-time-code" maxLength={12} required /></label>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button primary full" disabled={busy || config.isError} type="submit">
          {busy ? <LoaderCircle size={19} className="spin" /> : <>{step === "code" ? register ? "Create account" : "Sign in" : "Continue"}<ArrowRight size={18} /></>}
        </button>
      </form>
      {step === "code" ? <p className="demo-code">Nothing was sent to your phone. Demo code: <strong>{config.data?.demo_otp || "…"}</strong></p> : <>
        <div className="auth-divider"><span>or try a demo account</span></div>
        <div className="demo-accounts">{(config.data?.demo_accounts || []).map(name => <button key={name} type="button" onClick={() => {
          setUsername(name); setRegister(false); setStep("code"); setError("");
        }}>{name[0].toUpperCase() + name.slice(1)}<ArrowRight size={14} /></button>)}</div>
      </>}
      {config.isError && <p className="form-error" role="alert">Cannot reach the backend. Check that it is running.</p>}
      <p className="switch-auth">{register ? "Already have an account?" : "New here?"} <button onClick={switchMode}>{register ? "Sign in" : "Create an account"}</button></p>
    </section>
    <p className="auth-disclaimer"><LockKeyhole size={15} />A learning project, not the official Signal app.<br />Demo authentication. No end-to-end encryption.</p>
  </main>;
}
