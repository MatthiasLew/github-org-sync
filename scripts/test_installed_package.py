from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build"


class SmokeError(RuntimeError):
    pass


def main() -> int:
    temp_root: Path | None = None
    try:
        print("[1/6] Cleaning build and dist artifacts...")
        _remove_build_artifacts()

        print("[2/6] Building wheel distribution package...")
        _run([sys.executable, "-m", "build", "--wheel"], ROOT)
        wheel = _find_single_wheel()
        print(f"      Built wheel: {wheel.name}")

        print("[3/6] Setting up isolated clean virtualenv...")
        temp_root = Path(tempfile.mkdtemp(prefix="github org sync wheel smoke "))
        venv_dir = temp_root / "clean venv"
        project_dir = temp_root / "workspace with spaces"
        project_dir.mkdir(parents=True)

        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
        py = _venv_python(venv_dir)

        print("[4/6] Installing wheel into clean virtualenv (CLI only, no GUI extra)...")
        _run(
            [str(py), "-m", "pip", "install", str(wheel)],
            project_dir,
        )

        print("[5/6] Verifying GUI dependencies are NOT installed in base CLI...")
        py = _venv_python(venv_dir)
        pyside_check = subprocess.run(
            [str(py), "-c", "import PySide6"],
            capture_output=True,
            text=True,
        )
        if pyside_check.returncode == 0:
            raise SmokeError("PySide6 was installed in base CLI! It must remain optional under [gui] extra.")
        print("      Confirmed: PySide6 is completely isolated and not installed.")

        print("[6/6] Verifying installed CLI entrypoint and commands from directory with spaces...")
        entrypoint = _entrypoint_path(venv_dir)
        if not entrypoint.exists():
            raise SmokeError(f"Missing installed entrypoint: {entrypoint}")

        _smoke_entrypoint(entrypoint, project_dir)
        print(f"\nSUCCESS: Installed wheel smoke test passed for {wheel.name}")
        return 0

    except SmokeError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if temp_root is not None and temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)


def _entrypoint_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "github-org-sync.exe"
    return venv_dir / "bin" / "github-org-sync"


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _remove_build_artifacts() -> None:
    for path in (DIST, BUILD):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def _find_single_wheel() -> Path:
    wheels = sorted(DIST.glob("*.whl"))
    if len(wheels) != 1:
        raise SmokeError(f"Expected exactly one wheel in {DIST}, found {len(wheels)}")
    return wheels[0]


def _smoke_entrypoint(entrypoint: Path, cwd: Path) -> None:
    # 1. Version check
    res_ver = _run([str(entrypoint), "--version"], cwd)
    from github_org_sync import __version__

    expected_ver = f"github-org-sync {__version__}"
    if expected_ver not in res_ver.stdout and expected_ver not in res_ver.stderr:
        raise SmokeError(f"--version output mismatch: expected '{expected_ver}', got '{res_ver.stdout}'")
    print(f"      --version: {expected_ver}")

    # 2. Help check
    res_help = _run([str(entrypoint), "--help"], cwd)
    if "Safe, CLI-first synchronization tool" not in res_help.stdout:
        raise SmokeError("Failed to render --help correctly")
    print("      --help: OK")

    # 3. Doctor check (text)
    res_doc = _run([str(entrypoint), "doctor"], cwd)
    if "Environment Doctor" not in res_doc.stdout:
        raise SmokeError("Failed to run doctor command")
    print("      doctor (text): OK")

    # 4. Doctor check (JSON envelope)
    res_doc_json = _run([str(entrypoint), "doctor", "--json"], cwd)
    _assert_envelope_json(res_doc_json.stdout, "doctor")
    print("      doctor (--json): OK")

    # 5. Doctor with workspace in path containing spaces
    res_doc_ws = _run([str(entrypoint), "doctor", "--workspace", ".", "--json"], cwd)
    payload = _assert_envelope_json(res_doc_ws.stdout, "doctor")
    checks = {c["key"]: c["status"] for c in payload.get("data", {}).get("checks", [])}
    if checks.get("workspace") != "ok" or checks.get("locking") != "ok":
        raise SmokeError(f"Workspace/locking failed in directory with spaces: {checks}")
    print("      doctor (--workspace with spaces): OK")


def _assert_envelope_json(output: str, command: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = json.loads(output)
    except json.JSONDecodeError as exc:
        raise SmokeError(f"Command '{command}' did not return valid JSON: {exc}\nOutput was: {output}") from exc

    required_fields = {"schema_version", "tool_version", "command", "status", "exit_code", "summary", "data", "errors"}
    missing = required_fields - set(payload)
    if missing:
        raise SmokeError(f"Command '{command}' JSON missing required envelope fields: {sorted(missing)}")
    if payload["schema_version"] != "1.0":
        raise SmokeError(f"Unexpected schema_version: {payload['schema_version']}")
    return payload


def _run(command: list[str], cwd: Path, *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    # Clear PYTHONPATH to prevent importing development tree
    clean_env = dict(os.environ)
    clean_env.pop("PYTHONPATH", None)

    result = subprocess.run(
        command,
        cwd=cwd,
        env=clean_env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        input=input_text,
        shell=False,
        timeout=180,
    )
    if result.returncode != 0:
        rendered = " ".join(command)
        raise SmokeError(
            f"Command failed with exit code {result.returncode}:\n{rendered}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


if __name__ == "__main__":
    sys.exit(main())
