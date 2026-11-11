"use client";
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert, Bar, FLAG_LABEL, ScoreBadge, Spinner, StatusChip, STATUS_LABEL, useGuard } from "@/components/ui";
import { LANGS } from "@/lib/labels";
import { SUBSCORE_LABEL } from "@/lib/types";

const REASONS = { skills: "Skills", experience: "Experience", position_filled: "Position filled", other: "Other" };
const REQ_CLS: Record<string, string> = { satisfied: "bg-emerald-100 text-emerald-800", partial: "bg-amber-100 text-amber-900", absent: "bg-slate-200 text-slate-700" };
const REQ_LABEL: Record<string, string> = { satisfied: "Demonstrated", partial: "Partially demonstrated", absent: "Not demonstrated" };
const HOW: Record<string, string> = { exact: "found", specific: "more specific skill found", no_context: "listed without context", related: "related skill", missing: "not found" };

export default function ApplicationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { t, locale } = useApp();
  const user = useGuard("recruiter");
  const [a, setA] = useState<any>(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [rejecting, setRejecting] = useState(false);

  const fail = (e: unknown) => setError(e instanceof ApiError ? t(String(e.detail)) : t("Something went wrong"));
  const load = useCallback(() => api(`/applications/${id}`).then(setA).catch(fail), [id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (user) load(); }, [user, load]);
  if (!user || !a) return error ? <Alert>{error}</Alert> : <Spinner />;

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setError(""); setInfo("");
    try { await fn(); if (ok) setInfo(t(ok)); await load(); } catch (e) { fail(e); }
  };
  const move = (to: string, extra: Record<string, unknown> = {}) => act(() => api(`/applications/${id}/move`, { method: "POST", json: { to, ...extra } }));
  const d = a.detail;
  return (
    <div className="space-y-5">
      <Link href={`/recruiter/jobs/${a.job.id}`} className="text-sm text-brand-700 hover:underline">← {a.job.title}</Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="h1">{a.name}</h1>
          <p className="muted">{a.title}{a.years ? ` · ${t("{n} yrs", { n: a.years })}` : ""}{a.email ? ` · ${a.email}` : ""}{a.phone ? ` · ${a.phone}` : ""}</p>
          {a.masked && <p className="muted">{t("Anonymous screening is on: identity appears once you advance this candidate.")}</p>}
        </div>
        <div className="flex items-center gap-2"><ScoreBadge score={a.score} /><StatusChip status={a.status} /></div>
      </div>
      {error && <Alert>{error}</Alert>}
      {info && <Alert kind="success">{info}</Alert>}
      {a.human_review_requested && <Alert kind="warning">{t("This candidate asked for a human review. Examine the application individually; it cannot be rejected in a batch.")}</Alert>}
      {a.flags.length > 0 && <Alert kind="warning">{a.flags.map((f: string) => t(FLAG_LABEL[f] || f)).join(" · ")}</Alert>}

      <div className="card flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{t("Your decision")}:</span>
        {a.allowed_moves.filter((m: string) => m !== "rejected").map((m: string) => <button key={m} className="btn-secondary" onClick={() => move(m)}>{t(STATUS_LABEL[m])}</button>)}
        {a.allowed_moves.includes("rejected") && <button className="btn-danger" onClick={() => setRejecting(true)}>{t("Reject…")}</button>}
        {a.pending_rejection && <button className="btn-secondary" onClick={() => act(() => api(`/applications/${id}/undo-reject`, { method: "POST" }), "Rejection cancelled.")}>{t("Cancel the rejection")}</button>}
        <button className="btn-secondary" onClick={() => act(() => api(`/applications/${id}/pin`, { method: "POST", json: { pinned: !a.pinned } }))}>{a.pinned ? t("Unpin") : t("Pin")}</button>
        {!a.masked && a.document && <a className="btn-secondary" href={`/api/applications/${id}/cv`}>{t("Download the CV")}</a>}
        {a.processing === "failed" && <button className="btn-secondary" onClick={() => act(() => api(`/applications/${id}/reprocess`, { method: "POST" }), "Analysis restarted.")}>{t("Retry the analysis")}</button>}
      </div>
      {rejecting && (
        <form className="card space-y-3 border-red-200" onSubmit={(e) => {
          e.preventDefault(); const f = new FormData(e.currentTarget);
          move("rejected", { reason: f.get("reason"), message: f.get("message") || "" }).then(() => { setRejecting(false); setInfo(t("Rejected. The e-mail is sent after the cancellation delay; you can still cancel.")); });
        }}>
          <h2 className="h2">{t("Reject this application")}</h2>
          <div><label className="label" htmlFor="reason">{t("Reason")}</label>
            <select id="reason" name="reason" className="input" required>{Object.entries(REASONS).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}</select></div>
          <div><label className="label" htmlFor="message">{t("Message to the candidate (optional)")}</label><textarea id="message" name="message" className="input" maxLength={2000} /></div>
          <div className="flex gap-2"><button className="btn-danger">{t("Confirm the rejection")}</button><button type="button" className="btn-secondary" onClick={() => setRejecting(false)}>{t("Cancel")}</button></div>
        </form>
      )}

      {!d ? <div className="card muted">{a.processing === "failed" ? t("The analysis failed.") : t("Being analysed")}</div> : (
        <div className="grid gap-5 lg:grid-cols-2">
          <section className="card space-y-3">
            <h2 className="h2">{t("Why this score")}</h2>
            <div className="space-y-2">{Object.entries(a.subscores as Record<string, number>).map(([k, v]) => (
              <div key={k}><Bar label={`${t(SUBSCORE_LABEL[k])} (${Math.round((d.weights[k] || 0) * 100)}%)`} value={v} /></div>))}</div>
            <p className="muted">{t("Score = weighted sum of the criteria above. Identity plays no part.")}</p>
            <p className="text-xs text-slate-400">{t("Job version")} {a.score_meta.job_version} · {t("weights")} v{a.score_meta.weights_version} · {a.score_meta.model} · {new Date(a.score_meta.computed_at).toLocaleString(locale)}</p>
            {d.experience && <p className="text-sm">{t("Relevant experience")}: <span className="font-medium">{d.experience.relevant_years}</span> / {d.experience.required_years} {t("years required")} ({t("total")} {d.experience.total_years})</p>}
            {d.knockouts?.length > 0 && <ul className="text-sm">{d.knockouts.map((k: any, i: number) => (
              <li key={i} className={k.passed ? "text-emerald-700" : "text-red-700"}>{k.passed ? "✓" : "✗"} {t("Eliminatory criterion")}: {k.kind} {String(k.value)} {k.unknown ? `(${t("could not be verified")})` : ""}</li>))}</ul>}
          </section>
          <section className="card space-y-3">
            <h2 className="h2">{t("What would raise the score")}</h2>
            {d.counterfactuals.length === 0 ? <p className="muted">{t("Nothing significant is missing.")}</p> : (
              <ul className="space-y-1 text-sm">{d.counterfactuals.map((c: any, i: number) => (
                <li key={i} className="flex justify-between gap-3"><span>{c.type === "skill" ? t("Skill") : t("Requirement")}: {c.label}</span><span className="tabular-nums text-emerald-700">+{c.gain}</span></li>))}</ul>)}
            <h2 className="h2 pt-2">{t("Skills")}</h2>
            <ul className="space-y-1 text-sm">{d.skills.map((s: any, i: number) => (
              <li key={i} className="flex items-center justify-between gap-2">
                <span>{s.match === 1 ? "✓" : s.match > 0 ? "◐" : "✗"} {s.label} {s.kind === "nice" && <span className="muted">({t("nice to have")})</span>}</span>
                <span className="muted">{t(HOW[s.how] || s.how)}</span></li>))}</ul>
          </section>
          <section className="card space-y-3 lg:col-span-2">
            <h2 className="h2">{t("Requirements, with evidence from the CV")}</h2>
            {d.requirements.length === 0 && <p className="muted">{t("This job lists no requirement.")}</p>}
            <ul className="space-y-3">{d.requirements.map((r: any) => (
              <li key={r.id} className="text-sm">
                <div className="flex flex-wrap items-center gap-2"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${REQ_CLS[r.status]}`}>{t(REQ_LABEL[r.status])}</span><span className="font-medium">{r.text}</span></div>
                {r.evidence && <blockquote className="mt-1 border-s-2 border-slate-300 ps-3 text-slate-600">« {r.evidence} »</blockquote>}
              </li>))}</ul>
            <form className="flex flex-wrap items-end gap-2 border-t border-slate-100 pt-3" onSubmit={(e) => {
              e.preventDefault(); const f = new FormData(e.currentTarget); const form = e.currentTarget;
              act(() => api(`/applications/${id}/feedback`, { method: "POST", json: { type: f.get("type"), comment: f.get("comment") } }), "Thank you. Your feedback will be reviewed by the team; it never changes the model automatically.").then(() => form.reset());
            }}>
              <div><label className="label" htmlFor="fb_type">{t("Disagree with the analysis?")}</label>
                <select id="fb_type" name="type" className="input"><option value="should_be_in">{t("Should be in the shortlist")}</option><option value="should_be_out">{t("Should not be in the shortlist")}</option><option value="requirement_wrong">{t("A requirement is wrongly assessed")}</option></select></div>
              <div className="flex-1"><label className="label" htmlFor="fb_comment">{t("Comment")}</label><input id="fb_comment" name="comment" required minLength={3} className="input" /></div>
              <button className="btn-secondary">{t("Send feedback")}</button>
            </form>
          </section>
          <section className="card space-y-2">
            <h2 className="h2">{t("Extracted profile")}</h2>
            {a.profile.summary && <p className="text-sm text-slate-700">{a.profile.summary}</p>}
            <h3 className="pt-2 text-sm font-semibold">{t("Experience")}</h3>
            <ul className="space-y-2 text-sm">{(a.profile.experiences || []).map((e: any, i: number) => (
              <li key={i}><span className="font-medium">{e.title}</span> <span className="muted">{e.start} → {e.end || t("today")}</span><p className="text-slate-600">{e.description}</p></li>))}</ul>
            <h3 className="pt-2 text-sm font-semibold">{t("Education")}</h3>
            <ul className="text-sm">{(a.profile.education || []).map((e: any, i: number) => <li key={i}>{e.degree}</li>)}</ul>
            <h3 className="pt-2 text-sm font-semibold">{t("Languages")}</h3>
            <p className="text-sm">{(a.profile.languages || []).map((l: any) => `${t(LANGS[l.code] || l.code)}${l.level ? ` (${l.level})` : ""}`).join(" · ") || "—"}</p>
          </section>
          <section className="card space-y-2">
            <h2 className="h2">{t("Document and history")}</h2>
            {a.document && <p className="text-sm">{t("Reading method")}: {a.document.method} · {t("language")}: {a.document.lang || "?"} · {t("reading quality")}: {Math.round(a.document.quality * 100)}%</p>}
            {a.document?.flags?.hidden_text && <Alert kind="warning">{t("Hidden text was found in the file and ignored")}: « {a.document.flags.hidden_text.join(" ").slice(0, 200)} »</Alert>}
            {a.document?.flags?.injection && <Alert kind="warning">{t("Instruction-like sentences were removed before analysis")}: « {a.document.flags.injection.join(" | ").slice(0, 200)} »</Alert>}
            <ol className="space-y-1 pt-2 text-sm">{a.events.map((e: any, i: number) => (
              <li key={i} className="flex flex-wrap gap-2"><span className="muted">{new Date(e.at).toLocaleString(locale)}</span>
                <span>{t(STATUS_LABEL[e.from] || e.from)} → {t(STATUS_LABEL[e.to] || e.to)}</span>
                <span className="chip">{t(e.actor === "human" ? "by a recruiter" : e.actor === "candidate" ? "by the candidate" : "automatic sort")}</span>{e.reason && e.actor === "human" && <span className="muted">{e.reason}</span>}</li>))}</ol>
          </section>
        </div>
      )}
    </div>
  );
}
