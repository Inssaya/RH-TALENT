import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Membership, Organization, User
from .security import COOKIE, read_session


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    token = request.cookies.get(COOKIE)
    uid = read_session(token) if token else None
    if not uid:
        return None
    user = db.get(User, uuid.UUID(uid))
    return user if user and user.status == "active" else None


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if not user:
        raise HTTPException(401, "Authentication required")
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
