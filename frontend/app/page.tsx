import Link from "next/link";
import JobCard, { PublicJob } from "@/components/JobCard";
import { serverApi } from "@/lib/api";
import { getT } from "@/lib/locale";

export default async function Home() {
  const { t } = await getT();
  const data = await serverApi<{ total: number; items: PublicJob[] }>("/public/jobs", 30);
  return (
    <div className="space-y-12">
      <section className="rounded-2xl bg-gradient-to-br from-brand-700 to-brand-500 px-6 py-12 text-white sm:px-10">
        <h1 className="max-w-2xl text-3xl font-bold tracking-tight sm:text-4xl">{t("Hire faster. Explain every decision.")}</h1>
        <p className="mt-3 max-w-2xl text-brand-100">
          {t("The AI reads, ranks and explains every application. A human always takes the decision.")}
        </p>
        <form action="/jobs" className="mt-6 flex max-w-2xl flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor="q">{t("Job title, skill or company")}</label>
          <input id="q" name="q" className="input text-ink" placeholder={t("Job title, skill or company")} />
          <label className="sr-only" htmlFor="city">{t("City")}</label>
          <input id="city" name="city" className="input text-ink sm:max-w-44" placeholder={t("City")} />
          <button className="btn bg-white text-brand-700 hover:bg-brand-50">{t("Search")}</button>
        </form>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {[
          ["Publish in 5 minutes", "Describe the job by chat, voice, pasted text, file or form."],
          ["A shortlist you control", "Choose top-N or a score threshold. Every candidate gets an explanation."],
          ["Compliant by design", "No automatic rejection, audit log, GDPR rights, bias checks."],
        ].map(([title, body]) => (
          <div key={title} className="card">
            <h2 className="font-semibold">{t(title)}</h2>
            <p className="muted mt-1">{t(body)}</p>
          </div>
        ))}
      </section>

      <section>
        <div className="mb-4 flex items-end justify-between">
          <h2 className="h1">{t("Latest jobs")}</h2>
          <Link href="/jobs" className="text-sm font-medium text-brand-700 hover:underline">{t("See all jobs")} →</Link>
        </div>
        {data && data.items.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2">{data.items.slice(0, 8).map((j) => <JobCard key={j.slug} job={j} t={t} />)}</div>
        ) : (
          <p className="muted">{t("No job is published yet.")}</p>
        )}
      </section>
    </div>
  );
}
