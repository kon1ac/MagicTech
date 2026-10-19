# Восстановление из копии (Windows). Проверка на тестовом контуре:
#   .\scripts\restore.ps1 -File backups\MagicTech_full_20261019_020000.dump
param(
  [Parameter(Mandatory = $true)][string]$File, [string]$TargetDb = "MagicTech_restore_test",
  [string]$DbUser = "postgres", [string]$DbHost = "localhost", [int]$DbPort = 5432,
  [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin"
)
$ErrorActionPreference = "Stop"
$env:PGPASSWORD = if ($env:DB_PASSWORD) { $env:DB_PASSWORD } else { "1" }
$sw = [Diagnostics.Stopwatch]::StartNew()
if ($TargetDb -like "*_restore_test") {
  & "$PgBin\dropdb.exe" -h $DbHost -p $DbPort -U $DbUser --if-exists $TargetDb
  & "$PgBin\createdb.exe" -h $DbHost -p $DbPort -U $DbUser $TargetDb
  & "$PgBin\pg_restore.exe" -h $DbHost -p $DbPort -U $DbUser -d $TargetDb --no-owner -j 4 $File
} else {
  & "$PgBin\pg_restore.exe" -h $DbHost -p $DbPort -U $DbUser -d $TargetDb --clean --if-exists --no-owner --single-transaction $File
}
& "$PgBin\psql.exe" -h $DbHost -p $DbPort -U $DbUser -d $TargetDb -tAc "SELECT count(*) AS orders FROM orders"
Write-Host ("Восстановлено в {0} за {1:n1} с" -f $TargetDb, $sw.Elapsed.TotalSeconds)
