param(
    [ValidateRange(1024,65535)][int]$Port = 8766,
    [string]$EnergyPlusPath = $env:ENERGYPLUS_EXE,
    [string]$DataDirectory = ''
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$vraCandidates = @((Join-Path $PSScriptRoot '.venv/Scripts/python.exe'), (Join-Path $PSScriptRoot '../.codex_work/vra-venv/Scripts/python.exe'))
$vraPython = $vraCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $vraPython) { throw 'Run Setup.ps1 first to create the Python environment.' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw 'Build frontend first: cd frontend; npm ci; npm run build' }
$env:DEMO_MODE = 'false'
$env:PYTHONUTF8 = '1'
if ($EnergyPlusPath) {
    if (-not (Test-Path -LiteralPath $EnergyPlusPath -PathType Leaf)) { throw 'EnergyPlusPath must point to energyplus.exe.' }
    $env:ENERGYPLUS_EXE = (Resolve-Path -LiteralPath $EnergyPlusPath).Path
}
if ($DataDirectory) {
    $env:VRA_DATA_DIR = [System.IO.Path]::GetFullPath($DataDirectory)
}
Write-Host "VRA-Trust: http://127.0.0.1:$Port"
# Queue admission and the engine semaphore require one server process.
& $vraPython -m uvicorn backend.api:app --host 127.0.0.1 --port $Port --workers 1
