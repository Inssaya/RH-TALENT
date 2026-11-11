"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApp } from "@/components/Providers";
import { Spinner, StatusChip, useGuard } from "@/components/ui";
import { Job } from "@/lib/types";

export default function Recruiter() {
  const { t, locale } = useApp();
  const user = useGuard("recruiter");
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [stats, setStats] = useState<{ applications: number; average_score: number | null; jobs: Record<string, number> } | null>(null);
  useEffect(() => {
    if (!user) return;
    api<Job[]>("/jobs").then(setJobs);
    api("/org/analytics").then(setStats);
  }, [user]);
  if (!user || !jobs) return <Spinner />;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="h1">{t("My job posts")}</h1><p className="muted">{user.organization?.name}</p></div>
        <Link href="/recruiter/jobs/new" className="btn-primary">+ {t("New job post")}</Link>
      </div>
      {stats && (
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="card"><p className="muted">{t("Published jobs")}</p><p className="text-2xl font-semibold">{stats.jobs.published || 0}</p></div>
          <div className="card"><p className="muted">{t("Applications received")}</p><p className="text-2xl font-semibold">{stats.applications}</p></div>
          <div className="card"><p className="muted">{t("Average score")}</p><p className="text-2xl font-semibold">{stats.average_score ?? "—"}</p></div>
        </div>
      )}
      {jobs.length === 0 ? (
        <div className="card text-center"><p className="muted">{t("No job post yet. Create your first one in a few minutes.")}</p></div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-start text-slate-600"><tr>
              <th className="px-4 py-2 text-start font-medium">{t("Job")}</th><th className="px-4 py-2 text-start font-medium">{t("Status")}</th>
              <th className="px-4 py-2 text-start font-medium">{t("Applications")}</th><th className="px-4 py-2 text-start font-medium">{t("Shortlist")}</th>
              <th className="px-4 py-2 text-start font-medium">{t("Created")}</th></tr></thead>
            <tbody>{jobs.map((j) => (
              <tr key={j.id} className="border-t border-slate-100">
                <td className="px-4 py-3"><Link href={`/recruiter/jobs/${j.id}`} className="font-medium text-brand-700 hover:underline">{j.title || t("Untitled")}</Link>
                  <div className="muted">{[j.city, j.country].filter(Boolean).join(", ")}</div></td>
                <td className="px-4 py-3"><StatusChip status={j.status} /></td>
                <td className="px-4 py-3 tabular-nums">{j.applications}</td>
                <td className="px-4 py-3">{j.policy.mode === "THRESHOLD" ? `≥ ${j.policy.threshold}` : `Top ${j.policy.n}`}</td>
                <td className="px-4 py-3 text-slate-500">{new Date(j.created_at).toLocaleDateString(locale)}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
