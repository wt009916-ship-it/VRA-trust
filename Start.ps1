param([int]$Port = 8766)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$vraCandidates = @((Join-Path $PSScriptRoot '.venv/Scripts/python.exe'), (Join-Path $PSScriptRoot '../.codex_work/vra-venv/Scripts/python.exe'))
$vraPython = $vraCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $vraPython) { throw 'Create .venv and install backend/requirements-dev.txt as described in README.md.' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Build frontend first: cd frontend; npm ci; npm run build' }
$env:DEMO_MODE = 'false'
& $vraPython -m uvicorn backend.api:app --host 127.0.0.1 --port $Port --workers 1
