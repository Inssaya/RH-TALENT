"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Locale, translate } from "@/lib/i18n";

export type User = {
  id: string; email: string; full_name: string; role: "candidate" | "recruiter" | "platform_admin";
  locale: string; totp_enabled: boolean;
  organization: { id: string; name: string; role: string; verified: boolean } | null;
};

type Ctx = {
  locale: Locale; setLocale: (l: Locale) => void; t: (key: string, vars?: Record<string, string | number>) => string;
  user: User | null | undefined; refresh: () => Promise<void>; logout: () => Promise<void>;
};
const AppCtx = createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => useContext(AppCtx);

export default function Providers({ initialLocale, children }: { initialLocale: Locale; children: React.ReactNode }) {
  const [locale, setLoc] = useState<Locale>(initialLocale);
  const [user, setUser] = useState<User | null | undefined>(undefined);

  const refresh = useCallback(async () => {
    try {
      setUser(await api<User>("/auth/me"));
    } catch {
      setUser(null);
    }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const setLocale = (l: Locale) => {
    document.cookie = `tm_locale=${l}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.lang = l;
    document.documentElement.dir = l === "ar" ? "rtl" : "ltr";
    setLoc(l);
  };
  const logout = async () => {
    await api("/auth/logout", { method: "POST" });
    setUser(null);
    window.location.href = "/";
  };
  const t = useCallback((key: string, vars?: Record<string, string | number>) => translate(locale, key, vars), [locale]);

  return <AppCtx.Provider value={{ locale, setLocale, t, user, refresh, logout }}>{children}</AppCtx.Provider>;
}
