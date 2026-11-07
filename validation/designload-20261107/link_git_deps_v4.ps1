param([string]$FrontendDirectory, [string]$DependencyDirectory)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Junction -Path (Join-Path $FrontendDirectory 'node_modules') -Target $DependencyDirectory | Out-Null
