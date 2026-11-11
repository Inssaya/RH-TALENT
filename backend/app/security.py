import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import get_settings

_ph = PasswordHasher()
COOKIE = "tm_session"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, Exception):
        return False


def create_session(user_id: str) -> str:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(minutes=s.session_minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, s.secret_key, algorithm="HS256")


def read_session(token: str) -> str | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        return None


def new_token() -> tuple[str, str]:
    """Return (token to send to the user, hash to store)."""
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


VERIFY_DAYS = 7


def _verify_sig(user_id: str, email: str, exp: int) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"verify:{user_id}:{email}:{exp}".encode(), hashlib.sha256).hexdigest()[:40]


def make_verify_token(user_id, email: str, days: int = VERIFY_DAYS) -> str:
    """Signed, expiring e-mail verification token: "<user id>.<expiry>.<HMAC>". The e-mail address is part
    of the signature, so changing the address invalidates old links. Nothing is stored."""
    exp = int((datetime.now(UTC) + timedelta(days=days)).timestamp())
    uid = str(user_id)
    return f"{uid}.{exp}.{_verify_sig(uid, email, exp)}"


def read_verify_token(token: str, email_of) -> str | None:
    """Return the user id if the token is valid and unexpired. `email_of(uid)` gives the user's current e-mail."""
    try:
        uid, exp_s, sig = token.split(".")
        exp = int(exp_s)
    except ValueError:
        return None
    if exp < datetime.now(UTC).timestamp():
        return None
    email = email_of(uid)
    if not email or not hmac.compare_digest(sig, _verify_sig(uid, email, exp)):
        return None
    return uid
