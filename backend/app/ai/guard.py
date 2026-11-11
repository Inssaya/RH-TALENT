"""Defences for untrusted documents: prompt-injection detection and personal-data redaction.

The ranking never depends on free LLM text: the model only extracts facts whose evidence is
verified against the CV, and the score is computed by a deterministic formula."""
import re

from .textutil import fold

_INJECTION = [
    r"ignore (all |any |the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |the )?(previous|prior|above)",
    r"ignore[rz]? (toutes )?les instructions",
    r"oublie[rz]? (toutes )?les instructions",
    r"you are now", r"tu es maintenant", r"system prompt", r"as an ai",
    r"(rank|score|rate|classe[rz]?|note[rz]?) (this|me|ce|cette|moi)[^.\n]{0,40}(first|highest|top|premier|100|maximum|best)",
    r"(give|attribue[rz]?|donne[rz]?)[^.\n]{0,30}(maximum|highest|meilleure?|100)[^.\n]{0,20}(score|note|rating)",
    r"this candidate (is|must be) (the )?(best|perfect|ideal|hired|selected)",
    r"ce candidat (est|doit etre) (le )?(meilleur|parfait|ideal|retenu)",
    r"تجاهل (جميع )?التعليمات",
    r"</?(cv_document|system|instructions?)>",
]
_RX = re.compile("|".join(f"(?:{p})" for p in _INJECTION))
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+|00)?\d[\d\s().-]{7,16}\d(?!\d)")
_URL = re.compile(r"https?://\S+|www\.\S+|linkedin\.com/\S+")


def scan_injection(text: str) -> tuple[str, list[str]]:
    """Return (text without suspicious lines, list of removed lines)."""
    kept, removed = [], []
    for line in text.splitlines():
        if _RX.search(fold(line)):
            removed.append(line.strip()[:200])
        else:
            kept.append(line)
    return "\n".join(kept), removed


def redact_pii(text: str, name: str = "") -> str:
    """Pseudonymise before any provider call: contact details and the candidate's name."""
    text = _EMAIL.sub("[EMAIL]", text)
    text = _URL.sub("[URL]", text)
    text = _PHONE.sub("[PHONE]", text)
    for part in [p for p in re.split(r"\s+", name.strip()) if len(p) > 2]:
        text = re.sub(rf"(?i)\b{re.escape(part)}\b", "[NAME]", text)
    return text
