"""Two-way matching: jobs for a candidate, candidates for a job."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import emailer
from .ai.extraction import profile_text
from .ai.scoring import DEFAULT_WEIGHTS, compute_score
from .config import get_settings
from .models import Applicant, Application, CandidateProfile, Job, JobAlert, JobVersion, User, now


def _reasons(result: dict) -> list[str]:
    rows = result["detail"]["skills"]
    return [r["label"] for r in rows if r["match"] >= 1.0][:5]


def recommend_jobs(db: Session, profile: CandidateProfile, limit: int = 20, exclude_applied_user=None) -> list[dict]:
    """Nearest published jobs by embedding, re-ranked with the transparent score (no LLM call)."""
    if profile.embedding is None:
        return []
    q = (select(Job, JobVersion).join(JobVersion, (JobVersion.job_id == Job.id) & (JobVersion.number == Job.current_version))
         .where(Job.status == "published").order_by(JobVersion.embedding.cosine_distance(profile.embedding)).limit(60))
    applied = set()
    if exclude_applied_user:
        applied = set(db.scalars(select(Application.job_id).join(Applicant).where(Applicant.user_id == exclude_applied_user)))
    text = profile_text(profile.data)
    out = []
    for job, v in db.execute(q):
        r = compute_score(v.draft, DEFAULT_WEIGHTS, profile.data, text, job_emb=v.embedding,
                          profile_emb=profile.embedding, fast=True)
        if r["knockout_failed"]:
            continue
        out.append({"job": job, "score": r["total"], "matched_skills": _reasons(r), "applied": job.id in applied})
    return sorted(out, key=lambda x: -x["score"])[:limit]


def suggest_talents(db: Session, job: Job, version: JobVersion, limit: int = 15) -> list[dict]:
    """Profiles that opted in to recruiter visibility and have not applied to this job."""
    applied = select(Applicant.user_id).join(Application).where(Application.job_id == job.id, Applicant.user_id.is_not(None))
    q = (select(CandidateProfile, User).join(User, User.id == CandidateProfile.user_id)
         .where(CandidateProfile.visible_to_recruiters.is_(True), CandidateProfile.embedding.is_not(None),
                User.email_verified_at.is_not(None),
                CandidateProfile.user_id.notin_(applied))
         .order_by(CandidateProfile.embedding.cosine_distance(version.embedding)).limit(50))
    out = []
    for prof, user in db.execute(q):
        r = compute_score(version.draft, job.weights or DEFAULT_WEIGHTS, prof.data, profile_text(prof.data),
                          job_emb=version.embedding, profile_emb=prof.embedding, fast=True)
        if r["knockout_failed"]:
            continue
        out.append({"profile_id": str(prof.id), "name": user.full_name, "title": prof.data.get("title", ""),
                    "score": r["total"], "matched_skills": _reasons(r),
                    "years": round((prof.data.get("total_months") or 0) / 12, 1)})
    return sorted(out, key=lambda x: -x["score"])[:limit]


def send_job_alerts(db: Session) -> int:
    sent = 0
    week_ago = now() - timedelta(days=7)
    for alert, user, prof in db.execute(
            select(JobAlert, User, CandidateProfile).join(User, User.id == JobAlert.user_id)
            .join(CandidateProfile, CandidateProfile.user_id == User.id)
            .where(JobAlert.enabled.is_(True), User.email_verified_at.is_not(None))):
        recs = [r for r in recommend_jobs(db, prof, 5, user.id)
                if not r["applied"] and r["job"].published_at and r["job"].published_at >= (alert.last_sent_at or week_ago)]
        if not recs:
            continue
        base = get_settings().public_url
        lines = "\n".join(f"- {r['job'].title} ({r['job'].city or 'remote'}) : {base}/jobs/{r['job'].slug}" for r in recs)
        emailer.send(user.email, "TalentMatch : nouvelles offres pour vous / new jobs for you", lines)
        alert.last_sent_at = now()
        sent += 1
    return sent
