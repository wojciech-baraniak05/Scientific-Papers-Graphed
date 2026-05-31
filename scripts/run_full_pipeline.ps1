# powershell -ExecutionPolicy Bypass -File .\scripts\run_full_pipeline.ps1 -TargetGb 2
# .\scripts\run_full_pipeline.ps1 -TargetGb 1 -MaxEnrichmentIds 200000 -StartApi
# .\scripts\run_full_pipeline.ps1 -Scope "field:22" -MaxPapers 5000
[CmdletBinding()]
param(
    [string]$Scope = "popular",
    [double]$TargetGb = 1.0,
    [int]$MaxEnrichmentIds = 50000,
    [int]$MaxPapers = -1,
    [switch]$SkipReferenceData,
    [switch]$StartApi,
    [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"

$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

function Read-DotEnv {
    param([string]$Path)
    $map = @{}
    if (Test-Path $Path) {
        foreach ($line in Get-Content $Path) {
            $t = $line.Trim()
            if ($t -and -not $t.StartsWith("#") -and $t.Contains("=")) {
                $i = $t.IndexOf("=")
                $map[$t.Substring(0, $i).Trim()] = $t.Substring($i + 1).Trim()
            }
        }
    }
    return $map
}

function Get-OrDefault {
    param($Map, [string]$Key, [string]$Default)
    if ($Map.ContainsKey($Key) -and $Map[$Key]) { return $Map[$Key] }
    return $Default
}

Write-Host "=== Paper Citation Explorer - full data pipeline ===" -ForegroundColor Cyan

$envMap = Read-DotEnv (Join-Path $Root ".env")
$RootPw = Get-OrDefault $envMap "MYSQL_ROOT_PASSWORD" "rootpass"
$DbUser = Get-OrDefault $envMap "MYSQL_USER" "papers"
$DbName = Get-OrDefault $envMap "MYSQL_DATABASE" "papers"

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[setup] Creating .venv and installing requirements ..." -ForegroundColor Yellow
    python -m venv (Join-Path $Root ".venv")
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
}

Write-Host "[1/5] Starting MySQL container ..." -ForegroundColor Green
docker compose up -d mysql | Out-Host

Write-Host "[2/5] Waiting for MySQL to become healthy ..." -ForegroundColor Green
$Deadline = (Get-Date).AddSeconds(180)
$Status = ""
while ($Status -ne "healthy") {
    Start-Sleep -Seconds 3
    try { $Status = (docker inspect --format "{{.State.Health.Status}}" papers-mysql).Trim() }
    catch { $Status = "starting" }
    Write-Host "    health: $Status"
    if ((Get-Date) -gt $Deadline) { throw "MySQL did not become healthy within 180s." }
}

Write-Host "[3/5] Ensuring PROCESS grant for accurate size gauge ..." -ForegroundColor Green
$GrantSql = "GRANT PROCESS ON *.* TO '$DbUser'@'%'; FLUSH PRIVILEGES;"
docker compose exec -T mysql mysql "-uroot" "-p$RootPw" -e $GrantSql | Out-Host

Write-Host "[4/5] Running population pipeline (scope=$Scope, target=$TargetGb GB) ..." -ForegroundColor Green
$TargetStr = $TargetGb.ToString([System.Globalization.CultureInfo]::InvariantCulture)
$PipelineArgs = @(
    (Join-Path "scripts" "run_pipeline.py"),
    "--scope", $Scope,
    "--target-gb", $TargetStr,
    "--max-enrichment-ids", "$MaxEnrichmentIds"
)
if ($SkipReferenceData) { $PipelineArgs += "--skip-reference-data" }
if ($MaxPapers -ge 0)   { $PipelineArgs += @("--max-papers", "$MaxPapers") }

& $VenvPython @PipelineArgs
if ($LASTEXITCODE -ne 0) { throw "Pipeline failed (exit $LASTEXITCODE)." }

Write-Host "[5/5] Final dataset summary:" -ForegroundColor Green
$SummarySql = "SELECT (SELECT COUNT(*) FROM $DbName.papers) AS papers, (SELECT SUM(ingested=1) FROM $DbName.papers) AS ingested, (SELECT SUM(ingested=0 AND title IS NOT NULL) FROM $DbName.papers) AS stubs_labeled, (SELECT COUNT(*) FROM $DbName.paper_references) AS edges; SELECT ROUND(SUM(file_size)/1024/1024,1) AS real_mb FROM information_schema.innodb_tablespaces WHERE SUBSTRING_INDEX(name,'/',1)='$DbName';"
docker compose exec -T mysql mysql "-uroot" "-p$RootPw" -e $SummarySql | Out-Host

if ($StartApi) {
    Write-Host "Starting API at http://127.0.0.1:$ApiPort/docs (Ctrl+C to stop) ..." -ForegroundColor Cyan
    & $VenvPython -m uvicorn app.api.main:app --host 127.0.0.1 --port $ApiPort
}

Write-Host "=== Done ===" -ForegroundColor Cyan
