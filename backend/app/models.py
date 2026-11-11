"""Data model. Personal data is never soft-deleted: erasure is real (see app/gdpr.py)."""
import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

EMB_DIM = 1024


def now() -> datetime:
    return datetime.now(UTC)


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def fk(target: str, **kw) -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=kw.pop("ondelete", "CASCADE")), **kw)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200), default="")
    role: Mapped[str] = mapped_column(String(20))  # candidate | recruiter | platform_admin
    locale: Mapped[str] = mapped_column(String(5), default="fr")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | suspended
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reset_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    sector: Mapped[str] = mapped_column(String(120), default="")
    size: Mapped[str] = mapped_column(String(40), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | suspended
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)
    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = fk("users.id")
    organization_id: Mapped[uuid.UUID] = fk("organizations.id")
    role: Mapped[str] = mapped_column(String(20), default="recruiter")  # recruiter | org_admin
    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship()


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = pk()
    organization_id: Mapped[uuid.UUID] = fk("organizations.id", index=True)
    slug: Mapped[str] = mapped_column(String(260), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft|published|closed|suspended
    title: Mapped[str] = mapped_column(String(200), default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    country: Mapped[str] = mapped_column(String(80), default="")
    remote: Mapped[str] = mapped_column(String(20), default="onsite")
    contract_type: Mapped[str] = mapped_column(String(40), default="")
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    blind_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    # shortlist policy (never a constant in business code)
    sl_mode: Mapped[str] = mapped_column(String(20), default="TOP_N")  # TOP_N | THRESHOLD | TOP_N_FLOOR
    sl_n: Mapped[int] = mapped_column(Integer, default=10)
    sl_threshold: Mapped[float] = mapped_column(Float, default=65.0)
    sl_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weights: Mapped[dict] = mapped_column(JSONB, default=dict)
    weights_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    organization: Mapped[Organization] = relationship()
    versions: Mapped[list["JobVersion"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="JobVersion.number"
    )


class JobVersion(Base):
    """Immutable snapshot of the job template. Scores always reference a version."""
    __tablename__ = "job_versions"
    __table_args__ = (
        UniqueConstraint("job_id", "number"),
        Index("ix_job_versions_emb", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    id: Mapped[uuid.UUID] = pk()
    job_id: Mapped[uuid.UUID] = fk("jobs.id", index=True)
    number: Mapped[int] = mapped_column(Integer)
    draft: Mapped[dict] = mapped_column(JSONB)
    embedding = mapped_column(Vector(EMB_DIM), nullable=True)
    created_by: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    job: Mapped[Job] = relationship(back_populates="versions")


class Applicant(Base):
    __tablename__ = "applicants"
    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    locale: Mapped[str] = mapped_column(String(5), default="fr")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    __table_args__ = (
        Index("ix_profiles_emb", "embedding", postgresql_using="hnsw",
              postgresql_ops={"embedding": "vector_cosine_ops"}),
    )
    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = fk("users.id", unique=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    embedding = mapped_column(Vector(EMB_DIM), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    visible_to_recruiters: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = pk()
    owner_user_id: Mapped[uuid.UUID | None] = fk("users.id", ondelete="CASCADE", nullable=True)
    storage_key: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    av_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|clean|infected|skipped
    # parsed output
    text: Mapped[str] = mapped_column(Text, default="")
    lang: Mapped[str] = mapped_column(String(5), default="")
    method: Mapped[str] = mapped_column(String(30), default="")  # native | ocr-mistral | ocr-tesseract
    quality: Mapped[float] = mapped_column(Float, default=0.0)
    flags: Mapped[dict] = mapped_column(JSONB, default=dict)  # hidden_text, injection, ...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("job_id", "applicant_id"),)
    id: Mapped[uuid.UUID] = pk()
    job_id: Mapped[uuid.UUID] = fk("jobs.id", index=True)
    applicant_id: Mapped[uuid.UUID] = fk("applicants.id", index=True)
    document_id: Mapped[uuid.UUID | None] = fk("documents.id", ondelete="SET NULL", nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    source: Mapped[str] = mapped_column(String(20), default="public")  # public | one_click | invitation
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    human_review_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    opened_by_recruiter: Mapped[bool] = mapped_column(Boolean, default=False)
    profile: Mapped[dict] = mapped_column(JSONB, default=dict)  # frozen profile snapshot
    embedding = mapped_column(Vector(EMB_DIM), nullable=True)
    processing: Mapped[str] = mapped_column(String(20), default="queued")  # queued|processing|scored|failed
    processing_error: Mapped[str] = mapped_column(Text, default="")
    magic_token_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    magic_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_rejection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str] = mapped_column(String(60), default="")
    rejection_message: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    job: Mapped[Job] = relationship()
    applicant: Mapped[Applicant] = relationship()
    document: Mapped[Document | None] = relationship()
    score: Mapped["Score | None"] = relationship(
        back_populates="application", uselist=False, cascade="all, delete-orphan"
    )


class Score(Base):
    """Current score of an application for the current job version."""
    __tablename__ = "scores"
    __table_args__ = (Index("ix_scores_job_total", "job_id", "total"),)
    id: Mapped[uuid.UUID] = pk()
    application_id: Mapped[uuid.UUID] = fk("applications.id", unique=True)
    job_id: Mapped[uuid.UUID] = fk("jobs.id")
    job_version: Mapped[int] = mapped_column(Integer)
    total: Mapped[float] = mapped_column(Float)  # 0..100
    subscores: Mapped[dict] = mapped_column(JSONB)
    detail: Mapped[dict] = mapped_column(JSONB)  # skills, requirement assessments, knockouts, explanation
    knockout_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    provisional: Mapped[bool] = mapped_column(Boolean, default=False)  # degraded mode
    flags: Mapped[list] = mapped_column(JSONB, default=list)
    weights_version: Mapped[int] = mapped_column(Integer, default=1)
    prompt_version: Mapped[str] = mapped_column(String(40), default="")
    model_id: Mapped[str] = mapped_column(String(80), default="")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    application: Mapped[Application] = relationship(back_populates="score")


class ShortlistSnapshot(Base):
    __tablename__ = "shortlist_snapshots"
    id: Mapped[uuid.UUID] = pk()
    job_id: Mapped[uuid.UUID] = fk("jobs.id", index=True)
    policy: Mapped[dict] = mapped_column(JSONB)
    members: Mapped[list] = mapped_column(JSONB)
    below: Mapped[list] = mapped_column(JSONB)
    review_lane: Mapped[list] = mapped_column(JSONB)
    cutoff_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    diff: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id: Mapped[uuid.UUID] = pk()
    application_id: Mapped[uuid.UUID] = fk("applications.id", index=True)
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_kind: Mapped[str] = mapped_column(String(20))  # human | system | candidate
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[uuid.UUID] = pk()
    application_id: Mapped[uuid.UUID] = fk("applications.id", index=True)
    recruiter_id: Mapped[uuid.UUID | None] = fk("users.id", ondelete="SET NULL", nullable=True)
    type: Mapped[str] = mapped_column(String(40))  # should_be_in | should_be_out | requirement_wrong
    comment: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[uuid.UUID] = pk()
    applicant_id: Mapped[uuid.UUID | None] = fk("applicants.id", nullable=True, index=True)
    user_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(40))  # application | talent_pool | alerts
    notice_version: Mapped[str] = mapped_column(String(20))
    granted: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DataSubjectRequest(Base):
    __tablename__ = "data_subject_requests"
    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(320), index=True)
    applicant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    type: Mapped[str] = mapped_column(String(30))  # access | erasure | human_review
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done | rejected
    note: Mapped[str] = mapped_column(Text, default="")
    report: Mapped[dict] = mapped_column(JSONB, default=dict)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    """Append-only, hash-chained audit log."""
    __tablename__ = "audit_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_label: Mapped[str] = mapped_column(String(320), default="")
    action: Mapped[str] = mapped_column(String(60), index=True)
    resource: Mapped[str] = mapped_column(String(120), default="")
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    ip_trunc: Mapped[str] = mapped_column(String(45), default="")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LlmCall(Base):
    """AI supervision: one row per provider call (cost, latency, degraded mode)."""
    __tablename__ = "llm_calls"
    id: Mapped[uuid.UUID] = pk()
    kind: Mapped[str] = mapped_column(String(40), index=True)
    model: Mapped[str] = mapped_column(String(80))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class JobAlert(Base):
    __tablename__ = "job_alerts"
    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = fk("users.id", unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
