"use client";
import { useApp } from "./Providers";

export function Alert({ kind = "error", children }: { kind?: "error" | "success" | "info" | "warning"; children: React.ReactNode }) {
  const cls = { error: "border-red-200 bg-red-50 text-red-800", success: "border-emerald-200 bg-emerald-50 text-emerald-800",
    info: "border-blue-200 bg-blue-50 text-blue-800", warning: "border-amber-200 bg-amber-50 text-amber-900" }[kind];
  return <div role={kind === "error" ? "alert" : "status"} className={`rounded-lg border px-3 py-2 text-sm ${cls}`}>{children}</div>;
}

export function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) return <span className="chip">…</span>;
  const cls = score >= 70 ? "bg-emerald-100 text-emerald-800" : score >= 50 ? "bg-amber-100 text-amber-900" : "bg-slate-200 text-slate-700";
  return <span className={`inline-flex min-w-12 justify-center rounded-md px-2 py-1 text-sm font-semibold tabular-nums ${cls}`}>{Math.round(score)}</span>;
}

export function Bar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  return (
    <div className="grid grid-cols-[9rem_1fr_3rem] items-center gap-2 text-sm">
      <span className="truncate text-slate-600">{label}</span>
      <div className="h-2 rounded bg-slate-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className="h-2 rounded bg-brand-600" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-end tabular-nums text-slate-700">{pct}%</span>
    </div>
  );
}

const STATUS_CLS: Record<string, string> = {
  new: "bg-slate-100 text-slate-700", shortlisted: "bg-brand-100 text-brand-700", to_contact: "bg-cyan-100 text-cyan-800",
  interview: "bg-violet-100 text-violet-800", offer: "bg-amber-100 text-amber-900", hired: "bg-emerald-100 text-emerald-800",
  rejected: "bg-red-100 text-red-800", withdrawn: "bg-slate-200 text-slate-600",
  in_review: "bg-blue-100 text-blue-800", not_retained: "bg-red-100 text-red-800", retained: "bg-emerald-100 text-emerald-800",
  draft: "bg-slate-100 text-slate-700", published: "bg-emerald-100 text-emerald-800", closed: "bg-slate-200 text-slate-600",
  suspended: "bg-red-100 text-red-800",
};
export const STATUS_LABEL: Record<string, string> = {
  new: "New", shortlisted: "AI shortlist", to_contact: "To contact", interview: "Interview", offer: "Offer made",
  hired: "Hired", rejected: "Rejected", withdrawn: "Withdrawn", in_review: "Under review", not_retained: "Not selected",
  retained: "Selected", draft: "Draft", published: "Published", closed: "Closed", suspended: "Suspended",
};

export function StatusChip({ status }: { status: string }) {
  const { t } = useApp();
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_CLS[status] || "bg-slate-100"}`}>{t(STATUS_LABEL[status] || status)}</span>;
}

export const FLAG_LABEL: Record<string, string> = {
  hidden_text: "Hidden text removed", injection_suspected: "Instruction-like text removed",
  low_parsing_quality: "CV hard to read: check manually", rule_based_assessment: "Assessed by rules (no LLM)",
  possible_duplicate: "Possible duplicate", skills_without_context: "Skills listed without context",
  experience_unknown: "Experience dates not found", knockout_unknown: "Eliminatory criterion could not be verified",
};

export function Spinner() {
  return <div className="py-10 text-center text-sm text-slate-500" role="status">…</div>;
}

export function useGuard(role: "candidate" | "recruiter" | "platform_admin") {
  const { user } = useApp();
  if (typeof window !== "undefined" && user === null) window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
  // Organization and platform admins must enrol two-factor authentication before anything else.
  if (typeof window !== "undefined" && user?.totp_setup_required) { window.location.href = "/security"; return null; }
  return user && user.role === role ? user : null;
}
