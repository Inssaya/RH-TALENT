"""E-mail verification and mandatory two-factor authentication."""
import re
import time
import uuid

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import emailer
from app.db import session_factory
from app.main import app
from app.matching import suggest_talents
from app.models import CandidateProfile, Job, Membership, Organization, User
from app.security import hash_password, make_verify_token
from app.services import current_version

from .conftest import CV_LINA, JOB, PASSWORD, enroll_totp, published_job, register, verify_email


def u():
    return uuid.uuid4().hex[:8]


def candidate_with_cv(email):
    c = TestClient(app)
    register(c, email, role="candidate")
    r = c.post("/api/candidate/profile/cv", files={"file": ("cv.txt", CV_LINA.encode(), "text/plain")})
    assert r.status_code == 200
    return c


def test_registration_sends_a_verification_link_and_starts_unverified():
    email = f"new-{u()}@ver.example.org"
    c = TestClient(app)
    me = register(c, email, role="candidate")
    assert me["email_verified"] is False
    mail = [m for m in emailer.outbox if m["to"] == email][-1]
    assert re.search(r"/verify\?token=[\w.-]+", mail["body"])
    verify_email(c, email)
    assert c.get("/api/auth/me").json()["email_verified"] is True


def test_unverified_candidate_cannot_apply_in_one_click_or_become_visible_or_get_alerts():
    email = f"unv-{u()}@ver.example.org"
    rec = TestClient(app)
    register(rec, f"r-{u()}@ver.example.org", org="Ver")
    job = published_job(rec)
    cand = candidate_with_cv(email)

    r = cand.post(f"/api/candidate/apply/{job['slug']}")
    assert r.status_code == 403 and r.json()["detail"] == "email_not_verified"
    prof = cand.get("/api/candidate/profile").json()["data"]
    body = {"title": prof["title"], "summary": prof["summary"], "location": "", "skills": [s["label"] for s in prof["skills"]]}
    assert cand.put("/api/candidate/profile", json={**body, "visible_to_recruiters": True, "alerts": False}).status_code == 403
    assert cand.put("/api/candidate/profile", json={**body, "visible_to_recruiters": False, "alerts": True}).status_code == 403
    # saving the profile itself is allowed
    assert cand.put("/api/candidate/profile", json={**body, "visible_to_recruiters": False, "alerts": False}).status_code == 200

    verify_email(cand, email)
    assert cand.put("/api/candidate/profile", json={**body, "visible_to_recruiters": True, "alerts": True}).status_code == 200
    assert cand.post(f"/api/candidate/apply/{job['slug']}").status_code == 200


def test_unverified_profile_is_never_suggested_to_recruiters():
    rec = TestClient(app)
    register(rec, f"r-{u()}@ver.example.org", org="Ver2")
    job = published_job(rec)
    email = f"hid-{u()}@ver.example.org"
    candidate_with_cv(email)
    with session_factory()() as db:  # force the opt-in flag, as a stale or tampered row would
        user = db.scalar(select(User).where(User.email == email))
        prof = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
        prof.visible_to_recruiters = True
        db.commit()
        j = db.get(Job, uuid.UUID(job["id"]))
        names = [t["name"] for t in suggest_talents(db, j, current_version(db, j))]
        assert user.full_name not in names
        user.email_verified_at = user.created_at
        db.commit()
        assert user.full_name in [t["name"] for t in suggest_talents(db, j, current_version(db, j))]


def test_verification_token_cannot_be_forged_reused_across_users_or_expired():
    a, b = f"a-{u()}@ver.example.org", f"b-{u()}@ver.example.org"
    ca, cb = TestClient(app), TestClient(app)
    register(ca, a, role="candidate")
    register(cb, b, role="candidate")
    with session_factory()() as db:
        ua = db.scalar(select(User).where(User.email == a))
        ub = db.scalar(select(User).where(User.email == b))
        a_id, a_email, b_id = ua.id, ua.email, ub.id
    anon = TestClient(app)
    good = make_verify_token(a_id, a_email)
    uid, exp, sig = good.split(".")
    for bad in [f"{uid}.{exp}.{'0' * 40}",                       # wrong signature
                f"{b_id}.{exp}.{sig}",                            # A's signature on B's id
                f"{uid}.{int(exp) + 99999}.{sig}",                # tampered expiry
                make_verify_token(a_id, a_email, days=-1),        # expired
                make_verify_token(a_id, "someone@else.org"),      # signed for another address
                "garbage", ""]:
        assert anon.post("/api/auth/verify", json={"token": bad}).status_code == 400, bad
    assert cb.get("/api/auth/me").json()["email_verified"] is False
    assert anon.post("/api/auth/verify", json={"token": good}).status_code == 200  # no session needed
    assert ca.get("/api/auth/me").json()["email_verified"] is True
    assert cb.get("/api/auth/me").json()["email_verified"] is False


def test_resend_verification_is_limited_and_idempotent_once_verified():
    email = f"rs-{u()}@ver.example.org"
    c = TestClient(app)
    register(c, email, role="candidate")
    before = len([m for m in emailer.outbox if m["to"] == email])
    assert c.post("/api/auth/resend-verification").status_code == 200
    assert len([m for m in emailer.outbox if m["to"] == email]) == before + 1
    assert TestClient(app).post("/api/auth/resend-verification").status_code == 401
    verify_email(c, email)
    assert c.post("/api/auth/resend-verification").json()["already_verified"] is True


def test_password_reset_proves_ownership_of_the_address():
    email = f"pw-{u()}@ver.example.org"
    c = TestClient(app)
    register(c, email, role="candidate")
    assert c.post("/api/auth/forgot", json={"email": email}).status_code == 200
    token = re.search(r"token=([\w-]+)", [m for m in emailer.outbox if m["to"] == email and "reset" in m["body"]][-1]["body"]).group(1)
    assert TestClient(app).post("/api/auth/reset", json={"token": token, "password": "another-long-password"}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401  # the reset signed the old session out
    again = TestClient(app)
    assert again.post("/api/auth/login", json={"email": email, "password": "another-long-password"}).status_code == 200
    assert again.get("/api/auth/me").json()["email_verified"] is True


# ---------------------------------------------------------------- mandatory two-factor
def test_organization_admin_is_locked_out_of_everything_until_two_factor_is_enrolled():
    email = f"adm-{u()}@tfa.example.org"
    c = TestClient(app)
    me = register(c, email, org="Tfa Org", enroll=False, verify=False)
    assert me["totp_setup_required"] is True and me["organization"]["role"] == "org_admin"
    for method, path in [("get", "/api/jobs"), ("post", "/api/jobs"), ("get", "/api/org"), ("get", "/api/org/analytics"),
                         ("get", "/api/org/members")]:
        r = getattr(c, method)(path) if method == "get" else c.post(path, json=JOB)
        assert r.status_code == 403 and r.json()["detail"] == "totp_setup_required", path
    assert c.get("/api/auth/me").status_code == 200  # status and enrolment stay reachable

    secret = enroll_totp(c)
    assert c.get("/api/jobs").status_code == 200
    me = c.get("/api/auth/me").json()
    assert me["totp_enabled"] is True and me["totp_setup_required"] is False

    # the factor cannot be removed while the role requires it
    r = c.post("/api/auth/totp/disable", json={"email": email, "password": PASSWORD})
    assert r.status_code == 403 and c.get("/api/auth/me").json()["totp_enabled"] is True

    # logging in now needs the code
    other = TestClient(app)
    r = other.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 401 and r.json()["detail"] == "totp_required"
    r = other.post("/api/auth/login", json={"email": email, "password": PASSWORD, "totp": "000000"})
    assert r.status_code == 401 and r.json()["detail"] == "Invalid credentials"
    r = other.post("/api/auth/login", json={"email": email, "password": PASSWORD, "totp": pyotp.TOTP(secret).now()})
    assert r.status_code == 200 and other.get("/api/jobs").status_code == 200


def test_platform_admin_needs_two_factor_but_plain_recruiters_and_candidates_do_not():
    suffix = u()
    with session_factory()() as db:
        db.add(User(email=f"root-{suffix}@tfa.example.org", password_hash=hash_password(PASSWORD), full_name="Root",
                    role="platform_admin"))
        org = Organization(name=f"Member Org {suffix}", slug=f"member-org-{suffix}")
        member = User(email=f"member-{suffix}@tfa.example.org", password_hash=hash_password(PASSWORD), full_name="Member",
                      role="recruiter")
        db.add_all([org, member])
        db.flush()
        db.add(Membership(user_id=member.id, organization_id=org.id, role="recruiter"))
        db.commit()

    admin = TestClient(app)
    assert admin.post("/api/auth/login", json={"email": f"root-{suffix}@tfa.example.org", "password": PASSWORD}).status_code == 200
    r = admin.get("/api/admin/stats")
    assert r.status_code == 403 and r.json()["detail"] == "totp_setup_required"
    enroll_totp(admin)
    assert admin.get("/api/admin/stats").status_code == 200

    plain = TestClient(app)
    assert plain.post("/api/auth/login", json={"email": f"member-{suffix}@tfa.example.org", "password": PASSWORD}).status_code == 200
    me = plain.get("/api/auth/me").json()
    assert me["totp_setup_required"] is False and plain.get("/api/jobs").status_code == 200

    cand = TestClient(app)
    assert register(cand, f"c-{suffix}@tfa.example.org", role="candidate")["totp_setup_required"] is False
    assert cand.get("/api/candidate/profile").status_code == 200


def test_promoting_a_member_to_admin_requires_two_factor_from_then_on():
    suffix = u()
    owner = TestClient(app)
    register(owner, f"own-{suffix}@tfa.example.org", org=f"Promo {suffix}")
    assert owner.post("/api/org/members", json={"email": f"new-{suffix}@tfa.example.org", "full_name": "New Admin",
                                                "role": "org_admin"}).status_code == 200
    mail = [m for m in emailer.outbox if m["to"] == f"new-{suffix}@tfa.example.org"][-1]
    token = re.search(r"token=([\w-]+)", mail["body"]).group(1)
    invited = TestClient(app)
    assert invited.post("/api/auth/reset", json={"token": token, "password": "a-brand-new-password"}).status_code == 200
    assert invited.post("/api/auth/login", json={"email": f"new-{suffix}@tfa.example.org", "password": "a-brand-new-password"}).status_code == 200
    r = invited.get("/api/jobs")
    assert r.status_code == 403 and r.json()["detail"] == "totp_setup_required"
    assert invited.get("/api/auth/me").json()["email_verified"] is True  # invitation link proved the address


# ---------------------------------------------------------------- replacing the second factor
def test_replacing_the_authenticator_needs_the_current_code_and_stays_pending_until_confirmed():
    email = f"rep-{u()}@tfa.example.org"
    c = TestClient(app)
    old = register(c, email, org="Rep Org")["totp_secret"]

    # a session cookie alone cannot start a replacement
    assert c.post("/api/auth/totp/setup").status_code == 403
    assert c.post("/api/auth/totp/setup", json={"code": "000000"}).status_code == 403
    login = {"email": email, "password": PASSWORD, "totp": pyotp.TOTP(old).now()}
    assert TestClient(app).post("/api/auth/login", json=login).status_code == 200  # old factor untouched

    # with the current code, a new secret is issued but is not active yet
    r = c.post("/api/auth/totp/setup", json={"code": pyotp.TOTP(old).now()})
    assert r.status_code == 200
    new = r.json()["secret"]
    assert new != old
    assert TestClient(app).post("/api/auth/login", json=login).status_code == 200  # old code still logs in
    assert TestClient(app).post("/api/auth/login", json={**login, "totp": pyotp.TOTP(new).now()}).status_code == 401

    # confirming with a code from the OLD secret does not activate it; the new one does
    assert c.post("/api/auth/totp/enable", json={"code": pyotp.TOTP(old).now()}).status_code == 400
    assert c.post("/api/auth/totp/enable", json={"code": pyotp.TOTP(new).now()}).status_code == 200
    assert TestClient(app).post("/api/auth/login", json={**login, "totp": pyotp.TOTP(old).now()}).status_code == 401
    assert TestClient(app).post("/api/auth/login", json={**login, "totp": pyotp.TOTP(new).now()}).status_code == 200
    # nothing pending any more: enable without a new setup is refused
    assert c.post("/api/auth/totp/enable", json={"code": pyotp.TOTP(new).now()}).status_code == 400


def test_inviting_a_talent_never_emails_an_unverified_address():
    rec = TestClient(app)
    register(rec, f"inv-{u()}@tfa.example.org", org="Invite Org")
    job = published_job(rec)
    email = f"talent-{u()}@ver.example.org"
    candidate_with_cv(email)
    with session_factory()() as db:  # a row flagged visible although the address was never confirmed
        user = db.scalar(select(User).where(User.email == email))
        prof = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
        prof.visible_to_recruiters = True
        pid, uid = str(prof.id), user.id
        db.commit()
    sent = lambda: len([m for m in emailer.outbox if m["to"] == email and "invites you to apply" in m["subject"]])  # noqa: E731
    r = rec.post(f"/api/jobs/{job['id']}/talents/{pid}/invite")
    assert r.status_code == 404 and sent() == 0
    with session_factory()() as db:
        db.get(User, uid).email_verified_at = db.get(User, uid).created_at
        db.commit()
    assert rec.post(f"/api/jobs/{job['id']}/talents/{pid}/invite").status_code == 200 and sent() == 1


def test_unverified_employer_can_draft_but_not_publish():
    email = f"pub-{u()}@tfa.example.org"
    c = TestClient(app)
    register(c, email, org="Pub Org", verify=False)
    job = c.post("/api/jobs", json=JOB)
    assert job.status_code == 200                                    # drafts are allowed
    r = c.post(f"/api/jobs/{job.json()['id']}/publish")
    assert r.status_code == 403 and r.json()["detail"] == "email_not_verified"
    assert TestClient(app).get(f"/api/public/jobs/{job.json()['slug']}").status_code == 404   # nothing went public
    verify_email(c, email)
    assert c.post(f"/api/jobs/{job.json()['id']}/publish").status_code == 200
    assert TestClient(app).get(f"/api/public/jobs/{job.json()['slug']}").status_code == 200


# ---------------------------------------------------------------- passwords and sessions
def _clone_session(client):
    """A second client holding the same session cookie, like a stolen or forgotten browser."""
    other = TestClient(app)
    for cookie in client.cookies.jar:
        other.cookies.set(cookie.name, cookie.value)
    return other


def test_password_change_signs_out_other_sessions_and_keeps_the_caller_signed_in():
    email = f"chg-{u()}@pw.example.org"
    c = TestClient(app)
    register(c, email, role="candidate")
    old_session = _clone_session(c)
    assert old_session.get("/api/auth/me").status_code == 200

    # wrong current password, same password, too short: nothing changes
    assert c.post("/api/auth/password", json={"current_password": "nope-nope-nope", "new_password": "a-very-new-password"}).status_code == 401
    assert c.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": PASSWORD}).status_code == 422
    assert c.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"}).status_code == 422
    assert old_session.get("/api/auth/me").status_code == 200

    assert c.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "a-very-new-password"}).status_code == 200
    assert old_session.get("/api/auth/me").status_code == 401        # stolen or forgotten session is dead
    assert c.get("/api/auth/me").status_code == 200                   # caller got a fresh cookie
    assert TestClient(app).post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"email": email, "password": "a-very-new-password"}).status_code == 200
    assert TestClient(app).post("/api/auth/password", json={"current_password": "x", "new_password": "y" * 12}).status_code == 401


def test_password_change_asks_for_a_second_factor_code_when_enabled():
    email = f"chg2-{u()}@pw.example.org"
    c = TestClient(app)
    secret = register(c, email, org="Pw Org")["totp_secret"]
    body = {"current_password": PASSWORD, "new_password": "a-very-new-password"}
    r = c.post("/api/auth/password", json=body)
    assert r.status_code == 401 and r.json()["detail"] == "totp_required"
    assert c.post("/api/auth/password", json={**body, "totp": "000000"}).status_code == 401
    assert c.post("/api/auth/password", json={**body, "totp": pyotp.TOTP(secret).now()}).status_code == 200


def test_password_reset_also_signs_out_every_existing_session():
    email = f"rst-{u()}@pw.example.org"
    c = TestClient(app)
    register(c, email, role="candidate")
    stolen = _clone_session(c)
    assert c.post("/api/auth/forgot", json={"email": email}).status_code == 200
    token = re.search(r"token=([\w-]+)", [m for m in emailer.outbox if m["to"] == email and "reset" in m["body"]][-1]["body"]).group(1)
    assert TestClient(app).post("/api/auth/reset", json={"token": token, "password": "reset-long-password"}).status_code == 200
    assert stolen.get("/api/auth/me").status_code == 401 and c.get("/api/auth/me").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"email": email, "password": "reset-long-password"}).status_code == 200


def test_a_session_issued_before_this_feature_without_a_version_claim_still_works_until_the_password_changes():
    """Existing cookies (no 'pwv' claim) keep working for users who never changed their password."""
    import jwt

    from app.config import get_settings
    email = f"old-{u()}@pw.example.org"
    c = TestClient(app)
    me = register(c, email, role="candidate")
    legacy = jwt.encode({"sub": me["id"], "exp": int(time.time()) + 600}, get_settings().secret_key, algorithm="HS256")
    old = TestClient(app)
    old.cookies.set("tm_session", legacy)
    assert old.get("/api/auth/me").status_code == 200
    assert c.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "a-very-new-password"}).status_code == 200
    assert old.get("/api/auth/me").status_code == 401
