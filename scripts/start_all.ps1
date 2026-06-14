param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = 'Stop'

$backendScript = Join-Path $PSScriptRoot 'start_backend.ps1'
$frontendScript = Join-Path $PSScriptRoot 'start_frontend.ps1'

Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', $backendScript, '-RepoRoot', $RepoRoot | Out-Null
Start-Process powershell -ArgumentList '-NoExit', '-ExecutionPolicy', 'Bypass', '-File', $frontendScript, '-RepoRoot', $RepoRoot | Out-Null
