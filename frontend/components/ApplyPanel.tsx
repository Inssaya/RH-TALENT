"use client";
import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "./Providers";
import { Alert } from "./ui";

export default function ApplyPanel({ slug, open }: { slug: string; open: boolean }) {
  const { t, user, locale } = useApp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<{ token?: string } | null>(null);

  if (!open) return <div className="card"><Alert kind="info">{t("This job is closed.")}</Alert></div>;
  if (done) {
    return (
      <div className="card space-y-3">
        <Alert kind="success">{t("Application received. A confirmation e-mail with your tracking link is on its way.")}</Alert>
        {done.token
          ? <Link className="btn-primary w-full" href={`/track/${done.token}`}>{t("Track my application")}</Link>
          : <Link className="btn-primary w-full" href="/candidate">{t("My applications")}</Link>}
      </div>
    );
  }

  const oneClick = async () => {
    setBusy(true); setError("");
    try {
      await api(`/candidate/apply/${slug}`, { method: "POST" });
      setDone({});
    } catch (e) {
      setError(e instanceof ApiError ? t(String(e.detail)) : t("Something went wrong"));
    } finally { setBusy(false); }
  };

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true); setError("");
    const fd = new FormData(e.currentTarget);
    fd.set("locale", locale);
    fd.set("consent", fd.get("consent") ? "true" : "false");
    try {
      const r = await api<{ tracking_token: string }>(`/public/jobs/${slug}/apply`, { method: "POST", body: fd });
      setDone({ token: r.tracking_token });
    } catch (err) {
      setError(err instanceof ApiError ? t(String(err.detail)) : t("Something went wrong"));
    } finally { setBusy(false); }
  };

  if (user?.role === "recruiter" || user?.role === "platform_admin") {
    return <div className="card"><p className="muted">{t("You are signed in as an employer. Sign out to apply.")}</p></div>;
  }

  return (
    <div className="card sticky top-4 space-y-4">
      <h2 className="h2">{t("Apply")}</h2>
      {error && <Alert>{error}</Alert>}
      {user?.role === "candidate" && (
        <>
          <button className="btn-primary w-full" onClick={oneClick} disabled={busy}>{t("Apply in one click")}</button>
          <p className="muted">{t("Uses the CV of your profile.")} <Link href="/candidate" className="text-brand-700 underline">{t("My space")}</Link></p>
          <hr className="border-slate-200" />
          <p className="muted">{t("Or apply with another CV:")}</p>
        </>
      )}
      <form onSubmit={submit} className="space-y-3">
        <div><label className="label" htmlFor="full_name">{t("Full name")}</label>
          <input id="full_name" name="full_name" required minLength={2} className="input" autoComplete="name" defaultValue={user?.full_name} /></div>
        <div><label className="label" htmlFor="email">{t("E-mail")}</label>
          <input id="email" name="email" type="email" required className="input" autoComplete="email" defaultValue={user?.email} /></div>
        <div><label className="label" htmlFor="phone">{t("Phone (optional)")}</label>
          <input id="phone" name="phone" type="tel" className="input" autoComplete="tel" /></div>
        <div><label className="label" htmlFor="file">{t("CV (PDF, Word, photo or scan, 10 MB max)")}</label>
          <input id="file" name="file" type="file" required className="input"
                 accept=".pdf,.docx,.odt,.rtf,.txt,.png,.jpg,.jpeg,application/pdf,image/*" /></div>
        <label className="flex items-start gap-2 text-sm text-slate-600">
          <input type="checkbox" name="consent" required className="mt-1" />
          <span>{t("I have read the privacy notice and agree that my application is processed for this job. An AI ranks applications; a human takes every decision.")}{" "}
            <Link href="/legal/privacy" className="text-brand-700 underline" target="_blank">{t("Privacy and your rights")}</Link></span>
        </label>
        <button className="btn-primary w-full" disabled={busy}>{busy ? "…" : t("Send my application")}</button>
        <p className="muted">{t("No account needed.")}</p>
      </form>
    </div>
  );
}
