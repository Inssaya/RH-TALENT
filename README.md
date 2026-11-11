# TalentMatch

Recruitment platform with an explainable AI screening layer. Employers publish jobs (chat, voice, pasted
text, file or form); candidates apply without an account or in one click; the AI **reads, scores, ranks and
explains** every application, and **a human takes every decision** (rejection, interview, hire).

The full specification is `TalentMatch_Cahier_des_Charges.pdf` (LaTeX source in the same folder).
`PLAN.md` is the engineering handoff plan and status log.

## Architecture

```
Browser ──HTTPS──> Caddy ──/api/*──> api    (FastAPI)  ──> PostgreSQL 16 + pgvector
                     │                 │                ──> Redis (queue, rate limits, LLM cache)
                     └──everything──> web    (Next.js)  ──> storage volume (or S3)
                                       worker (Celery, same image as api) ──> Mistral API (optional)
                                       beat   (Celery beat, same image)
```

- Modular monolith: one Python package (`backend/app`), one image used by `api`, `worker` and `beat`.
- One database (PostgreSQL + pgvector, HNSW indexes). Same-origin API under `/api`, HttpOnly session cookie.
- **AI is optional at runtime.** Without `MISTRAL_API_KEY` everything works on deterministic rules (flagged
  `rule_based_assessment` on each score). With a key, the LLM only extracts facts and quotes evidence; the
  **ranking is always a transparent formula** (`backend/app/ai/scoring.py`): 7 weighted sub-scores
  (skills 30, requirements 25, experience 15, similarity 15, education 5, languages 5, location 5).

### Rules the code enforces

1. No rejection without a human: the system only moves candidates between `new` and `shortlisted`.
2. The shortlist size is a per-job setting (top-N, threshold, or both); never a constant.
3. Recruiters only ever reach their own organization's data (404 otherwise).
4. Quoted evidence must exist in the CV, or the requirement counts as absent.
5. Erasure is real (rows, extracted profile, score, stored file). Audit log is append-only and hash-chained.
6. Name, e-mail, phone and demographics never enter the score and are removed before any provider call.

## Quick start (Docker)

```bash
cp .env.example .env        # then fill SECRET_KEY, POSTGRES_PASSWORD, ADMIN_PASSWORD
# local test over plain HTTP: set DOMAIN=:80, PUBLIC_URL=http://localhost, COOKIE_SECURE=false
docker compose up -d --build
docker compose exec api python -m app.cli seed-demo     # optional: 10 companies x 3 jobs with candidates
```

Open `http://localhost`. Administrator: `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`. Demo recruiters:
`recruteur1@demo.example.org` … `recruteur10@…` with the `seed-demo` password (`demo-password-2026` by default).

For production set `DOMAIN` to your domain (Caddy gets a Let's Encrypt certificate), `PUBLIC_URL=https://…`,
`COOKIE_SECURE=true`, and configure SMTP; see `docs/runbook.md`.

## Development without Docker

```bash
# backend (needs PostgreSQL 16 with the pgvector extension and Redis)
cd backend && python -m venv .venv && .venv/bin/pip install -e ".[dev,ocr]"
.venv/bin/alembic upgrade head
TASKS_EAGER=true .venv/bin/uvicorn app.main:app --port 8000     # TASKS_EAGER runs jobs inline, no worker needed
.venv/bin/pytest -q && .venv/bin/ruff check app tests
.venv/bin/python -m app.cli eval                                # AI evaluation bench

# frontend
cd frontend && npm install && npm run dev                       # /api is proxied to API_INTERNAL_URL (default :8000)
python3 scripts/check-i18n.py                                   # every t("…") key has a French translation

# browser journeys against a running stack (see PLAN.md section 6)
BASE_URL=http://localhost ADMIN_EMAIL=… ADMIN_PASSWORD=… node e2e/smoke.mjs
```

CLI (`python -m app.cli <command>`): `bootstrap`, `seed-demo`, `synth`, `eval`, `import-esco`, `task`, `audit-verify`.

## Configuration

All settings are environment variables (`backend/app/config.py`, documented in `.env.example`).

| Capability | Variables | Notes |
|---|---|---|
| LLM extraction, chatbot, requirement evidence | `MISTRAL_API_KEY`, `LLM_MODEL` | Off by default. CV text is sent with name and contact details removed. Responses are cached in Redis. |
| OCR for scans and photos | `OCR_MODEL` (Mistral), Tesseract in the default image | Order: Mistral OCR, then Tesseract, else the CV is flagged "to check". Build with `--build-arg WITH_OCR=0` for a smaller image. |
| Embeddings | `EMBEDDINGS_PROVIDER` = `hash` (default, offline) / `mistral` / `bge-m3`, `SEM_LOW`, `SEM_HIGH` | `bge-m3` needs `pip install ".[bge]"`. Recalibrate `SEM_LOW/HIGH` when changing provider (`docs/evaluation.md`). |
| Antivirus | `CLAMAV_HOST`, `docker compose --profile antivirus up -d` | Without it, uploads are only type-checked (magic bytes), size-limited and stored privately. |
| File storage | `STORAGE_BACKEND=s3`, `S3_*` | Needs the `s3` extra (included in the image). Default: local volume. |
| E-mail | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` | Without `SMTP_HOST`, messages are only logged: candidates will not receive their tracking links. |
| Rate limits | built in (`RATE_LIMIT_ENABLED`) | 5 applications/h/IP, 3/day/e-mail, 5 sign-ups/h/IP, 30 chat messages/10 min/user. |
| GDPR | `RETENTION_MONTHS`, `ERASURE_DAYS`, `NOTICE_VERSION`, `REJECT_UNDO_MINUTES` | Retention purge runs nightly (beat). |
| Monitoring | `SENTRY_DSN` | Needs `pip install sentry-sdk`; not in the image yet. Logs are JSON on stdout. |

## Tests and quality gates

- Backend: 40 tests on a real PostgreSQL + pgvector (flows, organization isolation, GDPR erasure, shortlist edge
  cases, identity-neutrality, injection and hidden-text handling).
- `python -m app.cli eval` fails if the ranking does not beat a BM25 baseline by 0.05 nDCG@10 or if the
  counterfactual score gap reaches 0.03. **These numbers come from synthetic data** (see `docs/evaluation.md`).
- CI (`.github/workflows/ci.yml`): lint, tests, migration check, evaluation, frontend type-check and build,
  French-translation coverage, Docker builds with Trivy scan, browser journeys, gitleaks. No deployment job:
  deploying is a manual, approved step.

## What is not built or not verified

Be aware of these before using the platform with real candidates.

- **No real LLM call has ever been made** (no API key during development). The LLM paths are written but untested
  against the real Mistral API; the verified behaviour is the rule-based mode.
- **No human-annotated evaluation set exists.** Reported quality numbers are synthetic and prove non-regression,
  not real-world accuracy. The annotation tool of the specification is not built (the bench reads the same JSON
  format, so an annotated set can be dropped in).
- Candidate comparison view, interview guide, screening questions, CV tips, candidate chat assistant and
  CSV/PDF export (all "Could" in the specification) are not built.
- Voice dictation uses the browser's speech recognition, not server-side transcription.
- The built-in skill taxonomy has about 135 entries. Import the full ESCO export with `python -m app.cli import-esco`.
- Arabic UI covers the public, authentication, candidate and tracking screens; recruiter and admin screens fall
  back to English. French and Arabic wording has not been reviewed by native speakers.
- **E-mail addresses are not verified at sign-up.** For that reason an account never inherits earlier account-less
  applications made with the same address (regression test included). Add verification before relying on account e-mails.
- Two-factor authentication is optional for everyone; the specification makes it mandatory for organization and platform
  administrators. There is no change-password screen (only the reset-link flow).
- Captcha: the API can verify Cloudflare Turnstile, but the apply form has no widget. Keep `TURNSTILE_SECRET` empty.
- ClamAV, S3, SMTP, Sentry and bge-m3 are wired but were not exercised against real services.
- Backups are logical dumps (`scripts/backup.sh`). The specification's 15-minute RPO needs continuous WAL archiving
  (WAL-G), which is not configured.
- The default API image (with Tesseract) and the CI workflow were written but not executed in the development
  environment (network restrictions); the image was verified without Tesseract.
- Legal texts are templates. `docs/compliance.md` lists what the operator must complete and have reviewed.
- SQLAlchemy is used in synchronous mode (the specification says asynchronous): simpler and testable at this scale.
