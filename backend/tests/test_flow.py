"""End-to-end flows on a real PostgreSQL database with pgvector."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import emailer
from app.audit import verify_chain
from app.db import session_factory
from app.main import app
from app.models import Application, ApplicationEvent, Document
from app.services import send_pending_rejections

from .conftest import CV_LINA, CV_YOUSSEF, JOB, apply, published_job, register


def u():
    return uuid.uuid4().hex[:8]


def test_full_recruitment_flow(client):
    register(client, f"samira-{u()}@acme.example.org")
    job = published_job(client)
    slug = job["slug"]

    # public page is visible without an account
    anon = TestClient(app)
    assert anon.get(f"/api/public/jobs/{slug}").json()["title"] == "Data Scientist"
    assert any(j["slug"] == slug for j in anon.get("/api/public/jobs", params={"q": "Data Scientist"}).json()["items"])

    t_lina = apply(client, slug, CV_LINA, f"lina-{u()}@example.com", "Lina Benali")
    t_youssef = apply(client, slug, CV_YOUSSEF, f"youssef-{u()}@example.com", "Youssef El Amrani")
    assert any("Candidature reçue" in m["subject"] for m in emailer.outbox)

    sl = client.get(f"/api/jobs/{job['id']}/shortlist").json()
    ranked = sl["members"] + sl["below"]
    assert len(ranked) == 2
    assert ranked[0]["name"] == "Lina Benali" and ranked[0]["score"] > ranked[1]["score"] + 20
    assert all(r["status"] == "shortlisted" for r in sl["members"])  # top-N default 10 > 2 candidates
    assert any(n["code"] == "fewer_eligible" for n in sl["notes"])

    # explanation for everyone, with verified evidence
    lina = client.get(f"/api/applications/{ranked[0]['id']}").json()
    req = lina["detail"]["requirements"][0]
    assert req["status"] in ("satisfied", "partial") and req["evidence_verified"]
    assert req["evidence"] in CV_LINA.replace("\n", " ") or req["evidence"].split(".")[0] in CV_LINA
    youssef = client.get(f"/api/applications/{ranked[1]['id']}").json()
    assert youssef["detail"]["counterfactuals"], "non-selected candidates also get an explanation"

    # shortlist size is a setting: top-1 leaves one candidate out and moves it back to 'new'
    r = client.put(f"/api/jobs/{job['id']}/policy", json={"mode": "TOP_N", "n": 1, "threshold": 65})
    assert r.status_code == 200
    sl = client.get(f"/api/jobs/{job['id']}/shortlist").json()
    assert [m["name"] for m in sl["members"]] == ["Lina Benali"]
    assert sl["below"][0]["status"] == "new"

    # human decision: rejection needs a reason, is traced, and can be undone during the delay
    yid = sl["below"][0]["id"]
    assert client.post(f"/api/applications/{yid}/move", json={"to": "rejected"}).status_code == 422
    assert client.post(f"/api/applications/{yid}/move", json={"to": "hired", "reason": "x"}).status_code == 409
    assert client.post(f"/api/applications/{yid}/move", json={"to": "rejected", "reason": "skills"}).status_code == 200
    assert anon.get(f"/api/public/track/{t_youssef}").json()["status"] == "in_review"  # not announced yet
    assert client.post(f"/api/applications/{yid}/undo-reject").status_code == 200
    assert client.post(f"/api/applications/{yid}/move", json={"to": "rejected", "reason": "skills"}).status_code == 200

    with session_factory()() as db:
        a = db.get(Application, uuid.UUID(yid))
        a.pending_rejection_at = a.submitted_at  # the cancellation delay has elapsed
        db.commit()
        assert send_pending_rejections(db) == 1
        db.commit()
        # no rejection was ever written by the system
        evs = db.scalars(select(ApplicationEvent).where(ApplicationEvent.to_status == "rejected")).all()
        assert evs and all(e.actor_kind == "human" and e.actor_id for e in evs)
        assert verify_chain(db)["ok"]

    tr = anon.get(f"/api/public/track/{t_youssef}").json()
    assert tr["status"] == "not_retained" and "Python" in tr["explanation"]["missing_skills"]
    assert tr["explanation"]["decided_by"] == "human"
    # right to human review, then the candidate cannot be rejected in a batch
    assert anon.post(f"/api/public/track/{t_lina}/human-review").json()["human_review_requested"]
    lid = sl["members"][0]["id"]
    r = client.post(f"/api/jobs/{job['id']}/bulk-reject", json={"application_ids": [lid], "reason": "other", "reviewed": True})
    assert r.json() == {"rejected": 0, "skipped": [lid]}
    assert client.post(f"/api/jobs/{job['id']}/bulk-reject",
                       json={"application_ids": [lid], "reason": "other", "reviewed": False}).status_code == 422

    assert client.post(f"/api/applications/{lid}/move", json={"to": "interview"}).status_code == 200
    assert anon.get(f"/api/public/track/{t_lina}").json()["status"] == "interview"
    an = client.get(f"/api/jobs/{job['id']}/analytics").json()
    assert an["total"] == 2 and an["by_status"]["interview"] == 1

    # GDPR: export then real erasure (row, score and file)
    assert anon.get(f"/api/public/track/{t_youssef}/export").json()["applications"]
    with session_factory()() as db:
        key = db.get(Application, uuid.UUID(yid)).document.storage_key
    assert anon.post(f"/api/public/track/{t_youssef}/erase").json()["report"]["files"] == 1
    with session_factory()() as db:
        assert db.get(Application, uuid.UUID(yid)) is None
        assert not db.scalar(select(Document).where(Document.storage_key == key))
    assert anon.get(f"/api/public/track/{t_youssef}").status_code == 404


def test_organization_isolation(client):
    register(client, f"a-{u()}@one.example.org", org="Org One")
    job = published_job(client)
    apply(client, job["slug"], CV_LINA, f"l-{u()}@example.com", "Lina Benali")
    app_id = client.get(f"/api/jobs/{job['id']}/shortlist").json()["members"][0]["id"]

    other = TestClient(app)
    register(other, f"b-{u()}@two.example.org", org="Org Two")
    for method, path in [("get", f"/api/jobs/{job['id']}"), ("get", f"/api/jobs/{job['id']}/shortlist"),
                         ("get", f"/api/jobs/{job['id']}/analytics"), ("get", f"/api/applications/{app_id}"),
                         ("get", f"/api/applications/{app_id}/cv"), ("post", f"/api/jobs/{job['id']}/close")]:
        assert getattr(other, method)(path).status_code == 404, path
    assert other.post(f"/api/applications/{app_id}/move", json={"to": "interview"}).status_code == 404
    assert other.get("/api/jobs").json() == []

    cand = TestClient(app)
    register(cand, f"c-{u()}@mail.example.org", role="candidate")
    assert cand.get("/api/jobs").status_code == 403
    assert cand.get("/api/admin/stats").status_code == 403
    assert TestClient(app).get("/api/jobs").status_code == 401


def test_candidate_space_and_matching(client):
    register(client, f"r-{u()}@corp.example.org", org="Corp")
    job = published_job(client)
    maint = published_job(client, {**JOB, "title": "Technicien de maintenance", "skills_required": ["Maintenance industrielle", "Électricité"],
                                   "skills_nice": [], "requirements": [], "min_years_experience": 2, "education_level": 0,
                                   "description": JOB["description"].replace("data scientist", "technicien de maintenance")})
    cand = TestClient(app)
    email = f"lina-{u()}@mail.example.org"
    register(cand, email, role="candidate")
    assert cand.post(f"/api/candidate/apply/{job['slug']}").status_code == 409  # no CV yet
    r = cand.post("/api/candidate/profile/cv", files={"file": ("cv.txt", CV_LINA.encode(), "text/plain")})
    assert r.status_code == 200 and r.json()["data"]["education_level"] == 7
    recs = cand.get("/api/candidate/recommendations").json()
    slugs = [x["slug"] for x in recs]
    assert slugs.index(job["slug"]) < slugs.index(maint["slug"])

    assert cand.post(f"/api/candidate/apply/{job['slug']}").status_code == 200
    assert cand.post(f"/api/candidate/apply/{job['slug']}").status_code == 409
    mine = cand.get("/api/candidate/applications").json()
    assert mine[0]["status"] == "in_review" and "score" not in mine[0]

    # talent suggestions only show candidates who opted in
    assert client.get(f"/api/jobs/{maint['id']}/talents").json() == []
    prof = cand.get("/api/candidate/profile").json()["data"]
    cand.put("/api/candidate/profile", json={"title": prof["title"], "summary": prof["summary"], "location": "Casablanca",
                                             "skills": [s["label"] for s in prof["skills"]],
                                             "visible_to_recruiters": True, "alerts": True})
    assert len(client.get(f"/api/jobs/{maint['id']}/talents").json()) >= 1

    assert cand.get("/api/candidate/export").json()["account"]["email"] == email
    assert cand.post("/api/candidate/erase").json()["report"]["account"] == 1
    assert cand.get("/api/auth/me").status_code == 401


def test_job_authoring_channels(client):
    register(client, f"k-{u()}@esn.example.org", org="ESN")
    text = """Développeur Full-Stack
Lieu : Rabat, Maroc
CDI - télétravail partiel

Missions
- Concevoir des API REST avec Node.js et PostgreSQL
- Développer des interfaces en React

Profil recherché
- 3 ans d'expérience en développement web
- Maîtrise de React et TypeScript
- Bac+5 en informatique
- Anglais professionnel

Atouts : Docker, Kubernetes
"""
    d = client.post("/api/jobs/extract", json={"text": text}).json()["draft"]
    assert d["title"] == "Développeur Full-Stack" and d["city"] == "Rabat" and d["contract_type"] == "permanent"
    assert d["remote"] == "hybrid" and d["min_years_experience"] == 3 and d["education_level"] == 7
    assert "React" in d["skills_required"] and "Docker" in d["skills_nice"] and len(d["requirements"]) == 4

    # chatbot in rule mode: fills the template turn by turn and asks for what is missing
    empty = {"title": ""}
    r = client.post("/api/jobs/chat", json={"draft": empty, "message": "Je cherche un cariste", "asked_field": "title"}).json()
    assert r["draft"]["title"] and r["asked_field"] == "description" and r["degraded"]
    r = client.post("/api/jobs/chat", json={"draft": r["draft"], "asked_field": "location", "message": "Tanger, Maroc"}).json()
    assert r["draft"]["city"] == "Tanger"

    q = client.post("/api/jobs/quality", json={**JOB, "description": JOB["description"] + " Nous cherchons un jeune homme dynamique."}).json()
    codes = {w["code"] for w in q["warnings"]}
    assert {"bias_age", "bias_gender"} <= codes and q["publishable"]
    draft = client.post("/api/jobs", json={"title": "Incomplet"}).json()
    assert client.post(f"/api/jobs/{draft['id']}/publish").status_code == 422


def test_new_version_rescores_and_weights(client):
    register(client, f"w-{u()}@w.example.org", org="W")
    job = published_job(client)
    apply(client, job["slug"], CV_LINA, f"l-{u()}@example.com", "Lina Benali")
    before = client.get(f"/api/jobs/{job['id']}/shortlist").json()["members"][0]["score"]
    r = client.put(f"/api/jobs/{job['id']}", json={**JOB, "skills_required": ["Python", "Machine learning", "SQL", "Kafka", "Spark"]})
    assert r.json()["version"] == 2
    after = client.get(f"/api/jobs/{job['id']}/shortlist").json()["members"][0]["score"]
    assert after < before
    assert client.put(f"/api/jobs/{job['id']}/weights", json={"weights": {"skills": 0.9}}).status_code == 422
    assert client.put(f"/api/jobs/{job['id']}/weights", json={"weights": {"skills": 0.5, "requirements": 0.1}}).status_code == 200
    snaps = client.get(f"/api/jobs/{job['id']}/snapshots").json()
    assert len(snaps) >= 1
