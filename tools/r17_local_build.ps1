param(
    [string]$InputRoot = ".cache/r17-inputs",
    [string]$Output = ".cache/r17/atolia_runtime_v3.nc",
    [switch]$SkipDownload,
    [switch]$StructuralOnly
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repo

$inputAbs = Join-Path $repo $InputRoot
$fragmentRoot = Join-Path $inputAbs "fragments"
$mendRoot = Join-Path $inputAbs "mend"
New-Item -ItemType Directory -Force -Path $fragmentRoot, $mendRoot | Out-Null

if (-not $SkipDownload) {
    $count = @(Get-ChildItem $fragmentRoot -Recurse -Filter "compact-*.json.gz" -ErrorAction SilentlyContinue).Count
    if ($count -ne 580) {
        Write-Host "Downloading the existing 580 Phase-08 compact artifacts (no new Actions run)..."
        gh run download 33645294772 -R DomnSpace/Watershed -p "atolia-v3-phase08-dr-fragment-*" -D $fragmentRoot
    }
    $certs = @(Get-ChildItem $mendRoot -Recurse -Filter "repair-certificate.json" -ErrorAction SilentlyContinue)
    if ($certs.Count -ne 1) {
        Write-Host "Downloading the existing successful Phase-07 mend certificate..."
        gh run download 33623991317 -R DomnSpace/Watershed -n "atolia-v3-phase07-canonical-mend" -D $mendRoot
    }
}

$fragments = @(Get-ChildItem $fragmentRoot -Recurse -Filter "compact-*.json.gz")
if ($fragments.Count -ne 580) { throw "Expected 580 compact fragments, found $($fragments.Count)" }
$certs = @(Get-ChildItem $mendRoot -Recurse -Filter "repair-certificate.json")
$plans = @(Get-ChildItem $mendRoot -Recurse -Filter "atolia_v3_cutoff_replay_plan.json")
if ($certs.Count -ne 1) { throw "Expected one repair-certificate.json, found $($certs.Count)" }
if ($plans.Count -ne 1) { throw "Expected one atolia_v3_cutoff_replay_plan.json, found $($plans.Count)" }

python -m pip install -r requirements-atolia.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency install failed" }

$outAbs = Join-Path $repo $Output
New-Item -ItemType Directory -Force -Path (Split-Path $outAbs -Parent) | Out-Null
Write-Host "Building one frozen R17 locally -> $outAbs"
python src/atolia/v3_build_runtime_v3.py `
    --fragments $fragmentRoot `
    --repair-certificate $certs[0].FullName `
    --cutoff-plan $plans[0].FullName `
    --hypothesis hypotheses/atolia_atesis_1800_1000_v0.json `
    --out $outAbs
if ($LASTEXITCODE -ne 0) { throw "R17 build failed" }

$smokeArgs = @("tools/r17_local_smoke.py", "--runtime", $outAbs)
if ($StructuralOnly) { $smokeArgs += "--structural-only" }
python @smokeArgs
if ($LASTEXITCODE -ne 0) { throw "R17 local smoke failed" }

Write-Host "PASS: local two-NetCDF gate completed without starting a GitHub Actions build."
