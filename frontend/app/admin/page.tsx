"use client";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Alert, Spinner, StatusChip, useGuard } from "@/components/ui";

type Tab = "overview" | "organizations" | "jobs" | "requests" | "audit" | "ai";

export default function Admin() {
  const { t, locale } = useApp();
  const user = useGuard("platform_admin");
  const [tab, setTab] = useState<Tab>("overview");
  const [data, setData] = useState<any>(null);
  const [chain, setChain] = useState<any>(null);
  const [error, setError] = useState("");
  const paths: Record<Tab, string> = { overview: "/admin/stats", organizations: "/admin/organizations", jobs: "/admin/jobs", requests: "/admin/requests", audit: "/admin/audit", ai: "/admin/ai" };
  const load = useCallback(() => { setData(null); api(paths[tab]).then(setData).catch((e: ApiError) => setError(String(e.detail))); }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (user) load(); }, [user, load]);
  if (!user) return <Spinner />;
  const act = (fn: () => Promise<unknown>) => fn().then(load).catch((e: ApiError) => setError(String(e.detail)));
  const tabs: [Tab, string][] = [["overview", "Overview"], ["organizations", "Organizations"], ["jobs", "Jobs"], ["requests", "GDPR requests"], ["audit", "Audit log"], ["ai", "AI supervision"]];
  const date = (s: string) => new Date(s).toLocaleString(locale);
  return (
    <div className="space-y-5">
      <h1 className="h1">{t("Administration")}</h1>
      <div className="flex flex-wrap gap-2 border-b border-slate-200" role="tablist">
        {tabs.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${tab === k ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500"}`}>{t(label)}</button>)}
      </div>
      {error && <Alert>{error}</Alert>}
      {!data ? <Spinner /> : (
        <>
          {tab === "overview" && <div className="grid gap-3 sm:grid-cols-4">{Object.entries(data).map(([k, v]) => <div key={k} className="card"><p className="muted">{k.replace(/_/g, " ")}</p><p className="text-2xl font-semibold">{String(v)}</p></div>)}</div>}
          {tab === "organizations" && (
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">{data.map((o: any) => (
              <li key={o.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <span className="flex-1 font-medium">{o.name} <span className="muted">{o.city} · {o.jobs} {t("Jobs").toLowerCase()}</span></span>
                {o.verified && <span className="chip bg-emerald-100 text-emerald-800">{t("Verified organization")}</span>}
                {o.status === "suspended" && <StatusChip status="suspended" />}
                <button className="btn-secondary" onClick={() => act(() => api(`/admin/organizations/${o.id}`, { method: "PUT", json: { verified: !o.verified } }))}>{t(o.verified ? "Unverify" : "Verify")}</button>
                <button className="btn-danger" onClick={() => act(() => api(`/admin/organizations/${o.id}`, { method: "PUT", json: { status: o.status === "active" ? "suspended" : "active" } }))}>{t(o.status === "active" ? "Suspend" : "Reactivate")}</button>
              </li>))}</ul>)}
          {tab === "jobs" && (
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">{data.map((j: any) => (
              <li key={j.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <a className="flex-1 font-medium text-brand-700 hover:underline" href={`/jobs/${j.slug}`} target="_blank">{j.title} <span className="muted">{j.organization}</span></a>
                <StatusChip status={j.status} />
                {j.status === "published" && <button className="btn-danger" onClick={() => act(() => api(`/admin/jobs/${j.id}`, { method: "PUT", json: { status: "suspended" } }))}>{t("Suspend")}</button>}
                {j.status === "suspended" && <button className="btn-secondary" onClick={() => act(() => api(`/admin/jobs/${j.id}`, { method: "PUT", json: { status: "published" } }))}>{t("Reactivate")}</button>}
              </li>))}</ul>)}
          {tab === "requests" && (
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">{data.length === 0 && <li className="muted px-4 py-3">—</li>}{data.map((r: any) => (
              <li key={r.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <span className="chip">{r.type}</span><span className="flex-1">{r.email} <span className="muted">{date(r.created_at)} · {t("due")} {date(r.due_at)}</span></span>
                <span className="chip">{r.status}</span>
                {r.status === "open" && r.type === "erasure" && <button className="btn-danger" onClick={() => window.confirm(t("Erase this person's data now?")) && act(() => api(`/admin/requests/${r.id}`, { method: "POST", json: { action: "execute_erasure" } }))}>{t("Execute the erasure")}</button>}
                {r.status === "open" && <button className="btn-secondary" onClick={() => act(() => api(`/admin/requests/${r.id}`, { method: "POST", json: { action: "complete" } }))}>{t("Mark as handled")}</button>}
              </li>))}</ul>)}
          {tab === "audit" && (
            <div className="space-y-3">
              <div className="flex items-center gap-3"><button className="btn-secondary" onClick={() => api("/admin/audit/verify").then(setChain)}>{t("Verify the integrity of the log")}</button>
                {chain && <Alert kind={chain.ok ? "success" : "error"}>{chain.ok ? t("Chain intact: {n} events checked", { n: chain.checked }) : t("Chain broken at event {n}", { n: chain.broken_at })}</Alert>}</div>
              <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white"><table className="w-full text-sm"><tbody>{data.map((e: any) => (
                <tr key={e.seq} className="border-t border-slate-100 first:border-0"><td className="px-3 py-2 tabular-nums text-slate-400">{e.seq}</td><td className="px-3 py-2 text-slate-500">{date(e.at)}</td>
                  <td className="px-3 py-2 font-medium">{e.action}</td><td className="px-3 py-2">{e.actor}</td><td className="px-3 py-2 text-slate-500">{e.resource}</td>
                  <td className="max-w-xs truncate px-3 py-2 text-xs text-slate-400">{JSON.stringify(e.payload)}</td></tr>))}</tbody></table></div>
            </div>)}
          {tab === "ai" && (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="card"><h2 className="h2">{t("Last 7 days")}</h2>
                <dl className="mt-2 grid grid-cols-2 gap-2 text-sm"><dt className="muted">{t("Rule-based (degraded) rate")}</dt><dd className="font-medium">{Math.round(data.degraded_rate * 100)}%</dd>
                  <dt className="muted">{t("Estimated AI cost")}</dt><dd className="font-medium">{data.estimated_cost_eur} €</dd>
                  <dt className="muted">{t("Average score")}</dt><dd className="font-medium">{data.average_score ? Math.round(data.average_score * 10) / 10 : "—"}</dd></dl></div>
              <div className="card"><h2 className="h2">{t("Calls by type")}</h2>
                <ul className="mt-2 space-y-1 text-sm">{data.calls.map((c: any, i: number) => <li key={i} className="flex justify-between"><span>{c.kind} {c.degraded && <span className="chip">rules</span>}</span><span className="tabular-nums">{c.count} · {c.avg_latency_ms} ms · {c.errors} err</span></li>)}</ul></div>
              <div className="card"><h2 className="h2">{t("Flags raised")}</h2><ul className="mt-2 space-y-1 text-sm">{Object.entries(data.flags).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><span>{String(v)}</span></li>)}</ul></div>
              <div className="card"><h2 className="h2">{t("Recruiter disagreements")}</h2><ul className="mt-2 space-y-1 text-sm">{Object.entries(data.feedback).length === 0 && <li className="muted">—</li>}{Object.entries(data.feedback).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><span>{String(v)}</span></li>)}</ul></div>
            </div>)}
        </>
      )}
    </div>
  );
}
