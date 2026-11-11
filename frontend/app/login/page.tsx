"use client";
import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp, User } from "@/components/Providers";
import { Alert } from "@/components/ui";

export default function Login() {
  const { t, refresh } = useApp();
  const [error, setError] = useState("");
  const [needTotp, setNeedTotp] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true); setError("");
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    try {
      const u = await api<User>("/auth/login", { method: "POST", json: { email: f.email, password: f.password, totp: f.totp || null } });
      await refresh();
      const next = new URLSearchParams(window.location.search).get("next");
      window.location.href = next && next.startsWith("/") && !next.startsWith("//") ? next
        : u.role === "recruiter" ? "/recruiter" : u.role === "platform_admin" ? "/admin" : "/candidate";
    } catch (err) {
      const d = String((err as ApiError).detail);
      if (d === "totp_required") setNeedTotp(true);
      else setError(t(d));
    } finally { setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-sm space-y-4">
      <h1 className="h1">{t("Sign in")}</h1>
      <form onSubmit={submit} className="card space-y-3">
        {error && <Alert>{error}</Alert>}
        <div><label className="label" htmlFor="email">{t("E-mail")}</label><input id="email" name="email" type="email" required className="input" autoComplete="email" /></div>
        <div><label className="label" htmlFor="password">{t("Password")}</label><input id="password" name="password" type="password" required className="input" autoComplete="current-password" /></div>
        {needTotp && <div><label className="label" htmlFor="totp">{t("Authentication code")}</label><input id="totp" name="totp" inputMode="numeric" required className="input" autoComplete="one-time-code" autoFocus /></div>}
        <button className="btn-primary w-full" disabled={busy}>{t("Sign in")}</button>
        <div className="flex justify-between text-sm">
          <Link href="/forgot" className="text-brand-700 hover:underline">{t("Forgot password?")}</Link>
          <Link href="/register" className="text-brand-700 hover:underline">{t("Create an account")}</Link>
        </div>
      </form>
    </div>
  );
}
