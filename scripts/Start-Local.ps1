param([ValidateSet('run','test','sync')][string]$Action='run', [int]$Port=8000)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (!(Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv: https://docs.astral.sh/uv/getting-started/installation/' }
$env:PYTHONDONTWRITEBYTECODE='1'
$env:UV_CACHE_DIR=Join-Path $projectRoot '.cache\uv'
$taskTemp=Join-Path $projectRoot 'runtime\tmp'
New-Item -ItemType Directory -Path $taskTemp -Force | Out-Null
$env:TEMP=$taskTemp
$env:TMP=$taskTemp
$env:TMPDIR=$taskTemp
if ($Action -eq 'sync') { & uv sync --frozen; exit $LASTEXITCODE }
if ($Action -eq 'test') { & uv run --frozen pytest -q --basetemp runtime/pytest; exit $LASTEXITCODE }
& uv run --frozen uvicorn app.api:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
