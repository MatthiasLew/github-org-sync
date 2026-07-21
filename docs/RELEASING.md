# Releasing Guide

This document describes how to prepare, build, and publish new stable versions of `github-org-sync`.

## Versioning Checklist

1.  Update the version number in `pyproject.toml` (`version` field under `[tool.poetry]` or `[project]`).
2.  Update the default version string fallback in `src/github_org_sync/__init__.py`.
3.  Update `CHANGELOG.md` with release notes under the corresponding version header.

## Compiling and Packaging (Windows)

To package the standalone Windows binary manually:
```powershell
# Installs pyinstaller
pip install pyinstaller
# Run build spec
pyinstaller github-org-sync.spec
```
This produces `dist/github-org-sync.exe` containing embedded assets and icons.

### SmartScreen Unsigned Binary Notice
Compiled binaries are unsigned by default. When running `github-org-sync.exe` on Windows for the first time, Windows Defender SmartScreen might show a warning message ("Windows protected your PC").
*   To run the binary, click **More info** -> **Run anyway**.
*   To bypass this warning permanently, sign the executable using a valid code-signing certificate (e.g. using `scripts/sign_windows.ps1` if credentials are set up).

## Tag Release & Automatic Deployment

Pushing a version tag triggers the `Publish Release` workflow on GitHub Actions. It compiles the EXE, runs the smoke test, packages it as a zip, calculates the SHA256 checksum, and creates a GitHub Release containing all compiled assets.

### Release tag push
```bash
git tag -a v1.2.0 -m "Release version 1.2.0"
git push origin v1.2.0
```
Once the CI pipeline completes, the draft or public release will be populated automatically on GitHub.
