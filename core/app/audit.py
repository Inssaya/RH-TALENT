"""Append-only audit log. Each row stores the hash of the previous one, so any later
modification or deletion breaks the chain (checked by `verify_chain`)."""
import hashlib
import json

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import AuditEvent, now


def _digest(prev: str, e: AuditEvent) -> str:
    body = json.dumps([prev, str(e.actor_id or ""), e.actor_label, e.action, e.resource,
                       str(e.organization_id or ""), e.ip_trunc, e.payload, e.created_at.isoformat()],
                      sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def trunc_ip(ip: str) -> str:
    if ":" in ip:
        return ":".join(ip.split(":")[:3]) + "::"
    parts = ip.split(".")
    return ".".join(parts[:3] + ["0"]) if len(parts) == 4 else ""


def log(db: Session, action: str, *, actor=None, actor_label: str = "", resource: str = "",
        organization_id=None, ip: str = "", payload: dict | None = None) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(7411)"))  # serialise the chain
    prev = db.scalar(select(AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)) or ""
    e = AuditEvent(actor_id=getattr(actor, "id", None), actor_label=actor_label or getattr(actor, "email", "system"),
                   action=action, resource=resource, organization_id=organization_id, ip_trunc=trunc_ip(ip),
                   payload=payload or {}, prev_hash=prev, created_at=now())
    e.hash = _digest(prev, e)
    db.add(e)
    db.flush()


def verify_chain(db: Session) -> dict:
    prev, count = "", 0
    for e in db.scalars(select(AuditEvent).order_by(AuditEvent.seq)).yield_per(500):
        if e.prev_hash != prev or e.hash != _digest(prev, e):
            return {"ok": False, "broken_at": e.seq, "checked": count}
        prev, count = e.hash, count + 1
    return {"ok": True, "checked": count}
