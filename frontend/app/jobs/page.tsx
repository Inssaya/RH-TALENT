import type { Metadata } from "next";
import Link from "next/link";
import JobCard, { PublicJob } from "@/components/JobCard";
import { serverApi } from "@/lib/api";
import { CONTRACT, REMOTE } from "@/lib/labels";
import { getT } from "@/lib/locale";

export const metadata: Metadata = { title: "Jobs" };

export default async function Jobs({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const { t } = await getT();
  const qs = new URLSearchParams(Object.entries(sp).filter(([, v]) => v) as [string, string][]);
  const data = await serverApi<{ total: number; page: number; items: PublicJob[] }>(`/public/jobs?${qs}`, 15);
  const page = Number(sp.page || 1);
  const link = (p: number) => `/jobs?${new URLSearchParams({ ...Object.fromEntries(qs), page: String(p) })}`;
  return (
    <div className="space-y-6">
      <h1 className="h1">{t("Jobs")}</h1>
      <form className="card grid gap-3 sm:grid-cols-[2fr_1fr_1fr_1fr_auto]" role="search">
        <div><label className="label" htmlFor="q">{t("Keywords")}</label><input id="q" name="q" defaultValue={sp.q} className="input" /></div>
        <div><label className="label" htmlFor="city">{t("City")}</label><input id="city" name="city" defaultValue={sp.city} className="input" /></div>
        <div>
          <label className="label" htmlFor="remote">{t("Work mode")}</label>
          <select id="remote" name="remote" defaultValue={sp.remote || ""} className="input">
            <option value="">{t("All")}</option>
            {Object.entries(REMOTE).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="contract">{t("Contract")}</label>
          <select id="contract" name="contract" defaultValue={sp.contract || ""} className="input">
            <option value="">{t("All")}</option>
            {Object.entries(CONTRACT).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}
          </select>
        </div>
        <button className="btn-primary self-end">{t("Search")}</button>
      </form>
      <p className="muted">{t("{n} job(s)", { n: data?.total ?? 0 })}</p>
      <div className="grid gap-3 sm:grid-cols-2">{data?.items.map((j) => <JobCard key={j.slug} job={j} t={t} />)}</div>
      <div className="flex justify-between">
        {page > 1 ? <Link className="btn-secondary" href={link(page - 1)}>← {t("Previous")}</Link> : <span />}
        {data && data.total > page * 20 ? <Link className="btn-secondary" href={link(page + 1)}>{t("Next")} →</Link> : <span />}
      </div>
    </div>
  );
}
