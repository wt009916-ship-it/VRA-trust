param([string]$PythonExe = 'python', [switch]$Development)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$vraVersion = & $PythonExe -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"
if ($LASTEXITCODE -ne 0 -or $vraVersion -ne '3.12') { throw 'Use Python 3.12: ./Setup.ps1 -PythonExe <path-to-python.exe>' }
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    & $PythonExe -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
$vraRequirements = if ($Development) { 'backend/requirements-dev.txt' } else { 'backend/requirements.txt' }
& .venv/Scripts/python.exe -m pip install -r $vraRequirements
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check connectivity and retry Setup.ps1.' }
& .venv/Scripts/python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) {
    Push-Location frontend
    try {
        & npm ci
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed; Node 22+ is required for source builds.' }
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
Write-Host 'Ready. Run ./Start.ps1 -EnergyPlusPath <EnergyPlus-9.0.1/energyplus.exe>'
