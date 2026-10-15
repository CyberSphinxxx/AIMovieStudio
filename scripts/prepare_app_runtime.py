"""Prepare a private relocatable CPU application runtime; never install globally."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 100_000_000
DISK_RESERVE = 2_000_000_000
MAX_TREE_BYTES = 500_000_000


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, data):
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    with temporary.open("x", encoding="utf-8") as output:
        json.dump(data, output, indent=2)
        output.flush()
        os.fsync(output.fileno())
    for attempt in range(3):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as error:
            if os.name != "nt" or getattr(error, "winerror", None) not in {5, 32, 33} or attempt == 2:
                raise
            time.sleep(0.05 * (attempt + 1))


def safe_relative(value):
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or any(p in {"", ".", ".."} for p in value.split("/"))
    ):
        raise ValueError("Runtime manifest path is unsafe")
    return path


def plain_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Runtime inputs cannot be symbolic links or reparse points")


def load_manifest(path):
    if path.stat().st_size > 2_000_000:
        raise ValueError("Runtime manifest is too large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["schema"] != 1 or data["platform"] != "win_amd64" or data["python_version"] != "3.11.14":
        raise ValueError("Unsupported private runtime manifest")
    rows = data["base_files"] + data["artifacts"]
    if not 1 <= len(rows) <= 10000:
        raise ValueError("Runtime manifest file count is invalid")
    for row in rows:
        if (
            type(row["bytes"]) is not int
            or not 0 <= row["bytes"] <= MAX_TREE_BYTES
            or not re.fullmatch(r"[a-f0-9]{64}", row["sha256"])
        ):
            raise ValueError("Runtime files require bounded sizes and SHA256")
    paths = [safe_relative(row["path"]).as_posix() for row in data["base_files"]]
    if len(set(p.lower() for p in paths)) != len(paths):
        raise ValueError("Duplicate runtime path")
    names = []
    filenames = []
    for row in data["artifacts"]:
        name = safe_relative(row["filename"])
        url = urllib.parse.urlsplit(row["url"])
        if (
            len(name.parts) != 1
            or not name.name.endswith(".whl")
            or url.scheme != "https"
            or url.hostname != "files.pythonhosted.org"
            or url.username
            or url.password
            or url.fragment
            or url.query
        ):
            raise ValueError("Runtime wheels must use their pinned official file host")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", row["name"]) or not re.fullmatch(
            r"[0-9][a-zA-Z0-9.!+_-]*", row["version"]
        ):
            raise ValueError("Invalid pinned package requirement")
        names.append(row["name"].lower().replace("_", "-"))
        filenames.append(row["filename"].lower())
    if len(names) != len(set(names)):
        raise ValueError("Duplicate runtime package")
    if len(filenames) != len(set(filenames)):
        raise ValueError("Duplicate runtime wheel filename")
    if sum(row["bytes"] for row in data["artifacts"]) != data["wheel_bytes"] or data["wheel_bytes"] > LIMIT:
        raise ValueError("Runtime wheels exceed the small-download budget")
    if (
        sum(row["bytes"] for row in data["base_files"]) != data["base_bytes"]
        or data["base_bytes"] > MAX_TREE_BYTES
    ):
        raise ValueError("Runtime base exceeds its disk bound")
    if not {"python.exe", "python311.dll", "LICENSE.txt"} <= set(paths):
        raise ValueError("Runtime executable or license is missing")
    return data


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urllib.parse.urlsplit(newurl)
        if url.scheme != "https" or url.hostname != "files.pythonhosted.org" or url.username or url.password:
            raise ValueError("Runtime download redirected away from its official host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(row, cache, ledger, download, *, opener=None):
    destination = cache / row["filename"]
    if destination.exists():
        plain_file(destination)
        if destination.stat().st_size != row["bytes"] or digest(destination) != row["sha256"]:
            raise RuntimeError("Cached wheel differs from its checksum; inspect it before retrying")
        return destination
    if not download:
        raise RuntimeError(f"Offline wheel missing: {row['filename']}. Prepare once with --download.")
    if ledger["allocated_bytes"] + row["bytes"] > LIMIT:
        raise RuntimeError("Private runtime cumulative 100 MB download budget exhausted")
    # Reserve the entire attempt before opening the connection. Interrupted
    # downloads retain this conservative charge, including a hard process kill.
    ledger["allocated_bytes"] += row["bytes"]
    atomic_json(cache / "download-ledger.json", ledger)
    temporary = cache / f".{row['filename']}.{uuid4().hex}.partial"
    opener = opener or urllib.request.build_opener(OfficialRedirect())
    started, received = time.monotonic(), 0
    try:
        with opener.open(row["url"], timeout=30) as response:
            if int(response.headers.get("Content-Length", -1)) != row["bytes"]:
                raise RuntimeError("Runtime wheel length differs from pinned metadata")
            with temporary.open("xb") as output:
                while received < row["bytes"]:
                    if time.monotonic() - started > 180:
                        raise RuntimeError("Runtime wheel download timed out")
                    if shutil.disk_usage(cache).free < DISK_RESERVE:
                        raise RuntimeError("Runtime setup stopped at the disk reserve")
                    chunk = response.read(min(65536, row["bytes"] - received))
                    if not chunk:
                        raise RuntimeError("Runtime wheel download was interrupted")
                    ledger["received_bytes"] += len(chunk)
                    received += len(chunk)
                    output.write(chunk)
                    # Durable accounting even if a later read/hash/install fails.
                    atomic_json(cache / "download-ledger.json", ledger)
                output.flush()
                os.fsync(output.fileno())
        if digest(temporary) != row["sha256"]:
            raise RuntimeError("Runtime wheel checksum failed; partial retained for inspection")
        os.link(temporary, destination)  # Refuses concurrent replacement.
        temporary.unlink()
        return destination
    finally:
        atomic_json(cache / "download-ledger.json", ledger)


def prepare(root, source, download=False):
    root, source = root.resolve(), source.resolve()
    tools = root / "tools"
    tools.mkdir(exist_ok=True)
    cache, target = tools / "app-runtime-cache", tools / "app-runtime"
    if tools.resolve() != tools or cache.resolve() != cache or target.resolve() != target:
        raise ValueError("Runtime output must stay inside the application tools folder")
    cache.mkdir(exist_ok=True)
    lock = cache / "setup.lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise RuntimeError(
            "Runtime setup is already running or was interrupted. Review tools/app-runtime-cache/setup.lock before retrying."
        ) from error
    try:
        if target.exists():
            raise RuntimeError("App runtime already exists; originals are never overwritten")
        manifest_path = root / "contracts/app-runtime-windows.json"
        manifest = load_manifest(manifest_path)
        normalized_requirements = (root / "requirements.txt").read_text(encoding="utf-8").encode("utf-8")
        if hashlib.sha256(normalized_requirements).hexdigest() != manifest["requirements_sha256"]:
            raise RuntimeError("Application requirements changed; review the pinned runtime manifest")
        if shutil.disk_usage(tools).free < DISK_RESERVE + MAX_TREE_BYTES:
            raise RuntimeError("Runtime setup needs its 2 GB disk reserve plus 500 MB working space")
        consumed = sum(p.stat().st_size for p in cache.rglob("*") if p.is_file())
        if consumed > MAX_TREE_BYTES:
            raise RuntimeError("Runtime setup cache exceeded 500 MB; review retained interrupted files")
        stage = cache / f"runtime-{uuid4().hex}"
        stage.mkdir()
        for row in manifest["base_files"]:
            relative = safe_relative(row["path"])
            original = source / relative
            if not original.resolve().is_relative_to(source):
                raise ValueError("Runtime source escaped its selected installation")
            plain_file(original)
            if original.stat().st_size != row["bytes"] or digest(original) != row["sha256"]:
                raise RuntimeError(f"Installed Python differs from reviewed base: {relative}")
            output = stage / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, output)
            if digest(output) != row["sha256"]:
                raise RuntimeError("Runtime copy failed checksum verification")
        wheelhouse = cache / "wheels"
        if wheelhouse.resolve() != wheelhouse:
            raise ValueError("Runtime wheel cache cannot be a redirected folder")
        wheelhouse.mkdir(exist_ok=True)
        # Accounting lives beside the wheels and is retained independently of staging.
        wheel_ledger = wheelhouse / "download-ledger.json"
        ledger = (
            json.loads(wheel_ledger.read_text())
            if wheel_ledger.exists()
            else {"received_bytes": 0, "allocated_bytes": 0}
        )
        if (
            any(type(ledger.get(key)) is not int for key in ("received_bytes", "allocated_bytes"))
            or not 0 <= ledger["received_bytes"] <= ledger["allocated_bytes"] <= LIMIT
        ):
            raise RuntimeError("Runtime download ledger is invalid")
        for row in manifest["artifacts"]:
            print(f"Preparing {row['name']} {row['version']}", flush=True)
            fetch(row, wheelhouse, ledger, download)
        requirements = cache / "requirements-locked.txt"
        requirements.write_text(
            "\n".join(
                f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}" for r in manifest["artifacts"]
            )
            + "\n",
            encoding="utf-8",
        )
        executable = stage / "python.exe"
        install_env = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith(("PYTHON", "PIP_"))
            and key.upper() not in {"VIRTUAL_ENV", "CONDA_PREFIX"}
        }
        install_env.update(PIP_CONFIG_FILE=os.devnull, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        pip = [str(source / "python.exe"), "-I", "-B", "-m", "pip", "--isolated", "--python", str(executable)]
        subprocess.run(
            pip
            + [
                "install",
                "--target",
                str(stage / "Lib/site-packages"),
                "--no-index",
                "--find-links",
                str(wheelhouse),
                "--require-hashes",
                "--only-binary=:all:",
                "--no-compile",
                "--no-cache-dir",
                "--disable-pip-version-check",
                "-r",
                str(requirements),
            ],
            check=True,
            timeout=180,
            env=install_env,
        )
        subprocess.run(pip + ["check"], check=True, timeout=30, env=install_env)
        versions = {row["name"]: row["version"] for row in manifest["artifacts"]}
        script = "import sys,json,sqlite3; import fastapi,uvicorn,httpx,PIL,imageio_ffmpeg; from importlib.metadata import version; expected=json.loads(sys.argv[1]); assert sys.version_info[:3]==(3,11,14); assert all(version(n)==v for n,v in expected.items()); assert sqlite3.connect(':memory:').execute('select 1').fetchone()==(1,); print(json.dumps({'python':sys.version.split()[0],'prefix':sys.prefix,'packages':expected}))"
        checked = subprocess.run(
            [str(executable), "-I", "-B", "-c", script, json.dumps(versions)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
            env=install_env,
        )
        receipt = {
            "schema": 1,
            "status": "READY",
            "python_version": manifest["python_version"],
            "manifest_sha256": digest(manifest_path),
            "packages": versions,
            "validation": json.loads(checked.stdout),
            "download_received_bytes": ledger["received_bytes"],
            "private_only": True,
            "native_generation_verified": False,
        }
        # Prefix in the staging validation is evidence, never a runtime locator.
        atomic_json(stage / "studio-runtime.json", receipt)
        stage.rename(target)
        print(f"Private application runtime ready: {target}")
        return receipt
    finally:
        lock.rmdir()  # Only our newly created empty setup lock, never originals.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python-root", type=Path, default=ROOT / "tools/gpu/python/cpython-3.11.14-windows-x86_64-none"
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Fetch pinned small wheels; 100 MB cumulative ceiling, no models",
    )
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This reviewed private runtime is for 64-bit Windows only")
    prepare(ROOT, args.python_root, args.download)


if __name__ == "__main__":
    main()
