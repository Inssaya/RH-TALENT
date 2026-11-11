"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert } from "@/components/ui";

export default function Register() {
  const { t, refresh, locale } = useApp();
  const [role, setRole] = useState<"candidate" | "recruiter">("candidate");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (new URLSearchParams(window.location.search).get("role") === "recruiter") setRole("recruiter"); }, []);

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true); setError("");
    const f = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    try {
      await api("/auth/register", { method: "POST", json: {
        email: f.email, password: f.password, full_name: f.full_name, role, locale,
        organization_name: role === "recruiter" ? f.organization_name : null, accept_terms: !!f.accept_terms } });
      await refresh();
      window.location.href = role === "recruiter" ? "/recruiter" : "/candidate";
    } catch (err) { setError(t(String((err as ApiError).detail))); } finally { setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-md space-y-4">
      <h1 className="h1">{t("Create an account")}</h1>
      <div className="grid grid-cols-2 gap-2" role="tablist">
        {(["candidate", "recruiter"] as const).map((r) => (
          <button key={r} role="tab" aria-selected={role === r} onClick={() => setRole(r)}
                  className={role === r ? "btn-primary" : "btn-secondary"}>{t(r === "candidate" ? "I am looking for a job" : "I am hiring")}</button>
        ))}
      </div>
      <form onSubmit={submit} className="card space-y-3">
        {error && <Alert>{error}</Alert>}
        <div><label className="label" htmlFor="full_name">{t("Full name")}</label><input id="full_name" name="full_name" required minLength={2} className="input" autoComplete="name" /></div>
        {role === "recruiter" && <div><label className="label" htmlFor="organization_name">{t("Company name")}</label><input id="organization_name" name="organization_name" required minLength={2} className="input" autoComplete="organization" /></div>}
        <div><label className="label" htmlFor="email">{t("E-mail")}</label><input id="email" name="email" type="email" required className="input" autoComplete="email" /></div>
        <div><label className="label" htmlFor="password">{t("Password (10 characters minimum)")}</label><input id="password" name="password" type="password" required minLength={10} className="input" autoComplete="new-password" /></div>
        <label className="flex items-start gap-2 text-sm text-slate-600">
          <input type="checkbox" name="accept_terms" required className="mt-1" />
          <span>{t("I accept the terms of use and the privacy notice.")} <Link href="/legal/privacy" className="text-brand-700 underline" target="_blank">{t("Privacy and your rights")}</Link></span>
        </label>
        <button className="btn-primary w-full" disabled={busy}>{t("Create my account")}</button>
        <p className="text-sm"><Link href="/login" className="text-brand-700 hover:underline">{t("I already have an account")}</Link></p>
      </form>
    </div>
  );
}
