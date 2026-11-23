import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Membership, Organization, User
from .security import COOKIE, read_session, session_version


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE)
    session = read_session(token) if token else None
    if not session:
        return None
    user = db.get(User, uuid.UUID(session[0]))
    if not user or user.status != "active" or session[1] != session_version(user):
        return None  # unknown, suspended, or issued before the last password change or reset
    return user


def totp_required(db: Session, user: User) -> bool:
    """Two-factor authentication is mandatory for platform admins and organization admins."""
    if user.role == "platform_admin":
        return True
    if user.role == "recruiter":
        return db.scalar(select(Membership.id).where(Membership.user_id == user.id, Membership.role == "org_admin")) is not None
    return False


def current_user(request: Request, user: User | None = Depends(current_user_optional),
                 db: Session = Depends(get_db)) -> User:
    if not user:
        raise HTTPException(401, "Authentication required")
    # Until two-factor is set up, only the /api/auth/* routes (setup, status, logout) are reachable.
    if not user.totp_enabled and not request.url.path.startswith("/api/auth/") and totp_required(db, user):
        raise HTTPException(403, "totp_setup_required")
    return user


def verified_user(user: User = Depends(current_user)) -> User:
    if user.email_verified_at is None:
        raise HTTPException(403, "email_not_verified")
    return user


def require_role(*roles: str):
    """Deny by default: a route only opens for the roles it lists."""
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Forbidden")
        return user
    return dep


class OrgContext:
    def __init__(self, user: User, org: Organization, role: str):
        self.user, self.org, self.role = user, org, role

    @property
    def is_admin(self) -> bool:
        return self.role == "org_admin"


def org_context(user: User = Depends(require_role("recruiter")), db: Session = Depends(get_db)) -> OrgContext:
    m = db.scalar(select(Membership).where(Membership.user_id == user.id))
    if not m:
        raise HTTPException(403, "No organization")
    if m.organization.status != "active":
        raise HTTPException(403, "Organization suspended")
    return OrgContext(user, m.organization, m.role)
