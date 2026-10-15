import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[1] / "scripts/runtime.ps1"
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Actual Windows PowerShell launcher checks")


def invoke(tmp_path, root, expression, process=None):
    harness = tmp_path / "harness.ps1"
    harness.write_text(
        "param($Helper,$Root,$ProcessFile)\n$ErrorActionPreference='Stop'\n"
        "[Console]::OutputEncoding=New-Object Text.UTF8Encoding $false\n. $Helper\n" + expression,
        encoding="utf-8",
    )
    source = tmp_path / "process.json"
    source.write_text(json.dumps(process), encoding="utf-8")
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(harness), str(HELPER), str(root), str(source)],
        capture_output=True,
        encoding="utf-8",
        timeout=20,
    )


def private_fixture(root):
    directory = root / "tools/app-runtime"
    directory.mkdir(parents=True)
    rows = []
    for name in ("python.exe", "python311.dll"):
        path = directory / name
        path.write_bytes(b"development fixture only")
        rows.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = root / "contracts/app-runtime-windows.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"base_files": rows}))
    receipt = {
        "schema": 1,
        "status": "READY",
        "python_version": "3.11.14",
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    }
    (directory / "studio-runtime.json").write_text(json.dumps(receipt))
    return directory


def test_private_runtime_selection_and_changed_executable_refusal(tmp_path):
    root = tmp_path / "Studio folder"
    runtime = private_fixture(root)
    result = invoke(tmp_path, root, "Get-StudioPython $Root")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(runtime / "python.exe")
    (runtime / "python.exe").write_bytes(b"changed executable")
    result = invoke(tmp_path, root, "Get-StudioPython $Root")
    assert result.returncode != 0 and "checksum changed" in result.stderr
    assert (runtime / "python.exe").read_bytes() == b"changed executable"


def test_incomplete_private_runtime_does_not_silently_fall_back(tmp_path):
    root = tmp_path / "Studio"
    (root / "tools/app-runtime").mkdir(parents=True)
    development = root / ".venv/Scripts/python.exe"
    development.parent.mkdir(parents=True)
    development.write_bytes(b"development fixture")
    result = invoke(tmp_path, root, "Get-StudioPython $Root")
    assert result.returncode != 0 and "incomplete" in result.stderr


def test_development_runtime_still_works_without_private_install(tmp_path):
    root = tmp_path / "Studio"
    development = root / ".venv/Scripts/python.exe"
    development.parent.mkdir(parents=True)
    development.write_bytes(b"development fixture")
    result = invoke(tmp_path, root, "Get-StudioPython $Root")
    assert result.returncode == 0 and result.stdout.strip() == str(development)


@pytest.mark.parametrize(
    "change,expected",
    [
        ("none", True),
        ("other-root", False),
        ("other-python", False),
        ("host", False),
        ("port", False),
        ("no-root", False),
        ("no-app", False),
    ],
)
def test_ownership_checks_exact_folder_host_port_and_executable(tmp_path, change, expected):
    root = tmp_path / "Studio folder"
    arguments = f'-I -B -m uvicorn studio.api:app --app-dir "{root}" --host 127.0.0.1 --port 8765'
    executable = str(root / "tools/app-runtime/python.exe")
    if change == "other-root":
        arguments = arguments.replace(str(root), str(root / "another"))
    elif change == "other-python":
        executable = str(tmp_path / "unrelated.exe")
    elif change == "host":
        arguments = arguments.replace("127.0.0.1", "0.0.0.0")
    elif change == "port":
        arguments = arguments.replace("8765", "87650")
    elif change == "no-root":
        arguments = arguments.replace(f'--app-dir "{root}" ', "")
    elif change == "no-app":
        arguments = arguments.replace("studio.api:app", "unrelated.api:app")
    result = invoke(
        tmp_path,
        root,
        "Test-StudioProcessOwned $Root (Get-Content -LiteralPath $ProcessFile -Raw | ConvertFrom-Json)",
        {"ExecutablePath": executable, "CommandLine": f'"{executable}" {arguments}'},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(expected)


def test_development_redirector_can_stop_its_base_process(tmp_path):
    root = tmp_path / "Studio folder"
    (root / ".venv").mkdir(parents=True)
    base = tmp_path / "standalone base"
    (root / ".venv/pyvenv.cfg").write_text(f"home = {base}\n")
    process = {
        "ExecutablePath": str(base / "python.exe"),
        "CommandLine": f'"{base / "python.exe"}" -I -m uvicorn studio.api:app --app-dir "{root}" --host 127.0.0.1 --port 8765',
    }
    result = invoke(
        tmp_path,
        root,
        "Test-StudioProcessOwned $Root (Get-Content -LiteralPath $ProcessFile -Raw | ConvertFrom-Json)",
        process,
    )
    assert result.returncode == 0 and result.stdout.strip() == "True", result.stderr


def test_launcher_verification_does_not_wait_for_background_pipe_eof(tmp_path):
    import signal
    import sys
    import time
    from scripts.runtime_relocation_smoke import powershell

    child = tmp_path / "background.py"
    child.write_text("import time; time.sleep(20)\n")
    pidfile = tmp_path / "child.pid"
    script = tmp_path / "launch.ps1"
    script.write_text(
        "param($Python,$Child,$PidFile)\n"
        "$start=New-Object Diagnostics.ProcessStartInfo\n"
        "$start.FileName=$Python\n$start.Arguments='\"'+$Child+'\"'\n"
        "$start.UseShellExecute=$false\n$start.CreateNoWindow=$true\n"
        "$process=[Diagnostics.Process]::Start($start)\n"
        "[IO.File]::WriteAllText($PidFile,[string]$process.Id)\n",
        encoding="utf-8",
    )
    started = time.monotonic()
    try:
        result = powershell(
            script,
            os.environ.copy(),
            tmp_path / "launch.log",
            getattr(sys, "_base_executable", sys.executable),
            str(child),
            str(pidfile),
        )
        assert result.returncode == 0, result.stderr
        assert time.monotonic() - started < 10
        assert pidfile.exists()
    finally:
        if pidfile.exists():
            os.kill(int(pidfile.read_text()), signal.SIGTERM)


def test_ffprobe_unicode_filename_does_not_use_windows_console_encoding(tmp_path):
    import wave
    from scripts.runtime_relocation_smoke import probe_media
    from studio.media import binary

    path = tmp_path / "media \u706f\u53f0 \u00e9.wav"
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, 16000, 160, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 160)
    result = probe_media(binary("ffprobe"), path)
    assert result["format"]["filename"] == str(path)
    assert result["streams"][0]["codec_name"] == "pcm_s16le"
