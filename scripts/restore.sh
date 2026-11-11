#!/bin/sh
# Restore a backup into the running stack. Usage: scripts/restore.sh <db-dump> <storage-tar>
# DESTRUCTIVE: replaces the database content and the stored files.
set -eu
DB="$1"; STORE="$2"
printf 'This replaces ALL data of the running stack. Type "restore" to continue: '; read -r ok
[ "$ok" = "restore" ] || { echo aborted; exit 1; }
docker compose stop api worker beat web
docker compose exec -T db psql -U talentmatch -d postgres -c "DROP DATABASE IF EXISTS talentmatch" -c "CREATE DATABASE talentmatch OWNER talentmatch"
docker compose exec -T db psql -U talentmatch -d talentmatch -c "CREATE EXTENSION IF NOT EXISTS vector"
docker compose exec -T db pg_restore -U talentmatch -d talentmatch --no-owner < "$DB"
docker compose run --rm --no-deps -T -u root --entrypoint sh api -c "rm -rf /data/storage/* && tar -C /data -xf - && chown -R app:app /data/storage" < "$STORE"
docker compose up -d
echo "restored; check: curl -fsS http://localhost/api/ready"
