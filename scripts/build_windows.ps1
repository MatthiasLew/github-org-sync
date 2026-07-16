# PowerShell script to build the Windows standalone executable

Write-Host "Starting build process for github-org-sync..." -ForegroundColor Cyan

# Ensure PyInstaller is installed
$has_pyinstaller = python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller not found. Installing..." -ForegroundColor Yellow
    python -m pip install pyinstaller
}

# Clean previous builds
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

# Run PyInstaller
# --noconfirm: Overwrite existing output directory without prompting
# --windowed: Do not open a console window when the executable starts (GUI mode)
# --name: Specify name of the executable
python -m PyInstaller --noconfirm --onedir --windowed --name="github-org-sync" src/github_org_sync/__main__.py

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build completed successfully!" -ForegroundColor Green
    Write-Host "Executable can be found at: dist\github-org-sync\github-org-sync.exe" -ForegroundColor Green
} else {
    Write-Host "Build failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
