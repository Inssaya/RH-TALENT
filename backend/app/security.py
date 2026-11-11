import hashlib
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
