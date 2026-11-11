"""LLM client: one function, `complete_json`, so the provider can be swapped without touching
business modules. Temperature 0, JSON output, 3 exponential retries, response cache keyed by
(model, prompt version, messages). Returns None when no provider is configured or it fails:
callers then fall back to deterministic rules ("degraded mode")."""
import hashlib
import json
import logging
import time

import httpx

from ..config import get_settings

log = logging.getLogger("tm.llm")
_redis = None


def _cache():
    global _redis
    if _redis is None:
        try:
            import redis
            _redis = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
            _redis.ping()
        except Exception:
            _redis = False
    return _redis or None


def llm_available() -> bool:
    return bool(get_settings().mistral_api_key)


def _record(kind: str, ok: bool, degraded: bool, usage: dict, ms: int, org_id=None) -> None:
    try:
        from ..db import session_factory
        from ..models import LlmCall
        with session_factory()() as db:
            db.add(LlmCall(kind=kind, model=get_settings().llm_model if not degraded else "rules",
                           ok=ok, degraded=degraded, organization_id=org_id,
                           tokens_in=usage.get("prompt_tokens", 0), tokens_out=usage.get("completion_tokens", 0),
                           latency_ms=ms))
            db.commit()
    except Exception:  # supervision must never break the pipeline
        log.debug("could not record llm call", exc_info=True)


def record_degraded(kind: str, org_id=None) -> None:
    _record(kind, True, True, {}, 0, org_id)


def complete_json(kind: str, prompt_version: str, system: str, user: str, org_id=None,
                  max_tokens: int = 2500) -> dict | None:
    s = get_settings()
    if not s.mistral_api_key:
        return None
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    key = "llm:" + hashlib.sha256(json.dumps([s.llm_model, prompt_version, messages]).encode()).hexdigest()
    cache = _cache()
    if cache:
        hit = cache.get(key)
        if hit:
            return json.loads(hit)
    started = time.monotonic()
    for attempt in range(3):
        try:
            r = httpx.post(
                f"{s.mistral_base_url}/chat/completions", timeout=60,
                headers={"Authorization": f"Bearer {s.mistral_api_key}"},
                json={"model": s.llm_model, "messages": messages, "temperature": 0,
                      "max_tokens": max_tokens, "response_format": {"type": "json_object"}},
            )
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
            r.raise_for_status()
            body = r.json()
            data = json.loads(body["choices"][0]["message"]["content"])
            if not isinstance(data, dict):
                raise ValueError("LLM output is not a JSON object")
            _record(kind, True, False, body.get("usage", {}), int((time.monotonic() - started) * 1000), org_id)
            if cache:
                cache.setex(key, 60 * 60 * 24 * 30, json.dumps(data))
            return data
        except Exception as exc:
            log.warning("llm call %s failed (attempt %s): %s", kind, attempt + 1, exc)
            time.sleep(0.5 * 2 ** attempt if s.env != "test" else 0)
    _record(kind, False, False, {}, int((time.monotonic() - started) * 1000), org_id)
    return None
