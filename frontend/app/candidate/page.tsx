"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import JobCard, { PublicJob } from "@/components/JobCard";
import TrackingDetail, { Tracking } from "@/components/TrackingDetail";
import { Alert, Spinner, StatusChip, useGuard } from "@/components/ui";
import { LANGS } from "@/lib/labels";

export default function Candidate() {
  const { t } = useApp();
  const user = useGuard("candidate");
  const [profile, setProfile] = useState<any>(null);
  const [recs, setRecs] = useState<PublicJob[]>([]);
  const [apps, setApps] = useState<(Tracking & { id: string })[]>([]);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const p = await api("/candidate/profile");
    setProfile(p);
    api("/candidate/applications").then(setApps);
    if (p.exists) api("/candidate/recommendations").then(setRecs);
  }, []);
  useEffect(() => { if (user) load(); }, [user, load]);
  if (!user || !profile) return <Spinner />;
  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true); setMsg(null);
    try { await fn(); if (ok) setMsg({ kind: "success", text: t(ok) }); await load(); }
    catch (e) { setMsg({ kind: "error", text: t(String((e as ApiError).detail)) }); } finally { setBusy(false); }
  };
  const upload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData(); fd.set("file", file);
    run(() => api("/candidate/profile/cv", { method: "POST", body: fd }), "CV analysed. Check your profile below and validate it.");
  };
  const exportData = async () => {
    const blob = new Blob([JSON.stringify(await api("/candidate/export"), null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "talentmatch-my-data.json"; a.click();
  };
  const d = profile.data;
  return (
    <div className="space-y-6">
      <h1 className="h1">{t("My space")}</h1>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <section className="card space-y-3">
          <h2 className="h2">{t("My profile")}</h2>
          <div><label className="label" htmlFor="cv">{profile.exists ? t("Replace my CV") : t("Upload my CV to build my profile")}</label>
            <input id="cv" type="file" className="input" onChange={upload} disabled={busy} accept=".pdf,.docx,.odt,.rtf,.txt,.png,.jpg,.jpeg,application/pdf,image/*" /></div>
          {profile.exists && (
            <form className="space-y-3" key={profile.updated_at} onSubmit={(e) => {
              e.preventDefault(); const f = new FormData(e.currentTarget);
              run(() => api("/candidate/profile", { method: "PUT", json: {
                title: f.get("title"), summary: f.get("summary"), location: f.get("location"),
                skills: String(f.get("skills")).split(",").map((s) => s.trim()).filter(Boolean),
                visible_to_recruiters: !!f.get("visible"), alerts: !!f.get("alerts") } }), "Profile saved.");
            }}>
              {!profile.validated && <Alert kind="info">{t("This profile was extracted automatically from your CV. Correct it if needed, then save.")}</Alert>}
              <div><label className="label" htmlFor="title">{t("Title")}</label><input id="title" name="title" className="input" defaultValue={d.title} /></div>
              <div><label className="label" htmlFor="location">{t("City")}</label><input id="location" name="location" className="input" defaultValue={d.location} /></div>
              <div><label className="label" htmlFor="summary">{t("Summary")}</label><textarea id="summary" name="summary" className="input" defaultValue={d.summary} /></div>
              <div><label className="label" htmlFor="skills">{t("Skills (comma separated)")}</label>
                <textarea id="skills" name="skills" className="input" defaultValue={[...d.skills.map((s: any) => s.label), ...(d.raw_skills || [])].join(", ")} /></div>
              <p className="text-sm text-slate-600">{t("Experience")}: {Math.round((d.total_months || 0) / 12 * 10) / 10} {t("years")} · {t("Languages")}: {(d.languages || []).map((l: any) => t(LANGS[l.code] || l.code)).join(", ") || "—"}</p>
              {!user.email_verified && <Alert kind="warning">{t("Confirm your e-mail address to become visible to recruiters or receive job alerts.")}</Alert>}
              <label className="flex items-start gap-2 text-sm"><input type="checkbox" name="visible" defaultChecked={profile.visible_to_recruiters} disabled={!user.email_verified} className="mt-1" />
                <span>{t("Let recruiters find my profile and invite me to apply (optional, you can change this at any time).")}</span></label>
              <label className="flex items-start gap-2 text-sm"><input type="checkbox" name="alerts" defaultChecked={profile.alerts} disabled={!user.email_verified} className="mt-1" />
                <span>{t("Send me a weekly e-mail with new matching jobs.")}</span></label>
              <button className="btn-primary" disabled={busy}>{t("Save and validate")}</button>
            </form>
          )}
        </section>
        <section className="space-y-3">
          <h2 className="h2">{t("My applications")}</h2>
          {apps.length === 0 && <div className="card muted">{t("You have not applied to any job yet.")}</div>}
          {apps.map((a) => (
            <details key={a.id} className="card">
              <summary className="flex cursor-pointer items-center justify-between gap-3">
                <span><span className="font-medium">{a.job.title}</span> <span className="muted">{a.job.organization}</span></span><StatusChip status={a.status} /></summary>
              <div className="mt-3 space-y-3">
                <TrackingDetail data={a} onHumanReview={() => run(() => api(`/candidate/applications/${a.id}/human-review`, { method: "POST" }))} />
                {a.can_withdraw && <button className="btn-secondary" onClick={() => window.confirm(t("Withdraw this application?")) && run(() => api(`/candidate/applications/${a.id}/withdraw`, { method: "POST" }))}>{t("Withdraw my application")}</button>}
              </div>
            </details>))}
        </section>
      </div>
      <section className="space-y-3">
        <div className="flex items-end justify-between"><h2 className="h2">{t("For you")}</h2><Link href="/jobs" className="text-sm font-medium text-brand-700 hover:underline">{t("See all jobs")} →</Link></div>
        <p className="muted">{t("Sorted by relevance to your profile. No job is hidden: the full list is one click away.")}</p>
        {!profile.exists ? <div className="card muted">{t("Upload your CV to get recommendations.")}</div>
          : <div className="grid gap-3 sm:grid-cols-2">{recs.map((j) => <JobCard key={j.slug} job={j} t={t} />)}</div>}
      </section>
      <section className="card space-y-3">
        <h2 className="h2">{t("Your rights")}</h2>
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary" onClick={exportData}>{t("Download my data")}</button>
          <button className="btn-danger" onClick={() => window.confirm(t("Delete your account, your profile and all your applications? This cannot be undone.")) && api("/candidate/erase", { method: "POST" }).then(() => { window.location.href = "/"; })}>{t("Delete my account")}</button>
        </div>
      </section>
    </div>
  );
}
