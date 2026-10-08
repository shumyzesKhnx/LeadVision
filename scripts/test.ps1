$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Project virtual environment is missing. Follow README.md setup instructions.'
}
# Keep each run separate from old Windows temporary folders and pytest caches.
$testRunPath = Join-Path $projectPath ('.cache\test-runs\' + [guid]::NewGuid().ToString('N'))
$testCachePath = Join-Path $testRunPath 'cache'
$testTempPath = Join-Path $testRunPath 'temp'
New-Item -ItemType Directory -Path $testRunPath -Force | Out-Null
Push-Location -LiteralPath (Join-Path $projectPath 'backend')
try {
    & $pythonPath -m pytest -o "cache_dir=$testCachePath" "--basetemp=$testTempPath" @args
    $commandExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $commandExitCode
