"""Fixed-window rate limiting on Redis, with an in-process fallback."""
import time

from fastapi import HTTPException, Request

from .config import get_settings

_mem: dict[str, tuple[int, float]] = {}
_redis = None


def _client():
    global _redis
    if _redis is None:
        try:
            import redis
            _redis = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
            _redis.ping()
        except Exception:
            _redis = False
    return _redis or None


def hit(key: str, limit: int, window: int) -> bool:
    """Count one event; return False when the limit is exceeded."""
    if not get_settings().rate_limit_enabled:
        return True
    r = _client()
    if r:
        try:
            n = r.incr(f"rl:{key}")
            if n == 1:
                r.expire(f"rl:{key}", window)
            return n <= limit
        except Exception:
            pass
    count, start = _mem.get(key, (0, time.time()))
    if time.time() - start > window:
        count, start = 0, time.time()
    _mem[key] = (count + 1, start)
    return count + 1 <= limit


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")


def limiter(name: str, limit: int, window: int):
    def dep(request: Request) -> None:
        if not hit(f"{name}:{client_ip(request)}", limit, window):
            raise HTTPException(429, "Too many requests, please retry later")
    return dep
