import secrets
from datetime import timedelta

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, emailer
from ..config import get_settings
from ..db import get_db
from ..deps import OrgContext, current_user, org_context
from ..models import Applicant, Membership, Organization, User, now
from ..ratelimit import client_ip, hit, limiter
from ..schemas import LoginIn, OrgIn, RegisterIn
from ..security import COOKIE, create_session, hash_password, new_token, token_hash, verify_password
from ..services import record_consent, unique_slug

router = APIRouter(tags=["auth"])


def _set_cookie(response: Response, user: User) -> None:
    s = get_settings()
    response.set_cookie(COOKIE, create_session(user.id), max_age=s.session_minutes * 60, httponly=True,
                        secure=s.cookie_secure, samesite="lax", path="/")


def user_out(db: Session, user: User) -> dict:
    m = db.scalar(select(Membership).where(Membership.user_id == user.id))
    return {"id": str(user.id), "email": user.email, "full_name": user.full_name, "role": user.role,
            "locale": user.locale, "totp_enabled": user.totp_enabled,
            "organization": {"id": str(m.organization.id), "name": m.organization.name, "role": m.role,
                             "verified": m.organization.verified} if m else None}


@router.post("/auth/register", dependencies=[Depends(limiter("register", 5, 3600))])
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "An account already exists for this e-mail")
    if body.role == "recruiter" and not (body.organization_name or "").strip():
        raise HTTPException(422, "organization_name is required for employers")
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name.strip(),
                role=body.role, locale=body.locale)
    db.add(user)
    db.flush()
    if body.role == "recruiter":
        org = Organization(name=body.organization_name.strip(), slug=unique_slug(db, Organization, body.organization_name))
        db.add(org)
        db.flush()
        db.add(Membership(user_id=user.id, organization_id=org.id, role="org_admin"))
        audit.log(db, "organization.created", actor=user, resource=f"organization:{org.id}",
                  organization_id=org.id, ip=client_ip(request))
    else:
        # link earlier account-less applications made with the same e-mail
        for a in db.scalars(select(Applicant).where(Applicant.email == email, Applicant.user_id.is_(None))):
            a.user_id = user.id
    record_consent(db, "terms", True, user_id=user.id)
    db.flush()
    _set_cookie(response, user)
    return user_out(db, user)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    if not hit(f"login:{email}", 10, 900):
        raise HTTPException(429, "Too many attempts, retry in 15 minutes")
    user = db.scalar(select(User).where(User.email == email))
    ok = bool(user) and user.status == "active" and verify_password(body.password, user.password_hash)
    if ok and user.totp_enabled:
        if not body.totp:
            raise HTTPException(401, "totp_required")
        ok = pyotp.TOTP(user.totp_secret).verify(body.totp, valid_window=1)
    audit.log(db, "auth.login_success" if ok else "auth.login_failed", actor=user if ok else None,
              actor_label=email, ip=client_ip(request))
    if not ok:
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    _set_cookie(response, user)
    return user_out(db, user)


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return user_out(db, user)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    password: str = Field(min_length=10, max_length=128)


@router.post("/auth/forgot", dependencies=[Depends(limiter("forgot", 5, 3600))])
def forgot(body: ForgotIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user:
        token, digest = new_token()
        user.reset_token_hash, user.reset_expires_at = digest, now() + timedelta(hours=2)
        emailer.send(user.email, "TalentMatch : réinitialisation du mot de passe / password reset",
                     f"{get_settings().public_url}/reset?token={token}\n\nValable 2 heures / valid for 2 hours.")
    return {"ok": True}  # same answer whether or not the account exists


@router.post("/auth/reset")
def reset(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.reset_token_hash == token_hash(body.token)))
    if not user or not user.reset_expires_at or user.reset_expires_at < now():
        raise HTTPException(400, "Invalid or expired link")
    user.password_hash, user.reset_token_hash, user.reset_expires_at = hash_password(body.password), None, None
    audit.log(db, "auth.password_reset", actor=user, ip=client_ip(request))
    return {"ok": True}


class TotpIn(BaseModel):
    code: str


@router.post("/auth/totp/setup")
def totp_setup(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.totp_secret, user.totp_enabled = pyotp.random_base32(), False
    return {"secret": user.totp_secret,
            "uri": pyotp.TOTP(user.totp_secret).provisioning_uri(user.email, issuer_name="TalentMatch")}


@router.post("/auth/totp/enable")
def totp_enable(body: TotpIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.totp_secret or not pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1):
        raise HTTPException(400, "Invalid code")
    user.totp_enabled = True
    audit.log(db, "auth.2fa_enabled", actor=user, ip=client_ip(request))
    return {"ok": True}


@router.post("/auth/totp/disable")
def totp_disable(body: LoginIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    user.totp_enabled, user.totp_secret = False, None
    audit.log(db, "auth.2fa_disabled", actor=user, ip=client_ip(request))
    return {"ok": True}


# ---------------------------------------------------------------- organization
def org_out(o: Organization) -> dict:
    return {"id": str(o.id), "name": o.name, "slug": o.slug, "sector": o.sector, "size": o.size, "city": o.city,
            "country": o.country, "website": o.website, "description": o.description, "verified": o.verified}


@router.get("/org")
def get_org(ctx: OrgContext = Depends(org_context)):
    return org_out(ctx.org)


@router.put("/org")
def update_org(body: OrgIn, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    if not ctx.is_admin:
        raise HTTPException(403, "Organization admin required")
    for k, v in body.model_dump().items():
        setattr(ctx.org, k, v)
    return org_out(ctx.org)


@router.get("/org/members")
def members(ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    rows = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                      .where(Membership.organization_id == ctx.org.id))
    return [{"id": str(u.id), "email": u.email, "full_name": u.full_name, "role": m.role} for m, u in rows]


class InviteIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    role: str = "recruiter"


@router.post("/org/members")
def invite(body: InviteIn, request: Request, ctx: OrgContext = Depends(org_context), db: Session = Depends(get_db)):
    if not ctx.is_admin:
        raise HTTPException(403, "Organization admin required")
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "This e-mail already has an account")
    token, digest = new_token()
    user = User(email=email, password_hash=hash_password(secrets.token_urlsafe(24)), full_name=body.full_name,
                role="recruiter", reset_token_hash=digest, reset_expires_at=now() + timedelta(days=7))
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=ctx.org.id,
                      role="org_admin" if body.role == "org_admin" else "recruiter"))
    audit.log(db, "organization.member_added", actor=ctx.user, resource=f"user:{user.id}",
              organization_id=ctx.org.id, ip=client_ip(request), payload={"role": body.role})
    emailer.send(email, f"Invitation TalentMatch : {ctx.org.name}",
                 f"{ctx.user.full_name} vous invite à rejoindre {ctx.org.name}.\n"
                 f"Choisissez votre mot de passe : {get_settings().public_url}/reset?token={token}")
    return {"ok": True}
