# TalentMatch Core

A reduced version of the project: the **backend core** and the **AI screening pipeline**.
No frontend, no Docker, no assistant.

## What it does

1. **Backend core** (FastAPI + PostgreSQL): accounts (JWT in an HttpOnly cookie), companies, job posts, applications.
2. **AI pipeline**: a candidate applies with a CV, then:
   - the file is read (PDF, DOCX, OCR for scans);
   - hidden text and prompt-injection sentences are removed, names and contact details are redacted;
   - a profile is extracted (LLM, or rules when there is no API key);
   - the CV is scored against the job (weighted criteria, each one explained with evidence from the CV);
   - the best candidates form a shortlist.

Key rule: **the AI sorts, ranks and explains; only a human can reject a candidate.**

## Layout

```
app/
  main.py, config.py, db.py, models.py, schemas.py   API, settings, database
  security.py, deps.py, ratelimit.py                  auth, permissions, rate limits
  services.py                                         application flow, shortlist refresh, human-only rejection
  audit.py                                            tamper-evident audit log
  ai/  parsing, guard, extraction, scoring,           the AI pipeline
       shortlist, skills, llm, embeddings
  routers/                                            HTTP endpoints
alembic/                                              database migrations
tests/                                                58 tests
```

## Run it

You need Python 3.12+, PostgreSQL 16 with the `pgvector` extension, and Redis.

```bash
# 1. database (once)
sudo -u postgres psql -c "CREATE USER talentmatch WITH PASSWORD 'talentmatch' SUPERUSER;"
sudo -u postgres psql -c "CREATE DATABASE talentmatch OWNER talentmatch;"
sudo -u postgres psql -c "CREATE DATABASE talentmatch_test OWNER talentmatch;"

# 2. install
cd core
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. create the tables and start the API (jobs run inline, no worker needed)
alembic upgrade head
TASKS_EAGER=true uvicorn app.main:app --port 8000
```

API docs: http://localhost:8000/api/docs

Try it: register an employer (`POST /api/auth/register`), create and publish a job, then apply with a CV
(`POST /api/jobs/{slug}/apply`) and read the shortlist (`GET /api/jobs/{id}/shortlist`).

## Real LLM (optional)

Without a key everything runs in **rules mode** (deterministic, no network). To use Mistral:

```bash
export MISTRAL_API_KEY=your-key
```

## Tests

```bash
pytest -q
```

## Limits

- No real LLM call has been tested in this environment; rules mode is the verified path.
- Scores and evaluation numbers come from synthetic data, not real recruiters.
- The `admin`, `candidate` and `public` routers are kept because the core code depends on them.
