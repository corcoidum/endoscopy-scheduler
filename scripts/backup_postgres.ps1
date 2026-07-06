$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path "backups" | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$plainFile = "backups/endoscopy_$timestamp.dump"
$encryptedFile = "$plainFile.gpg"

if (-not $env:POSTGRES_USER -or -not $env:POSTGRES_DB -or -not $env:BACKUP_ENCRYPTION_PASSPHRASE) {
  throw "POSTGRES_USER, POSTGRES_DB, BACKUP_ENCRYPTION_PASSPHRASE 환경변수가 필요합니다."
}

pg_dump -Fc -U $env:POSTGRES_USER $env:POSTGRES_DB | Set-Content -Encoding Byte -Path $plainFile
gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase $env:BACKUP_ENCRYPTION_PASSPHRASE -o $encryptedFile $plainFile
Remove-Item -LiteralPath $plainFile -Force
Get-ChildItem backups -Filter "endoscopy_*.dump.gpg" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-28) } | Remove-Item -Force
Write-Host "created encrypted backup: $encryptedFile"

