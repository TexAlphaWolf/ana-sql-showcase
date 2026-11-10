# The full measurement on your own computer, in Docker, from Windows PowerShell: PostgreSQL 18 and sqlshow, the data at
# the given scale, every query and every index experiment, and the report in $Out.
# Usage: .\tools\run_full.ps1 [-Scale 1] [-Repeat 5] [-Out results]
param(
    [double]$Scale = 1,
    [int]$Repeat = 5,
    [string]$Out = "results"
)
# Windows PowerShell 5.1 turns anything a program writes on stderr into an error under "Stop": docker compose prints its
# progress there, so only the exit code is looked at.
$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$outFull = (Resolve-Path -LiteralPath $Out).Path

docker compose build sqlshow
if ($LASTEXITCODE -ne 0) { Write-Host "docker build failed"; exit 1 }
docker compose up -d --wait db
if ($LASTEXITCODE -ne 0) { Write-Host "the database did not start"; exit 1 }

try {
    Write-Host "== init (scale $Scale) =="
    docker compose run --rm sqlshow init --scale $Scale
    if ($LASTEXITCODE -ne 0) { Write-Host "init failed (exit code $LASTEXITCODE)"; exit 1 }
    Write-Host "== evaluate =="
    docker compose run --rm -v "${outFull}:/out" sqlshow evaluate --repeat $Repeat --out /out
    if ($LASTEXITCODE -ne 0) { Write-Host "evaluate failed (exit code $LASTEXITCODE)"; exit 1 }
}
finally {
    docker compose down -v --remove-orphans 2>&1 | Out-Null
}
Write-Host "Done. Send me $Out\report.json (and look at $Out\summary.png)."
