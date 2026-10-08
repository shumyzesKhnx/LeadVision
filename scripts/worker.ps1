# Run the separate worker using the same environment and settings as the API.
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Project virtual environment is missing. Follow README.md setup instructions.'
}
Push-Location -LiteralPath (Join-Path $projectPath 'backend')
try {
    & $pythonPath -m app.worker.main
    $commandExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $commandExitCode
