"""Platform administration: moderation, GDPR requests, audit log, AI supervision."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..deps import require_role
from ..models import (
    Applicant,
    Application,
    AuditEvent,
    DataSubjectRequest,
    Feedback,
    Job,
    LlmCall,
    Organization,
    Score,
    User,
    now,
)
from ..ratelimit import client_ip
from ..services import erase_applicant, erase_user

router = APIRouter(prefix="/admin", tags=["admin"])
admin = require_role("platform_admin")


@router.get("/stats")
def stats(user: User = Depends(admin), db: Session = Depends(get_db)):
    c = lambda m, *w: db.scalar(select(func.count()).select_from(m).where(*w)) or 0  # noqa: E731
    return {"organizations": c(Organization), "users": c(User), "jobs_published": c(Job, Job.status == "published"),
            "jobs_total": c(Job), "applications": c(Application),
            "applications_scored": c(Application, Application.processing == "scored"),
            "applications_failed": c(Application, Application.processing == "failed"),
            "open_requests": c(DataSubjectRequest, DataSubjectRequest.status == "open")}


@router.get("/organizations")
def organizations(user: User = Depends(admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Organization, func.count(Job.id)).join(Job, Job.organization_id == Organization.id, isouter=True)
                      .group_by(Organization.id).order_by(Organization.created_at.desc()).limit(500))
    return [{"id": str(o.id), "name": o.name, "verified": o.verified, "status": o.status, "city": o.city,
             "jobs": n, "created_at": o.created_at.isoformat()} for o, n in rows]


class OrgAction(BaseModel):
    verified: bool | None = None
    status: str | None = None


@router.put("/organizations/{org_id}")
def moderate_org(org_id: uuid.UUID, body: OrgAction, request: Request, user: User = Depends(admin),
                 db: Session = Depends(get_db)):
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(404, "Not found")
    if body.verified is not None:
        org.verified = body.verified
    if body.status in ("active", "suspended"):
        org.status = body.status
        if body.status == "suspended":  # fraudulent posts disappear immediately
            for job in db.scalars(select(Job).where(Job.organization_id == org.id, Job.status == "published")):
                job.status = "suspended"
    audit.log(db, "moderation.organization", actor=user, resource=f"organization:{org.id}", organization_id=org.id,
              ip=client_ip(request), payload=body.model_dump(exclude_none=True))
    return {"ok": True}


@router.get("/jobs")
def jobs(user: User = Depends(admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Job, Organization.name).join(Organization, Organization.id == Job.organization_id)
                      .order_by(Job.created_at.desc()).limit(300))
    return [{"id": str(j.id), "slug": j.slug, "title": j.title, "status": j.status, "organization": name,
             "created_at": j.created_at.isoformat()} for j, name in rows]


class JobAction(BaseModel):
    status: str


@router.put("/jobs/{job_id}")
def moderate_job(job_id: uuid.UUID, body: JobAction, request: Request, user: User = Depends(admin),
                 db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or body.status not in ("suspended", "published", "closed"):
        raise HTTPException(404, "Not found")
    job.status = body.status
    audit.log(db, "moderation.job", actor=user, resource=f"job:{job.id}", organization_id=job.organization_id,
              ip=client_ip(request), payload={"status": body.status})
    return {"ok": True}


@router.get("/requests")
def requests(user: User = Depends(admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(DataSubjectRequest).order_by(DataSubjectRequest.created_at.desc()).limit(300))
    return [{"id": str(r.id), "type": r.type, "status": r.status, "email": r.email, "note": r.note,
             "report": r.report, "due_at": r.due_at.isoformat(), "created_at": r.created_at.isoformat(),
             "completed_at": r.completed_at.isoformat() if r.completed_at else None} for r in rows]


class RequestAction(BaseModel):
    action: str  # complete | reject | execute_erasure
    note: str = ""


@router.post("/requests/{req_id}")
def handle_request(req_id: uuid.UUID, body: RequestAction, request: Request, user: User = Depends(admin),
                   db: Session = Depends(get_db)):
    r = db.get(DataSubjectRequest, req_id)
    if not r or r.status != "open":
        raise HTTPException(404, "Not found")
    if body.action == "execute_erasure":
        report = {}
        if r.user_id and (u := db.get(User, r.user_id)):
            report = erase_user(db, u)
        elif r.applicant_id and (a := db.get(Applicant, r.applicant_id)):
            report = erase_applicant(db, a)
        r.report, r.status = report, "done"
    elif body.action == "reject":
        r.status = "rejected"
    else:
        r.status = "done"
    r.note, r.completed_at = (r.note + "\n" + body.note).strip(), now()
    audit.log(db, "gdpr.request_handled", actor=user, resource=f"dsr:{r.id}", ip=client_ip(request),
              payload={"action": body.action, "type": r.type})
    return {"ok": True}


@router.get("/audit")
def audit_log(action: str = "", page: int = 1, user: User = Depends(admin), db: Session = Depends(get_db)):
    q = select(AuditEvent).order_by(AuditEvent.seq.desc())
    if action:
        q = q.where(AuditEvent.action.like(f"{action[:40]}%"))
    rows = db.scalars(q.offset((max(1, page) - 1) * 100).limit(100))
    return [{"seq": e.seq, "at": e.created_at.isoformat(), "actor": e.actor_label, "action": e.action,
             "resource": e.resource, "payload": e.payload, "hash": e.hash[:12]} for e in rows]


@router.get("/audit/verify")
def audit_verify(user: User = Depends(admin), db: Session = Depends(get_db)):
    return audit.verify_chain(db)


@router.get("/ai")
def ai_supervision(user: User = Depends(admin), db: Session = Depends(get_db)):
    """Model usage, degraded-mode rate, score distribution and recruiter disagreements."""
    since = now() - timedelta(days=7)
    rows = db.execute(select(LlmCall.kind, LlmCall.degraded, func.count(), func.sum(LlmCall.tokens_in),
                             func.sum(LlmCall.tokens_out), func.avg(LlmCall.latency_ms),
                             func.sum(func.cast(~LlmCall.ok, Integer)))
                      .where(LlmCall.created_at >= since).group_by(LlmCall.kind, LlmCall.degraded)).all()
    calls = [{"kind": k, "degraded": d, "count": n, "tokens_in": int(ti or 0), "tokens_out": int(to or 0),
              "avg_latency_ms": int(lat or 0), "errors": int(err or 0)} for k, d, n, ti, to, lat, err in rows]
    total = sum(c["count"] for c in calls) or 1
    tokens_in, tokens_out = sum(c["tokens_in"] for c in calls), sum(c["tokens_out"] for c in calls)
    fb = db.execute(select(Feedback.type, func.count()).group_by(Feedback.type)).all()
    flags = db.execute(select(func.jsonb_array_elements_text(Score.flags).label("f"), func.count()).group_by("f")).all()
    return {"window_days": 7, "calls": calls,
            "degraded_rate": round(sum(c["count"] for c in calls if c["degraded"]) / total, 3),
            "estimated_cost_eur": round((tokens_in * 0.10 + tokens_out * 0.30) / 1e6 * 0.92, 4),
            "average_score": db.scalar(select(func.avg(Score.total))),
            "feedback": dict(fb), "flags": dict(flags)}


@router.get("/feedback")
def feedback(user: User = Depends(admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Feedback, Job.title).join(Application, Application.id == Feedback.application_id)
                      .join(Job, Job.id == Application.job_id).order_by(Feedback.created_at.desc()).limit(200))
    return [{"type": f.type, "comment": f.comment, "job": title, "at": f.created_at.isoformat()} for f, title in rows]
