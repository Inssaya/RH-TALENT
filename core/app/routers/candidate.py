"""Candidate space: profile built from the CV, recommendations, one-click apply, tracking, rights."""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, storage
from ..ai.embeddings import embed
from ..ai.extraction import extract_profile, profile_text
from ..ai.skills import taxonomy
from ..db import get_db
from ..deps import require_role, verified_user
from ..matching import recommend_jobs
from ..models import (
    Applicant,
    Application,
    CandidateProfile,
    Document,
    Job,
    JobAlert,
    Organization,
    User,
    now,
)
from ..ratelimit import client_ip
from ..services import (
    candidate_status,
    erase_user,
    export_person,
    open_dsr,
    parse_stored,
    record_consent,
    store_document,
)
from ..tasks import enqueue, process
from .public import create_application, public_job, tracking_view

router = APIRouter(prefix="/candidate", tags=["candidate"])
candidate = require_role("candidate")


def _profile(db: Session, user: User) -> CandidateProfile | None:
    return db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))


def profile_out(p: CandidateProfile | None, db: Session, user: User) -> dict:
    alert = db.scalar(select(JobAlert).where(JobAlert.user_id == user.id))
    if not p:
        return {"exists": False, "alerts": bool(alert and alert.enabled)}
    return {"exists": True, "data": p.data, "visible_to_recruiters": p.visible_to_recruiters,
            "validated": p.validated_at is not None, "has_cv": p.document_id is not None,
            "alerts": bool(alert and alert.enabled), "updated_at": p.updated_at.isoformat()}


@router.get("/profile")
def get_profile(user: User = Depends(candidate), db: Session = Depends(get_db)):
    return profile_out(_profile(db, user), db, user)


@router.post("/profile/cv")
async def upload_cv(file: UploadFile = File(...), user: User = Depends(candidate), db: Session = Depends(get_db)):
    """Upload a CV: the profile is extracted from it and shown to the candidate for validation."""
    data = await file.read()
    doc = store_document(db, data, file.filename or "cv", owner_user_id=user.id)
    parse_stored(doc)
    if doc.quality == 0 and not doc.text:
        raise HTTPException(422, "We could not read this document. Try a PDF or DOCX file.")
    data_, _ = extract_profile(doc.text)
    data_["full_name"] = user.full_name
    p = _profile(db, user)
    old_doc = p.document_id if p else None
    if not p:
        p = CandidateProfile(user_id=user.id)
        db.add(p)
    p.data, p.embedding, p.document_id, p.validated_at = data_, embed(profile_text(data_)), doc.id, None
    db.flush()
    if old_doc:
        old = db.get(Document, old_doc)
        if old and not db.scalar(select(Application.id).where(Application.document_id == old.id)):
            storage.delete(old.storage_key)
            db.delete(old)
    return profile_out(p, db, user)


class ProfileIn(BaseModel):
    title: str = ""
    summary: str = ""
    location: str = ""
    skills: list[str] = []
    visible_to_recruiters: bool = False
    alerts: bool = False


@router.put("/profile")
def update_profile(body: ProfileIn, user: User = Depends(candidate), db: Session = Depends(get_db)):
    """The candidate corrects and validates the extracted profile; visibility is an explicit opt-in."""
    p = _profile(db, user)
    if not p:
        raise HTTPException(404, "Upload a CV first")
    # Visibility to recruiters and alert e-mails both rely on the address being the candidate's own.
    if (body.visible_to_recruiters or body.alerts) and user.email_verified_at is None:
        raise HTTPException(403, "email_not_verified")
    tax = taxonomy()
    known = {s["id"]: s for s in p.data.get("skills") or []}
    skills, raw = [], []
    for label in body.skills[:60]:
        sid = tax.normalise(label)
        if sid:
            skills.append(known.get(sid) or {"id": sid, "label": tax.label(sid), "has_context": True, "mentions": 1})
        elif label.strip():
            raw.append(label.strip()[:80])
    seen = set()
    skills = [s for s in skills if not (s["id"] in seen or seen.add(s["id"]))]
    p.data = {**p.data, "title": body.title[:160], "summary": body.summary[:600], "location": body.location[:120],
              "skills": skills, "raw_skills": raw}
    p.embedding, p.validated_at = embed(profile_text(p.data)), now()
    if body.visible_to_recruiters != p.visible_to_recruiters:
        record_consent(db, "talent_pool", body.visible_to_recruiters, user_id=user.id)
        p.visible_to_recruiters = body.visible_to_recruiters
    alert = db.scalar(select(JobAlert).where(JobAlert.user_id == user.id))
    if body.alerts != bool(alert and alert.enabled):
        record_consent(db, "alerts", body.alerts, user_id=user.id)
        if alert:
            alert.enabled = body.alerts
        else:
            db.add(JobAlert(user_id=user.id, enabled=body.alerts))
    db.flush()
    return profile_out(p, db, user)


@router.get("/recommendations")
def recommendations(user: User = Depends(candidate), db: Session = Depends(get_db)):
    """'For you' feed sorted by relevance. All jobs stay one click away in the public search."""
    p = _profile(db, user)
    if not p:
        return []
    out = []
    for r in recommend_jobs(db, p, 20, user.id):
        org = db.get(Organization, r["job"].organization_id)
        out.append({**public_job(r["job"], org), "match": r["score"], "matched_skills": r["matched_skills"],
                    "applied": r["applied"]})
    return out


@router.post("/apply/{slug}")
def one_click(slug: str, request: Request, user: User = Depends(verified_user), db: Session = Depends(get_db)):
    if user.role != "candidate":
        raise HTTPException(403, "Forbidden")
    p = _profile(db, user)
    if not p or not p.document_id:
        raise HTTPException(409, "Upload your CV to apply in one click")
    job = db.scalar(select(Job).where(Job.slug == slug, Job.status == "published"))
    if not job:
        raise HTTPException(404, "This job is not open")
    doc = db.get(Document, p.document_id)
    app, _ = create_application(db, job, email=user.email, full_name=user.full_name,
                                phone=p.data.get("phone", ""), locale=user.locale,
                                data=storage.get(doc.storage_key), filename=doc.filename, source="one_click",
                                user=user, ip=client_ip(request))
    db.commit()
    enqueue(process, str(app.id))
    return {"ok": True, "application_id": str(app.id)}


@router.get("/applications")
def my_applications(user: User = Depends(candidate), db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).join(Applicant).where(Applicant.user_id == user.id)
                      .order_by(Application.submitted_at.desc())).all()
    return [{"id": str(a.id), **tracking_view(a)} for a in apps]


def _own(db: Session, user: User, app_id: str) -> Application:
    import uuid
    try:
        app = db.get(Application, uuid.UUID(app_id))
    except ValueError:
        app = None
    if not app or app.applicant.user_id != user.id:
        raise HTTPException(404, "Not found")
    return app


@router.post("/applications/{app_id}/withdraw")
def withdraw(app_id: str, user: User = Depends(candidate), db: Session = Depends(get_db)):
    from ..models import ApplicationEvent
    from ..services import FINAL, refresh_shortlist
    app = _own(db, user, app_id)
    if app.status in FINAL:
        raise HTTPException(409, "This application is already closed")
    db.add(ApplicationEvent(application_id=app.id, from_status=app.status, to_status="withdrawn",
                            actor_id=user.id, actor_kind="candidate", reason="withdrawn by candidate"))
    app.status = "withdrawn"
    db.flush()
    refresh_shortlist(db, app.job, reason="withdrawal")
    return {"id": str(app.id), **tracking_view(app)}


@router.post("/applications/{app_id}/human-review")
def human_review(app_id: str, user: User = Depends(candidate), db: Session = Depends(get_db)):
    app = _own(db, user, app_id)
    if not app.human_review_requested:
        app.human_review_requested = True
        open_dsr(db, "human_review", user.email, user_id=user.id, application_id=app.id)
    return {"id": str(app.id), **tracking_view(app), "status": candidate_status(app)}


@router.get("/export")
def export(user: User = Depends(candidate), db: Session = Depends(get_db)):
    ids = list(db.scalars(select(Applicant.id).where(Applicant.user_id == user.id)))
    audit.log(db, "gdpr.export", actor=user, resource=f"user:{user.id}")
    return export_person(db, ids, user)


@router.post("/erase")
def erase(user: User = Depends(candidate), db: Session = Depends(get_db)):
    """Delete the account and everything attached to it, immediately."""
    req = open_dsr(db, "erasure", user.email, user_id=user.id)
    report = erase_user(db, user)
    req.status, req.completed_at, req.report = "done", now(), report
    audit.log(db, "gdpr.erasure_done", actor_label="candidate", resource=f"dsr:{req.id}", payload=report)
    return {"ok": True, "report": report}
