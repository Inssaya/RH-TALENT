"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert, Spinner, useGuard } from "@/components/ui";

export default function Org() {
  const { t, refresh } = useApp();
  const user = useGuard("recruiter");
  const [org, setOrg] = useState<any>(null);
  const [members, setMembers] = useState<any[]>([]);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [totp, setTotp] = useState<{ secret: string; uri: string } | null>(null);
  const load = () => { api("/org").then(setOrg); api("/org/members").then(setMembers); };
  useEffect(() => { if (user) load(); }, [user]);
  if (!user || !org) return <Spinner />;
  const admin = user.organization?.role === "org_admin";
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); setMsg({ kind: "success", text: t(ok) }); load(); } catch (e) { setMsg({ kind: "error", text: t(String((e as ApiError).detail)) }); }
  };
  return (
    <div className="space-y-5">
      <h1 className="h1">{t("Organization")}</h1>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <div className="grid gap-5 lg:grid-cols-2">
        <form className="card space-y-3" onSubmit={(e) => { e.preventDefault(); run(() => api("/org", { method: "PUT", json: Object.fromEntries(new FormData(e.currentTarget)) }), "Saved."); }}>
          <h2 className="h2">{t("Public profile")} {org.verified && <span className="chip bg-emerald-100 text-emerald-800">{t("Verified organization")}</span>}</h2>
          {[["name", "Company name"], ["sector", "Sector"], ["size", "Size"], ["city", "City"], ["country", "Country"], ["website", "Website"]].map(([k, label]) => (
            <div key={k}><label className="label" htmlFor={k}>{t(label)}</label><input id={k} name={k} className="input" defaultValue={org[k]} disabled={!admin} required={k === "name"} /></div>))}
          <div><label className="label" htmlFor="description">{t("Presentation")}</label><textarea id="description" name="description" className="input min-h-28" defaultValue={org.description} disabled={!admin} /></div>
          {admin && <button className="btn-primary">{t("Save")}</button>}
        </form>
        <div className="space-y-5">
          <div className="card space-y-3">
            <h2 className="h2">{t("Members")}</h2>
            <ul className="text-sm">{members.map((m) => <li key={m.id} className="flex justify-between border-t border-slate-100 py-2 first:border-0"><span>{m.full_name} <span className="muted">{m.email}</span></span><span className="chip">{m.role}</span></li>)}</ul>
            {admin && (
              <form className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); const form = e.currentTarget; run(() => api("/org/members", { method: "POST", json: Object.fromEntries(new FormData(form)) }).then(() => form.reset()), "Invitation sent."); }}>
                <div><label className="sr-only" htmlFor="m_name">{t("Full name")}</label><input id="m_name" name="full_name" required className="input" placeholder={t("Full name")} /></div>
                <div><label className="sr-only" htmlFor="m_email">{t("E-mail")}</label><input id="m_email" name="email" type="email" required className="input" placeholder={t("E-mail")} /></div>
                <button className="btn-secondary">{t("Invite")}</button>
              </form>)}
          </div>
          <div className="card space-y-3">
            <h2 className="h2">{t("Two-factor authentication")}</h2>
            <p className="muted">{t("Mandatory for organization administrators.")}</p>
            {user.totp_enabled ? <Alert kind="success">{t("Two-factor authentication is active on your account.")}</Alert> : totp ? (
              <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run(() => api("/auth/totp/enable", { method: "POST", json: { code: new FormData(e.currentTarget).get("code") } }).then(() => { setTotp(null); return refresh(); }), "Two-factor authentication is active on your account."); }}>
                <p className="text-sm">{t("Add this key to your authenticator app, then enter the 6-digit code.")}</p>
                <code className="block break-all rounded bg-slate-100 p-2 text-sm">{totp.secret}</code>
                <label className="sr-only" htmlFor="code">{t("Authentication code")}</label>
                <input id="code" name="code" required inputMode="numeric" className="input" placeholder="123456" />
                <button className="btn-primary">{t("Activate")}</button>
              </form>
            ) : <button className="btn-secondary" onClick={() => api("/auth/totp/setup", { method: "POST" }).then(setTotp)}>{t("Set up two-factor authentication")}</button>}
          </div>
        </div>
      </div>
    </div>
  );
}
