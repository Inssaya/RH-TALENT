"""Text embeddings behind one interface.

Providers:
- "hash"    deterministic, dependency-free signed feature hashing, made concept-aware by
            injecting canonical skill ids as tokens (so FR/EN/AR mentions of a skill align).
            Default: works offline with zero cost.
- "bge-m3"  BAAI/bge-m3 through sentence-transformers (install the `bge` extra).
- "mistral" mistral-embed through the API (padded/truncated to the configured dimension).
"""
import hashlib
import math
from functools import lru_cache

import numpy as np

from ..config import get_settings
from .skills import taxonomy
from .textutil import tokens

_STOP = set("le la les des de du et en un une pour avec dans sur au aux the and of to in for with on a an at by "
            "from as is are was be this that ou or par que qui est sont في من على إلى و".split())


def _bucket(tok: str, dim: int) -> tuple[int, float]:
    h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
    idx = int.from_bytes(h[:4], "little") % dim
    sign = 1.0 if h[4] & 1 else -1.0
    return idx, sign


def _hash_embed(text: str, dim: int) -> list[float]:
    vec = np.zeros(dim, dtype=np.float32)
    toks = [t for t in tokens(text) if t not in _STOP and len(t) > 1]
    counts: dict[str, float] = {}
    for t in toks:
        counts[t] = counts.get(t, 0) + 1.0
    for a, b in zip(toks, toks[1:], strict=False):
        counts[f"{a}_{b}"] = counts.get(f"{a}_{b}", 0) + 0.5
    tax = taxonomy()
    for sid, n in tax.find_in_text(text).items():
        counts[f"skill:{sid}"] = counts.get(f"skill:{sid}", 0) + 3.0 * n
        for anc in tax.ancestors(sid):
            counts[f"skill:{anc}"] = counts.get(f"skill:{anc}", 0) + 1.0
    for tok, c in counts.items():
        idx, sign = _bucket(tok, dim)
        vec[idx] += sign * (1.0 + math.log(c))
    norm = float(np.linalg.norm(vec))
    return (vec / norm).tolist() if norm else vec.tolist()


@lru_cache
def _st_model():
    from sentence_transformers import SentenceTransformer  # optional dependency
    return SentenceTransformer("BAAI/bge-m3")


def _fit(vec: list[float], dim: int) -> list[float]:
    v = np.zeros(dim, dtype=np.float32)
    v[: min(dim, len(vec))] = vec[:dim]
    n = float(np.linalg.norm(v))
    return (v / n).tolist() if n else v.tolist()


def embed(text: str) -> list[float]:
    s = get_settings()
    text = (text or "")[:8000]
    if s.embeddings_provider == "bge-m3":
        return _fit(_st_model().encode(text, normalize_embeddings=True).tolist(), s.embedding_dim)
    if s.embeddings_provider == "mistral" and s.mistral_api_key:
        import httpx
        r = httpx.post(f"{s.mistral_base_url}/embeddings", timeout=30,
                       headers={"Authorization": f"Bearer {s.mistral_api_key}"},
                       json={"model": "mistral-embed", "input": [text]})
        r.raise_for_status()
        return _fit(r.json()["data"][0]["embedding"], s.embedding_dim)
    return _hash_embed(text, s.embedding_dim)


def cosine(a, b) -> float:
    if a is None or b is None:
        return 0.0
    a, b = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return float(a @ b / (na * nb)) if na and nb else 0.0
