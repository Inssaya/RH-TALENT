"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert, Spinner } from "@/components/ui";

export default function Account() {
  const { t, user } = useApp();
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  useEffect(() => { if (user === null) window.location.href = "/login?next=/account"; }, [user]);
  if (!user) return <Spinner />;
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const f = Object.fromEntries(new FormData(form)) as Record<string, string>;
    setMsg(null);
    try {
      await api("/auth/password", { method: "POST", json: { current_password: f.current, new_password: f.next, totp: f.totp || null } });
      form.reset();
      setMsg({ kind: "success", text: t("Password changed. Your other sessions were signed out.") });
    } catch (err) { setMsg({ kind: "error", text: t(String((err as ApiError).detail)) }); }
  };
  return (
    <div className="mx-auto max-w-md space-y-5">
      <h1 className="h1">{t("My account")}</h1>
      <p className="muted">{user.full_name} · {user.email}</p>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <form onSubmit={submit} className="card space-y-3">
        <h2 className="h2">{t("Change my password")}</h2>
        <div><label className="label" htmlFor="current">{t("Current password")}</label><input id="current" name="current" type="password" required className="input" autoComplete="current-password" /></div>
        <div><label className="label" htmlFor="next">{t("New password (10 characters minimum)")}</label><input id="next" name="next" type="password" required minLength={10} className="input" autoComplete="new-password" /></div>
        {user.totp_enabled && <div><label className="label" htmlFor="totp">{t("Authentication code")}</label><input id="totp" name="totp" required inputMode="numeric" autoComplete="one-time-code" className="input" /></div>}
        <button className="btn-primary">{t("Change my password")}</button>
      </form>
      <div className="card space-y-2">
        <h2 className="h2">{t("Two-factor authentication")}</h2>
        <Link href="/security" className="text-sm font-medium text-brand-700 underline">{user.totp_enabled ? t("Replace my authenticator") : t("Set up two-factor authentication")}</Link>
      </div>
    </div>
  );
}
