# GroundZero backend one-click starter (Windows PowerShell).
# Run from this folder:   .\START_BACKEND.ps1
# What it does: starts Postgres+Redis (Docker), makes a venv, installs deps,
# creates .env, applies DB migrations, loads Mangaluru places once, runs the API on :8000.
$ErrorActionPreference = "Continue"  # docker prints warnings on stderr; real failures are checked below
Set-Location $PSScriptRoot

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

Step "Checking Docker"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw "Docker Desktop is not installed or not on PATH. Install it, start it, then run this script again."
}
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not running. Open Docker Desktop, wait until it says 'running', then run this again." }

Step "Starting Postgres (PostGIS) and Redis"
docker compose up -d
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
  docker compose exec -T postgres pg_isready -U groundzero *> $null
  if ($LASTEXITCODE -eq 0) { $ready = $true; break }
  Start-Sleep -Seconds 2
}
if (-not $ready) { throw "Postgres did not become ready. Run: docker compose logs postgres" }

Step "Python environment"
if (-not (Test-Path ".venv")) { python -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r requirements.txt

Step "Config (.env)"
if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  $key = & $py -c "import secrets; print(secrets.token_urlsafe(48))"
  (Get-Content ".env") -replace '^AUTH_SECRET_KEY=.*$', "AUTH_SECRET_KEY=$key" | Set-Content ".env"
  Write-Host "Created .env with a fresh AUTH_SECRET_KEY"
}

Step "Database tables"
& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Migrations failed (see above)." }

Step "Loading Mangaluru places (skips quickly if already loaded)"
& $py import_master_data.py

Step "API is starting at http://localhost:8000  (docs: http://localhost:8000/docs). Keep this window open."
& $py -m uvicorn main:app --host 0.0.0.0 --port 8000
