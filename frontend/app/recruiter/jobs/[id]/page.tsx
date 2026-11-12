"use client";
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import JobForm, { QualityReport } from "@/components/JobForm";
import { Alert, Bar, FLAG_LABEL, ScoreBadge, Spinner, StatusChip, STATUS_LABEL, useGuard } from "@/components/ui";
import { Draft, Job, Row, SUBSCORE_LABEL } from "@/lib/types";

type Shortlist = {
  job: Job; members: Row[]; review_lane: Row[]; below: Row[]; excluded: Row[]; processing: Row[]; closed: Row[];
  cutoff_score: number | null; notes: Record<string, any>[]; diff: { entered?: string[]; left?: string[] };
};
type Tab = "shortlist" | "pipeline" | "analytics" | "talents" | "settings";
const REASONS = { skills: "Skills", experience: "Experience", position_filled: "Position filled", other: "Other" };

function note(t: (k: string, v?: any) => string, n: Record<string, any>) {
  switch (n.code) {
    case "fewer_eligible": return t("{a} eligible candidate(s) for {b} requested", { a: n.eligible, b: n.requested });
    case "fewer_qualified": return t("Only {a} candidate(s) reach the threshold, for {b} requested", { a: n.qualified, b: n.requested });
    case "ties_included": return t("Tie at the boundary: {a} extra candidate(s) included (N + {a})", { a: n.extra });
    case "empty_shortlist": return t("No candidate reaches the threshold. Lowering it to {a} would include {b} candidate(s).", { a: n.suggested_threshold, b: n.would_include });
    case "provisional_excluded": return t("{a} provisional score(s) not counted yet", { a: n.count });
    default: return n.code;
  }
}

function CandidateRow({ r, rank, selected, onSelect }: { r: Row; rank?: number; selected?: boolean; onSelect?: (v: boolean) => void }) {
  const { t } = useApp();
  return (
    <li className="flex flex-wrap items-center gap-3 border-t border-slate-100 px-4 py-3 first:border-t-0">
      {onSelect && <input type="checkbox" aria-label={t("Select")} checked={!!selected} onChange={(e) => onSelect(e.target.checked)} />}
      {rank !== undefined && <span className="w-6 text-sm tabular-nums text-slate-400">{rank}</span>}
      <ScoreBadge score={r.score} />
      <div className="min-w-0 flex-1">
        <Link href={`/recruiter/applications/${r.id}`} className="font-medium text-brand-700 hover:underline">{r.name}</Link>
        {r.pinned && <span className="ms-1" title={t("Pinned")}>📌</span>}
        <p className="muted truncate">{r.title}{r.years ? ` · ${t("{n} yrs", { n: r.years })}` : ""}</p>
        {r.top_missing.length > 0 && <p className="truncate text-xs text-slate-500">{t("Missing")}: {r.top_missing.join(" · ")}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {r.human_review_requested && <span className="chip bg-amber-100 text-amber-900">{t("Human review requested")}</span>}
        {r.flags.filter((f) => f !== "rule_based_assessment").map((f) => <span key={f} className="chip bg-amber-50 text-amber-800" title={t(FLAG_LABEL[f] || f)}>⚠ {t(FLAG_LABEL[f] || f)}</span>)}
        {r.pending_rejection && <span className="chip">{t("Rejection pending (can be undone)")}</span>}
        <StatusChip status={r.status} />
      </div>
    </li>
  );
}

function Lane({ title, hint, rows, ranked, select }: { title: string; hint?: string; rows: Row[]; ranked?: boolean; select?: [Set<string>, (id: string, v: boolean) => void] }) {
  if (rows.length === 0) return null;
  return (
    <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <header className="bg-slate-50 px-4 py-2"><h3 className="text-sm font-semibold">{title} <span className="font-normal text-slate-500">({rows.length})</span></h3>
        {hint && <p className="text-xs text-slate-500">{hint}</p>}</header>
      <ul>{rows.map((r, i) => <CandidateRow key={r.id} r={r} rank={ranked ? i + 1 : undefined} selected={select?.[0].has(r.id)} onSelect={select ? (v) => select[1](r.id, v) : undefined} />)}</ul>
    </section>
  );
}

export default function JobDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t } = useApp();
  const user = useGuard("recruiter");
  const [tab, setTab] = useState<Tab>("shortlist");
  const [sl, setSl] = useState<Shortlist | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [analytics, setAnalytics] = useState<any>(null);
  const [talents, setTalents] = useState<any[] | null>(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState(false);

  const fail = (e: unknown) => setError(e instanceof ApiError ? t(String(e.detail)) : t("Something went wrong"));
  const load = useCallback(async () => {
    try {
      const [s, j] = await Promise.all([api<Shortlist>(`/jobs/${id}/shortlist`), api<Job>(`/jobs/${id}`)]);
      setSl(s); setJob(j); setDraft((d) => d ?? j.draft ?? null);
    } catch (e) { fail(e); }
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (user) load(); }, [user, load]);
  useEffect(() => {
    if (!user) return;
    if (tab === "analytics") api(`/jobs/${id}/analytics`).then(setAnalytics).catch(fail);
    if (tab === "talents") api(`/jobs/${id}/talents`).then(setTalents).catch(fail);
  }, [tab, user, id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {  // refresh while applications are still being processed
    if (!sl || sl.processing.length === 0) return;
    const h = setTimeout(load, 4000);
    return () => clearTimeout(h);
  }, [sl, load]);

  if (!user || !sl || !job) return error ? <Alert>{error}</Alert> : <Spinner />;
  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setError(""); setInfo("");
    try { await fn(); if (ok) setInfo(t(ok)); await load(); } catch (e) { fail(e); }
  };
  const setPolicy = (patch: Partial<Job["policy"]>) => act(() => api(`/jobs/${id}/policy`, { method: "PUT", json: { ...job.policy, ...patch } }));
  const toggle = (rid: string, v: boolean) => setSelected((s) => { const n = new Set(s); if (v) n.add(rid); else n.delete(rid); return n; });
  const all = [...sl.members, ...sl.review_lane, ...sl.below, ...sl.excluded, ...sl.closed];
  const chosen = all.filter((r) => selected.has(r.id));

  const tabs: [Tab, string][] = [["shortlist", "Shortlist"], ["pipeline", "Pipeline"], ["analytics", "Analytics"], ["talents", "Suggested talents"], ["settings", "Settings"]];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href="/recruiter" className="text-sm text-brand-700 hover:underline">← {t("My job posts")}</Link>
          <h1 className="h1 mt-1">{job.title || t("Untitled")}</h1>
          <p className="muted">{[job.city, job.country].filter(Boolean).join(", ")} · v{job.version} · {t("{n} application(s)", { n: job.applications })}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip status={job.status} />
          {job.status === "published" && <Link className="btn-secondary" href={`/jobs/${job.slug}`} target="_blank">{t("Public page")} ↗</Link>}
          {job.status === "draft" && <button className="btn-primary" disabled={!user.email_verified} onClick={() => act(() => api(`/jobs/${id}/publish`, { method: "POST" }), "Job published.")}>{t("Publish")}</button>}
          {job.status === "published" && <button className="btn-secondary" onClick={() => window.confirm(t("Close this job? It will no longer accept applications.")) && act(() => api(`/jobs/${id}/close`, { method: "POST" }))}>{t("Close")}</button>}
        </div>
      </div>
      <div className="flex flex-wrap gap-2 border-b border-slate-200" role="tablist">
        {tabs.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                  className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${tab === k ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-ink"}`}>{t(label)}</button>
        ))}
      </div>
      {error && <Alert>{error}</Alert>}
      {info && <Alert kind="success">{info}</Alert>}
      {job.status === "draft" && !user.email_verified && <Alert kind="warning">{t("Confirm your e-mail address to publish a job. Drafts are always allowed.")}</Alert>}

      {tab === "shortlist" && (
        <div className="space-y-4">
          <div className="card flex flex-wrap items-end gap-4">
            <div><label className="label" htmlFor="mode">{t("Shortlist rule")}</label>
              <select id="mode" className="input" value={job.policy.mode} onChange={(e) => setPolicy({ mode: e.target.value as Job["policy"]["mode"] })}>
                <option value="TOP_N">{t("The N best")}</option><option value="THRESHOLD">{t("All above a score")}</option><option value="TOP_N_FLOOR">{t("The N best above a score")}</option></select></div>
            {job.policy.mode !== "THRESHOLD" && (
              <div><label className="label" htmlFor="n">N</label>
                <div className="flex gap-1">{[5, 10, 20, 50].map((n) => <button key={n} className={job.policy.n === n ? "btn-primary" : "btn-secondary"} onClick={() => setPolicy({ n })}>{n}</button>)}
                  <input id="n" type="number" min={1} max={200} className="input w-20" defaultValue={job.policy.n} key={job.policy.n}
                         onBlur={(e) => { const n = Number(e.target.value); if (n >= 1 && n <= 200 && n !== job.policy.n) setPolicy({ n }); }} /></div></div>
            )}
            {job.policy.mode !== "TOP_N" && (
              <div><label className="label" htmlFor="thr">{t("Minimum score")}</label>
                <input id="thr" type="number" min={0} max={100} className="input w-24" defaultValue={job.policy.threshold} key={job.policy.threshold}
                       onBlur={(e) => { const v = Number(e.target.value); if (v >= 0 && v <= 100 && v !== job.policy.threshold) setPolicy({ threshold: v }); }} /></div>
            )}
            <p className="muted flex-1">{t("The AI only proposes. Nothing is sent to candidates without your action.")}</p>
          </div>
          {sl.notes.map((n, i) => <Alert key={i} kind="info">{note(t, n)}</Alert>)}
          {((sl.diff.entered?.length || 0) + (sl.diff.left?.length || 0)) > 0 && (
            <p className="muted">{t("Last update: {a} entered, {b} left the shortlist.", { a: sl.diff.entered?.length || 0, b: sl.diff.left?.length || 0 })}</p>
          )}
          {all.length + sl.processing.length === 0 && <div className="card text-center muted">{t("No application yet. Share the public page of the job.")}</div>}
          <Lane title={t("Shortlist")} rows={sl.members} ranked select={[selected, toggle]} />
          <Lane title={t("To check manually")} hint={t("CV hard to read: neither included nor excluded automatically.")} rows={sl.review_lane} select={[selected, toggle]} />
          <Lane title={t("Other candidates")} hint={t("Each one has an explanation too.")} rows={sl.below} select={[selected, toggle]} />
          <Lane title={t("Eliminatory criterion not met")} rows={sl.excluded} select={[selected, toggle]} />
          <Lane title={t("Being analysed")} rows={sl.processing} />
          <Lane title={t("Closed")} rows={sl.closed} />
          {chosen.length > 0 && (
            <div className="sticky bottom-3 flex flex-wrap items-center gap-3 rounded-xl border border-slate-300 bg-white p-3 shadow-lg">
              <span className="text-sm font-medium">{t("{n} selected", { n: chosen.length })}</span>
              <button className="btn-danger" onClick={() => setBulk(true)}>{t("Reject selected…")}</button>
              <button className="btn-secondary" onClick={() => setSelected(new Set())}>{t("Clear")}</button>
            </div>
          )}
          {bulk && (
            <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-labelledby="bulk-title">
              <form className="card max-h-[90vh] w-full max-w-2xl space-y-3 overflow-y-auto" onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                act(async () => {
                  const r = await api(`/jobs/${id}/bulk-reject`, { method: "POST", json: { application_ids: chosen.map((c) => c.id), reason: f.get("reason"), message: f.get("message") || "", reviewed: !!f.get("reviewed") } });
                  setBulk(false); setSelected(new Set());
                  setInfo(t("{a} rejected, {b} skipped (human review requested or already closed). E-mails are sent after the cancellation delay.", { a: r.rejected, b: r.skipped.length }));
                });
              }}>
                <h2 id="bulk-title" className="h2">{t("Grouped rejection: review before confirming")}</h2>
                <p className="muted">{t("You are taking this decision, not the AI. Check each candidate's score and main gap.")}</p>
                <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 text-sm">
                  {chosen.map((c) => (
                    <li key={c.id} className="flex items-center gap-3 px-3 py-2">
                      <ScoreBadge score={c.score} /><Link href={`/recruiter/applications/${c.id}`} target="_blank" className="font-medium text-brand-700 hover:underline">{c.name}</Link>
                      <span className="flex-1 truncate text-slate-500">{c.top_missing.length ? `${t("Missing")}: ${c.top_missing.join(" · ")}` : ""}</span>
                      {c.human_review_requested && <span className="chip bg-amber-100 text-amber-900">{t("will be skipped")}</span>}
                      {!c.opened && <span className="chip">{t("not opened")}</span>}
                    </li>))}
                </ul>
                <div><label className="label" htmlFor="reason">{t("Reason")}</label>
                  <select id="reason" name="reason" className="input" required>{Object.entries(REASONS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}</select></div>
                <div><label className="label" htmlFor="message">{t("Message to candidates (optional)")}</label><textarea id="message" name="message" className="input" maxLength={2000} /></div>
                <label className="flex items-start gap-2 text-sm"><input type="checkbox" name="reviewed" required className="mt-1" />{t("I have reviewed this list and I confirm these rejections.")}</label>
                <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={() => setBulk(false)}>{t("Cancel")}</button><button className="btn-danger">{t("Confirm the rejections")}</button></div>
              </form>
            </div>
          )}
        </div>
      )}

      {tab === "pipeline" && (
        <div className="grid gap-3 overflow-x-auto pb-2 lg:grid-cols-6" style={{ gridAutoFlow: "column", gridAutoColumns: "minmax(13rem,1fr)" }}>
          {["new", "shortlisted", "to_contact", "interview", "offer", "hired"].map((st) => {
            const rows = all.filter((r) => r.status === st).sort((a, b) => (b.score || 0) - (a.score || 0));
            return (
              <section key={st} className="rounded-xl border border-slate-200 bg-white">
                <header className="border-b border-slate-100 px-3 py-2 text-sm font-semibold">{t(STATUS_LABEL[st])} <span className="font-normal text-slate-500">({rows.length})</span></header>
                <ul className="space-y-2 p-2">{rows.map((r) => (
                  <li key={r.id} className="rounded-lg border border-slate-200 p-2 text-sm">
                    <div className="flex items-center justify-between gap-2"><Link href={`/recruiter/applications/${r.id}`} className="truncate font-medium text-brand-700 hover:underline">{r.name}</Link><ScoreBadge score={r.score} /></div>
                    <p className="muted truncate">{r.title}</p>
                  </li>))}</ul>
              </section>);
          })}
        </div>
      )}

      {tab === "analytics" && (analytics ? (
        <div className="grid gap-4 md:grid-cols-2">
          <div className="card"><h3 className="h2">{t("Overview")}</h3>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
              <dt className="muted">{t("Applications")}</dt><dd className="font-medium">{analytics.total}</dd>
              <dt className="muted">{t("Average score")}</dt><dd className="font-medium">{analytics.average_score ?? "—"}</dd>
              <dt className="muted">{t("Median time to score")}</dt><dd className="font-medium">{analytics.median_scoring_seconds != null ? `${Math.round(analytics.median_scoring_seconds)} s` : "—"}</dd>
              <dt className="muted">{t("Files opened before rejection")}</dt><dd className="font-medium">{analytics.opened_before_rejection != null ? `${Math.round(analytics.opened_before_rejection * 100)}%` : "—"}</dd>
              <dt className="muted">{t("Human review requests")}</dt><dd className="font-medium">{analytics.human_review_requests}</dd>
            </dl></div>
          <div className="card"><h3 className="h2">{t("Score distribution")}</h3>
            <div className="mt-3 flex h-32 items-end gap-1" role="img" aria-label={t("Score distribution")}>
              {analytics.score_histogram.map((n: number, i: number) => {
                const max = Math.max(1, ...analytics.score_histogram);
                return <div key={i} className="flex flex-1 flex-col items-center gap-1"><span className="text-xs text-slate-500">{n || ""}</span>
                  <div className="w-full rounded-t bg-brand-500" style={{ height: `${(n / max) * 90}px` }} /><span className="text-[10px] text-slate-400">{i * 10}</span></div>;
              })}</div></div>
          <div className="card"><h3 className="h2">{t("Required skills most often missing")}</h3>
            <div className="mt-3 space-y-2">{analytics.missing_required_skills.length === 0 && <p className="muted">—</p>}
              {analytics.missing_required_skills.map((m: any) => <Bar key={m.label} label={m.label} value={m.share} />)}</div>
            <p className="muted mt-2">{t("If most candidates miss a skill, consider making it nice-to-have.")}</p></div>
          <div className="card"><h3 className="h2">{t("By status")}</h3>
            <ul className="mt-2 space-y-1 text-sm">{Object.entries(analytics.by_status).map(([k, v]) => <li key={k} className="flex justify-between"><StatusChip status={k} /><span className="tabular-nums">{String(v)}</span></li>)}</ul>
            <h3 className="h2 mt-4">{t("CV language and reading method")}</h3>
            <p className="mt-1 text-sm text-slate-600">{Object.entries({ ...analytics.by_language }).map(([k, v]) => `${k}: ${v}`).join(" · ")} — {Object.entries(analytics.by_parsing_method).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p></div>
        </div>) : <Spinner />)}

      {tab === "talents" && (talents ? (
        <div className="space-y-3">
          <p className="muted">{t("Registered candidates who chose to be visible to recruiters and have not applied to this job.")}</p>
          {talents.length === 0 && <div className="card muted text-center">{t("No matching profile for now.")}</div>}
          {talents.map((p) => (
            <div key={p.profile_id} className="card flex flex-wrap items-center gap-3">
              <ScoreBadge score={p.score} />
              <div className="flex-1"><p className="font-medium">{p.name}</p><p className="muted">{p.title} · {t("{n} yrs", { n: p.years })} · {p.matched_skills.join(" · ")}</p></div>
              <button className="btn-secondary" onClick={() => act(() => api(`/jobs/${id}/talents/${p.profile_id}/invite`, { method: "POST" }), "Invitation sent.")}>{t("Invite to apply")}</button>
            </div>))}
        </div>) : <Spinner />)}

      {tab === "settings" && draft && (
        <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
          <div className="card space-y-4">
            <h3 className="h2">{t("Edit the job post")}</h3>
            {job.status === "published" && <Alert kind="warning">{t("Changing the requirements creates a new version and recalculates every score.")}</Alert>}
            <JobForm draft={draft} onChange={setDraft} />
            <button className="btn-primary" onClick={() => act(() => api(`/jobs/${id}`, { method: "PUT", json: draft }), "Saved.")}>{t("Save")}</button>
          </div>
          <aside className="space-y-4">
            <div className="card"><QualityReport quality={job.quality} /></div>
            <form className="card space-y-3" onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              act(() => api(`/jobs/${id}/weights`, { method: "PUT", json: { weights: Object.fromEntries(Object.keys(SUBSCORE_LABEL).map((k) => [k, Number(f.get(k)) / 100])) } }), "Weights saved. Scores are being recalculated.");
            }}>
              <h3 className="h2">{t("Score weights")}</h3>
              <p className="muted">{t("In percent. No criterion above 60. They are normalised to 100.")}</p>
              {Object.entries(SUBSCORE_LABEL).map(([k, label]) => (
                <div key={k} className="grid grid-cols-[1fr_5rem] items-center gap-2"><label className="text-sm" htmlFor={`w_${k}`}>{t(label)}</label>
                  <input id={`w_${k}`} name={k} type="number" min={0} max={60} step={1} className="input" defaultValue={Math.round((job.weights[k] || 0) * 100)} key={job.weights[k]} /></div>))}
              <button className="btn-secondary w-full">{t("Save the weights")}</button>
            </form>
            <div className="card space-y-2">
              <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={job.blind_mode}
                onChange={(e) => act(() => api(`/jobs/${id}/blind`, { method: "PUT", json: { blind_mode: e.target.checked } }))} />
                <span><span className="font-medium">{t("Anonymous screening")}</span><br /><span className="muted">{t("Hide names and contact details until you advance a candidate.")}</span></span></label>
              <button className="btn-secondary w-full" onClick={() => act(async () => { const j = await api(`/jobs/${id}/duplicate`, { method: "POST" }); window.location.href = `/recruiter/jobs/${j.id}`; })}>{t("Duplicate this job")}</button>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
