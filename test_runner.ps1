
$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
Set-Location "d:\My projects\Self Healing RAG"

# Clean old logs
Remove-Item -Path ts_stdout.log -ErrorAction SilentlyContinue
Remove-Item -Path ts_stderr.log -ErrorAction SilentlyContinue

Write-Host "Starting server..."
$proc = Start-Process -FilePath ".venv\Scripts\python.exe" `
    -ArgumentList "-u", "test_server_random.py" `
    -NoNewWindow `
    -PassThru `
    -RedirectStandardOutput "ts_stdout.log" `
    -RedirectStandardError "ts_stderr.log"

Write-Host "Server started with PID $($proc.Id)"
Write-Host "Waiting 45 seconds..."
Start-Sleep -Seconds 45

Write-Host "Checking process status..."
if ($proc.HasExited) {
    Write-Host "Process exited with code: $($proc.ExitCode)"
} else {
    Write-Host "Process still running"
}

Write-Host "--- STDOUT ---"
Get-Content ts_stdout.log

Write-Host "--- STDERR ---"
Get-Content ts_stderr.log

# Clean up
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
