# Полный бэкап БД MagicTech (Windows). Планировщик задач: ежедневно 02:00.
#   schtasks /Create /SC DAILY /ST 02:00 /TN MagicTechBackup /TR "powershell -File C:\MagicTech\scripts\backup_full.ps1"
param(
  [string]$DbName = "MagicTech", [string]$DbUser = "postgres", [string]$DbHost = "localhost", [int]$DbPort = 5432,
  [string]$BackupDir = "$PSScriptRoot\..\backups", [int]$KeepDays = 30,
  [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin"
)
$ErrorActionPreference = "Stop"
$env:PGPASSWORD = if ($env:DB_PASSWORD) { $env:DB_PASSWORD } else { "1" }
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$file = Join-Path $BackupDir ("{0}_full_{1}.dump" -f $DbName, (Get-Date -Format "yyyyMMdd_HHmmss"))
& "$PgBin\pg_dump.exe" -h $DbHost -p $DbPort -U $DbUser -d $DbName -F c -Z 6 -f $file
if ($LASTEXITCODE -ne 0) { throw "pg_dump завершился с кодом $LASTEXITCODE" }
(Get-FileHash $file -Algorithm SHA256).Hash | Out-File "$file.sha256"
& "$PgBin\pg_restore.exe" --list $file | Out-Null
Get-ChildItem $BackupDir -Filter "${DbName}_*.dump*" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } | Remove-Item
Write-Host "OK: $file"
