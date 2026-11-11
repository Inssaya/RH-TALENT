import type { Metadata } from "next";
import { notFound } from "next/navigation";
import ApplyPanel from "@/components/ApplyPanel";
import { SITE_URL, serverApi } from "@/lib/api";
import { CONTRACT, EDUCATION, LANGS, REMOTE } from "@/lib/labels";
import { getT } from "@/lib/locale";

type Job = {
  slug: string; title: string; city: string; country: string; remote: string; contract_type: string;
  published_at: string | null; open: boolean;
  organization: { name: string; verified: boolean; sector: string; city: string; website: string; description: string };
  draft: {
    description: string; missions: string[]; min_years_experience: number; education_level: number;
    languages: { code: string; level: string }[]; skills_required: string[]; skills_nice: string[];
    requirements: { id: string; text: string }[]; salary_min: number | null; salary_max: number | null; currency: string; lang: string;
  };
};

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const job = await serverApi<Job>(`/public/jobs/${(await params).slug}`);
  if (!job) return { title: "Job" };
  return {
    title: `${job.title} · ${job.organization.name}`,
    description: job.draft.description.slice(0, 160),
    alternates: { canonical: `/jobs/${job.slug}` },
    openGraph: { title: job.title, description: job.draft.description.slice(0, 200), type: "article" },
  };
}

const EMPLOYMENT: Record<string, string> = {
  permanent: "FULL_TIME", fixed_term: "TEMPORARY", internship: "INTERN", apprenticeship: "INTERN", freelance: "CONTRACTOR",
};

export default async function JobPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const job = await serverApi<Job>(`/public/jobs/${slug}`);
  if (!job) notFound();
  const { t } = await getT();
  const d = job.draft;
  // schema.org JobPosting: lets search engines index the job without any multiposting API
  const jsonLd = {
    "@context": "https://schema.org", "@type": "JobPosting", title: job.title, description: d.description,
    datePosted: job.published_at, employmentType: EMPLOYMENT[job.contract_type] || undefined,
    hiringOrganization: { "@type": "Organization", name: job.organization.name, sameAs: job.organization.website || undefined },
    jobLocation: job.city ? { "@type": "Place", address: { "@type": "PostalAddress", addressLocality: job.city, addressCountry: job.country } } : undefined,
    jobLocationType: job.remote === "remote" ? "TELECOMMUTE" : undefined,
    url: `${SITE_URL}/jobs/${job.slug}`, directApply: true,
    baseSalary: d.salary_min ? { "@type": "MonetaryAmount", currency: d.currency || undefined,
      value: { "@type": "QuantitativeValue", minValue: d.salary_min, maxValue: d.salary_max || undefined, unitText: "MONTH" } } : undefined,
  };
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <article className="space-y-6" lang={d.lang}>
        <header className="card">
          <h1 className="h1">{job.title}</h1>
          <p className="mt-1 text-slate-600">
            {job.organization.name}
            {job.organization.verified && <span className="ms-1 text-emerald-700" title={t("Verified organization")}>✓</span>}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {(job.city || job.country) && <span className="chip">{[job.city, job.country].filter(Boolean).join(", ")}</span>}
            <span className="chip">{t(REMOTE[job.remote])}</span>
            {job.contract_type && <span className="chip">{t(CONTRACT[job.contract_type])}</span>}
            {d.min_years_experience > 0 && <span className="chip">{t("{n}+ years of experience", { n: d.min_years_experience })}</span>}
            {d.education_level > 0 && <span className="chip">{t(EDUCATION[d.education_level] || "Degree required")}</span>}
            {d.salary_min && <span className="chip">{d.salary_min.toLocaleString()}{d.salary_max ? ` – ${d.salary_max.toLocaleString()}` : ""} {d.currency}</span>}
          </div>
        </header>
        <section className="card space-y-4">
          <h2 className="h2">{t("About the job")}</h2>
          <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700">{d.description}</p>
          {d.missions.length > 0 && (<><h3 className="font-semibold">{t("Missions")}</h3>
            <ul className="list-disc space-y-1 ps-5 text-sm text-slate-700">{d.missions.map((m) => <li key={m}>{m}</li>)}</ul></>)}
          {d.requirements.length > 0 && (<><h3 className="font-semibold">{t("Requirements")}</h3>
            <ul className="list-disc space-y-1 ps-5 text-sm text-slate-700">{d.requirements.map((r) => <li key={r.id}>{r.text}</li>)}</ul></>)}
          {d.skills_required.length > 0 && (<><h3 className="font-semibold">{t("Required skills")}</h3>
            <div className="flex flex-wrap gap-2">{d.skills_required.map((s) => <span key={s} className="chip bg-brand-50 text-brand-700">{s}</span>)}</div></>)}
          {d.skills_nice.length > 0 && (<><h3 className="font-semibold">{t("Nice to have")}</h3>
            <div className="flex flex-wrap gap-2">{d.skills_nice.map((s) => <span key={s} className="chip">{s}</span>)}</div></>)}
          {d.languages.length > 0 && (<><h3 className="font-semibold">{t("Languages")}</h3>
            <div className="flex flex-wrap gap-2">{d.languages.map((l) => <span key={l.code} className="chip">{t(LANGS[l.code] || l.code)} · {l.level}</span>)}</div></>)}
        </section>
        {job.organization.description && (
          <section className="card"><h2 className="h2">{job.organization.name}</h2>
            <p className="mt-2 whitespace-pre-line text-sm text-slate-700">{job.organization.description}</p></section>
        )}
      </article>
      <aside><ApplyPanel slug={job.slug} open={job.open} /></aside>
    </div>
  );
}
