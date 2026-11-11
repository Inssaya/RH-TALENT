import os

os.environ.update({
    "ENV": "test", "TASKS_EAGER": "true", "RATE_LIMIT_ENABLED": "false", "MISTRAL_API_KEY": "",
    "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://talentmatch:talentmatch@localhost:5432/talentmatch_test"),
    "STORAGE_DIR": "/tmp/tm-test-storage", "SMTP_HOST": "", "EMBEDDINGS_PROVIDER": "hash",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import Base, get_engine  # noqa: E402
from app.main import app  # noqa: E402

CV_LINA = """Lina Benali
Data Scientist
lina.benali@example.com | +212 6 12 34 56 78 | Casablanca

Profil
Data scientist avec une forte pratique du machine learning et du NLP.

Expérience professionnelle
Data Scientist – OCP Group
03/2021 - 09/2024
Développement et déploiement de modèles de machine learning avec Python et scikit-learn. Mise en production avec Docker.

Développeuse Python
Janvier 2019 – Décembre 2020
API REST avec FastAPI et PostgreSQL. Tests avec pytest.

Formation
Master Data Science, Université Mohammed V, 2019

Compétences
Python, SQL, PyTorch, Docker, Git

Langues
Français : courant
Anglais : B2
"""

CV_YOUSSEF = """Youssef El Amrani
Technicien de maintenance
youssef@example.com
Tanger

Expérience professionnelle
Technicien de maintenance industrielle – Renault
2012 - 2023
Maintenance préventive et corrective des lignes de production. Automatisme Siemens.

Formation
BTS Électromécanique, 2011

Compétences
Maintenance, électricité, mécanique

Langues
Arabe : langue maternelle
Français : intermédiaire
"""

JOB = {
    "title": "Data Scientist",
    "description": "Nous recherchons un data scientist pour concevoir, entraîner et mettre en production des modèles "
                   "de machine learning au sein de notre équipe data. Vous travaillerez avec les équipes produit et "
                   "ingénierie pour transformer les données en décisions, de l'exploration à la mise en production.",
    "city": "Casablanca", "country": "Maroc", "remote": "hybrid", "contract_type": "permanent",
    "min_years_experience": 3, "education_level": 7,
    "languages": [{"code": "fr", "level": "B2"}],
    "skills_required": ["Python", "Machine learning", "SQL"], "skills_nice": ["Docker"],
    "requirements": [{"id": "r1", "text": "Expérience de mise en production de modèles de machine learning", "type": "requirement"}],
}


@pytest.fixture(scope="session", autouse=True)
def schema():
    engine = get_engine()
    with engine.begin() as c:
        c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def client():
    return TestClient(app)


def register(client, email, role="recruiter", org="Acme Logistics"):
    r = client.post("/api/auth/register", json={
        "email": email, "password": "correct-horse-battery", "full_name": email.split("@")[0].title(),
        "role": role, "organization_name": org if role == "recruiter" else None, "accept_terms": True})
    assert r.status_code == 200, r.text
    return r.json()


def published_job(client, draft=None):
    r = client.post("/api/jobs", json=draft or JOB)
    assert r.status_code == 200, r.text
    job = r.json()
    r = client.post(f"/api/jobs/{job['id']}/publish")
    assert r.status_code == 200, r.text
    return r.json()


def apply(client, slug, cv, email, name="Test Candidate", filename="cv.txt"):
    data = cv if isinstance(cv, bytes) else cv.encode()
    r = TestClient(app).post(f"/api/public/jobs/{slug}/apply",
                             data={"full_name": name, "email": email, "consent": "true", "locale": "fr"},
                             files={"file": (filename, data, "application/octet-stream")})
    assert r.status_code == 200, r.text
    return r.json()["tracking_token"]
