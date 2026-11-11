"""Job-side AI: structured extraction from free text, chatbot with structured output, quality check.

All five entry channels (chat, voice dictation, pasted text, file, form) converge on the same
JobDraft object validated by one schema (app/schemas.py)."""
import re
import uuid

from .extraction import _EDU_LEVELS, _languages
from .llm import complete_json, record_degraded
from .skills import taxonomy
from .textutil import detect_lang, fold

PROMPT_VERSION = "job_chat_v1"
REQUIRED_FIELDS = ["title", "description", "location", "contract_type", "skills_required"]
_CONTRACTS = [
    ("internship", ["stage", "internship", "stagiaire", "pfe", "تدريب"]),
    ("apprenticeship", ["alternance", "apprentissage", "apprenticeship"]),
    ("freelance", ["freelance", "independant", "contractor", "consultant externe"]),
    ("fixed_term", ["cdd", "fixed-term", "fixed term", "contrat a duree determinee", "temporary", "interim"]),
    ("permanent", ["cdi", "permanent", "contrat a duree indeterminee", "full-time", "full time", "temps plein", "دوام كامل"]),
]
_CITIES = ["casablanca", "rabat", "marrakech", "tanger", "tangier", "fes", "agadir", "kenitra", "oujda", "meknes",
           "tunis", "sfax", "alger", "oran", "paris", "lyon", "marseille", "toulouse", "lille", "bordeaux", "nantes",
           "bruxelles", "brussels", "geneve", "montreal", "dubai", "london", "berlin", "madrid", "barcelona"]
_COUNTRY_OF = {"casablanca": "Maroc", "rabat": "Maroc", "marrakech": "Maroc", "tanger": "Maroc", "tangier": "Maroc",
               "fes": "Maroc", "agadir": "Maroc", "kenitra": "Maroc", "oujda": "Maroc", "meknes": "Maroc",
               "tunis": "Tunisie", "sfax": "Tunisie", "alger": "Algérie", "oran": "Algérie", "paris": "France",
               "lyon": "France", "marseille": "France", "toulouse": "France", "lille": "France", "bordeaux": "France",
               "nantes": "France", "bruxelles": "Belgique", "brussels": "Belgique", "geneve": "Suisse",
               "montreal": "Canada", "dubai": "UAE", "london": "UK", "berlin": "Deutschland", "madrid": "España",
               "barcelona": "España"}
_NICE = re.compile(r"souhaite|nice to have|atout|un plus|bonus|apprecie|ideally|ideal|preferred|serait un plus|يفضل")
_REQ_HEAD = re.compile(r"profil|requirements|qualifications|competences requises|what we expect|you have|vous avez|"
                       r"prerequis|المؤهلات|المتطلبات")
_MIS_HEAD = re.compile(r"missions?|responsab|responsibilit|what you will do|vos taches|role|المهام")
_BULLET = re.compile(r"^\s*(?:[-•*·▪●–]|\d+[.)])\s+(.{8,})$")


def empty_draft() -> dict:
    return {"title": "", "description": "", "missions": [], "city": "", "country": "", "remote": "onsite",
            "contract_type": "", "min_years_experience": 0, "education_level": 0, "languages": [],
            "skills_required": [], "skills_nice": [], "requirements": [], "knockouts": [],
            "salary_min": None, "salary_max": None, "currency": "", "lang": "fr"}


def _rid() -> str:
    return "r" + uuid.uuid4().hex[:8]


def extract_job_rules(text: str) -> dict:
    """Deterministic extraction of a job template from free text."""
    tax = taxonomy()
    f = fold(text)
    d = empty_draft()
    d["lang"] = detect_lang(text) or "fr"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        first = re.sub(r"(?i)^(offre d'emploi|job (offer|posting|title)|poste|intitule|titre)\s*[:\-–]\s*", "", lines[0])
        if len(first) <= 110:
            d["title"] = first.strip(" #*")
    d["description"] = text.strip()[:6000]

    section, nice_ids, req_items, missions = "", set(), [], []
    for ln in text.splitlines():
        fl = fold(ln).strip()
        if len(fl) <= 60 and not _BULLET.match(ln):
            if _MIS_HEAD.search(fl):
                section = "missions"
                continue
            if _NICE.search(fl):
                section = "nice"
                nice_ids.update(tax.find_in_text(ln))
                continue
            if _REQ_HEAD.search(fl):
                section = "req"
                continue
        m = _BULLET.match(ln)
        if _NICE.search(fl) or section == "nice":
            nice_ids.update(tax.find_in_text(ln))
        if m and section == "missions":
            missions.append(m.group(1).strip()[:300])
        elif m and section in ("req", "nice"):
            req_items.append(m.group(1).strip()[:300])
    found = tax.find_in_text(text)
    ordered = sorted(found, key=lambda s: -found[s])
    # keep the most specific skills: drop a parent when one of its children is present
    specific = [s for s in ordered if not any(s in tax.ancestors(o) for o in ordered)]
    lang = d["lang"] if d["lang"] in ("fr", "en") else "en"
    d["skills_required"] = [tax.label(s, lang) for s in specific if s not in nice_ids][:10]
    d["skills_nice"] = [tax.label(s, lang) for s in specific if s in nice_ids][:8]
    d["missions"] = missions[:10]
    d["requirements"] = [{"id": _rid(), "text": t, "type": "requirement"} for t in req_items[:10]]

    m = re.search(r"(\d{1,2})\s*(?:\+|a\s*\d{1,2}|-\s*\d{1,2}|to\s*\d{1,2})?\s*(?:ans|annees|years|yrs|سنوات|سنة)", f)
    if m and int(m.group(1)) <= 30:
        d["min_years_experience"] = int(m.group(1))
    for lvl, kws in _EDU_LEVELS:
        if any(re.search(rf"(?<![a-z0-9]){re.escape(k.strip())}(?![a-z0-9+])", f) for k in kws):
            d["education_level"] = lvl
            break
    d["languages"] = [{"code": lg["code"], "level": lg["level"] or "B2"} for lg in _languages(text, "")]
    for code, kws in _CONTRACTS:
        if any(re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", f) for k in kws):
            d["contract_type"] = code
            break
    if re.search(r"full remote|100 ?% (remote|teletravail)|teletravail (complet|total|integral)|fully remote|remote only|عن بعد", f):
        d["remote"] = "remote"
    elif re.search(r"hybrid|teletravail partiel|\d jours? de teletravail|teletravail", f):
        d["remote"] = "hybrid"
    m = re.search(r"(?im)^(?:lieu|location|localisation|ville|city|المكان)\s*[:\-–]\s*([^\n,;(]+)(?:,\s*([^\n;(]+))?", text)
    if m:
        d["city"] = m.group(1).strip()[:80]
        d["country"] = (m.group(2) or _COUNTRY_OF.get(fold(m.group(1).strip()), "")).strip()[:80]
    else:
        for c in _CITIES:
            if re.search(rf"(?<![a-z]){c}(?![a-z])", f):
                d["city"], d["country"] = c.capitalize(), _COUNTRY_OF.get(c, "")
                break
    m = re.search(r"(\d[\d\s.,]{2,9})\s*(?:-|–|a|to)\s*(\d[\d\s.,]{2,9})\s*(mad|dh|dhs|eur|€|usd|\$|tnd|dzd)", f)
    if m:
        try:
            d["salary_min"] = int(re.sub(r"\D", "", m.group(1)))
            d["salary_max"] = int(re.sub(r"\D", "", m.group(2)))
            d["currency"] = {"€": "EUR", "$": "USD", "dh": "MAD", "dhs": "MAD"}.get(m.group(3), m.group(3).upper())
        except ValueError:
            pass
    return d


def missing_required(draft: dict) -> list[str]:
    miss = []
    if len((draft.get("title") or "").strip()) < 3:
        miss.append("title")
    if len((draft.get("description") or "").strip()) < 200:
        miss.append("description")
    if draft.get("remote") != "remote" and not (draft.get("city") and draft.get("country")):
        miss.append("location")
    if not draft.get("contract_type"):
        miss.append("contract_type")
    if not draft.get("skills_required"):
        miss.append("skills_required")
    return miss


_BIAS = [
    ("age", r"(?<![a-z])(jeune|jeunes|young|junior de moins|moins de \d{2} ans|under \d{2}|digital native|recent graduate|"
            r"jeune diplome|dynamique et jeune|شاب)(?![a-z])"),
    ("gender", r"(?<![a-z])(homme|femme|male|female|man|woman|he will|she will|salesman|waitress|hotesse|"
               r"vendeuse|serveuse|infirmiere|secretaire feminine|رجل|امرأة)(?![a-z])"),
    ("origin", r"(?<![a-z])(native speaker|langue maternelle|mother tongue|nationalite|nationality|de souche)(?![a-z])"),
    ("jargon", r"(?<![a-z])(rockstar|ninja|guru|superstar|hero)(?![a-z])"),
    ("other", r"(?<![a-z])(bonne presentation|good looking|photo (requise|obligatoire|required)|celibataire|single|"
              r"en bonne sante|physically fit)(?![a-z])"),
]


def quality_report(draft: dict) -> dict:
    """Completeness and bias check of a job post. Returns warnings; nothing is blocked silently."""
    warnings = [{"code": f"missing_{f}", "severity": "blocking"} for f in missing_required(draft)]
    text = f"{draft.get('title', '')}\n{draft.get('description', '')}\n" + "\n".join(
        r.get("text", "") for r in draft.get("requirements") or [])
    f = fold(text)
    for kind, pattern in _BIAS:
        for m in re.finditer(pattern, f):
            warnings.append({"code": f"bias_{kind}", "severity": "warning", "term": m.group(0)})
    if len(draft.get("skills_required") or []) > 10:
        warnings.append({"code": "too_many_required_skills", "severity": "warning"})
    if not draft.get("requirements"):
        warnings.append({"code": "no_requirements", "severity": "info"})
    if not draft.get("salary_min"):
        warnings.append({"code": "no_salary", "severity": "info"})
    if draft.get("min_years_experience", 0) and draft["min_years_experience"] > 10:
        warnings.append({"code": "high_experience_bar", "severity": "info"})
    seen, unique = set(), []
    for w in warnings:
        key = (w["code"], w.get("term"))
        if key not in seen:
            seen.add(key)
            unique.append(w)
    score = max(0, 100 - 25 * sum(w["severity"] == "blocking" for w in unique)
                - 8 * sum(w["severity"] == "warning" for w in unique) - 3 * sum(w["severity"] == "info" for w in unique))
    return {"score": score, "warnings": unique, "publishable": not any(w["severity"] == "blocking" for w in unique)}


_QUESTIONS = {
    "title": {"fr": "Quel est l'intitulé du poste ?", "en": "What is the job title?", "ar": "ما هو المسمى الوظيفي؟"},
    "description": {
        "fr": "Décrivez le poste en quelques phrases : missions principales, équipe, contexte.",
        "en": "Describe the role in a few sentences: main missions, team, context.",
        "ar": "صف الوظيفة في بضع جمل: المهام الرئيسية، الفريق، السياق."},
    "location": {"fr": "Où se situe le poste (ville, pays) ? Ou est-il en télétravail complet ?",
                 "en": "Where is the job based (city, country)? Or is it fully remote?",
                 "ar": "أين مقر الوظيفة (المدينة، البلد)؟ أم أنها عن بعد بالكامل؟"},
    "contract_type": {"fr": "Quel type de contrat : CDI, CDD, stage, alternance ou freelance ?",
                      "en": "Which contract type: permanent, fixed-term, internship, apprenticeship or freelance?",
                      "ar": "ما نوع العقد: دائم، محدد المدة، تدريب أم عمل حر؟"},
    "skills_required": {"fr": "Quelles compétences sont indispensables pour ce poste ?",
                        "en": "Which skills are essential for this role?",
                        "ar": "ما هي المهارات الأساسية لهذه الوظيفة؟"},
    "done": {"fr": "L'offre est complète. Relisez le formulaire, puis publiez-la quand vous êtes prêt.",
             "en": "The job post is complete. Review the form, then publish when you are ready.",
             "ar": "عرض العمل مكتمل. راجع النموذج ثم انشره عندما تكون جاهزا."},
}
_PATCHABLE = {"title", "description", "missions", "city", "country", "remote", "contract_type",
              "min_years_experience", "education_level", "languages", "skills_required", "skills_nice",
              "requirements", "salary_min", "salary_max", "currency"}
_SYSTEM = """You help a recruiter build a structured job post. Reply with ONE JSON object:
{"patch": {...fields to set...}, "next_question": "...", "warnings": ["..."]}.
Allowed patch keys: title, description, missions (array of strings), city, country,
remote ("onsite"|"hybrid"|"remote"), contract_type ("permanent"|"fixed_term"|"internship"|
"apprenticeship"|"freelance"), min_years_experience (number), education_level (ISCED 0-8),
languages (array of {code, level}), skills_required, skills_nice (arrays of strings),
requirements (array of {text}), salary_min, salary_max, currency.
Only set what the recruiter actually said. Never touch locked fields. Ask one short question
about the most important missing field, in the recruiter's language."""


def _merge(draft: dict, patch: dict, locked: set[str]) -> dict:
    out = dict(draft)
    for k, v in patch.items():
        if k not in _PATCHABLE or k in locked or v in (None, "", [], 0):
            continue
        if k in ("skills_required", "skills_nice", "missions"):
            if isinstance(v, list):
                cur = list(out.get(k) or [])
                out[k] = cur + [str(x)[:120] for x in v if str(x).strip() and fold(str(x)) not in {fold(c) for c in cur}]
        elif k == "requirements":
            cur = list(out.get(k) or [])
            known = {fold(r["text"]) for r in cur}
            for r in v if isinstance(v, list) else []:
                t = (r.get("text") if isinstance(r, dict) else str(r) or "").strip()
                if t and fold(t) not in known:
                    cur.append({"id": _rid(), "text": t[:300], "type": "requirement"})
            out[k] = cur[:15]
        elif k == "languages":
            out[k] = [{"code": str(x.get("code", ""))[:5], "level": x.get("level") or "B2"}
                      for x in v if isinstance(x, dict) and x.get("code")]
        elif k == "description":
            cur = out.get("description") or ""
            out[k] = str(v) if len(str(v)) > len(cur) or not cur else f"{cur}\n{v}"
        else:
            out[k] = v
    out["skills_nice"] = [s for s in out.get("skills_nice") or []
                          if fold(s) not in {fold(x) for x in out.get("skills_required") or []}]
    return out


def chat_turn(draft: dict, message: str, asked_field: str | None, locked: list[str], org_id=None) -> dict:
    """One chatbot turn. Returns the updated draft, the reply and the next field being asked."""
    locked_set = set(locked or [])
    lang = detect_lang(message) or draft.get("lang") or "fr"
    lang = lang if lang in ("fr", "en", "ar") else "fr"
    warnings: list[str] = []
    data = complete_json(
        "job_chat", PROMPT_VERSION, _SYSTEM,
        f"Current draft: {draft}\nLocked fields: {sorted(locked_set)}\nQuestion just asked about: {asked_field}\n"
        f"<recruiter_message>\n{message[:4000]}\n</recruiter_message>", org_id, max_tokens=1200)
    if data and isinstance(data.get("patch"), dict):
        new = _merge(draft, data["patch"], locked_set)
        warnings = [str(w)[:200] for w in data.get("warnings") or []][:5]
    else:
        record_degraded("job_chat", org_id)
        patch = extract_job_rules(message)
        # in rule mode the first line is only a title when that is the question being answered
        if asked_field != "title" and (draft.get("title") or len(message.splitlines()) < 3):
            patch["title"] = ""
        if asked_field == "title" and not patch["title"]:
            patch["title"] = message.strip()[:110]
        if asked_field == "skills_required" and not patch["skills_required"]:
            patch["skills_required"] = [s.strip() for s in re.split(r"[,;\n]| et | and ", message) if 1 < len(s.strip()) < 60]
        if asked_field == "location" and not patch["city"]:
            parts = [p.strip() for p in re.split(r"[,/]", message) if p.strip()]
            if parts and len(parts[0]) < 60:
                patch["city"], patch["country"] = parts[0], (parts[1] if len(parts) > 1 else "")
        if asked_field != "description" and draft.get("description") and len(message) < 200:
            patch["description"] = ""
        if patch.get("remote") == "onsite":
            patch.pop("remote")
        new = _merge(draft, patch, locked_set)
    new["lang"] = draft.get("lang") or lang
    miss = missing_required(new)
    nxt = miss[0] if miss else None
    reply = _QUESTIONS[nxt or "done"][lang]
    if data and data.get("next_question") and nxt:
        reply = str(data["next_question"])[:400]
    return {"draft": new, "reply": reply, "asked_field": nxt, "missing_required": miss, "warnings": warnings,
            "degraded": data is None}
