# Start from any terminal directory; the project environment stays at the root.
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Project virtual environment is missing. Follow README.md setup instructions.'
}
Push-Location -LiteralPath (Join-Path $projectPath 'backend')
try {
    & $pythonPath -m app
    $commandExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $commandExitCode
