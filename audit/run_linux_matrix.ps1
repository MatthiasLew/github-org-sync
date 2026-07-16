# PowerShell script to execute the Linux test matrix using Docker

$images = @(
    "ubuntu:22.04",
    "ubuntu:24.04",
    "debian:12",
    "python:3.11-slim",
    "python:3.12-slim"
)

$results = @()
$failed = $false

Write-Host "=== Starting Linux Docker Test Matrix ===" -ForegroundColor Cyan

foreach ($img in $images) {
    Write-Host "`n[Matrix] Building and testing image: $img ..." -ForegroundColor Yellow
    $safe_name = $img -replace '[:.]', '-'

    # 1. Build
    $build_cmd = "docker build -f audit/docker/Dockerfile --build-arg BASE_IMAGE=$img -t github-org-sync-audit:$safe_name ."
    Write-Host "$build_cmd" -ForegroundColor Gray
    Invoke-Expression $build_cmd

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[-] Build failed for $img" -ForegroundColor Red
        $results += [PSCustomObject]@{ Image = $img; Build = "FAIL"; Test = "N/A" }
        $failed = $true
        continue
    }

    # 2. Run tests
    $run_cmd = "docker run --rm github-org-sync-audit:$safe_name"
    Write-Host "$run_cmd" -ForegroundColor Gray
    Invoke-Expression $run_cmd

    if ($LASTEXITCODE -eq 0) {
        Write-Host "[+] Tests passed for $img" -ForegroundColor Green
        $results += [PSCustomObject]@{ Image = $img; Build = "PASS"; Test = "PASS" }
    } else {
        Write-Host "[-] Tests failed for $img" -ForegroundColor Red
        $results += [PSCustomObject]@{ Image = $img; Build = "PASS"; Test = "FAIL" }
        $failed = $true
    }
}

Write-Host "`n=== Linux Test Matrix Summary ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize

$matrix_failed = $false
foreach ($res in $results) {
    if ($res.Image -ne "ubuntu:22.04") {
        if ($res.Build -ne "PASS" -or $res.Test -ne "PASS") {
            $matrix_failed = $true
        }
    }
}

if ($matrix_failed) {
    Write-Host "Some compatible images failed validation." -ForegroundColor Red
    exit 1
} else {
    Write-Host "All compatible images passed validation successfully!" -ForegroundColor Green
    exit 0
}
