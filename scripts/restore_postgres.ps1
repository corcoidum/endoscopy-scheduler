param(
  [Parameter(Mandatory = $true)]
  [string]$BackupFile
)

$ErrorActionPreference = "Stop"
$tmpFile = New-TemporaryFile

if (-not $env:POSTGRES_USER -or -not $env:POSTGRES_DB -or -not $env:BACKUP_ENCRYPTION_PASSPHRASE) {
  throw "POSTGRES_USER, POSTGRES_DB, BACKUP_ENCRYPTION_PASSPHRASE 환경변수가 필요합니다."
}

gpg --batch --yes --decrypt --passphrase $env:BACKUP_ENCRYPTION_PASSPHRASE -o $tmpFile.FullName $BackupFile
pg_restore --clean --if-exists -U $env:POSTGRES_USER -d $env:POSTGRES_DB $tmpFile.FullName
Remove-Item -LiteralPath $tmpFile.FullName -Force
Write-Host "restore complete"

