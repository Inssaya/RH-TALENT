"use client";
import { useApp } from "./Providers";
import { Alert } from "./ui";

export type Tracking = {
  id?: string; job: { title: string; slug: string; organization: string }; status: string; submitted_at: string;
  processing: string; human_review_requested: boolean; can_withdraw: boolean;
  explanation?: { reason: string; missing_skills: string[]; requirements: { text: string; status: string }[]; decided_by: string };
};

const REASON: Record<string, string> = {
  skills: "The required skills were not sufficiently demonstrated", experience: "The experience did not match the requirement",
  position_filled: "The position has been filled", other: "Another reason",
};

export default function TrackingDetail({ data, onHumanReview }: { data: Tracking; onHumanReview: () => void }) {
  const { t, locale } = useApp();
  return (
    <div className="space-y-3 text-sm">
      <p className="muted">{t("Submitted on")} {new Date(data.submitted_at).toLocaleDateString(locale)}</p>
      {data.status === "in_review" && <p>{t("Your application is being reviewed by the recruitment team.")}</p>}
      {data.status === "interview" && <Alert kind="success">{t("Good news: the recruiter wants to go further with you. They will contact you directly.")}</Alert>}
      {data.status === "retained" && <Alert kind="success">{t("Congratulations, your application was selected.")}</Alert>}
      {data.explanation && (
        <div className="space-y-2 rounded-lg bg-slate-50 p-3">
          <p className="font-medium">{t("Why your application was not selected")}</p>
          <p>{t("This decision was taken by a person on the recruitment team, with the help of an automated analysis of your CV.")}</p>
          {data.explanation.reason && <p>{t("Main reason")}: {t(REASON[data.explanation.reason] || data.explanation.reason)}</p>}
          {data.explanation.missing_skills.length > 0 && (
            <p>{t("Required skills not found in your CV")}: <span className="font-medium">{data.explanation.missing_skills.join(", ")}</span></p>
          )}
          {data.explanation.requirements.filter((r) => r.status !== "satisfied").length > 0 && (
            <ul className="list-disc ps-5">
              {data.explanation.requirements.filter((r) => r.status !== "satisfied").map((r) => (
                <li key={r.text}>{r.text} — {t(r.status === "partial" ? "partially demonstrated" : "not demonstrated")}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {data.human_review_requested
        ? <Alert kind="info">{t("You asked for a human review. The recruiter has been notified and must examine your application individually.")}</Alert>
        : data.status !== "withdrawn" && data.status !== "retained" && (
          <button className="btn-secondary" onClick={onHumanReview}>{t("Request a human review")}</button>
        )}
    </div>
  );
}
