"""Operations CLI: `tm <command>` (or `python -m app.cli <command>`)."""
import argparse
import json
import random
import sys

from sqlalchemy import select

from .config import get_settings
from .db import session_factory


def bootstrap(_):
    """Create the platform administrator from ADMIN_EMAIL / ADMIN_PASSWORD (idempotent)."""
    from .models import User
    from .security import hash_password
    s = get_settings()
    if not s.admin_email or not s.admin_password:
        print("ADMIN_EMAIL / ADMIN_PASSWORD not set: no administrator created")
        return
    with session_factory()() as db:
        if db.scalar(select(User.id).where(User.email == s.admin_email.lower())):
            print("administrator already exists")
            return
        db.add(User(email=s.admin_email.lower(), password_hash=hash_password(s.admin_password),
                    full_name="Platform Admin", role="platform_admin"))
        db.commit()
        print(f"administrator {s.admin_email} created")


def seed_demo(args):
    """Demo base: 10 fictitious companies x 3 jobs = 30 published jobs, with synthetic applications."""
    from . import services
    from .ai.scoring import DEFAULT_WEIGHTS
    from .evaluation import OCCUPATIONS, make_candidate, make_job
    from .models import Applicant, Application, Job, Membership, Organization, User
    from .security import hash_password
    rng = random.Random(42)
    names = ["Atlas Logistique", "Nova Data", "Médina Santé", "Sahara Industries", "Rif Finance", "Oasis Digital",
             "Cèdre Conseil", "Maghreb Auto", "Zellige Tech", "Horizon Retail"]
    occs = list(OCCUPATIONS)
    with session_factory()() as db:
        if db.scalar(select(Organization.id).where(Organization.slug == "atlas-logistique")):
            print("demo data already present")
            return
        idx = 0
        for i, name in enumerate(names):
            user = User(email=f"recruteur{i + 1}@demo.example.org", password_hash=hash_password(args.password),
                        full_name=f"Recruteur {name}", role="recruiter")
            org = Organization(name=name, slug=services.slugify(name), verified=True, city=rng.choice(["Casablanca", "Rabat", "Tanger"]),
                               country="Maroc", description=f"{name} (entreprise fictive de démonstration).")
            db.add_all([user, org])
            db.flush()
            db.add(Membership(user_id=user.id, organization_id=org.id, role="org_admin"))
            for k in range(3):
                draft = make_job(rng, occs[(i * 3 + k) % len(occs)], "fr" if (i + k) % 3 else "en")
                clean = {kk: v for kk, v in draft.items() if not kk.startswith("_") and kk != "occupation"}
                clean["country"] = {"Casablanca": "Maroc", "Rabat": "Maroc", "Tanger": "Maroc", "Marrakech": "Maroc",
                                    "Paris": "France", "Lyon": "France", "Tunis": "Tunisie"}.get(clean["city"], "Maroc")
                job = Job(organization_id=org.id, slug=services.unique_slug(db, Job, f"{clean['title']}-{name}"),
                          created_by=user.id, weights=dict(DEFAULT_WEIGHTS), status="published", published_at=services.now())
                db.add(job)
                db.flush()
                services.new_job_version(db, job, clean, user)
                grades = [3, 3, 2, 2, 1, 1, 0, 0][: args.candidates]
                for g in grades:
                    idx += 1
                    c = make_candidate(rng, draft, g, idx)
                    email = c["text"].split("\n")[2].split(" | ")[0]
                    applicant = Applicant(email=email, full_name=c["name"])
                    db.add(applicant)
                    db.flush()
                    doc = services.store_document(db, c["text"].encode(), "cv.txt")
                    app = Application(job_id=job.id, applicant_id=applicant.id, document_id=doc.id, source="public")
                    services.issue_magic_link(app)
                    db.add(app)
                    db.flush()
                    services.process_application(db, app.id)
            db.commit()
            print(f"{name}: 3 jobs")
    print(f"done. Recruiter logins: recruteur1..10@demo.example.org / {args.password}")


def synth(args):
    from .evaluation import generate
    data = generate(args.jobs, args.per_job, args.seed)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    print(f"{args.out}: {len(data['jobs'])} jobs x {args.per_job} candidates")


def eval_(args):
    """Evaluation bench. Exits 1 when the ranking does not beat BM25 by the required margin."""
    from .evaluation import evaluate, load_or_generate
    report = evaluate(load_or_generate(args.data), args.n)
    print(json.dumps(report, indent=2))
    ok = report["gain_vs_bm25"] >= args.min_gain and report["counterfactual_gap_max"] < 0.03
    sys.exit(0 if ok else 1)


def import_esco(args):
    from .ai.skills import import_esco as run
    print(f"{run(args.csv, args.lang)} ESCO skills in the local extension")


def tasks(args):
    """Run a maintenance task now (same code as the scheduler)."""
    from . import matching, services
    fn = {"rejections": services.send_pending_rejections, "retention": services.purge_retention,
          "alerts": matching.send_job_alerts}[args.name]
    with session_factory()() as db:
        print(fn(db))
        db.commit()


def audit_verify(_):
    from .audit import verify_chain
    with session_factory()() as db:
        out = verify_chain(db)
    print(out)
    sys.exit(0 if out["ok"] else 1)


def main():
    p = argparse.ArgumentParser(prog="tm")
    sub = p.add_subparsers(required=True)
    sub.add_parser("bootstrap").set_defaults(fn=bootstrap)
    s = sub.add_parser("seed-demo")
    s.add_argument("--password", default="demo-password-2026")
    s.add_argument("--candidates", type=int, default=6)
    s.set_defaults(fn=seed_demo)
    s = sub.add_parser("synth")
    s.add_argument("--out", default="synth.json")
    s.add_argument("--jobs", type=int, default=20)
    s.add_argument("--per-job", type=int, default=15)
    s.add_argument("--seed", type=int, default=7)
    s.set_defaults(fn=synth)
    s = sub.add_parser("eval")
    s.add_argument("--data")
    s.add_argument("--n", type=int, default=5)
    s.add_argument("--min-gain", type=float, default=0.05)
    s.set_defaults(fn=eval_)
    s = sub.add_parser("import-esco")
    s.add_argument("csv")
    s.add_argument("--lang", default="en")
    s.set_defaults(fn=import_esco)
    s = sub.add_parser("task")
    s.add_argument("name", choices=["rejections", "retention", "alerts"])
    s.set_defaults(fn=tasks)
    sub.add_parser("audit-verify").set_defaults(fn=audit_verify)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
