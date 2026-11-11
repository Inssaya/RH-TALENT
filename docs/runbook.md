# Runbook

Ten procedures. All commands run from the repository folder on the server, with the stack managed by
`docker compose`. Status legend: **tested** = executed in development; **untested** = written from the design,
run it once in staging before you rely on it. A procedure that is untested on purpose says so.

Useful everywhere:

```bash
docker compose ps                          # state and health of each service
docker compose logs --tail 200 api worker  # JSON logs; add -f to follow
curl -fsS https://YOUR_DOMAIN/api/ready    # database reachable? prints llm/embeddings mode
docker compose exec api python -m app.cli audit-verify   # audit chain integrity
```

## 1. Site unavailable (untested)

1. `curl -I https://YOUR_DOMAIN/` and `curl https://YOUR_DOMAIN/api/ready` to see which layer answers.
2. `docker compose ps`. A service that is `unhealthy` or restarting: `docker compose logs --tail 100 <service>`.
3. Restart the failing one: `docker compose restart api` (or `web`, `caddy`). Restart everything: `docker compose up -d`.
4. If the database is the cause, see procedure 6 (disk) or 2 (restore). If the whole VM is lost, procedure 2.
5. Certificate problems: `docker compose logs caddy`; check the DNS record points to this VM and ports 80/443 are open.

## 2. Full restoration on a new VM (tested on a single host: backup, destructive change, restore, audit chain intact)

1. Install Docker, clone the repository, copy `.env` from your secret store (same `SECRET_KEY`, otherwise tracking
   links and sessions are invalidated).
2. `docker compose up -d --build db redis`, then copy the latest `db-*.dump` and `storage-*.tar` to the VM.
3. `./scripts/restore.sh db-<stamp>.dump storage-<stamp>.tar` (asks you to type `restore`; it replaces all data and
   restarts the stack).
4. Check: `curl -fsS localhost/api/ready`, log in as admin, `python -m app.cli audit-verify`, open a candidate file.
5. Point DNS to the new VM.

Backups: `./scripts/backup.sh /srv/backups` (cron it daily; set `RCLONE_REMOTE` for an off-site copy and test that
the copy restores). Recovery point = age of the last backup. The specification's 15-minute RPO needs continuous WAL
archiving (WAL-G) which is **not configured**: until it is, state a 24-hour RPO.

## 3. Restoration to a point in time (not available)

Needs WAL archiving, which is not set up. Closest option: restore the most recent logical backup (procedure 2).
To enable it, configure WAL-G on the `db` service with an encrypted off-site bucket, then document the
`recovery_target_time` restore here and test it.

## 4. AI provider or OCR outage (untested against a real provider)

Behaviour built in: 3 exponential retries, then **rule-based mode** for extraction and requirement assessment
(flag `rule_based_assessment` on each score), Tesseract fallback for OCR when installed, otherwise CVs are flagged
"to check". Applications are never lost; failed ones can be retried (`Retry the analysis` on the application page).

1. Watch the share of degraded calls: admin, tab *AI supervision*. No automatic alert exists yet; the specification asks for one above 10 percent.
2. If the outage lasts: nothing to do, the platform stays usable. To stop spending on a failing provider, clear
   `MISTRAL_API_KEY` in `.env` and `docker compose up -d api worker`.
3. After recovery, rescore: saving the job's weights or editing its requirements triggers a rescore of that job.

## 5. Saturated worker queue (untested)

1. `docker compose exec redis redis-cli llen scoring` (pending scoring tasks) and `llen low`.
2. `docker compose logs --tail 100 worker`: look for repeated failures or a slow provider.
3. Scale out: `docker compose up -d --scale worker=3`.
4. Applications stay in `queued` until processed; candidates and recruiters see "being analysed".

## 6. Disk full (untested)

1. `df -h`; `docker system df`.
2. Free space: `docker image prune -af`, `docker builder prune -af`, old backups in the backup folder.
3. Large consumers are the `pgdata` and `storage` volumes. Move CV storage to S3-compatible storage
   (`STORAGE_BACKEND=s3`, see README) or grow the disk.
4. After freeing space: `docker compose up -d`, then procedure 1 checks.

## 7. Rotating a compromised secret (untested)

- **`SECRET_KEY`**: sessions and every candidate tracking link are signed with it. Rotating logs everyone out and
  **invalidates all tracking links**. Candidates with an account keep access by logging in again; account-less
  candidates lose their link and there is no "resend link" feature yet (known gap). Edit `.env`, `docker compose up -d`.
  Do this on a confirmed leak.
- **`POSTGRES_PASSWORD`**: `docker compose exec db psql -U talentmatch -c "ALTER USER talentmatch PASSWORD '…'"`, update `.env`,
  `docker compose up -d`.
- **Provider keys** (`MISTRAL_API_KEY`, SMTP, S3): revoke at the provider, create a new one, edit `.env`, restart api and worker.
- **Admin password**: there is no change-password screen yet; use the reset link flow ("Forgot password?") or set it directly (this command was run once and works):
  `docker compose exec api python -c "from app.db import session_factory; from app.models import User; from app.security import hash_password; from sqlalchemy import select; s=session_factory()(); u=s.scalar(select(User).where(User.email=='admin@example.org')); u.password_hash=hash_password('NEW-PASSWORD'); s.commit()"`
- Rotate at least every 6 months. Check Git history is clean (`gitleaks`, run in CI).

## 8. Personal-data breach (untested; a legal duty)

1. Contain: rotate secrets (procedure 7), suspend affected accounts (admin), take the site offline if needed
   (`docker compose stop caddy`).
2. Establish what was exposed: `docker compose logs`, the admin **Audit log** (CV downloads, file opens, exports,
   logins) and `python -m app.cli audit-verify` to detect tampering.
3. **Within 72 hours of becoming aware**, notify the data protection authority (CNIL in France, CNDP in Morocco) if
   there is a risk to people. The recruiting companies are the data controllers of applications: inform them without
   delay so they can meet their own duties. Notify affected individuals if the risk is high.
4. Record the incident (what, when, who, data categories, number of people, measures) in the processing register.
5. Post-mortem and fix; add a test.

## 9. Rolling back a deployment or a migration (untested)

1. Application only: `git checkout <previous tag>` then `docker compose up -d --build`. Images keep their layers, so
   a rebuild of a known version is quick.
2. A migration went wrong: **take a backup first** (`scripts/backup.sh`), then
   `docker compose exec api alembic downgrade -1` (the initial migration also drops tables: only use downgrade for later migrations).
3. If data is damaged, restore the backup taken before the deployment (procedure 2).
4. Always run `./scripts/backup.sh` before each production deployment.

## 10. Fraudulent job post or mass abuse (untested)

1. Admin, *Organizations*: **Suspend** the organization. Its published jobs become `suspended` immediately and disappear
   from search and the sitemap. For a single job use *Jobs*, **Suspend**.
2. Abuse on public forms: the limits are 5 applications/hour/IP, 3/day/e-mail, 5 sign-ups/hour/IP. To block an address
   at the edge, add it to the Caddyfile (`@blocked remote_ip 203.0.113.7` + `respond @blocked 403`) and `docker compose restart caddy`.
3. Check what the account did: Audit log, filter on the action prefix (`job.`, `application.`).
4. Candidate complaints: reply from the administrator mailbox; offer the human review and erasure rights.

## Routine tasks

| Task | How |
|---|---|
| Daily backup | cron `./scripts/backup.sh /srv/backups` |
| Monthly restore test | restore the latest backup on a spare VM (procedure 2) |
| Retention purge | automatic nightly (beat). Run now: `docker compose exec api python -m app.cli task retention` |
| Pending rejection e-mails | automatic every minute. Run now: `... task rejections` |
| GDPR requests | admin, *GDPR requests*: answer within 30 days (`ERASURE_DAYS`) |
| Updates | `git pull && ./scripts/backup.sh && docker compose up -d --build` |
