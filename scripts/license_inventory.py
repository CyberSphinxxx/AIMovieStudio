"""Offline inventory of installed declarations/notices; never a distribution clearance."""

import json
import re
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import distributions
from pathlib import Path

from studio.storage import atomic_json, digest

ROOT = Path(__file__).resolve().parents[1]
NOTICE = re.compile(r"^(licen[cs]e|copying|notice|copyright)([._-].*)?$", re.I)
MAX_NOTICE = 2 * 1024 * 1024


def notice_record(path: Path, boundary: Path, root: Path):
    resolved = path.resolve()
    if not resolved.is_relative_to(boundary.resolve()) or not resolved.is_relative_to(root.resolve()):
        raise ValueError("Notice path escapes its installed component")
    if not resolved.is_file() or resolved.stat().st_size > MAX_NOTICE:
        raise ValueError("Notice is missing or exceeds the 2 MB inventory limit")
    return {
        "path": resolved.relative_to(root.resolve()).as_posix(),
        "sha256": digest(resolved),
        "bytes": resolved.stat().st_size,
    }


def python_inventory(root: Path, relative: str, scope: str):
    directory = root / relative
    if not directory.is_dir():
        return [], [f"{scope}: environment not installed"]
    if not directory.resolve().is_relative_to(root.resolve()):
        return [], [f"{scope}: environment redirected outside workspace"]
    items, findings = [], []
    # Reading distribution metadata never imports any dependency or CUDA DLL.
    for dist in distributions(path=[str(directory)]):
        name = dist.metadata.get("Name", "UNKNOWN")
        expression = dist.metadata.get("License-Expression")
        legacy = dist.metadata.get("License")
        classifiers = [v for v in dist.metadata.get_all("Classifier", []) if v.startswith("License ::")]
        declared = (
            expression
            or (legacy if legacy and len(legacy) <= 200 else None)
            or "; ".join(classifiers)
            or None
        )
        notices, problems = [], []
        for file in dist.files or []:
            if NOTICE.match(Path(str(file)).name):
                try:
                    notices.append(notice_record(Path(dist.locate_file(file)), directory, root))
                except (OSError, ValueError):
                    problems.append(f"{scope}:{name}: unavailable or redirected notice")
        if not declared:
            problems.append(f"{scope}:{name}: no compact license declaration")
        if not notices:
            problems.append(f"{scope}:{name}: no installed notice file found")
        items.append(
            {
                "scope": scope,
                "name": name,
                "version": dist.version,
                "declaration": declared,
                "declaration_source": "License-Expression" if expression else "legacy metadata/classifiers",
                "notices": sorted(notices, key=lambda n: n["path"]),
                "findings": problems,
            }
        )
        findings.extend(problems)
    return sorted(items, key=lambda x: (x["name"].lower(), x["version"])), findings


def node_inventory(root: Path):
    lock_path = root / "client/package-lock.json"
    if not lock_path.is_file():
        return [], ["frontend: package lock is missing"]
    if not lock_path.resolve().is_relative_to(root.resolve()):
        return [], ["frontend: package lock redirected outside workspace"]
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    items, findings = [], []
    for relative, locked in sorted(lock["packages"].items()):
        if not relative:
            continue
        directory = (root / "client" / relative).resolve()
        if not directory.is_relative_to(root.resolve()) or not directory.is_relative_to(
            (root / "client/node_modules").resolve()
        ):
            findings.append("frontend: rejected redirected or external package location")
            continue
        manifest = directory / "package.json"
        if not manifest.is_file():
            # Optional packages for other operating systems may be absent.
            findings.append(f"frontend:{relative}: not installed (optional={bool(locked.get('optional'))})")
            continue
        if not manifest.resolve().is_relative_to(directory):
            findings.append(f"frontend:{relative}: rejected redirected package metadata")
            continue
        info = json.loads(manifest.read_text(encoding="utf-8"))
        name, version = info.get("name", relative), info.get("version", "UNKNOWN")
        declared = info.get("license")
        if isinstance(declared, dict):
            declared = declared.get("type")
        if not isinstance(declared, str) or len(declared) > 200:
            declared = None
        notices, problems = [], []
        for file in directory.iterdir():
            if NOTICE.match(file.name):
                try:
                    notices.append(notice_record(file, directory, root))
                except (OSError, ValueError):
                    problems.append(f"frontend:{name}: unavailable or redirected notice")
        if not declared:
            problems.append(f"frontend:{name}: no compact license declaration")
        if not notices:
            problems.append(f"frontend:{name}: no installed notice file found")
        if version != locked.get("version"):
            problems.append(f"frontend:{name}: installed version differs from lock")
        items.append(
            {
                "scope": "frontend",
                "name": name,
                "version": version,
                "development": bool(locked.get("dev")),
                "declaration": declared,
                "declaration_source": "installed package.json",
                "notices": notices,
                "findings": problems,
            }
        )
        findings.extend(problems)
    return items, findings


def inventory(root: Path):
    components, findings = [], []
    for relative, scope in [
        (".venv/Lib/site-packages", "main-python"),
        ("tools/wan-gp/.venv/Lib/site-packages", "optional-gpu-python"),
    ]:
        items, problems = python_inventory(root, relative, scope)
        components.extend(items)
        findings.extend(problems)
    items, problems = node_inventory(root)
    components.extend(items)
    findings.extend(problems)
    notice_files = [
        root / "tools/ffmpeg/LICENSE",
        root / "tools/wan-gp/LICENSE.txt",
        root / "tools/story/qwen1.5b-LICENSE",
    ]
    # Optional approved writer: inventory only when present, no download or clearance.
    notice_files.extend(
        path
        for path in [
            root / "tools/story/qwen4b-LICENSE",
            root / "tools/story/qwen4b-UPSTREAM-CARD.md",
            root / "tools/story/qwen4b-CONVERTER-CARD.md",
        ]
        if path.is_file()
    )
    notice_files.extend(
        [
            root / "tools/wan-gp/mmgp/LICENSE.md",
            root / "tools/gpu/python/cpython-3.11.14-windows-x86_64-none/LICENSE.txt",
        ]
    )
    standalone = []
    index = root / "ops/evidence/model-license-sources.json"
    if index.is_file():
        model_sources = json.loads(index.read_text(encoding="utf-8"))
        for source in model_sources["sources"]:
            path = root / source["path"]
            try:
                record = notice_record(path, root / "tools/licenses", root)
                if record["sha256"] != source["sha256"]:
                    raise ValueError("Captured source checksum changed")
                standalone.append(record)
            except (OSError, ValueError):
                findings.append("model sources: captured notice unavailable, redirected or changed")
        for model in model_sources.get("models", []):
            if not model.get("upstream_notice_found"):
                findings.append(f"model:{model['repo']}: no separate upstream license file found")
            if model.get("vae_hash_matches_upstream") is False:
                findings.append(
                    "model:converted VAE differs from current upstream blob; exact provenance mapping remains unverified"
                )
    for path in notice_files:
        try:
            standalone.append(notice_record(path, path.parent, root))
        except (OSError, ValueError):
            findings.append(f"standalone:{path.relative_to(root).as_posix()}: notice unavailable")
    findings.extend(
        [
            "Application source license has not been selected; no redistribution clearance.",
            "FFmpeg linked-library sources/notices and codec obligations require separate review.",
            "llama.cpp release DLLs, portable Python/uv and CUDA binary notices require separate review.",
            "All model/voice/media rights remain separate from Python/npm metadata.",
            "Converted weight provenance and missing model-specific notices require review even when upstream declarations are permissive.",
            "WanGP Community License 2.0 restrictions and vendor security findings remain unresolved release gates.",
        ]
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "INVENTORY_ONLY_NOT_CLEARED",
        "scope": "Installed workstation packages, including development tools; not a complete binary SBOM",
        "no_network": True,
        "native_dependencies_imported": False,
        "counts": dict(Counter(c["scope"] for c in components)),
        "components": components,
        "standalone_notices": standalone,
        "findings": findings,
    }


def main():
    report = inventory(ROOT)
    path = ROOT / "ops/evidence/installed-license-inventory.json"
    atomic_json(path, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "counts": report["counts"],
                "findings": len(report["findings"]),
                "output": str(path),
            }
        )
    )


if __name__ == "__main__":
    main()
