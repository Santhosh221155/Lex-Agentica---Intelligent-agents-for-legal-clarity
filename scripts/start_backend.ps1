param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = 'Stop'
Set-Location $RepoRoot

if (Test-Path ".venv\Scripts\Activate.ps1") {
  . .\.venv\Scripts\Activate.ps1
}

Set-Location "backend"
alembic upgrade head
Set-Location "$RepoRoot"

$hostName = if ($env:UVICORN_HOST) { $env:UVICORN_HOST } else { '0.0.0.0' }
$port = if ($env:UVICORN_PORT) { $env:UVICORN_PORT } else { '8000' }

uvicorn backend.app.main:app --reload --reload-dir backend --reload-dir scripts --host $hostName --port $port
