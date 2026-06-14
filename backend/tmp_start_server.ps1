$ErrorActionPreference = 'Stop'
$port = 8000
$connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($connections) {
    $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($p in $pids) {
        try { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue } catch {}
    }
}
$env:DISABLE_AUTH = '1'
$env:ENABLE_SENTENCE_TRANSFORMERS = '1'
$backend = 'd:/My projects/Self Healing RAG/backend'
$python = 'd:/My projects/Self Healing RAG/.venv/Scripts/python.exe'
$stdout = Join-Path $backend 'server_stdout.log'
$stderr = Join-Path $backend 'server_stderr.log'
if (Test-Path $stdout) { Remove-Item $stdout -Force }
if (Test-Path $stderr) { Remove-Item $stderr -Force }
Start-Process -FilePath $python -ArgumentList @('-u','-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $backend -RedirectStandardOutput $stdout -RedirectStandardError $stderr | Out-Null
Start-Sleep -Seconds 8
if (-not (Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue)) { throw 'uvicorn did not start on port 8000' }
'uvicorn_started'
