"use client";
import { useApp } from "./Providers";
import { Alert } from "./ui";
import { CONTRACT, EDUCATION, LANGS, REMOTE } from "@/lib/labels";
import { Draft, Quality, QUALITY_LABEL } from "@/lib/types";

const list = (s: string) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

export function QualityReport({ quality }: { quality: Quality | null | undefined }) {
  const { t } = useApp();
  if (!quality) return null;
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{t("Quality of the job post")}: <span className="tabular-nums">{quality.score}/100</span></p>
      {quality.warnings.length === 0 && <Alert kind="success">{t("Nothing to report.")}</Alert>}
      <ul className="space-y-1 text-sm">
        {quality.warnings.map((w, i) => (
          <li key={i} className={w.severity === "blocking" ? "text-red-700" : w.severity === "warning" ? "text-amber-800" : "text-slate-600"}>
            {w.severity === "blocking" ? "●" : w.severity === "warning" ? "▲" : "○"} {t(QUALITY_LABEL[w.code] || w.code)}{w.term ? ` : « ${w.term} »` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function JobForm({ draft, onChange }: { draft: Draft; onChange: (d: Draft) => void }) {
  const { t } = useApp();
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => onChange({ ...draft, [k]: v });
  const lang = (code: string) => draft.languages.find((l) => l.code === code);
  return (
    <div className="space-y-4">
      <div><label className="label" htmlFor="title">{t("Job title")} *</label>
        <input id="title" className="input" value={draft.title} onChange={(e) => set("title", e.target.value)} maxLength={200} /></div>
      <div><label className="label" htmlFor="description">{t("Description and missions")} *</label>
        <textarea id="description" className="input min-h-40" value={draft.description} onChange={(e) => set("description", e.target.value)} />
        <p className="muted mt-1">{draft.description.length} / 200+</p></div>
      <div className="grid gap-3 sm:grid-cols-4">
        <div><label className="label" htmlFor="city">{t("City")}</label><input id="city" className="input" value={draft.city} onChange={(e) => set("city", e.target.value)} /></div>
        <div><label className="label" htmlFor="country">{t("Country")}</label><input id="country" className="input" value={draft.country} onChange={(e) => set("country", e.target.value)} /></div>
        <div><label className="label" htmlFor="remote">{t("Work mode")}</label>
          <select id="remote" className="input" value={draft.remote} onChange={(e) => set("remote", e.target.value as Draft["remote"])}>
            {Object.entries(REMOTE).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}</select></div>
        <div><label className="label" htmlFor="contract">{t("Contract")} *</label>
          <select id="contract" className="input" value={draft.contract_type} onChange={(e) => set("contract_type", e.target.value)}>
            <option value="">—</option>{Object.entries(CONTRACT).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}</select></div>
      </div>
      <div><label className="label" htmlFor="skills_required">{t("Required skills (comma separated)")} *</label>
        <input id="skills_required" className="input" defaultValue={draft.skills_required.join(", ")} key={"r" + draft.skills_required.join("|")}
               onBlur={(e) => set("skills_required", list(e.target.value))} /></div>
      <div><label className="label" htmlFor="skills_nice">{t("Nice-to-have skills")}</label>
        <input id="skills_nice" className="input" defaultValue={draft.skills_nice.join(", ")} key={"n" + draft.skills_nice.join("|")}
               onBlur={(e) => set("skills_nice", list(e.target.value))} /></div>
      <div><label className="label" htmlFor="requirements">{t("Requirements (one per line, 15 max). Each one is assessed with evidence from the CV.")}</label>
        <textarea id="requirements" className="input min-h-24" defaultValue={draft.requirements.map((r) => r.text).join("\n")}
                  key={"q" + draft.requirements.map((r) => r.id).join("|")}
                  onBlur={(e) => set("requirements", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 15).map((text, i) => ({
                    id: draft.requirements.find((r) => r.text === text)?.id || `r${Date.now().toString(36)}${i}`, text, type: "requirement" as const })))} /></div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div><label className="label" htmlFor="years">{t("Minimum years of experience")}</label>
          <input id="years" type="number" min={0} max={40} className="input" value={draft.min_years_experience} onChange={(e) => set("min_years_experience", Number(e.target.value))} /></div>
        <div><label className="label" htmlFor="edu">{t("Minimum education")}</label>
          <select id="edu" className="input" value={draft.education_level} onChange={(e) => set("education_level", Number(e.target.value))}>
            {Object.entries(EDUCATION).map(([k, v]) => <option key={k} value={k}>{t(v)}</option>)}</select></div>
        <div><label className="label" htmlFor="joblang">{t("Language of the post")}</label>
          <select id="joblang" className="input" value={draft.lang} onChange={(e) => set("lang", e.target.value as Draft["lang"])}>
            <option value="fr">Français</option><option value="en">English</option><option value="ar">العربية</option></select></div>
      </div>
      <fieldset>
        <legend className="label">{t("Required languages")}</legend>
        <div className="flex flex-wrap gap-3">
          {["fr", "en", "ar", "es", "de"].map((code) => (
            <label key={code} className="flex items-center gap-1 text-sm">
              <input type="checkbox" checked={!!lang(code)} onChange={(e) => set("languages", e.target.checked
                ? [...draft.languages, { code, level: "B2" }] : draft.languages.filter((l) => l.code !== code))} />
              {t(LANGS[code])}
              {lang(code) && (
                <select aria-label={t("Level")} className="rounded border border-slate-300 px-1 py-0.5 text-xs" value={lang(code)!.level}
                        onChange={(e) => set("languages", draft.languages.map((l) => l.code === code ? { ...l, level: e.target.value } : l))}>
                  {["A2", "B1", "B2", "C1", "C2"].map((l) => <option key={l}>{l}</option>)}</select>
              )}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-3">
        <div><label className="label" htmlFor="smin">{t("Salary min (monthly)")}</label><input id="smin" type="number" min={0} className="input" value={draft.salary_min ?? ""} onChange={(e) => set("salary_min", e.target.value ? Number(e.target.value) : null)} /></div>
        <div><label className="label" htmlFor="smax">{t("Salary max")}</label><input id="smax" type="number" min={0} className="input" value={draft.salary_max ?? ""} onChange={(e) => set("salary_max", e.target.value ? Number(e.target.value) : null)} /></div>
        <div><label className="label" htmlFor="cur">{t("Currency")}</label><input id="cur" className="input" maxLength={6} value={draft.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} /></div>
      </div>
      <fieldset className="rounded-lg border border-slate-200 p-3">
        <legend className="px-1 text-sm font-medium">{t("Eliminatory criteria (optional)")}</legend>
        <p className="muted mb-2">{t("A candidate who clearly fails one is set aside from the shortlist, but stays visible and is never rejected automatically.")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div><label className="label" htmlFor="ko_years">{t("Minimum years (eliminatory)")}</label>
            <input id="ko_years" type="number" min={0} max={40} className="input" value={(draft.knockouts.find((k) => k.kind === "min_years")?.value as number) ?? ""}
                   onChange={(e) => set("knockouts", [...draft.knockouts.filter((k) => k.kind !== "min_years"), ...(e.target.value ? [{ kind: "min_years", value: Number(e.target.value) }] : [])])} /></div>
          <div><label className="label" htmlFor="ko_skill">{t("Mandatory skill (eliminatory)")}</label>
            <input id="ko_skill" className="input" defaultValue={(draft.knockouts.find((k) => k.kind === "skill")?.value as string) ?? ""}
                   onBlur={(e) => set("knockouts", [...draft.knockouts.filter((k) => k.kind !== "skill"), ...(e.target.value.trim() ? [{ kind: "skill", value: e.target.value.trim() }] : [])])} /></div>
        </div>
      </fieldset>
    </div>
  );
}
