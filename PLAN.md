# TalentMatch: architecture and handoff plan

This file is the working plan for whoever continues the build (human or AI agent).
Read sections 1 to 3 once, then execute section 4 in order. Each task has an acceptance check.
Source of truth for requirements: `docs/TalentMatch_Cahier_des_Charges.pdf`.

## 1. State of the repository

| Area | State | Verified how |
|---|---|---|
| `backend/` API, AI pipeline, scoring, shortlist, GDPR, audit, CLI | **Done** | 39 pytest tests pass on PostgreSQL 16 + pgvector; `python -m app.cli eval` passes |
| `backend/alembic/` initial migration `0001` | **Done** | `alembic upgrade head` applied on a clean database |
| `frontend/` Next.js pages and components | **Done (T1)** | `tsc` clean, `next build` OK, `frontend/scripts/check-i18n.py` finds no missing French key |
| Docker, Caddy, compose, `.env.example`, backup/restore scripts | **Done (T3)** | Images built, stack up, `/api/ready` OK, `seed-demo` gives 30 jobs on the home page |
| `e2e/smoke.mjs` six browser journeys | **Done (T4)** | 6/6 passed twice in a row against the compose stack |
| CI (`.github/workflows/ci.yml`) | **Written (T5), never run** | YAML parses; its backend steps (migrations from empty DB, `alembic check`, eval) were run locally; the `images`, `e2e`, `secrets` jobs cannot run here |
| README, `docs/runbook.md`, `docs/compliance.md`, `docs/evaluation.md` | **Done (T6)** | Backup and restore procedure executed for real; other runbook procedures are marked untested |

Local services used so far (not containers): PostgreSQL 16 (`talentmatch` / `talentmatch`, databases
`talentmatch` and `talentmatch_test`), Redis on 6379. Backend venv: `backend/.venv`.

```bash
cd backend && .venv/bin/pytest -q                      # 39 passed
cd backend && .venv/bin/python -m app.cli eval         # exit 0, prints nDCG vs BM25
cd backend && TASKS_EAGER=true .venv/bin/uvicorn app.main:app --port 8000
```

## 2. Architecture (decided, do not redesign)

```
Browser ──HTTPS──> Caddy ──/api/*──> api  (FastAPI, uvicorn)  ──> PostgreSQL 16 + pgvector
                     │                 │                      ──> Redis (queue, rate limits, LLM cache)
                     └──everything──> web (Next.js 15)        ──> storage volume (or S3)
                                       worker (Celery, same image as api) ──> Mistral API (optional)
                                       beat   (Celery beat, same image)
```

- **Modular monolith**: one Python package `app`, one image used by `api`, `worker` and `beat`.
- **One database**: PostgreSQL with pgvector (HNSW indexes on job and profile embeddings).
- **Same origin**: the browser only calls `/api/...`; session is an HttpOnly cookie `tm_session`
  (JWT, SameSite=Lax). In development `next.config.mjs` rewrites `/api` to `API_INTERNAL_URL`.
- **AI is optional at runtime**. Without `MISTRAL_API_KEY` the platform runs on deterministic rules
  ("degraded mode": flag `rule_based_assessment` on scores). With a key, the LLM only extracts facts
  and quotes evidence; the ranking is always the formula in `app/ai/scoring.py`.
- **Embeddings** default to `hash` (offline, free). `bge-m3` and `mistral` are opt-in via
  `EMBEDDINGS_PROVIDER`. `SEM_LOW` / `SEM_HIGH` must be recalibrated when the provider changes.

### Invariants that every change must keep

1. **No rejection without a human.** `services.transition()` is the only path to `rejected` and
   requires a recruiter. The system only moves applications between `new` and `shortlisted`.
2. **Shortlist size is never a constant.** It comes from `Job.sl_mode / sl_n / sl_threshold / sl_cap`.
3. **Organization isolation.** Recruiter routes load objects through `get_job()` / `get_app()` in
   `routers/jobs.py`, which return 404 for another organization. New routes must do the same.
4. **Evidence is verified.** A quotation not found in the CV (`verify_evidence`) counts as absent.
5. **Erasure is real.** No soft delete of personal data; files are removed from storage.
6. **Audit log is append-only and hash-chained** (`app/audit.py`). Sensitive actions call `audit.log`.
7. **Identity never enters the score.** PII is redacted before any provider call (`guard.redact_pii`).

### Backend map

| File | Role |
|---|---|
| `app/config.py` | All settings, read from environment variables |
| `app/models.py` | 18 tables (25 spec entities, some merged into JSONB) |
| `app/services.py` | Application pipeline, shortlist refresh, transitions, tracking tokens, GDPR |
| `app/tasks.py` | Celery app, queues, beat schedule; `enqueue()` falls back to inline |
| `app/matching.py` | Job recommendations, talent suggestions, weekly alerts |
| `app/evaluation.py`, `app/cli.py` | Synthetic data, metrics, BM25 baseline; `tm` commands |
| `app/ai/parsing.py` | File sniffing, text extraction, OCR (Mistral, Tesseract fallback), quality score |
| `app/ai/guard.py` | Prompt-injection scan, PII redaction |
| `app/ai/extraction.py` | CV to profile (LLM with anchoring, or rules) |
| `app/ai/skills.py`, `app/data/skills.tsv` | Multilingual skill taxonomy, hierarchy, ESCO import |
| `app/ai/scoring.py`, `app/ai/shortlist.py` | Seven sub-scores, knockouts, counterfactuals; shortlist policy |
| `app/ai/jobs_ai.py` | Job extraction from text, chatbot turn, quality and bias report |
| `app/routers/` | `auth` (+ org), `jobs` (recruiter), `public`, `candidate`, `admin` |

API prefix is `/api`. Health: `/api/health`, readiness: `/api/ready`.

### Frontend map

Next.js 15 App Router, React 19, Tailwind 4, TypeScript strict. No UI library.

| Path | Role |
|---|---|
| `lib/api.ts` | `api()` for the browser, `serverApi()` for server components |
| `lib/locale.ts` | `getLocale()`, `getT()` for server components (cookie `tm_locale`) |
| `components/Providers.tsx` | Client context: `useApp()` gives `t`, `locale`, `user`, `refresh`, `logout` |
| `app/page.tsx`, `app/jobs/*` | Public job board; job page is server-rendered with JSON-LD |
| `app/track/[token]` | Account-less tracking, rights |
| `app/recruiter/*` | Dashboard, new job (chat, voice, paste, file, form), shortlist, application, organization |
| `app/candidate`, `app/admin` | Candidate space; platform administration |
| `app/how-ai-works`, `app/legal/privacy`, `app/help` | Static pages, already written in FR, EN, AR |

**i18n convention:** the English sentence is the key. `t("Sign in")` returns the French or Arabic
string, or the key itself when no translation exists. Placeholders use `{name}`.

## 3. Known gaps against the specification

State these honestly in the README; do not hide them.

- Annotation tool (F-DAT-03) not built: the evaluation bench reads the same JSON format, so a
  human-annotated set can be dropped in. No real annotated dataset exists yet.
- Voice dictation uses the browser Web Speech API, not Mistral transcription.
- Candidate comparison view, interview guide, screening questions, CV tips, candidate chat
  assistant, CSV/PDF export (all "Could") are not built.
- The built-in taxonomy has about 135 skills. Full ESCO must be imported with `tm import-esco`.
- ClamAV, Turnstile, S3, Sentry, bge-m3 are wired but off by default and untested against real services.
- No real Mistral call has ever been made in this environment (no key). LLM paths are untested.
- Evaluation numbers come from synthetic data only. They prove non-regression, not real quality.
- SQLAlchemy is used in sync mode (the spec says async). This is deliberate: simpler and testable.

## 4. Remaining tasks, in order

### T1. Make the frontend compile  (blocking)

1. Create `frontend/lib/i18n.ts` exporting:
   ```ts
   export type Locale = "fr" | "en" | "ar";
   export function translate(locale: Locale, key: string, vars?: Record<string, string | number>): string
   ```
   `en` returns the key. `fr` and `ar` look the key up in a dictionary and fall back to the key.
   Replace every `{name}` with `vars[name]`.
2. Collect the keys. Direct keys: every `t("...")` literal in `app/**/*.tsx` and `components/*.tsx`.
   Indirect keys (passed as `t(MAP[x])`): all values of `CONTRACT`, `REMOTE`, `EDUCATION`, `LANGS`
   (`lib/labels.ts`), `QUALITY_LABEL`, `SUBSCORE_LABEL` (`lib/types.ts`), `STATUS_LABEL`, `FLAG_LABEL`
   (`components/ui.tsx`), `REASON` (`components/TrackingDetail.tsx`), `REASONS`, `REQ_LABEL`, `HOW`
   (recruiter pages), tab labels, and the three feature cards in `app/page.tsx`.
   Also translate the backend error strings shown to users (search `HTTPException(` in
   `backend/app` for the `detail` texts).
3. Write the **French dictionary completely** (French is the default locale). Write Arabic for at
   least the public, auth, candidate and tracking screens and all status labels.
4. `cd frontend && npm install && npx tsc --noEmit && npm run build`. Fix every error.

Accept when: `npm run build` succeeds, and a script confirms no `t("...")` key is missing from `fr`.

### T2. Backend clean-up

- `cd backend && .venv/bin/ruff check app tests --fix` (one import-order error in `evaluation.py`).
- Add `backend/.env.example` content to the root `.env.example` (T3).

Accept when: `ruff check` is clean and `pytest -q` still shows 39 passed.

### T3. Containers and deployment

Create:

- `backend/Dockerfile`: `python:3.12-slim`; apt `tesseract-ocr tesseract-ocr-fra tesseract-ocr-ara
  libmagic1`; `pip install .[ocr,s3]`; non-root user; `ENTRYPOINT` script that runs
  `alembic upgrade head && python -m app.cli bootstrap` only when `RUN_MIGRATIONS=1`.
  Commands: api `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers`;
  worker `celery -A app.tasks.celery worker -Q scoring,low -c 2`; beat `celery -A app.tasks.celery beat`.
- `frontend/Dockerfile`: multi-stage `node:22-alpine`, `output: "standalone"` is already set.
  Build args `NEXT_PUBLIC_SITE_URL`; runtime env `API_INTERNAL_URL=http://api:8000`.
- `docker-compose.yml`: services `caddy`, `web`, `api`, `worker`, `beat`,
  `db` (`pgvector/pgvector:pg16`, healthcheck, volume), `redis` (`redis:7-alpine`),
  optional `clamav` under a compose profile. Volumes: `pgdata`, `storage` (shared by api and worker),
  `caddy_data`. Only Caddy publishes ports 80 and 443.
- `Caddyfile`: `{$DOMAIN}` site; `handle /api/* { reverse_proxy api:8000 }`, else `web:3000`;
  `request_body max_size 12MB`; HSTS, `encode zstd gzip`.
- `.env.example`: every variable from `app/config.py` with comments; `SECRET_KEY`, `POSTGRES_PASSWORD`,
  `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `DOMAIN`, `PUBLIC_URL`; production values `ENV=production`,
  `COOKIE_SECURE=true`.
- `scripts/backup.sh` and `scripts/restore.sh`: `pg_dump` custom format plus a tar of the storage
  volume, optional upload with `rclone`; restore into a fresh stack. Document that continuous WAL
  archiving (RPO 15 min in the spec) needs WAL-G and is not set up by these scripts.

Accept when: `docker compose up --build -d` on a clean machine gives a working site on
`http://localhost`, `curl localhost/api/ready` returns ready, and `docker compose exec api python -m
app.cli seed-demo` creates 30 jobs visible on the home page.

### T4. End-to-end verification  (do not skip)

With the stack running, drive a real browser (Playwright is preinstalled; `chromium.launch()` needs
no options) through these journeys and fix what breaks:

1. Register an employer, create a job by pasting text, publish it.
2. Anonymous visitor opens the public page, applies with a PDF, opens the tracking link.
3. Recruiter sees the candidate in the shortlist, opens the explanation, changes top-N, rejects with
   a reason, cancels, rejects again.
4. Candidate registers, uploads a CV, sees recommendations, applies in one click.
5. Admin (from `ADMIN_EMAIL`) opens each admin tab and verifies the audit chain.
6. Switch to Arabic and check that the layout is right-to-left.

Commit the script as `e2e/smoke.spec.ts`. Accept when all six pass against the compose stack.

### T5. Continuous integration

`.github/workflows/ci.yml`: job `backend` (services `pgvector/pgvector:pg16` and `redis`; ruff,
pytest, `python -m app.cli eval`), job `frontend` (`npm ci`, `tsc --noEmit`, `next build`),
job `images` (docker build of both images, Trivy scan), `gitleaks` on the history.
No deployment job: production deploy stays a manual, approved step.

### T6. Documentation

- `README.md`: what it is, architecture diagram, quick start (compose), configuration table,
  how to enable Mistral, embeddings, OCR, ClamAV, S3, SMTP; section "What is not built" from section 3.
- `docs/runbook.md`: the ten procedures listed in the specification, section XIV.5.
- `docs/compliance.md`: GDPR roles, lawful bases, sub-processor list to fill in, DPIA to perform,
  AI Act mapping, and the bracketed items to complete in `app/legal/privacy/page.tsx`.
- `docs/evaluation.md`: dataset JSON format, how to run `tm synth` and `tm eval`, how to plug a
  human-annotated set, and the limits of synthetic data.

### T7. Finish

Run the full check once more (pytest, eval, frontend build, compose up, e2e), commit, push to
`claude/admiring-shannon-t2uktl`. Report what was verified and what was not.

## 5. Rules for the agent executing this plan

- Work task by task; commit after each task with a clear message.
- Never weaken an invariant from section 2 to make something pass. Never skip or delete a test to get green.
- Keep answers and code small: reuse existing helpers before adding new ones.
- If a requirement is unclear, the PDF specification decides; if it is silent, choose the simplest option and note it in the README.

## 6. Notes from T3 and T4 (read before T5)

- **Sandbox builds.** The agent proxy blocks Debian and Alpine mirrors and rate-limits Docker Hub (429).
  Local verification used: `docker buildx build --allow network.host --network host --build-arg WITH_OCR=0
  --build-arg HTTPS_PROXY=$HTTPS_PROXY -f backend/Dockerfile -t talentmatch-api:local --load .` (same for
  `frontend/Dockerfile`), then `docker compose up -d --no-build` with an override that sets `image:` to the local
  tags. Base images were pulled from `mirror.gcr.io/library/<image>` and retagged. The default image
  (`WITH_OCR=1`, Tesseract) was therefore **not built here**; build it in CI.
- **Rate limits** must be off for the E2E run (`RATE_LIMIT_ENABLED=false` in `.env`); production keeps them on.
- **E2E runner** is a plain Node script (`e2e/smoke.mjs`, uses the `playwright` library), not `@playwright/test`,
  because only the library is preinstalled. Run: `BASE_URL=http://localhost ADMIN_EMAIL=... ADMIN_PASSWORD=... node e2e/smoke.mjs`.
- **Bugs found by T4 and fixed:** demo e-mails used a reserved `.local` domain that login rejects; the admin page
  crashed when switching tabs (stale data of another tab).
- **Turnstile:** the API verifies a token when `TURNSTILE_SECRET` is set, but no widget exists in the apply form.
  Leave `TURNSTILE_SECRET` empty until the widget is added, otherwise every application is refused.
- Postgres and Redis used by the backend tests (outside Docker) stop between sessions; the compose stack has its own.

## 7. Final status (T7)

Verified in the last session: ruff clean; 39 pytest tests; `eval` exit 0; `tsc`, French key coverage and `next build`;
both images rebuilt; stack recreated from empty volumes; `seed-demo` gives 30 jobs; `e2e/smoke.mjs` 6/6;
backup then destructive change then `restore.sh` returned the data and the audit chain stayed intact.
Bug fixed on the way: `beat` was permanently "unhealthy" (the image healthcheck probes the API port).

Not verified: the GitHub Actions run, the default image with Tesseract, any real LLM / SMTP / S3 / ClamAV / Sentry,
real HTTPS with Let's Encrypt, runbook procedures 1 and 3 to 10, performance under load (the k6 load test of the
specification was not written), accessibility audit (axe), and human review of FR/AR wording and legal texts.
