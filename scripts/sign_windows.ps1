# PowerShell script to sign windows executable using SignTool
param(
    [string]$ExePath = "dist\github-org-sync\github-org-sync.exe",
    [string]$CertPath = $env:SIGNING_CERT_PATH,
    [string]$CertPassword = $env:SIGNING_CERT_PASSWORD
)

Write-Host "Checking code signing configuration..." -ForegroundColor Cyan

$signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
if (-not $signtool) {
    # Try typical Windows SDK paths
    $sdkPaths = @(
        "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe",
        "C:\Program Files (x86)\Windows Kits\8.1\bin\x64\signtool.exe"
    )
    foreach ($path in $sdkPaths) {
        $found = Resolve-Path $path -ErrorAction SilentlyContinue
        if ($found) {
            $signtool = $found[0].Path
            break
        }
    }
}

if (-not $signtool) {
    Write-Host "WARNING: signtool.exe was not found in PATH or Windows Kits directories." -ForegroundColor Yellow
    Write-Host "Skipping executable signing. Release will remain UNSIGNED." -ForegroundColor Yellow
    exit 0
}

if (-not (Test-Path $ExePath)) {
    Write-Host "Error: Executable not found at $ExePath" -ForegroundColor Red
    exit 1
}

if ([string]::IsNullOrWhiteSpace($CertPath) -or -not (Test-Path $CertPath)) {
    Write-Host "No valid certificate file specified at SIGNING_CERT_PATH." -ForegroundColor Yellow
    Write-Host "Skipping executable signing. Release will remain UNSIGNED." -ForegroundColor Yellow
    exit 0
}

Write-Host "Signing executable using signtool..." -ForegroundColor Cyan
if (![string]::IsNullOrWhiteSpace($CertPassword)) {
    & $signtool sign /f $CertPath /p $CertPassword /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $ExePath
} else {
    & $signtool sign /f $CertPath /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $ExePath
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "Successfully signed: $ExePath" -ForegroundColor Green
} else {
    Write-Host "Failed to sign: $ExePath" -ForegroundColor Red
    exit $LASTEXITCODE
}
