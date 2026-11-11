"""Business services: application processing, shortlist, human decisions, GDPR."""
import hashlib
import hmac
import logging
import re
import socket
import struct
import unicodedata
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import audit, emailer, storage
from .ai import parsing
from .ai.embeddings import embed
from .ai.extraction import extract_profile, profile_text
from .ai.scoring import DEFAULT_WEIGHTS, compute_score, job_text
from .ai.shortlist import Policy, compute_shortlist, diff
from .config import get_settings
from .models import (
    Applicant,
    Application,
    ApplicationEvent,
    CandidateProfile,
    ConsentRecord,
    DataSubjectRequest,
    Document,
    Feedback,
    Job,
    JobAlert,
    JobVersion,
    Score,
    ShortlistSnapshot,
    User,
    now,
)

log = logging.getLogger("tm.services")

HUMAN_TRANSITIONS = {
    "new": {"to_contact", "interview", "rejected"},
    "shortlisted": {"to_contact", "interview", "rejected"},
    "to_contact": {"interview", "offer", "rejected"},
    "interview": {"to_contact", "offer", "hired", "rejected"},
    "offer": {"hired", "rejected"},
    "hired": set(),
    "rejected": set(),
    "withdrawn": set(),
}
REJECTION_REASONS = {"skills", "experience", "position_filled", "other"}
FINAL = {"hired", "rejected", "withdrawn"}


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80] or "job"


def unique_slug(db: Session, model, base: str) -> str:
    slug = slugify(base)
    if not db.scalar(select(model.id).where(model.slug == slug)):
        return slug
    return f"{slug}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------- documents
def antivirus(data: bytes) -> str:
    """ClamAV INSTREAM scan when a daemon is configured; 'skipped' otherwise."""
    s = get_settings()
    if not s.clamav_host:
        return "skipped"
    try:
        with socket.create_connection((s.clamav_host, s.clamav_port), timeout=20) as sock:
            sock.sendall(b"zINSTREAM\0")
            for i in range(0, len(data), 8192):
                chunk = data[i:i + 8192]
                sock.sendall(struct.pack("!L", len(chunk)) + chunk)
            sock.sendall(struct.pack("!L", 0))
            reply = sock.recv(4096).decode(errors="ignore")
        return "infected" if "FOUND" in reply else "clean"
    except OSError:
        log.warning("antivirus unreachable")
        return "skipped"


def store_document(db: Session, data: bytes, filename: str, owner_user_id=None) -> Document:
    s = get_settings()
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File larger than {s.max_upload_mb} MB")
    if not data:
        raise HTTPException(422, "Empty file")
    try:
        kind = parsing.sniff(data, filename)
    except parsing.UnsupportedFile as exc:
        raise HTTPException(415, f"Unsupported file: {exc}") from exc
    av = antivirus(data)
    if av == "infected":
        raise HTTPException(422, "The file was rejected by the antivirus")
    doc = Document(id=uuid.uuid4(), owner_user_id=owner_user_id, filename=re.sub(r"[^\w.\- ]", "_", filename)[:200] or "cv",
                   mime=parsing.ALLOWED[kind], size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                   av_status=av, storage_key="")
    doc.storage_key = f"cv/{doc.id.hex[:2]}/{doc.id.hex}.{kind}"
    storage.put(doc.storage_key, data)
    db.add(doc)
    db.flush()
    return doc


def parse_stored(doc: Document) -> None:
    try:
        parsed = parsing.parse_document(storage.get(doc.storage_key), doc.filename)
    except parsing.UnsupportedFile as exc:
        doc.flags = {"unreadable": str(exc)}
        doc.quality, doc.text = 0.0, ""
        return
    doc.text, doc.lang, doc.method, doc.quality, doc.flags = parsed.text, parsed.lang, parsed.method, parsed.quality, parsed.flags


# ---------------------------------------------------------------- jobs
def current_version(db: Session, job: Job) -> JobVersion | None:
    return db.scalar(select(JobVersion).where(JobVersion.job_id == job.id, JobVersion.number == job.current_version))


def new_job_version(db: Session, job: Job, draft: dict, user: User | None) -> JobVersion:
    job.current_version += 1
    job.title, job.city, job.country = draft.get("title", "")[:200], draft.get("city", "")[:120], draft.get("country", "")[:80]
    job.remote, job.contract_type = draft.get("remote", "onsite"), draft.get("contract_type", "")
    v = JobVersion(job_id=job.id, number=job.current_version, draft=draft, embedding=embed(job_text(draft)),
                   created_by=user.id if user else None)
    db.add(v)
    db.flush()
    return v


# ---------------------------------------------------------------- scoring
def score_application(db: Session, app: Application, fast: bool = False) -> Score | None:
    job = app.job
    version = current_version(db, job)
    doc = app.document
    if not version or not doc:
        return None
    result = compute_score(version.draft, job.weights or DEFAULT_WEIGHTS, app.profile, doc.text,
                           job_emb=version.embedding, profile_emb=app.embedding,
                           org_id=job.organization_id, lang=version.draft.get("lang", "fr"), fast=fast)
    flags = list(result["flags"])
    if doc.flags.get("hidden_text"):
        flags.append("hidden_text")
    if doc.flags.get("injection"):
        flags.append("injection_suspected")
    if doc.quality < 0.6:
        flags.append("low_parsing_quality")
    if result["degraded"]:
        flags.append("rule_based_assessment")
    score = app.score or Score(application_id=app.id, job_id=job.id)
    score.job_version, score.total, score.subscores = version.number, result["total"], result["subscores"]
    score.detail, score.knockout_failed, score.flags = result["detail"], result["knockout_failed"], flags
    score.provisional, score.weights_version = False, job.weights_version
    score.prompt_version = "requirement_assess_v1"
    score.model_id = "rules" if result["degraded"] else get_settings().llm_model
    score.computed_at = now()
    if not app.score:
        app.score = score
        db.add(score)
    app.processing, app.scored_at, app.processing_error = "scored", now(), ""
    db.flush()
    return score


def find_duplicates(db: Session, app: Application) -> list[str]:
    """Same file or same e-mail already applied to this job under another applicant record."""
    if not app.document:
        return []
    q = (select(Application.id).join(Document, Application.document_id == Document.id)
         .where(Application.job_id == app.job_id, Application.id != app.id, Document.sha256 == app.document.sha256))
    return [str(i) for i in db.scalars(q)]


def process_application(db: Session, app_id) -> None:
    """Full pipeline for one application: parse, extract, embed, score, refresh the shortlist."""
    app = db.get(Application, app_id)
    if not app or not app.document:
        return
    app.processing = "processing"
    db.flush()
    try:
        doc = app.document
        if not doc.text and not doc.flags:
            parse_stored(doc)
        profile, _ = extract_profile(doc.text, app.job.organization_id)
        profile["full_name"] = app.applicant.full_name or profile.get("full_name", "")
        app.profile = profile
        app.embedding = embed(profile_text(profile))
        score = score_application(db, app)
        dups = find_duplicates(db, app)
        if dups and score:
            score.flags = [*score.flags, "possible_duplicate"]
            score.detail = {**score.detail, "duplicates": dups}
        refresh_shortlist(db, app.job, reason="new_score")
    except Exception as exc:  # the application is kept and can be reprocessed
        log.exception("processing failed for %s", app_id)
        app.processing, app.processing_error = "failed", str(exc)[:500]


def rescore_job(db: Session, job_id) -> int:
    job = db.get(Job, job_id)
    if not job:
        return 0
    apps = db.scalars(select(Application).where(Application.job_id == job.id, Application.processing.in_(["scored", "failed"]))).all()
    for app in apps:
        if app.document and app.profile:
            score_application(db, app)
    refresh_shortlist(db, job, reason="rescore")
    return len(apps)


# ---------------------------------------------------------------- shortlist
def _policy(job: Job) -> Policy:
    return Policy(mode=job.sl_mode, n=job.sl_n, threshold=job.sl_threshold, cap=job.sl_cap)


def shortlist_rows(db: Session, job: Job) -> list[dict]:
    q = (select(Application, Score, Document.quality).join(Score, Score.application_id == Application.id)
         .join(Document, Application.document_id == Document.id, isouter=True)
         .where(Application.job_id == job.id, Application.status.notin_(["withdrawn", "rejected"])))
    return [{"id": str(a.id), "total": s.total, "skills": s.subscores.get("skills", 0),
             "requirements": s.subscores.get("requirements", 0), "knockout_failed": s.knockout_failed,
             "provisional": s.provisional, "quality": q if q is not None else 1.0, "pinned": a.pinned,
             "status": a.status} for a, s, q in db.execute(q)]


def refresh_shortlist(db: Session, job: Job, reason: str = "") -> ShortlistSnapshot | None:
    """Recompute the shortlist; store an immutable snapshot when it changed. The only automatic
    transitions are new <-> shortlisted. No action is ever taken towards candidates here."""
    policy = _policy(job)
    result = compute_shortlist(shortlist_rows(db, job), policy)
    prev = db.scalar(select(ShortlistSnapshot).where(ShortlistSnapshot.job_id == job.id)
                     .order_by(ShortlistSnapshot.created_at.desc()).limit(1))
    pol = {"mode": policy.mode, "n": policy.n, "threshold": policy.threshold, "cap": policy.cap,
           "job_version": job.current_version, "weights_version": job.weights_version}
    members = result["members"]
    if prev and prev.members == members and prev.policy == pol and prev.review_lane == result["review_lane"]:
        return prev
    d = diff(prev.members if prev else [], members)
    snap = ShortlistSnapshot(job_id=job.id, policy=pol, members=members, below=result["below"],
                             review_lane=result["review_lane"], cutoff_score=result["cutoff_score"],
                             diff={**d, "reason": reason}, notes=result["notes"])
    db.add(snap)
    member_set = set(members)
    for app in db.scalars(select(Application).where(Application.job_id == job.id, Application.status.in_(["new", "shortlisted"]))):
        target = "shortlisted" if str(app.id) in member_set else "new"
        if app.status != target:
            db.add(ApplicationEvent(application_id=app.id, from_status=app.status, to_status=target,
                                    actor_kind="system", reason="shortlist"))
            app.status = target
    audit.log(db, "shortlist.snapshot", actor_label="system", resource=f"job:{job.id}",
              organization_id=job.organization_id,
              payload={"policy": pol, "size": len(members), "entered": len(d["entered"]), "left": len(d["left"])})
    db.flush()
    if prev and (d["entered"] or d["left"]):
        notify_shortlist(db, job, d)
    return snap


def notify_shortlist(db: Session, job: Job, d: dict) -> None:
    from .ratelimit import hit
    if not hit(f"slnotify:{job.id}", 1, 3600):  # grouped: at most one e-mail per hour and per job
        return
    owner = db.get(User, job.created_by) if job.created_by else None
    if owner:
        emailer.send(owner.email, f"Shortlist mise à jour / updated: {job.title}",
                     f"{len(d['entered'])} entrée(s), {len(d['left'])} sortie(s).\n"
                     f"{get_settings().public_url}/recruiter/jobs/{job.id}")


# ---------------------------------------------------------------- human decisions
def transition(db: Session, app: Application, to: str, actor: User, reason: str = "", message: str = "",
               ip: str = "") -> None:
    """Every transition except new <-> shortlisted is a traced human action."""
    if actor is None or actor.role != "recruiter":
        raise HTTPException(403, "A human recruiter is required for this action")
    if to not in HUMAN_TRANSITIONS.get(app.status, set()):
        raise HTTPException(409, f"Invalid transition {app.status} -> {to}")
    if to == "rejected":
        if reason not in REJECTION_REASONS:
            raise HTTPException(422, "A rejection reason is required")
        app.rejection_reason, app.rejection_message = reason, message[:2000]
        app.pending_rejection_at = now() + timedelta(minutes=get_settings().reject_undo_minutes)
    db.add(ApplicationEvent(application_id=app.id, from_status=app.status, to_status=to, actor_id=actor.id,
                            actor_kind="human", reason=reason or message[:200]))
    audit.log(db, "application.transition", actor=actor, resource=f"application:{app.id}",
              organization_id=app.job.organization_id, ip=ip,
              payload={"from": app.status, "to": to, "reason": reason})
    prev = app.status
    app.status = to
    db.flush()
    if to in ("interview", "offer", "hired"):
        _notify_candidate_status(app, to)
    if to == "rejected" or prev in ("new", "shortlisted"):
        refresh_shortlist(db, app.job, reason="decision")


def undo_rejection(db: Session, app: Application, actor: User) -> None:
    if app.status != "rejected" or not app.pending_rejection_at or app.pending_rejection_at <= now():
        raise HTTPException(409, "The rejection can no longer be cancelled")
    last = db.scalar(select(ApplicationEvent).where(ApplicationEvent.application_id == app.id,
                                                    ApplicationEvent.to_status == "rejected")
                     .order_by(ApplicationEvent.created_at.desc()).limit(1))
    back = last.from_status if last else "new"
    db.add(ApplicationEvent(application_id=app.id, from_status="rejected", to_status=back, actor_id=actor.id,
                            actor_kind="human", reason="undo"))
    app.status, app.pending_rejection_at, app.rejection_reason, app.rejection_message = back, None, "", ""
    audit.log(db, "application.rejection_undone", actor=actor, resource=f"application:{app.id}",
              organization_id=app.job.organization_id)
    db.flush()
    refresh_shortlist(db, app.job, reason="undo")


def tracking_link(app: Application, token: str) -> str:
    return f"{get_settings().public_url}/track/{token}"


def issue_magic_link(app: Application) -> str:
    """Signed, re-derivable tracking token: "<application id>.<HMAC>". Only a random nonce is
    stored, so the same link can be sent again later (e.g. in the decision e-mail) and can be
    revoked by rotating the nonce."""
    if not app.id:
        app.id = uuid.uuid4()
    if not app.magic_token_hash:
        app.magic_token_hash = uuid.uuid4().hex
    app.magic_expires_at = now() + timedelta(days=get_settings().magic_link_days)
    return f"{app.id.hex}.{_magic_sig(app)}"


def _magic_sig(app: Application) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"{app.id.hex}:{app.magic_token_hash}".encode(), hashlib.sha256).hexdigest()[:40]


def application_by_token(db: Session, token: str) -> Application | None:
    try:
        app_hex, sig = token.split(".", 1)
        app = db.get(Application, uuid.UUID(app_hex))
    except ValueError:
        return None
    if not app or not app.magic_expires_at or app.magic_expires_at < now():
        return None
    return app if hmac.compare_digest(sig, _magic_sig(app)) else None


def _notify_candidate_status(app: Application, status: str) -> None:
    labels = {"interview": {"fr": "entretien", "en": "interview", "ar": "مقابلة"},
              "offer": {"fr": "proposition", "en": "offer", "ar": "عرض"},
              "hired": {"fr": "candidature retenue", "en": "application selected", "ar": "تم قبول الطلب"}}
    loc = app.applicant.locale
    emailer.send_template("status", loc, app.applicant.email, name=app.applicant.full_name, job=app.job.title,
                          org=app.job.organization.name, status=labels[status].get(loc, labels[status]["fr"]),
                          link=f"{get_settings().public_url}/candidate")


def send_pending_rejections(db: Session) -> int:
    """Send rejection e-mails whose cancellation delay has elapsed."""
    q = select(Application).where(Application.status == "rejected", Application.pending_rejection_at.is_not(None),
                                  Application.pending_rejection_at <= now())
    sent = 0
    for app in db.scalars(q).all():
        token = issue_magic_link(app)
        emailer.send_template("rejected", app.applicant.locale, app.applicant.email, name=app.applicant.full_name,
                              job=app.job.title, org=app.job.organization.name,
                              message=(app.rejection_message + "\n") if app.rejection_message else "",
                              link=tracking_link(app, token))
        app.pending_rejection_at = None
        sent += 1
    db.flush()
    return sent


def candidate_status(app: Application) -> str:
    """Simplified status shown to candidates."""
    if app.status == "withdrawn":
        return "withdrawn"
    if app.status == "rejected":
        return "in_review" if app.pending_rejection_at else "not_retained"
    if app.status in ("interview", "offer"):
        return "interview"
    if app.status == "hired":
        return "retained"
    return "in_review"


# ---------------------------------------------------------------- GDPR
def record_consent(db: Session, type_: str, granted: bool, applicant_id=None, user_id=None) -> None:
    db.add(ConsentRecord(applicant_id=applicant_id, user_id=user_id, type=type_, granted=granted,
                         notice_version=get_settings().notice_version))


def export_person(db: Session, applicant_ids: list, user: User | None = None) -> dict:
    out: dict = {"generated_at": now().isoformat(), "applications": [], "consents": []}
    if user:
        prof = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
        out["account"] = {"email": user.email, "full_name": user.full_name, "created_at": user.created_at.isoformat()}
        out["profile"] = prof.data if prof else None
    for a in db.scalars(select(Application).where(Application.applicant_id.in_(applicant_ids))) if applicant_ids else []:
        out["applications"].append({
            "job": a.job.title, "organization": a.job.organization.name, "status": candidate_status(a),
            "submitted_at": a.submitted_at.isoformat(), "profile_extracted": a.profile,
            "score": {"total": a.score.total, "subscores": a.score.subscores,
                      "requirements": a.score.detail.get("requirements", [])} if a.score else None})
    cq = select(ConsentRecord).where(ConsentRecord.applicant_id.in_(applicant_ids) if applicant_ids else False)
    if user:
        cq = select(ConsentRecord).where((ConsentRecord.user_id == user.id) |
                                         (ConsentRecord.applicant_id.in_(applicant_ids or [uuid.uuid4()])))
    for c in db.scalars(cq):
        out["consents"].append({"type": c.type, "granted": c.granted, "notice_version": c.notice_version,
                                "at": c.created_at.isoformat()})
    return out


def _delete_document(db: Session, doc_id) -> int:
    doc = db.get(Document, doc_id) if doc_id else None
    if not doc:
        return 0
    try:
        storage.delete(doc.storage_key)
    except Exception:
        log.exception("could not delete file %s", doc.storage_key)
    db.delete(doc)
    return 1


def erase_application(db: Session, app: Application) -> dict:
    """Real erasure: rows, extracted profile, embedding, score and the stored file."""
    job = app.job
    doc_id = app.document_id
    db.execute(delete(Feedback).where(Feedback.application_id == app.id))
    db.delete(app)
    db.flush()
    files = _delete_document(db, doc_id)
    db.flush()
    refresh_shortlist(db, job, reason="erasure")
    return {"applications": 1, "files": files}


def erase_applicant(db: Session, applicant: Applicant) -> dict:
    report = {"applications": 0, "files": 0}
    for app in db.scalars(select(Application).where(Application.applicant_id == applicant.id)).all():
        r = erase_application(db, app)
        report["applications"] += r["applications"]
        report["files"] += r["files"]
    db.execute(delete(ConsentRecord).where(ConsentRecord.applicant_id == applicant.id))
    db.delete(applicant)
    db.flush()
    return report


def erase_user(db: Session, user: User) -> dict:
    report = {"applications": 0, "files": 0, "profile": 0, "account": 1}
    for applicant in db.scalars(select(Applicant).where(Applicant.user_id == user.id)).all():
        r = erase_applicant(db, applicant)
        report["applications"] += r["applications"]
        report["files"] += r["files"]
    prof = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
    if prof:
        doc_id = prof.document_id
        db.delete(prof)
        db.flush()
        report["files"] += _delete_document(db, doc_id)
        report["profile"] = 1
    db.execute(delete(JobAlert).where(JobAlert.user_id == user.id))
    db.execute(delete(ConsentRecord).where(ConsentRecord.user_id == user.id))
    db.delete(user)
    db.flush()
    return report


def open_dsr(db: Session, type_: str, email: str, applicant_id=None, user_id=None, application_id=None,
             note: str = "") -> DataSubjectRequest:
    r = DataSubjectRequest(type=type_, email=email, applicant_id=applicant_id, user_id=user_id,
                           application_id=application_id, note=note[:2000],
                           due_at=now() + timedelta(days=get_settings().erasure_days))
    db.add(r)
    db.flush()
    audit.log(db, "gdpr.request", actor_label=email, resource=f"dsr:{r.id}", payload={"type": type_})
    return r


def purge_retention(db: Session) -> dict:
    """Delete applications of closed jobs past the retention period and expired magic links."""
    s = get_settings()
    limit = now() - timedelta(days=30 * s.retention_months)
    purged = 0
    q = (select(Application).join(Job).where(Application.submitted_at < limit, Job.status.in_(["closed", "suspended"])))
    for app in db.scalars(q).all():
        erase_application(db, app)
        purged += 1
    orphans = db.scalars(select(Applicant).where(Applicant.user_id.is_(None),
                                                 ~select(Application.id).where(Application.applicant_id == Applicant.id).exists())).all()
    for a in orphans:
        db.execute(delete(ConsentRecord).where(ConsentRecord.applicant_id == a.id))
        db.delete(a)
    db.flush()
    if purged:
        audit.log(db, "gdpr.retention_purge", actor_label="system", payload={"applications": purged})
    return {"applications": purged, "applicants": len(orphans)}


def job_counts(db: Session, job_ids: list) -> dict:
    if not job_ids:
        return {}
    rows = db.execute(select(Application.job_id, func.count()).where(Application.job_id.in_(job_ids))
                      .group_by(Application.job_id))
    return {jid: n for jid, n in rows}
