#!/bin/sh
# Logical backup: PostgreSQL dump + stored files. Usage: scripts/backup.sh [output-dir]
# Optional off-site copy: set RCLONE_REMOTE (e.g. b2:talentmatch-backups).
# Note: this gives a daily-style RPO. The 15-minute RPO of the specification needs continuous
# WAL archiving (WAL-G), which is not configured here (see docs/runbook.md).
set -eu
OUT="${1:-./backups}"; STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$OUT"
docker compose exec -T db pg_dump -U talentmatch -Fc talentmatch > "$OUT/db-$STAMP.dump"
docker compose exec -T api tar -C /data -cf - storage > "$OUT/storage-$STAMP.tar"
sha256sum "$OUT/db-$STAMP.dump" "$OUT/storage-$STAMP.tar" > "$OUT/SHA256SUMS-$STAMP"
[ -n "${RCLONE_REMOTE:-}" ] && rclone copy "$OUT" "$RCLONE_REMOTE" --include "*$STAMP*"
ls -1 "$OUT" | grep "$STAMP"
# Keep the last 14 days locally
find "$OUT" -type f -mtime +14 -delete
