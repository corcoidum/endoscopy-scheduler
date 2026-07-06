#!/usr/bin/env bash
set -euo pipefail

backup_file="${1:?usage: restore_postgres.sh backups/endoscopy_YYYYmmdd_HHMMSS.dump.gpg}"
tmp_file="$(mktemp)"

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${BACKUP_ENCRYPTION_PASSPHRASE:?BACKUP_ENCRYPTION_PASSPHRASE is required}"

gpg --batch --yes --decrypt --passphrase "$BACKUP_ENCRYPTION_PASSPHRASE" -o "$tmp_file" "$backup_file"
pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$tmp_file"
shred -u "$tmp_file" 2>/dev/null || rm -f "$tmp_file"

echo "restore complete"

