"""Skill taxonomy and normalisation.

Ships with a compact multilingual taxonomy (FR/EN/AR aliases, one level of hierarchy).
The full ESCO export can be merged in with `tm import-esco <skills_xx.csv>`; the file is
appended to the taxonomy at load time (see ESCO_EXTRA).
"""
import csv
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

from .textutil import bounded, fold

DATA = Path(__file__).resolve().parent.parent / "data"
ESCO_EXTRA = DATA / "esco_extra.json"
# Labels that are also common words: only matched with their capitalised spelling.
CASE_SENSITIVE = {"Tableau", "Swift", "Go", "Rust", "Ruby", "Spring", "Flask", "Oracle", "Word", "Sage", "R", "Scala"}


@dataclass
class Skill:
    id: str
    broader: str
    label_en: str
    label_fr: str
    aliases: list[str] = field(default_factory=list)

    def label(self, lang: str = "en") -> str:
        return self.label_fr if lang == "fr" else self.label_en


class Taxonomy:
    def __init__(self, skills: list[Skill]):
        self.skills = {s.id: s for s in skills}
        self.alias_to_id: dict[str, str] = {}
        cs_alts: dict[str, str] = {}
        short_alts: dict[str, str] = {}
        for s in skills:
            for name in {s.label_en, s.label_fr, *s.aliases}:
                name = name.strip()
                if not name:
                    continue
                self.alias_to_id.setdefault(fold(name), s.id)
                if name in CASE_SENSITIVE:
                    cs_alts[name] = s.id
                elif len(name) <= 2:
                    short_alts[name.upper()] = s.id
        self._cs = cs_alts | short_alts
        folded = sorted((a for a in self.alias_to_id if len(a) > 2 and
                         not any(fold(c) == a for c in CASE_SENSITIVE)), key=len, reverse=True)
        self._rx = bounded("|".join(re.escape(a) for a in folded))
        self._rx_cs = bounded("|".join(re.escape(a) for a in sorted(self._cs, key=len, reverse=True)))
        self._choices = list(self.alias_to_id.keys())

    # --- hierarchy -----------------------------------------------------
    def ancestors(self, sid: str) -> list[str]:
        out, seen = [], set()
        cur = self.skills.get(sid)
        while cur and cur.broader and cur.broader not in seen:
            out.append(cur.broader)
            seen.add(cur.broader)
            cur = self.skills.get(cur.broader)
        return out

    def satisfies(self, have: str, need: str) -> bool:
        """A more specific skill satisfies a more general requirement, not the reverse."""
        return have == need or need in self.ancestors(have)

    def related(self, have: str, need: str) -> bool:
        """Sibling skills, or a general skill held where a specific one is required."""
        a, b = self.skills.get(have), self.skills.get(need)
        if not a or not b:
            return False
        if have in self.ancestors(need):
            return True
        return bool(a.broader) and a.broader == b.broader

    # --- normalisation --------------------------------------------------
    def normalise(self, raw: str) -> str | None:
        key = fold(raw.strip())
        if not key:
            return None
        if key in self.alias_to_id:
            return self.alias_to_id[key]
        if len(key) < 4:
            return None
        hit = process.extractOne(key, self._choices, scorer=fuzz.ratio, score_cutoff=90)
        return self.alias_to_id[hit[0]] if hit else None

    def find_in_text(self, text: str) -> dict[str, int]:
        """Return {skill_id: number of mentions} for skills mentioned in free text."""
        found: dict[str, int] = {}
        for m in self._rx.finditer(fold(text)):
            sid = self.alias_to_id[m.group(0)]
            found[sid] = found.get(sid, 0) + 1
        for m in self._rx_cs.finditer(text):
            sid = self._cs[m.group(0)]
            found[sid] = found.get(sid, 0) + 1
        return found

    def label(self, sid: str, lang: str = "en") -> str:
        s = self.skills.get(sid)
        return s.label(lang) if s else sid


def _load() -> list[Skill]:
    skills = []
    for line in (DATA / "skills.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        sid, broader, en, fr, aliases = (line.split("|") + [""] * 5)[:5]
        skills.append(Skill(sid, broader, en, fr, [a for a in aliases.split(",") if a.strip()]))
    if ESCO_EXTRA.exists():
        known = {fold(s.label_en) for s in skills}
        for row in json.loads(ESCO_EXTRA.read_text(encoding="utf-8")):
            if fold(row["label_en"]) not in known:
                skills.append(Skill(**row))
    return skills


@lru_cache
def taxonomy() -> Taxonomy:
    return Taxonomy(_load())


def import_esco(csv_path: str, lang: str = "en") -> int:
    """Merge an official ESCO skills CSV (columns conceptUri, preferredLabel, altLabels)."""
    existing = json.loads(ESCO_EXTRA.read_text(encoding="utf-8")) if ESCO_EXTRA.exists() else []
    by_id = {r["id"]: r for r in existing}
    with open(csv_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            uri = row.get("conceptUri", "")
            label = (row.get("preferredLabel") or "").strip()
            if not uri or not label:
                continue
            sid = "esco:" + uri.rsplit("/", 1)[-1]
            rec = by_id.setdefault(sid, {"id": sid, "broader": "", "label_en": label, "label_fr": label, "aliases": []})
            rec["label_fr" if lang == "fr" else "label_en"] = label
            alts = [a.strip() for a in (row.get("altLabels") or "").split("\n") if a.strip()]
            rec["aliases"] = sorted({*rec["aliases"], *alts, label})
    ESCO_EXTRA.write_text(json.dumps(list(by_id.values()), ensure_ascii=False), encoding="utf-8")
    taxonomy.cache_clear()
    return len(by_id)
