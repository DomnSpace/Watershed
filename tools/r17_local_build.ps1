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
$downloadScratch = Join-Path $inputAbs ".download-scratch"

function Get-GitHubToken {
    if ($env:GH_TOKEN) { return $env:GH_TOKEN }
    if ($env:GITHUB_TOKEN) { return $env:GITHUB_TOKEN }

    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if ($gh) {
        $token = (& gh auth token 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -eq 0 -and $token) { return [string]$token }
    }

    $credentialInput = "protocol=https`nhost=github.com`n`n"
    $credentialLines = @($credentialInput | git credential fill 2>$null)
    if ($LASTEXITCODE -eq 0) {
        foreach ($line in $credentialLines) {
            if ($line -like "password=*") {
                $token = $line.Substring("password=".Length)
                if ($token) { return $token }
            }
        }
    }

    throw @"
No GitHub API credential was found.
Nothing has been deleted and no build was started.
Either sign in through Git for Windows/Git Credential Manager, install GitHub CLI and run 'gh auth login',
or set GH_TOKEN for this PowerShell session. The token needs access to DomnSpace/Watershed Actions artifacts.
"@
}

function Get-GitHubHeaders([string]$Token) {
    return @{
        Authorization = "Bearer $Token"
        Accept = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
        "User-Agent" = "Watershed-R17-local-builder"
    }
}

function Get-RunArtifacts([Int64]$RunId, [string]$Token) {
    $headers = Get-GitHubHeaders $Token
    $all = @()
    $page = 1
    do {
        $uri = "https://api.github.com/repos/DomnSpace/Watershed/actions/runs/$RunId/artifacts?per_page=100&page=$page"
        $response = Invoke-RestMethod -Method Get -Uri $uri -Headers $headers
        $rows = @($response.artifacts)
        $all += $rows
        $page += 1
    } while ($rows.Count -eq 100)
    return $all
}

function Expand-GitHubArtifact($Artifact, [string]$Token, [scriptblock]$Extractor) {
    $headers = Get-GitHubHeaders $Token
    $id = [Int64]$Artifact.id
    $name = [string]$Artifact.name
    $work = Join-Path $downloadScratch ("artifact-" + $id + "-" + [Guid]::NewGuid().ToString("N"))
    $zip = "$work.zip"
    New-Item -ItemType Directory -Force -Path $work | Out-Null
    try {
        $uri = "https://api.github.com/repos/DomnSpace/Watershed/actions/artifacts/$id/zip"
        Write-Host "  downloading $name"
        Invoke-WebRequest -UseBasicParsing -Uri $uri -Headers $headers -OutFile $zip
        Expand-Archive -LiteralPath $zip -DestinationPath $work -Force
        & $Extractor $work
    }
    finally {
        Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Get-FragmentOrdinal([string]$ArtifactName) {
    $m = [regex]::Match($ArtifactName, '^atolia-v3-phase08-dr-fragment-(\d+)$')
    if (-not $m.Success) { return $null }
    return [int]$m.Groups[1].Value
}

function Existing-FragmentCount {
    return @(Get-ChildItem $fragmentRoot -Recurse -Filter "compact-*.json.gz" -File -ErrorAction SilentlyContinue).Count
}

if (-not $SkipDownload) {
    New-Item -ItemType Directory -Force -Path $fragmentRoot, $mendRoot, $downloadScratch | Out-Null

    $fragmentCount = Existing-FragmentCount
    $certsNow = @(Get-ChildItem $mendRoot -Recurse -Filter "repair-certificate.json" -File -ErrorAction SilentlyContinue)
    $plansNow = @(Get-ChildItem $mendRoot -Recurse -Filter "atolia_v3_cutoff_replay_plan.json" -File -ErrorAction SilentlyContinue)

    if ($fragmentCount -ne 580 -or $certsNow.Count -ne 1 -or $plansNow.Count -ne 1) {
        $token = Get-GitHubToken
    }

    if ($fragmentCount -ne 580) {
        Write-Host "Recovering existing Phase-08 compact artifacts locally (no new Actions run)..."
        Write-Host "Existing compact files: $fragmentCount / 580; completed files are preserved and skipped."
        $artifacts = @(Get-RunArtifacts 33645294772 $token | Where-Object { $_.name -like "atolia-v3-phase08-dr-fragment-*" -and -not $_.expired })
        if ($artifacts.Count -ne 580) {
            throw "Expected 580 unexpired Phase-08 fragment artifacts in run 33645294772, found $($artifacts.Count). Nothing local was deleted."
        }
        foreach ($artifact in ($artifacts | Sort-Object { Get-FragmentOrdinal ([string]$_.name) })) {
            $ordinal = Get-FragmentOrdinal ([string]$artifact.name)
            if ($null -eq $ordinal) { continue }
            $target = Join-Path $fragmentRoot ("compact-{0}.json.gz" -f $ordinal)
            if (Test-Path -LiteralPath $target) { continue }
            $ordinalLocal = $ordinal
            Expand-GitHubArtifact $artifact $token {
                param($stage)
                $matches = @(Get-ChildItem $stage -Recurse -Filter ("compact-{0}.json.gz" -f $ordinalLocal) -File)
                if ($matches.Count -ne 1) {
                    throw "Artifact for ordinal $ordinalLocal did not contain exactly one compact-$ordinalLocal.json.gz"
                }
                $partial = "$target.part"
                Copy-Item -LiteralPath $matches[0].FullName -Destination $partial -Force
                Move-Item -LiteralPath $partial -Destination $target -Force
            }
        }
    }

    $certsNow = @(Get-ChildItem $mendRoot -Recurse -Filter "repair-certificate.json" -File -ErrorAction SilentlyContinue)
    $plansNow = @(Get-ChildItem $mendRoot -Recurse -Filter "atolia_v3_cutoff_replay_plan.json" -File -ErrorAction SilentlyContinue)
    if ($certsNow.Count -ne 1 -or $plansNow.Count -ne 1) {
        Write-Host "Recovering the existing successful Phase-07 mend artifact..."
        $mendArtifacts = @(Get-RunArtifacts 33623991317 $token | Where-Object { $_.name -eq "atolia-v3-phase07-canonical-mend" -and -not $_.expired })
        if ($mendArtifacts.Count -ne 1) {
            throw "Expected one unexpired Phase-07 mend artifact, found $($mendArtifacts.Count). Nothing local was deleted."
        }
        Expand-GitHubArtifact $mendArtifacts[0] $token {
            param($stage)
            $cert = @(Get-ChildItem $stage -Recurse -Filter "repair-certificate.json" -File)
            $plan = @(Get-ChildItem $stage -Recurse -Filter "atolia_v3_cutoff_replay_plan.json" -File)
            if ($cert.Count -ne 1 -or $plan.Count -ne 1) {
                throw "Phase-07 mend artifact lacks the expected certificate/replay plan"
            }
            Copy-Item -LiteralPath $cert[0].FullName -Destination (Join-Path $mendRoot "repair-certificate.json") -Force
            Copy-Item -LiteralPath $plan[0].FullName -Destination (Join-Path $mendRoot "atolia_v3_cutoff_replay_plan.json") -Force
        }
    }
}

$fragments = @(Get-ChildItem $fragmentRoot -Recurse -Filter "compact-*.json.gz" -File -ErrorAction SilentlyContinue)
if ($fragments.Count -ne 580) { throw "Expected 580 compact fragments, found $($fragments.Count). Re-run without -SkipDownload to resume." }
$certs = @(Get-ChildItem $mendRoot -Recurse -Filter "repair-certificate.json" -File -ErrorAction SilentlyContinue)
$plans = @(Get-ChildItem $mendRoot -Recurse -Filter "atolia_v3_cutoff_replay_plan.json" -File -ErrorAction SilentlyContinue)
if ($certs.Count -ne 1) { throw "Expected one repair-certificate.json, found $($certs.Count)" }
if ($plans.Count -ne 1) { throw "Expected one atolia_v3_cutoff_replay_plan.json, found $($plans.Count)" }

python -c "import numpy, netCDF4, ijson" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing missing Atolia Python dependencies..."
    python -m pip install -r requirements-atolia.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency install failed" }
}

$outAbs = Join-Path $repo $Output
New-Item -ItemType Directory -Force -Path (Split-Path $outAbs -Parent) | Out-Null
Write-Host "Building one frozen R17 locally -> $outAbs"
python src/atolia/v3_build_runtime_v3_repaired_hydro.py `
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
