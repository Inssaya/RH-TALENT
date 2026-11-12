"""Recruiter API: jobs, shortlist, applications and human decisions.
Every query is scoped to the caller's organization; a foreign id answers 404."""
import uuid
from collections import Counter

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit, storage
from ..ai import jobs_ai, parsing
from ..ai.scoring import DEFAULT_WEIGHTS, validate_weights
from ..db import get_db
from ..deps import OrgContext, org_context
from ..matching import suggest_talents
from ..models import (
    Application,
    ApplicationEvent,
    Document,
    Feedback,
    Job,
    JobVersion,
    Score,
    ShortlistSnapshot,
    now,
)
from ..ratelimit import client_ip, hit
from ..schemas import BulkRejectIn, ChatIn, FeedbackIn, JobDraft, MoveIn, PolicyIn
from ..services import (
    FINAL,
    HUMAN_TRANSITIONS,
    current_version,
    job_counts,
    new_job_version,
    refresh_shortlist,
    transition,
    undo_rejection,
    unique_slug,
)
from ..tasks import enqueue, rescore

router = APIRouter(tags=["recruiter"])


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(404, "Not found") from exc


def get_job(db: Session, ctx: OrgContext, job_id: str) -> Job:
    job = db.get(Job, _uuid(job_id))
    if not job or job.organization_id != ctx.org.id:
        raise HTTPException(404, "Not found")
    return job


def get_app(db: Session, ctx: OrgContext, app_id: str) -> Application:
    app = db.get(Application, _uuid(app_id))
    if not app or app.job.organization_id != ctx.org.id:
        raise HTTPException(404, "Not found")
    return app


def job_out(job: Job, draft: dict | None = None, count: int = 0) -> dict:
    return {"id": str(job.id), "slug": job.slug, "status": job.status, "title": job.title, "city": job.city,
            "country": job.country, "remote": job.remote, "contract_type": job.contract_type,
            "version": job.current_version, "blind_mode": job.blind_mode,
            "policy": {"mode": job.sl_mode, "n": job.sl_n, "threshold": job.sl_threshold, "cap": job.sl_cap},
            "weights": job.weights or DEFAULT_WEIGHTS, "weights_version": job.weights_version,
            "published_at": job.published_at.isoformat() if job.published_at else None,
            "created_at": job.created_at.isoformat(), "applications": count,
            **({"draft": draft} if draft is not None else {})}


# ---------------------------------------------------------------- job authoring
@router.post("/jobs/extract")
async def extract(request: Request, file: UploadFile | None = File(None), ctx: OrgContext = Depends(org_context)):
    """Channels 'pasted text' and 'file': both return a JobDraft for review in the form."""
    if file is not None:
        data = await file.read()
        try:
            text = parsing.parse_document(data, file.filename or "").text
        except parsing.UnsupportedFile as exc:
            raise HTTPException(415, str(exc)) from exc
    else:
        text = str((await request.json()).get("text", ""))
    if len(text.strip()) < 30:
        raise HTTPException(422, "Not enough text to extract a job post")
    draft = JobDraft(**jobs_ai.extract_job_rules(text)).model_dump()
    return {"draft": draft, "quality": jobs_ai.quality_report(draft)}


@router.post("/jobs/chat")
def chat(body: ChatIn, ctx: OrgContext = Depends(org_context)):
    if not hit(f"chat:{ctx.user.id}", 30, 600):
        raise HTTPException(429, "Too many messages, please wait a few minutes")
    out = jobs_ai.chat_turn(body.draft.model_dump(), body.message, body.asked_field, body.locked, ctx.org.id)
    out["draft"] = JobDraft(**out["draft"]).model_dump()
    out["quality"] = jobs_ai.quality_report(out["draft"])
    return out


@router.post("/jobs/quality")
def quality(draft: JobDraft, ctx: OrgContext = Depends(org_context)):
    return jobs_ai.quality_report(draft.model_dump())


def _clean(draft: JobDraft) -> dict:
    d = draft.model_dump()
    for r in d["requirements"]:
        r["id"] = r["id"] or "r" + uuid.uuid4().hex[:8]
    d["skills_required"] = [s.strip() for s in d["skills_required"] if s.strip()]
    d["skills_nice"] = [s.strip() for s in d["skills_nice"] if s.strip()]
    return d


@router.get("/jobs")
def list_jobs(ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.organization_id == ctx.org.id).order_by(Job.created_at.desc())).all()
    counts = job_counts(db, [j.id for j in jobs])
    return [job_out(j, count=counts.get(j.id, 0)) for j in jobs]


@router.post("/jobs")
def create_job(draft: JobDraft, request: Request, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    d = _clean(draft)
    job = Job(organization_id=ctx.org.id, slug=unique_slug(db, Job, f"{d['title'] or 'offre'}-{ctx.org.name}"),
              created_by=ctx.user.id, weights=dict(DEFAULT_WEIGHTS))
    db.add(job)
    db.flush()
    new_job_version(db, job, d, ctx.user)
    audit.log(db, "job.created", actor=ctx.user, resource=f"job:{job.id}", organization_id=ctx.org.id,
              ip=client_ip(request))
    return job_out(job, d)


@router.get("/jobs/{job_id}")
def read_job(job_id: str, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    job = get_job(db, ctx, job_id)
    v = current_version(db, job)
    out = job_out(job, v.draft if v else None, job_counts(db, [job.id]).get(job.id, 0))
    out["quality"] = jobs_ai.quality_report(v.draft) if v else None
    return out


_SCORING_FIELDS = ["title", "description", "missions", "min_years_experience", "education_level", "languages",
                   "skills_required", "skills_nice", "requirements", "knockouts", "city", "country", "remote"]


@router.put("/jobs/{job_id}")
def update_job(job_id: str, draft: JobDraft, request: Request, ctx: OrgContext = Depends(org_context),
               db: Session = Depends(get_db)):
    job = get_job(db, ctx, job_id)
    d = _clean(draft)
    cur = current_version(db, job)
    changed = not cur or any(cur.draft.get(k) != d.get(k) for k in _SCORING_FIELDS)
    if job.status == "draft" and cur:
        from ..ai.embeddings import embed
        from ..ai.scoring import job_text
        cur.draft, cur.embedding = d, embed(job_text(d))
        job.title, job.city, job.country, job.remote, job.contract_type = d["title"], d["city"], d["country"], d["remote"], d["contract_type"]
    elif changed:
        # a change in requirements creates a new immutable version and invalidates the scores
        new_job_version(db, job, d, ctx.user)
        audit.log(db, "job.new_version", actor=ctx.user, resource=f"job:{job.id}", organization_id=ctx.org.id,
                  ip=client_ip(request), payload={"version": job.current_version})
        db.commit()
        enqueue(rescore, str(job.id))
    else:
        cur.draft = d
    return job_out(job, d)


@router.post("/jobs/{job_id}/publish")
def publish(job_id: str, request: Request, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    job = get_job(db, ctx, job_id)
    v = current_version(db, job)
    report = jobs_ai.quality_report(v.draft)
    if not report["publishable"]:
        raise HTTPException(422, {"message": "The job post is incomplete", "quality": report})
    if job.status == "suspended":
        raise HTTPException(403, "This job was suspended by moderation")
    job.status, job.published_at = "published", job.published_at or now()
    audit.log(db, "job.published", actor=ctx.user, resource=f"job:{job.id}", organization_id=ctx.org.id,
              ip=client_ip(request))
    return job_out(job, v.draft)


@router.post("/jobs/{job_id}/close")
def close(job_id: str, request: Request, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    job = get_job(db, ctx, job_id)
    job.status = "closed"
    audit.log(db, "job.closed", actor=ctx.user, resource=f"job:{job.id}", organization_id=ctx.org.id, ip=client_ip(request))
    return job_out(job)


@router.post("/jobs/{job_id}/duplicate")
def duplicate(job_id: str, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    src = get_job(db, ctx, job_id)
    v = current_version(db, src)
    d = {**v.draft, "title": f"{v.draft.get('title', '')} (copie)"}
    job = Job(organization_id=ctx.org.id, slug=unique_slug(db, Job, f"{d['title']}-{ctx.org.name}"),
              created_by=ctx.user.id, weights=src.weights, sl_mode=src.sl_mode, sl_n=src.sl_n,
              sl_threshold=src.sl_threshold, sl_cap=src.sl_cap)
    db.add(job)
    db.flush()
    new_job_version(db, job, d, ctx.user)
    return job_out(job, d)


# ---------------------------------------------------------------- shortlist settings
@router.put("/jobs/{job_id}/policy")
def set_policy(job_id: str, body: PolicyIn, request: Request, ctx: OrgContext = Depends(org_context),
               db: Session = Depends(get_db)):
    job = get_job(db, ctx, job_id)
    job.sl_mode, job.sl_n, job.sl_threshold, job.sl_cap = body.mode, body.n, body.threshold, body.cap
    audit.log(db, "shortlist.policy_changed", actor=ctx.user, resource=f"job:{job.id}", organization_id=ctx.org.id,
              ip=client_ip(request), payload=body.model_dump())
    db.flush()
    refresh_shortlist(db, job, reason="policy")
    return job_out(job)


class WeightsIn(BaseModel):
    weights: dict[str, float]


@router.put("/jobs/{job_id}/weights")
def set_weights(job_id: str, body: WeightsIn, request: Request, ctx: OrgContext = Depends(org_context),
                db: Session = Depends(get_db)):
    job = get_job(db, ctx, job_id)
    try:
        job.weights = validate_weights(body.weights)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    job.weights_version += 1
    audit.log(db, "scoring.weights_changed", actor=ctx.user, resource=f"job:{job.id}", organization_id=ctx.org.id,
              ip=client_ip(request), payload=job.weights)
    db.commit()
    enqueue(rescore, str(job.id))
    return job_out(job)


class BlindIn(BaseModel):
    blind_mode: bool


@router.put("/jobs/{job_id}/blind")
def set_blind(job_id: str, body: BlindIn, request: Request, ctx: OrgContext = Depends(org_context),
              db: Session = Depends(get_db)):
    job = get_job(db, ctx, job_id)
    job.blind_mode = body.blind_mode
    audit.log(db, "job.blind_mode", actor=ctx.user, resource=f"job:{job.id}", organization_id=ctx.org.id,
              ip=client_ip(request), payload={"enabled": body.blind_mode})
    return job_out(job)


# ---------------------------------------------------------------- applications
def _identity(app: Application, blind: bool) -> dict:
    """Blind view: identity is hidden until the candidate has been advanced by a human."""
    if blind and app.status in ("new", "shortlisted", "rejected"):
        return {"name": f"Candidat·e #{app.id.hex[:5].upper()}", "email": None, "phone": None, "masked": True}
    return {"name": app.applicant.full_name or app.profile.get("full_name") or app.applicant.email,
            "email": app.applicant.email, "phone": app.applicant.phone or app.profile.get("phone"), "masked": False}


def app_row(app: Application, blind: bool) -> dict:
    s = app.score
    return {"id": str(app.id), **_identity(app, blind), "status": app.status, "processing": app.processing,
            "pinned": app.pinned, "source": app.source, "submitted_at": app.submitted_at.isoformat(),
            "title": app.profile.get("title", ""), "years": round((app.profile.get("total_months") or 0) / 12, 1),
            "human_review_requested": app.human_review_requested, "opened": app.opened_by_recruiter,
            "pending_rejection": bool(app.pending_rejection_at),
            "score": s.total if s else None, "subscores": s.subscores if s else None,
            "knockout_failed": s.knockout_failed if s else False, "flags": s.flags if s else [],
            "top_missing": [c["label"] for c in (s.detail.get("counterfactuals") or [])[:2]] if s else [],
            "quality": app.document.quality if app.document else None}


@router.get("/jobs/{job_id}/shortlist")
def shortlist(job_id: str, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    """The explained shortlist plus every other candidate, grouped by lane."""
    job = get_job(db, ctx, job_id)
    snap = refresh_shortlist(db, job, reason="view")
    apps = db.scalars(select(Application).where(Application.job_id == job.id)).all()
    rows = {str(a.id): app_row(a, job.blind_mode) for a in apps}
    members = [rows[i] for i in (snap.members if snap else []) if i in rows]
    member_ids = {r["id"] for r in members}
    review = [rows[i] for i in (snap.review_lane if snap else []) if i in rows]
    review_ids = {r["id"] for r in review}
    rest = sorted((r for i, r in rows.items() if i not in member_ids and i not in review_ids),
                  key=lambda r: -(r["score"] or -1))
    return {
        "job": job_out(job, count=len(apps)),
        "members": members, "review_lane": review,
        "below": [r for r in rest if r["status"] not in ("rejected", "withdrawn") and not r["knockout_failed"]
                  and r["processing"] == "scored"],
        "excluded": [r for r in rest if r["knockout_failed"] and r["status"] not in ("rejected", "withdrawn")],
        "processing": [r for r in rest if r["processing"] != "scored"],
        "closed": [r for r in rest if r["status"] in ("rejected", "withdrawn")],
        "cutoff_score": snap.cutoff_score if snap else None, "notes": snap.notes if snap else [],
        "diff": snap.diff if snap else {}, "snapshot_at": snap.created_at.isoformat() if snap else None,
    }


@router.get("/jobs/{job_id}/snapshots")
def snapshots(job_id: str, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    job = get_job(db, ctx, job_id)
    snaps = db.scalars(select(ShortlistSnapshot).where(ShortlistSnapshot.job_id == job.id)
                       .order_by(ShortlistSnapshot.created_at.desc()).limit(30))
    return [{"id": str(s.id), "at": s.created_at.isoformat(), "policy": s.policy, "size": len(s.members),
             "cutoff_score": s.cutoff_score, "diff": s.diff, "notes": s.notes} for s in snaps]


@router.get("/applications/{app_id}")
def read_application(app_id: str, request: Request, ctx: OrgContext = Depends(org_context),
                     db: Session = Depends(get_db)):
    app = get_app(db, ctx, app_id)
    if not app.opened_by_recruiter:
        app.opened_by_recruiter = True
    audit.log(db, "application.opened", actor=ctx.user, resource=f"application:{app.id}",
              organization_id=ctx.org.id, ip=client_ip(request))
    s = app.score
    events = db.scalars(select(ApplicationEvent).where(ApplicationEvent.application_id == app.id)
                        .order_by(ApplicationEvent.created_at)).all()
    blind = app.job.blind_mode
    ident = _identity(app, blind)
    profile = dict(app.profile)
    if ident["masked"]:
        for k in ("full_name", "email", "phone"):
            profile.pop(k, None)
    return {
        **app_row(app, blind), "job": {"id": str(app.job.id), "title": app.job.title, "version": app.job.current_version},
        "profile": profile,
        "detail": s.detail if s else None,
        "score_meta": {"job_version": s.job_version, "weights_version": s.weights_version, "model": s.model_id,
                       "prompt_version": s.prompt_version, "computed_at": s.computed_at.isoformat()} if s else None,
        "document": {"filename": None if ident["masked"] else app.document.filename, "method": app.document.method,
                     "lang": app.document.lang, "quality": app.document.quality,
                     "flags": app.document.flags} if app.document else None,
        "events": [{"from": e.from_status, "to": e.to_status, "actor": e.actor_kind, "reason": e.reason,
                    "at": e.created_at.isoformat()} for e in events],
        "allowed_moves": sorted(HUMAN_TRANSITIONS.get(app.status, set())),
        "rejection_reason": app.rejection_reason,
    }


@router.get("/applications/{app_id}/cv")
def download_cv(app_id: str, request: Request, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    app = get_app(db, ctx, app_id)
    if not app.document:
        raise HTTPException(404, "Not found")
    if app.job.blind_mode and app.status in ("new", "shortlisted", "rejected"):
        raise HTTPException(403, "Blind mode: advance the candidate to see the original CV")
    audit.log(db, "application.cv_downloaded", actor=ctx.user, resource=f"application:{app.id}",
              organization_id=ctx.org.id, ip=client_ip(request))
    doc: Document = app.document
    return Response(storage.get(doc.storage_key), media_type=doc.mime,
                    headers={"Content-Disposition": f'attachment; filename="{doc.filename}"',
                             "X-Content-Type-Options": "nosniff"})


@router.post("/applications/{app_id}/move")
def move(app_id: str, body: MoveIn, request: Request, ctx: OrgContext = Depends(org_context),
         db: Session = Depends(get_db)):
    app = get_app(db, ctx, app_id)
    transition(db, app, body.to, ctx.user, body.reason, body.message, client_ip(request))
    return app_row(app, app.job.blind_mode)


@router.post("/applications/{app_id}/undo-reject")
def undo(app_id: str, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    app = get_app(db, ctx, app_id)
    undo_rejection(db, app, ctx.user)
    return app_row(app, app.job.blind_mode)


@router.post("/jobs/{job_id}/bulk-reject")
def bulk_reject(job_id: str, body: BulkRejectIn, request: Request, ctx: OrgContext = Depends(org_context),
                db: Session = Depends(get_db)):
    """Grouped rejection: allowed only after the recruiter has reviewed the list with reasons.
    Candidates who asked for a human review are never rejected in a batch."""
    job = get_job(db, ctx, job_id)
    if not body.reviewed:
        raise HTTPException(422, "You must review the list of candidates and reasons before a grouped rejection")
    apps = [get_app(db, ctx, i) for i in body.application_ids]
    if any(a.job_id != job.id for a in apps):
        raise HTTPException(404, "Not found")
    skipped, done = [], 0
    for a in apps:
        if a.human_review_requested or a.status in FINAL:
            skipped.append(str(a.id))
            continue
        transition(db, a, "rejected", ctx.user, body.reason, body.message, client_ip(request))
        done += 1
    audit.log(db, "application.bulk_rejection", actor=ctx.user, resource=f"job:{job.id}", organization_id=ctx.org.id,
              ip=client_ip(request),
              payload={"count": done, "skipped": len(skipped), "opened": sum(1 for a in apps if a.opened_by_recruiter)})
    return {"rejected": done, "skipped": skipped}


class PinIn(BaseModel):
    pinned: bool


@router.post("/applications/{app_id}/pin")
def pin(app_id: str, body: PinIn, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    app = get_app(db, ctx, app_id)
    app.pinned = body.pinned
    return {"pinned": app.pinned}


@router.post("/applications/{app_id}/feedback")
def feedback(app_id: str, body: FeedbackIn, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    """Disagreements feed a reviewed set used for recalibration. They never retrain anything automatically."""
    app = get_app(db, ctx, app_id)
    db.add(Feedback(application_id=app.id, recruiter_id=ctx.user.id, type=body.type, comment=body.comment))
    return {"ok": True}


@router.post("/applications/{app_id}/reprocess")
def reprocess(app_id: str, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    from ..tasks import process
    app = get_app(db, ctx, app_id)
    app.processing = "queued"
    db.commit()
    enqueue(process, str(app.id))
    return {"ok": True}


# ---------------------------------------------------------------- analytics and talents
@router.get("/jobs/{job_id}/analytics")
def analytics(job_id: str, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    job = get_job(db, ctx, job_id)
    apps = db.scalars(select(Application).where(Application.job_id == job.id)).all()
    scores = [a.score for a in apps if a.score]
    hist = [0] * 10
    for s in scores:
        hist[min(9, int(s.total // 10))] += 1
    missing: Counter = Counter()
    for s in scores:
        for r in s.detail.get("skills", []):
            if r["match"] < 1 and r["kind"] == "required":
                missing[r["label"]] += 1
    days: Counter = Counter(a.submitted_at.date().isoformat() for a in apps)
    delays = [(a.scored_at - a.submitted_at).total_seconds() for a in apps if a.scored_at]
    by_lang: Counter = Counter((a.document.lang or "?") for a in apps if a.document)
    by_method: Counter = Counter((a.document.method or "?") for a in apps if a.document)
    rejected = [a for a in apps if a.status == "rejected"]
    return {
        "total": len(apps), "by_status": dict(Counter(a.status for a in apps)),
        "score_histogram": hist, "average_score": round(sum(s.total for s in scores) / len(scores), 1) if scores else None,
        "missing_required_skills": [{"label": k, "count": v, "share": round(v / len(scores), 2)}
                                    for k, v in missing.most_common(8)],
        "per_day": sorted(days.items()), "median_scoring_seconds": sorted(delays)[len(delays) // 2] if delays else None,
        "by_language": dict(by_lang), "by_parsing_method": dict(by_method),
        "flags": dict(Counter(f for s in scores for f in s.flags)),
        "opened_before_rejection": round(sum(1 for a in rejected if a.opened_by_recruiter) / len(rejected), 2) if rejected else None,
        "human_review_requests": sum(1 for a in apps if a.human_review_requested),
    }


@router.get("/org/analytics")
def org_analytics(ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.organization_id == ctx.org.id)).all()
    ids = [j.id for j in jobs]
    by_status = dict(db.execute(select(Application.status, func.count()).where(Application.job_id.in_(ids))
                                .group_by(Application.status)).all()) if ids else {}
    avg = db.scalar(select(func.avg(Score.total)).where(Score.job_id.in_(ids))) if ids else None
    return {"jobs": dict(Counter(j.status for j in jobs)), "applications_by_status": by_status,
            "applications": sum(by_status.values()), "average_score": round(avg, 1) if avg else None}


@router.get("/jobs/{job_id}/talents")
def talents(job_id: str, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    job = get_job(db, ctx, job_id)
    v: JobVersion = current_version(db, job)
    return suggest_talents(db, job, v) if v else []


@router.post("/jobs/{job_id}/talents/{profile_id}/invite")
def invite_talent(job_id: str, profile_id: str, request: Request, ctx: OrgContext = Depends(org_context),
                  db: Session = Depends(get_db)):
    """Invite an opted-in candidate to apply. The candidate decides; nothing is created on their behalf."""
    from .. import emailer
    from ..config import get_settings
    from ..models import CandidateProfile, User
    job = get_job(db, ctx, job_id)
    prof = db.get(CandidateProfile, _uuid(profile_id))
    user = db.get(User, prof.user_id) if prof else None
    # Same conditions as the suggestion list: opted in AND a confirmed address. We never e-mail an address
    # whose owner has not proven it is theirs.
    if not prof or not user or not prof.visible_to_recruiters or user.email_verified_at is None or job.status != "published":
        raise HTTPException(404, "Not found")
    if not hit(f"invite:{job.id}:{prof.id}", 1, 86400 * 30):
        raise HTTPException(409, "Already invited")
    emailer.send(user.email, f"{ctx.org.name} vous invite à postuler / invites you to apply: {job.title}",
                 f"{get_settings().public_url}/jobs/{job.slug}")
    audit.log(db, "talent.invited", actor=ctx.user, resource=f"job:{job.id}", organization_id=ctx.org.id,
              ip=client_ip(request))
    return {"ok": True}
