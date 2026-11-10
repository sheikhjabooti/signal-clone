"use client";
import { createPortal } from "react-dom";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CheckCircle2, AlertCircle, X } from "lucide-react";

type Theme = "light" | "dark" | "system";
const ThemeContext = createContext<{ theme: Theme; setTheme: (value: Theme) => void }>({ theme: "system", setTheme: () => {} });
const ToastContext = createContext<(message: string, error?: boolean) => void>(() => {});
export const useTheme = () => useContext(ThemeContext);
export const useToast = () => useContext(ToastContext);

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: {
    retry: (count, error) => count < 1 && !("status" in error && [401, 403, 404].includes(Number(error.status))),
    staleTime: 10000, refetchOnWindowFocus: false,
  } } }));
  const [theme, updateTheme] = useState<Theme>("system");
  const [toast, updateToast] = useState<{ message: string; error: boolean; id: number } | null>(null);
  const notify = useCallback((message: string, error = false) => updateToast({ message, error, id: Date.now() }), []);
  const setTheme = useCallback((value: Theme) => {
    updateTheme(value);
    try { localStorage.setItem("signal-theme", value); } catch { /* Private browsing may deny storage. */ }
  }, []);
  useEffect(() => {
    try {
      const saved = localStorage.getItem("signal-theme");
      if (saved === "dark" || saved === "light" || saved === "system") updateTheme(saved);
    } catch { /* The app does not require local storage. */ }
  }, []);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => document.documentElement.dataset.theme = theme === "system" ? media.matches ? "dark" : "light" : theme;
    apply(); media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => updateToast(null), 4500);
    return () => clearTimeout(timer);
  }, [toast]);
  return <QueryClientProvider client={client}><ThemeContext.Provider value={{ theme, setTheme }}>
    <ToastContext.Provider value={notify}>{children}
      {toast && createPortal(<div className={`toast ${toast.error ? "error" : ""}`} role={toast.error ? "alert" : "status"}>
        {toast.error ? <AlertCircle size={19} /> : <CheckCircle2 size={19} />}
        <span>{toast.message}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => updateToast(null)}><X size={16} /></button>
      </div>, document.querySelector("dialog[open]") || document.body)}
    </ToastContext.Provider></ThemeContext.Provider></QueryClientProvider>;
}
