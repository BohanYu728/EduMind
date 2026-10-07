$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$pythonPath = Join-Path $backendRoot '.venv/Scripts/python.exe'
$logRoot = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Backend dependencies missing. Run: cd backend; uv sync'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules'))) {
    throw 'Frontend dependencies missing. Run: cd frontend; npm.cmd ci'
}
function Test-LocalService([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
        return $response.StatusCode -eq 200
    } catch { return $false }
}

if (-not (Test-LocalService 'http://127.0.0.1:8000/health')) {
    Start-Process -FilePath $pythonPath -WorkingDirectory $backendRoot -WindowStyle Hidden `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') `
        -RedirectStandardOutput (Join-Path $logRoot 'backend.log') `
        -RedirectStandardError (Join-Path $logRoot 'backend-error.log') | Out-Null
}
if (-not (Test-LocalService 'http://127.0.0.1:5173')) {
    $nodePath = (Get-Command node.exe -ErrorAction Stop).Source
    $vitePath = Join-Path $frontendRoot 'node_modules/vite/bin/vite.js'
    Start-Process -FilePath $nodePath -WorkingDirectory $frontendRoot -WindowStyle Hidden `
        -ArgumentList @(('"' + $vitePath + '"'), '--host', '127.0.0.1', '--port', '5173', '--strictPort') `
        -RedirectStandardOutput (Join-Path $logRoot 'frontend.log') `
        -RedirectStandardError (Join-Path $logRoot 'frontend-error.log') | Out-Null
}

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ((Test-LocalService 'http://127.0.0.1:8000/health') -and
        (Test-LocalService 'http://127.0.0.1:5173/api/v1/ping')) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw "Startup failed. Check logs in $logRoot" }
Write-Host 'EduMind is running: http://127.0.0.1:5173'
Write-Host 'API docs: http://127.0.0.1:8000/docs'
