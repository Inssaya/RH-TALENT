import Link from "next/link";
import { CONTRACT, REMOTE } from "@/lib/labels";

export type PublicJob = {
  slug: string; title: string; city: string; country: string; remote: string; contract_type: string;
  published_at: string | null; organization: { name: string; verified: boolean };
  match?: number; matched_skills?: string[]; applied?: boolean;
};

export default function JobCard({ job, t }: { job: PublicJob; t: (k: string) => string }) {
  return (
    <Link href={`/jobs/${job.slug}`} className="card block transition hover:border-brand-500 hover:shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-ink">{job.title}</h3>
          <p className="muted">
            {job.organization.name}
            {job.organization.verified && <span className="ms-1 text-emerald-700" title={t("Verified organization")}>✓</span>}
          </p>
        </div>
        {job.match !== undefined && (
          <span className="rounded-md bg-brand-50 px-2 py-1 text-sm font-semibold text-brand-700">{Math.round(job.match)}%</span>
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {(job.city || job.country) && <span className="chip">{[job.city, job.country].filter(Boolean).join(", ")}</span>}
        <span className="chip">{t(REMOTE[job.remote] || job.remote)}</span>
        {job.contract_type && <span className="chip">{t(CONTRACT[job.contract_type] || job.contract_type)}</span>}
        {job.applied && <span className="chip bg-emerald-100 text-emerald-800">{t("Applied")}</span>}
      </div>
      {job.matched_skills && job.matched_skills.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">{t("Why this job")}: {job.matched_skills.join(" · ")}</p>
      )}
    </Link>
  );
}
