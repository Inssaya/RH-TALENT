"""tm-synth and tm-eval: synthetic data with *planted* relevance, and the evaluation bench.

Relevance grades (0-3) are derived from each candidate's latent profile, never from the
scoring function, so the evaluation is not circular. Synthetic results only support
non-regression, robustness and bias claims; real performance must be measured on a
human-annotated set (same JSON format, see docs/evaluation.md)."""
import json
import math
import random
from pathlib import Path

from .ai.embeddings import embed
from .ai.extraction import extract_rules, profile_text
from .ai.scoring import DEFAULT_WEIGHTS, compute_score, job_text
from .ai.skills import taxonomy
from .ai.textutil import tokens

OCCUPATIONS = {
    "data_scientist": {"fr": "Data Scientist", "en": "Data Scientist", "core": ["python", "machine_learning", "sql", "statistics"],
                       "extra": ["pytorch", "scikit_learn", "nlp", "docker", "power_bi"], "near": ["data_engineer", "backend_dev"]},
    "data_engineer": {"fr": "Ingénieur Data", "en": "Data Engineer", "core": ["python", "sql", "data_engineering", "spark"],
                      "extra": ["kafka", "aws", "docker", "postgresql"], "near": ["data_scientist", "backend_dev"]},
    "backend_dev": {"fr": "Développeur Back-end", "en": "Back-end Developer", "core": ["java", "spring", "sql", "rest_api"],
                    "extra": ["docker", "kubernetes", "postgresql", "git", "ci_cd"], "near": ["frontend_dev", "data_engineer"]},
    "frontend_dev": {"fr": "Développeur Front-end", "en": "Front-end Developer", "core": ["javascript", "react", "html_css", "typescript"],
                     "extra": ["nextjs", "testing", "ux_design", "git"], "near": ["backend_dev"]},
    "accountant": {"fr": "Comptable", "en": "Accountant", "core": ["accounting", "excel", "tax", "erp"],
                   "extra": ["sap", "financial_analysis", "audit", "payroll"], "near": ["financial_analyst"]},
    "financial_analyst": {"fr": "Analyste financier", "en": "Financial Analyst", "core": ["financial_analysis", "excel", "accounting", "bi"],
                          "extra": ["power_bi", "sap", "sql", "audit"], "near": ["accountant"]},
    "maintenance_tech": {"fr": "Technicien de maintenance", "en": "Maintenance Technician", "core": ["maintenance", "electricity", "mechanics", "automation"],
                         "extra": ["hse", "lean", "cad", "welding"], "near": ["quality_tech"]},
    "quality_tech": {"fr": "Technicien qualité", "en": "Quality Technician", "core": ["quality", "lean", "hse", "excel"],
                     "extra": ["manufacturing", "audit", "cad", "problem_solving"], "near": ["maintenance_tech"]},
    "warehouse_op": {"fr": "Cariste magasinier", "en": "Warehouse Operator", "core": ["forklift", "warehouse", "logistics"],
                     "extra": ["driving", "hse", "teamwork", "excel"], "near": ["logistics_coord"]},
    "logistics_coord": {"fr": "Coordinateur logistique", "en": "Logistics Coordinator", "core": ["logistics", "transport", "procurement", "excel"],
                        "extra": ["sap", "warehouse", "negotiation", "erp"], "near": ["warehouse_op"]},
    "sales_rep": {"fr": "Commercial B2B", "en": "B2B Sales Representative", "core": ["sales", "negotiation", "crm", "customer_service"],
                  "extra": ["marketing", "communication", "excel", "leadership"], "near": ["marketer"]},
    "marketer": {"fr": "Chargé de marketing digital", "en": "Digital Marketing Specialist", "core": ["digital_marketing", "seo", "social_media", "content"],
                 "extra": ["graphic_design", "crm", "data_analysis", "communication"], "near": ["sales_rep"]},
    "hr_officer": {"fr": "Chargé de recrutement", "en": "Recruitment Officer", "core": ["recruitment", "hr", "labor_law", "communication"],
                   "extra": ["payroll", "training", "ms_office", "negotiation"], "near": []},
    "nurse": {"fr": "Infirmier", "en": "Nurse", "core": ["nursing", "teamwork", "communication"],
              "extra": ["hse", "ms_office", "autonomy"], "near": []},
}
FIRST = ["Lina", "Karim", "Samira", "Youssef", "Nadia", "Omar", "Salma", "Mehdi", "Claire", "Thomas", "Julie", "Hugo",
         "Fatima", "Amine", "Sarah", "David", "Imane", "Rachid", "Emma", "Paul"]
LAST = ["Benali", "El Amrani", "Idrissi", "Martin", "Dubois", "Tazi", "Bennani", "Moreau", "Alaoui", "Bernard",
        "Chraibi", "Lefevre", "Haddad", "Roux", "Fassi", "Petit", "Mansouri", "Garcia", "Berrada", "Laurent"]
CITIES = ["Casablanca", "Rabat", "Tanger", "Marrakech", "Paris", "Lyon", "Tunis"]
SCHOOL = {7: ("Master", "Master's degree"), 6: ("Licence", "Bachelor's degree"), 5: ("BTS", "Associate degree"), 3: ("Baccalauréat", "High school")}


def _alias(rng: random.Random, sid: str, lang: str) -> str:
    """Vary the vocabulary: a synonym or the other language, as real CVs do."""
    s = taxonomy().skills[sid]
    pool = [s.label(lang)] * 3 + [a for a in s.aliases if len(a) > 3 and a.isascii() is not None][:4]
    return rng.choice(pool)


def make_job(rng: random.Random, occ: str, lang: str) -> dict:
    o = OCCUPATIONS[occ]
    tax = taxonomy()
    years = rng.choice([1, 2, 3, 5])
    nice = rng.sample(o["extra"], 2)
    desc = {"fr": f"Nous recrutons un(e) {o['fr']} pour renforcer notre équipe. Vous interviendrez sur des projets variés, "
                  f"en lien avec les équipes métier, avec une réelle autonomie et des responsabilités croissantes. "
                  f"Le poste demande de la rigueur, le sens du service et l'envie de progresser au sein d'une structure en croissance.",
            "en": f"We are hiring a {o['en']} to strengthen our team. You will work on varied projects with business teams, "
                  f"with real autonomy and growing responsibilities. The role requires rigour, a sense of service and the "
                  f"wish to grow within an expanding organisation, in a collaborative and demanding environment."}[lang]
    return {"occupation": occ, "title": o[lang], "description": desc, "city": rng.choice(CITIES), "country": "",
            "remote": "hybrid", "contract_type": "permanent", "min_years_experience": years, "education_level": 0,
            "languages": [], "skills_required": [tax.label(s, lang) for s in o["core"]],
            "skills_nice": [tax.label(s, lang) for s in nice], "knockouts": [], "lang": lang,
            "requirements": [{"id": f"q{i}", "text": ({"fr": "Expérience pratique en ", "en": "Hands-on experience with "}[lang]) + tax.label(s, lang),
                              "type": "requirement"} for i, s in enumerate(o["core"][:2])],
            "_core": o["core"], "_years": years}


def make_candidate(rng: random.Random, job: dict, grade: int, idx: int) -> dict:
    """Build a latent profile for the target grade, then render it as CV text."""
    o = OCCUPATIONS[job["occupation"]]
    lang = rng.choice(["fr", "fr", "en"])
    if grade == 3:
        occ, skills, years = job["occupation"], o["core"] + rng.sample(o["extra"], 2), job["_years"] + rng.randint(0, 4)
    elif grade == 2:
        occ, skills, years = job["occupation"], rng.sample(o["core"], max(2, len(o["core"]) - 1)) + rng.sample(o["extra"], 1), max(1, job["_years"] - rng.randint(0, 1))
    elif grade == 1:
        occ = rng.choice(o["near"]) if o["near"] else job["occupation"]
        oo = OCCUPATIONS[occ]
        skills, years = rng.sample(oo["core"], 2) + rng.sample(o["core"], 1), rng.randint(1, 4)
    else:
        occ = rng.choice([k for k in OCCUPATIONS if k != job["occupation"] and k not in o["near"]])
        oo = OCCUPATIONS[occ]
        skills, years = rng.sample(oo["core"], min(3, len(oo["core"]))) + rng.sample(oo["extra"], 1), rng.randint(1, 10)
    oo = OCCUPATIONS[occ]
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    end = 2026
    start = end - years
    lvl = rng.choice([5, 6, 7])
    used = [_alias(rng, s, lang) for s in skills]
    hdr = {"fr": ("Expérience professionnelle", "Formation", "Compétences", "Langues", "Français : courant\nAnglais : B1"),
           "en": ("Work experience", "Education", "Skills", "Languages", "English: fluent\nFrench: B2")}[lang]
    tasks = {"fr": f"Missions réalisées avec {', '.join(used[:3])}. Travail en équipe et suivi d'indicateurs.",
             "en": f"Daily work using {', '.join(used[:3])}. Team work and monitoring of indicators."}[lang]
    text = (f"{name}\n{oo[lang]}\n{name.lower().replace(' ', '.')}{idx}@example.com | {rng.choice(CITIES)}\n\n"
            f"{hdr[0]}\n{oo[lang]} – Société {rng.choice('ABCDEFGH')}\n01/{start} - 12/{end - 1}\n{tasks}\n\n"
            f"{hdr[1]}\n{SCHOOL[lvl][0 if lang == 'fr' else 1]}, {start - 1}\n\n{hdr[2]}\n{', '.join(used)}\n\n{hdr[3]}\n{hdr[4]}\n")
    return {"id": f"c{idx}", "name": name, "text": text, "grade": grade, "lang": lang}


def generate(n_jobs: int = 20, per_job: int = 15, seed: int = 7) -> dict:
    rng = random.Random(seed)
    jobs = []
    occs = list(OCCUPATIONS)
    for j in range(n_jobs):
        job = make_job(rng, occs[j % len(occs)], rng.choice(["fr", "en"]))
        grades = [3] * 3 + [2] * 3 + [1] * 3 + [0] * (per_job - 9)
        rng.shuffle(grades)
        job["candidates"] = [make_candidate(rng, job, g, j * 1000 + i) for i, g in enumerate(grades)]
        jobs.append(job)
    return {"seed": seed, "jobs": jobs}


# ---------------------------------------------------------------- metrics
def ndcg(grades_in_rank_order: list[int], k: int = 10) -> float:
    dcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(grades_in_rank_order[:k]))
    ideal = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(sorted(grades_in_rank_order, reverse=True)[:k]))
    return dcg / ideal if ideal else 1.0


def precision_at(grades: list[int], n: int) -> float:
    top = grades[:n]
    return sum(1 for g in top if g >= 2) / len(top) if top else 0.0


def bm25_rank(query: str, docs: list[str]) -> list[int]:
    """Keyword baseline the system must beat."""
    toks = [tokens(d) for d in docs]
    avg = sum(len(t) for t in toks) / max(1, len(toks))
    q = set(tokens(query))
    df = {w: sum(1 for t in toks if w in t) for w in q}
    scores = []
    for t in toks:
        s = 0.0
        for w in q:
            f = t.count(w)
            if f:
                idf = math.log(1 + (len(toks) - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * len(t) / avg))
        scores.append(s)
    return sorted(range(len(docs)), key=lambda i: -scores[i])


def evaluate(dataset: dict, n: int = 5) -> dict:
    sys_ndcg, bm_ndcg, sys_p, bm_p, bias = [], [], [], [], []
    for job in dataset["jobs"]:
        draft = {k: v for k, v in job.items() if not k.startswith("_") and k not in ("candidates", "occupation")}
        emb = embed(job_text(draft))
        scored = []
        for c in job["candidates"]:
            prof = extract_rules(c["text"])
            total = compute_score(draft, DEFAULT_WEIGHTS, prof, c["text"], job_emb=emb, profile_emb=embed(profile_text(prof)))["total"]
            scored.append((total, c["grade"]))
            if c["grade"] == 3:  # counterfactual: same CV, another identity
                alt = c["text"].replace(c["name"], "Alex Morgan")
                p2 = extract_rules(alt)
                bias.append(abs(total - compute_score(draft, DEFAULT_WEIGHTS, p2, alt, job_emb=emb, profile_emb=embed(profile_text(p2)))["total"]) / 100)
        sys_order = [g for _, g in sorted(scored, key=lambda x: -x[0])]
        grades = [c["grade"] for c in job["candidates"]]
        bm_order = [grades[i] for i in bm25_rank(job_text(draft), [c["text"] for c in job["candidates"]])]
        sys_ndcg.append(ndcg(sys_order))
        bm_ndcg.append(ndcg(bm_order))
        sys_p.append(precision_at(sys_order, n))
        bm_p.append(precision_at(bm_order, n))
    mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731
    return {"jobs": len(dataset["jobs"]), "candidates": sum(len(j["candidates"]) for j in dataset["jobs"]),
            "ndcg@10": mean(sys_ndcg), "ndcg@10_bm25": mean(bm_ndcg), "gain_vs_bm25": round(mean(sys_ndcg) - mean(bm_ndcg), 4),
            f"precision@{n}": mean(sys_p), f"precision@{n}_bm25": mean(bm_p),
            "counterfactual_gap_mean": mean(bias), "counterfactual_gap_max": round(max(bias), 4) if bias else None}


def load_or_generate(path: str | None) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else generate()
