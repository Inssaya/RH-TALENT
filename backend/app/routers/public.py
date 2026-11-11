"""Public API: job board, account-less application, tracking by magic link."""
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import Text, func, or_, select
from sqlalchemy.orm import Session

from .. import audit, emailer
from ..config import get_settings
from ..db import get_db
from ..deps import current_user_optional
from ..models import Applicant, Application, Job, JobVersion, Organization, User, now
from ..ratelimit import client_ip, hit
from ..services import (
    FINAL,
    application_by_token,
    candidate_status,
    erase_application,
    export_person,
    issue_magic_link,
    open_dsr,
    record_consent,
    refresh_shortlist,
    store_document,
    tracking_link,
)
from ..tasks import enqueue, process

router = APIRouter(prefix="/public", tags=["public"])


def public_job(job: Job, org: Organization, draft: dict | None = None) -> dict:
    out = {"slug": job.slug, "title": job.title, "city": job.city, "country": job.country, "remote": job.remote,
           "contract_type": job.contract_type, "published_at": job.published_at.isoformat() if job.published_at else None,
           "organization": {"name": org.name, "slug": org.slug, "verified": org.verified, "sector": org.sector,
                            "city": org.city, "website": org.website, "description": org.description}}
    if draft is not None:
        out["draft"] = {k: draft.get(k) for k in (
            "description", "missions", "min_years_experience", "education_level", "languages", "skills_required",
            "skills_nice", "requirements", "salary_min", "salary_max", "currency", "lang")}
    return out


@router.get("/jobs")
def search(q: str = "", city: str = "", remote: str = "", contract: str = "", page: int = 1,
           db: Session = Depends(get_db)):
    page = max(1, min(page, 500))
    stmt = (select(Job, Organization).join(Organization, Organization.id == Job.organization_id)
            .join(JobVersion, (JobVersion.job_id == Job.id) & (JobVersion.number == Job.current_version))
            .where(Job.status == "published", Organization.status == "active"))
    if q.strip():
        like = f"%{q.strip()[:80]}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Organization.name.ilike(like),
                              JobVersion.draft["description"].astext.ilike(like),
                              func.cast(JobVersion.draft["skills_required"], Text).ilike(like)))
    if city.strip():
        stmt = stmt.where(Job.city.ilike(f"%{city.strip()[:60]}%"))
    if remote in ("onsite", "hybrid", "remote"):
        stmt = stmt.where(Job.remote == remote)
    if contract:
        stmt = stmt.where(Job.contract_type == contract)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Job.published_at.desc()).offset((page - 1) * 20).limit(20)).all()
    return {"total": total, "page": page, "items": [public_job(j, o) for j, o in rows]}


@router.get("/jobs/{slug}")
def job_detail(slug: str, db: Session = Depends(get_db)):
    row = db.execute(select(Job, Organization, JobVersion).join(Organization, Organization.id == Job.organization_id)
                     .join(JobVersion, (JobVersion.job_id == Job.id) & (JobVersion.number == Job.current_version))
                     .where(Job.slug == slug)).first()
    if not row or row[0].status not in ("published", "closed") or row[1].status != "active":
        raise HTTPException(404, "Not found")
    job, org, v = row
    return {**public_job(job, org, v.draft), "open": job.status == "published"}


@router.get("/sitemap")
def sitemap(db: Session = Depends(get_db)):
    rows = db.execute(select(Job.slug, Job.published_at).where(Job.status == "published").limit(5000)).all()
    return [{"slug": s, "at": p.isoformat() if p else None} for s, p in rows]


def _turnstile(token: str | None, ip: str) -> None:
    secret = get_settings().turnstile_secret
    if not secret:
        return
    try:
        r = httpx.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", timeout=8,
                       data={"secret": secret, "response": token or "", "remoteip": ip})
        ok = r.json().get("success", False)
    except Exception:
        ok = False
    if not ok:
        raise HTTPException(400, "Captcha verification failed")


def create_application(db: Session, job: Job, *, email: str, full_name: str, phone: str, locale: str,
                       data: bytes, filename: str, source: str, user: User | None, ip: str) -> tuple[Application, str]:
    email = email.strip().lower()
    applicant = db.scalar(select(Applicant).where(Applicant.email == email))
    if not applicant:
        applicant = Applicant(email=email, full_name=full_name.strip(), phone=phone.strip(), locale=locale,
                              user_id=user.id if user else None)
        db.add(applicant)
        db.flush()
    else:
        applicant.full_name = full_name.strip() or applicant.full_name
        applicant.phone = phone.strip() or applicant.phone
        if user and not applicant.user_id:
            applicant.user_id = user.id
    if db.scalar(select(Application.id).where(Application.job_id == job.id, Application.applicant_id == applicant.id)):
        raise HTTPException(409, "You have already applied to this job")
    doc = store_document(db, data, filename, owner_user_id=None)
    app = Application(job_id=job.id, applicant_id=applicant.id, document_id=doc.id, source=source)
    token = issue_magic_link(app)
    db.add(app)
    db.flush()
    record_consent(db, "application", True, applicant_id=applicant.id, user_id=user.id if user else None)
    audit.log(db, "application.submitted", actor_label="candidate", resource=f"application:{app.id}",
              organization_id=job.organization_id, ip=ip, payload={"source": source})
    emailer.send_template("received", locale, email, name=applicant.full_name, job=job.title,
                          org=job.organization.name, link=tracking_link(app, token),
                          days=get_settings().magic_link_days)
    return app, token


@router.post("/jobs/{slug}/apply")
async def apply(slug: str, request: Request, full_name: str = Form(..., min_length=2, max_length=200),
                email: str = Form(..., max_length=320), phone: str = Form("", max_length=40),
                locale: str = Form("fr"), consent: bool = Form(...), turnstile: str | None = Form(None),
                file: UploadFile = File(...), user: User | None = Depends(current_user_optional),
                db: Session = Depends(get_db)):
    ip = client_ip(request)
    if not hit(f"apply:{ip}", 5, 3600) or not hit(f"apply-mail:{email.lower()}", 3, 86400):
        raise HTTPException(429, "Too many applications, please retry later")
    if not consent:
        raise HTTPException(422, "Consent to the privacy notice is required to apply")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(422, "Invalid e-mail address")
    _turnstile(turnstile, ip)
    job = db.scalar(select(Job).where(Job.slug == slug, Job.status == "published"))
    if not job:
        raise HTTPException(404, "This job is not open")
    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    app, token = create_application(db, job, email=email, full_name=full_name, phone=phone,
                                    locale=locale if locale in ("fr", "en", "ar") else "fr", data=data,
                                    filename=file.filename or "cv", source="public", user=user, ip=ip)
    db.commit()
    enqueue(process, str(app.id))
    return {"ok": True, "tracking_token": token}


# ---------------------------------------------------------------- tracking (magic link)
def _by_token(db: Session, token: str) -> Application:
    app = application_by_token(db, token)
    if not app:
        raise HTTPException(404, "This link is invalid or has expired")
    return app


def tracking_view(app: Application) -> dict:
    status = candidate_status(app)
    out = {"job": {"title": app.job.title, "slug": app.job.slug, "organization": app.job.organization.name},
           "status": status, "submitted_at": app.submitted_at.isoformat(), "processing": app.processing,
           "human_review_requested": app.human_review_requested,
           "can_withdraw": app.status not in FINAL}
    if status == "not_retained" and app.score:
        # the candidate sees which requirements were not demonstrated, never a rank against others
        d = app.score.detail
        out["explanation"] = {
            "reason": app.rejection_reason,
            "missing_skills": [r["label"] for r in d.get("skills", []) if r["match"] < 1 and r["kind"] == "required"],
            "requirements": [{"text": r["text"], "status": r["status"]} for r in d.get("requirements", [])],
            "decided_by": "human",
        }
    return out


@router.get("/track/{token}")
def track(token: str, db: Session = Depends(get_db)):
    return tracking_view(_by_token(db, token))


@router.post("/track/{token}/withdraw")
def withdraw(token: str, db: Session = Depends(get_db)):
    from ..models import ApplicationEvent
    app = _by_token(db, token)
    if app.status in FINAL:
        raise HTTPException(409, "This application is already closed")
    db.add(ApplicationEvent(application_id=app.id, from_status=app.status, to_status="withdrawn",
                            actor_kind="candidate", reason="withdrawn by candidate"))
    app.status = "withdrawn"
    db.flush()
    refresh_shortlist(db, app.job, reason="withdrawal")
    return tracking_view(app)


@router.post("/track/{token}/human-review")
def human_review(token: str, request: Request, db: Session = Depends(get_db)):
    """Right to human intervention (GDPR art. 22): flags the application and opens a request."""
    app = _by_token(db, token)
    if not app.human_review_requested:
        app.human_review_requested = True
        open_dsr(db, "human_review", app.applicant.email, applicant_id=app.applicant_id, application_id=app.id)
        owner = db.get(User, app.job.created_by) if app.job.created_by else None
        if owner:
            emailer.send(owner.email, f"Demande de revue humaine / human review requested: {app.job.title}",
                         f"{get_settings().public_url}/recruiter/applications/{app.id}")
    return tracking_view(app)


@router.get("/track/{token}/export")
def export(token: str, db: Session = Depends(get_db)):
    app = _by_token(db, token)
    audit.log(db, "gdpr.export", actor_label=app.applicant.email, resource=f"applicant:{app.applicant_id}")
    return export_person(db, [app.applicant_id])


@router.post("/track/{token}/erase")
def erase(token: str, db: Session = Depends(get_db)):
    app = _by_token(db, token)
    req = open_dsr(db, "erasure", app.applicant.email, applicant_id=app.applicant_id, application_id=app.id)
    report = erase_application(db, app)
    req.status, req.completed_at, req.report = "done", now(), report
    audit.log(db, "gdpr.erasure_done", actor_label="candidate", resource=f"dsr:{req.id}", payload=report)
    return {"ok": True, "report": report}
