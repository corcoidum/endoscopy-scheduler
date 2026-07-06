#!/usr/bin/env bash
set -euo pipefail

mkdir -p backups
timestamp="$(date +%Y%m%d_%H%M%S)"
plain_file="backups/endoscopy_${timestamp}.dump"
encrypted_file="${plain_file}.gpg"

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${BACKUP_ENCRYPTION_PASSPHRASE:?BACKUP_ENCRYPTION_PASSPHRASE is required}"

pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB" > "$plain_file"
gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase "$BACKUP_ENCRYPTION_PASSPHRASE" -o "$encrypted_file" "$plain_file"
shred -u "$plain_file" 2>/dev/null || rm -f "$plain_file"

# 7일 초과 일일 백업은 정리합니다. 주간 보관은 운영 환경에서 별도 스냅샷 정책과 함께 적용하세요.
find backups -name "endoscopy_*.dump.gpg" -type f -mtime +28 -delete

echo "created encrypted backup: $encrypted_file"

