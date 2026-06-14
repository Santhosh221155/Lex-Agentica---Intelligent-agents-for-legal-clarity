param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = 'Stop'
Set-Location $RepoRoot
Set-Location "frontend"

if (-not (Test-Path "node_modules")) {
  npm install
}

if (-not $env:NEXT_PUBLIC_BACKEND_URL) {
  $env:NEXT_PUBLIC_BACKEND_URL = 'http://localhost:8000'
}

npm run dev
