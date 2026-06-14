$ErrorActionPreference = 'Stop'
$null = Add-Type -AssemblyName System.Net.Http
$pdfPath = Join-Path $PSScriptRoot 'test-ingest.pdf'
[IO.File]::WriteAllBytes($pdfPath, [Text.Encoding]::ASCII.GetBytes("%PDF-1.4`n1 0 obj<<>>endobj`ntrailer<<>>`n%%EOF"))

$client = [System.Net.Http.HttpClient]::new()
$form = [System.Net.Http.MultipartFormDataContent]::new()
$fileBytes = [IO.File]::ReadAllBytes($pdfPath)
$fileContent = [System.Net.Http.ByteArrayContent]::new($fileBytes)
$fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/pdf')
$form.Add($fileContent, 'file', 'test-ingest.pdf')

$response = $client.PostAsync('http://127.0.0.1:8000/api/ingest/file', $form).Result
Write-Output ([int]$response.StatusCode)
Write-Output $response.Content.ReadAsStringAsync().Result
