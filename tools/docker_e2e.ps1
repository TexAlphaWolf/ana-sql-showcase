# End to end with Docker Compose from Windows PowerShell: PostgreSQL and the sqlshow image, a small dataset, every
# command, and the result files are checked. Needs Docker Desktop. Usage: .\tools\docker_e2e.ps1
$ErrorActionPreference = "Stop"
$env:COMPOSE_PROJECT_NAME = "sqlshow-e2e-$(Get-Random)"

# Windows PowerShell 5.1 turns a program's message on stderr into an error under "Stop": docker compose prints its
# progress there, so the commands run with errors not terminating and only the exit code is looked at.
function Invoke-Compose([string[]]$ComposeArgs, [int[]]$Allowed = @(0), [switch]$StdoutOnly) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    if ($StdoutOnly) { $out = docker compose @ComposeArgs 2>$null } else { $out = docker compose @ComposeArgs 2>&1 }
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($Allowed -notcontains $code) { throw "docker compose $ComposeArgs exited with $code : $out" }
    ($out | Out-String)
}
function Invoke-Sqlshow([string[]]$SqlshowArgs) { Invoke-Compose (@("run", "--rm", "sqlshow") + $SqlshowArgs) }
# stdout only: the progress lines on stderr contain a random container name and would differ between two reads
function Read-Out($path) { Invoke-Compose @("run", "--rm", "--entrypoint", "cat", "sqlshow", $path) -StdoutOnly }
function Assert-Contains($text, $needle) { if ($text -notmatch [regex]::Escape($needle)) { throw "expected '$needle' in: $text" } }

try {
    Invoke-Compose @("build", "sqlshow") | Out-Null
    Invoke-Compose @("up", "-d", "--wait", "db") | Out-Null

    Assert-Contains (Invoke-Sqlshow @("init", "--scale", "0.02", "--seed", "3")) "loaded into schema 'sqlshow' (scale 0.02, seed 3)"
    Assert-Contains (Invoke-Sqlshow @("queries")) "q13"
    Assert-Contains (Invoke-Sqlshow @("run", "--repeat", "1", "--only", "q01,q07")) "q07"
    Assert-Contains (Invoke-Sqlshow @("bench", "--repeat", "1", "--only", "e01,e07")) "e07"
    Assert-Contains (Invoke-Sqlshow @("evaluate", "--repeat", "1", "--out", "/out")) "written: /out/report.json"

    $json = Read-Out "/out/report.json"
    Assert-Contains $json '"id": "q13"'
    Assert-Contains $json '"id": "e10"'
    $md = Read-Out "/out/evaluation.md"
    Assert-Contains $md "# Evaluation"
    Assert-Contains $md "PostgreSQL 18"

    Invoke-Sqlshow @("render", "/out/report.json", "-o", "/out/again.md") | Out-Null
    if ((Read-Out "/out/again.md") -ne $md) { throw "the report rebuilt from the JSON is not identical" }

    $bad = Invoke-Compose @("run", "--rm", "-e", "SQLSHOW_DSN=postgresql://sqlshow:wrong@db:5432/sqlshow", "sqlshow", "run") @(2)
    Assert-Contains $bad "cannot connect"
    Write-Host "docker end-to-end: OK"
}
finally {
    $ErrorActionPreference = "Continue"
    docker compose down -v --remove-orphans 2>&1 | Out-Null
}
