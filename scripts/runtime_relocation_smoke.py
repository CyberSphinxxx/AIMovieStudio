"""Actual private-folder relocation check; demo visuals, real local app/media tools."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import time
import traceback
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from scripts.prepare_app_runtime import ROOT, atomic_json


def powershell(script, env, log, *arguments):
    # A detached server can inherit otherwise unused pipe handles. Waiting for
    # pipe EOF would then wait for the server's lifetime after PowerShell exits.
    with log.open("ab") as output:
        output.write(f"\n{script.name}: starting\n".encode())
        output.flush()
        offset = output.tell()
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments],
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=60,
        )
        output.write(f"\n{script.name}: exit {result.returncode}\n".encode())
    with log.open("rb") as saved:
        saved.seek(offset)
        raw = saved.read(65536).decode("utf-8", errors="replace")
    return subprocess.CompletedProcess(result.args, result.returncode, stdout=raw, stderr=raw)


def request(path, body=None, method=None):
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "http://127.0.0.1:8765" + path,
        data=payload,
        method=method,
        headers={"Content-Type": "application/json"} if payload else {},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read(100_000_000)
        return json.loads(raw) if "application/json" in response.headers.get("Content-Type", "") else raw


def probe_media(executable, output):
    result = subprocess.run(
        [str(executable), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    # FFprobe JSON is UTF-8, independent of the Windows console code page.
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, help="Reuse an existing empty app-owned private test build")
    parser.add_argument(
        "--resume-project", help="Recheck a completed relocation sample after restarting its build"
    )
    args = parser.parse_args()
    builds = ROOT / "tools/private-builds"
    original = Path(
        (ROOT / "ops/evidence/app-runtime-private-build.log").read_text(encoding="utf-8").strip()
    ).resolve()
    target = builds / ("Studio caf\u00e9 \u706f\u53f0 " + uuid4().hex[:10])
    # Only the freshly created app-owned sample build is renamed, never source/data.
    if args.folder:
        target = args.folder.resolve()
        assert target.parent == builds and target.name.startswith("Studio ")
        assert json.loads((target / "private-build.json").read_text())["private_only"] is True
    else:
        assert original.is_relative_to(builds.resolve()) and target.resolve().is_relative_to(builds.resolve())
        assert original.parent == builds and original.name.startswith("Studio-") and not target.exists()
        assert json.loads((original / "private-build.json").read_text())["private_only"] is True
        original.rename(target)
    env = os.environ | {"STUDIO_DATA": str(target / "data")}
    poison = target / "ignored Python environment"
    poison.mkdir(exist_ok=True)
    for name in ("fastapi.py", "studio.py"):
        (poison / name).write_text("raise RuntimeError('Untrusted PYTHONPATH was imported')\n")
    env.update(PYTHONHOME=str(poison), PYTHONPATH=str(poison))
    token = uuid4().hex[:10]
    evidence = ROOT / "ops/evidence"
    log = evidence / f"app-runtime-relocation-{token}.log"
    report_path = evidence / f"app-runtime-relocation-{token}.json"
    report = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "STARTED",
        "folder": str(target),
        "is_mock": True,
        "native_generation_verified": False,
        "fresh_account_tested": False,
        "python_environment_poisoned": True,
    }
    started = time.monotonic()
    running = False
    source_env = os.environ.copy()
    atomic_json(report_path, report)
    try:
        stopped = powershell(ROOT / "scripts/stop.ps1", source_env, log)
        assert stopped.returncode == 0, stopped.stderr
        launched = powershell(target / "scripts/run.ps1", env, log, "-NoBrowser")
        assert launched.returncode == 0, launched.stderr
        running = True
        health = request("/api/health")
        assert health["runtime"]["isolated"] and health["runtime"]["app_owned"]
        assert health["runtime"]["python_version"] == "3.11.14"
        assert isinstance(health["runtime"]["process_id"], int)
        report["health"] = health
        projects = request("/api/projects")
        assert [p["id"] for p in projects] == ([args.resume_project] if args.resume_project else [])
        assert b"<html" in request("/")
        repeated = powershell(target / "scripts/run.ps1", env, log, "-NoBrowser")
        assert repeated.returncode == 0 and request("/api/health")["runtime"] == health["runtime"]
        report["repeat_start_same_process"] = True
        for action in ("run", "stop"):
            result = powershell(
                ROOT / f"scripts/{action}.ps1", source_env, log, *(["-NoBrowser"] if action == "run" else [])
            )
            assert result.returncode != 0, "Other-folder launcher incorrectly took ownership"
            assert request("/api/health")["runtime"] == health["runtime"]
        report["other_folder_start_stop_refused"] = True
        if args.resume_project:
            project = request(f"/api/projects/{args.resume_project}")
            assert project["spec"]["backend"] == "demo" and project["spec"]["idempotency_key"].startswith(
                "relocation-"
            )
            assert project["status"] == "COMPLETED"
            report["resumed_existing_completed_sample"] = True
        else:
            request("/api/settings", {"speech": "windows"}, "PATCH")
            project = request(
                "/api/projects",
                {
                    "idea": "A lighthouse keeper receives a quiet signal from a passing ship.",
                    "target_seconds": 5,
                    "orientation": "landscape",
                    "backend": "demo",
                    "idempotency_key": f"relocation-{token}",
                },
            )
        pid = project["id"]
        states = []
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            project = request(f"/api/projects/{pid}")
            if not states or states[-1] != project["status"]:
                states.append(project["status"])
            if project["status"] in {"COMPLETED", "FAILED"}:
                break
            time.sleep(0.25)
        assert project["status"] == "COMPLETED", project["jobs"][0].get("error")
        assert len(project["canon"]) == 1
        movie = next(a for a in project["assets"] if a["role"] == "export")
        assert movie["metadata"]["is_mock"] and movie["metadata"]["dialogue_present"]
        payload = request(f"/api/assets/{movie['id']}/content")
        assert hashlib.sha256(payload).hexdigest() == movie["sha256"]
        output = target / f"data/relocation-download-{token}.mp4"
        output.write_bytes(payload)
        media = probe_media(target / "tools/ffmpeg/ffprobe.exe", output)
        video = next(s for s in media["streams"] if s["codec_type"] == "video")
        assert (video["width"], video["height"], video["codec_name"]) == (640, 360, "h264")
        assert abs(float(media["format"]["duration"]) - 5) < 0.15
        assert any(s["codec_type"] == "audio" and s["codec_name"] == "aac" for s in media["streams"])
        subprocess.run(
            [
                str(target / "tools/ffmpeg/ffmpeg.exe"),
                "-v",
                "error",
                "-threads",
                "2",
                "-i",
                str(output),
                "-f",
                "null",
                "-",
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        voice = next(a for a in project["assets"] if a["role"] == "voice-1")
        assert request(f"/api/assets/{voice['id']}/content")[:4] == b"RIFF"
        with zipfile.ZipFile(io.BytesIO(request("/api/backup"))) as backup:
            assert backup.testzip() is None
        report.update(
            project_id=pid,
            states=states,
            movie_sha256=movie["sha256"],
            movie_metadata=movie["metadata"],
            ffprobe=media,
            windows_speech_downloaded=True,
            backup_verified=True,
        )
    except Exception:
        report.update(status="FAILED", error=traceback.format_exc())
        raise
    else:
        report["status"] = "PASS"
    finally:
        if running:
            result = powershell(target / "scripts/stop.ps1", env, log)
            report["relocated_stop_exit"] = result.returncode
        restarted = powershell(ROOT / "scripts/run.ps1", source_env, log, "-NoBrowser")
        report["original_restart_exit"] = restarted.returncode
        cleanup_ok = restarted.returncode == 0 and (not running or report["relocated_stop_exit"] == 0)
        if not cleanup_ok:
            report["status"] = "FAILED"
            report["cleanup_error"] = "A Studio launcher failed during cleanup; inspect the retained log."
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        atomic_json(report_path, report)
        print(report_path)
        if not cleanup_ok:
            raise RuntimeError(report["cleanup_error"])


if __name__ == "__main__":
    main()
