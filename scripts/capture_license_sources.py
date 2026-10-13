"""Capture small public license/card sources for approved installed models; no weights."""

import hashlib
import json
import urllib.request
from pathlib import Path
from uuid import uuid4

from studio.storage import atomic_json

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 512 * 1024  # Total received bodies, including metadata, for this invocation.


def capture(root=ROOT):
    budget_path = root / "tools/gpu/download-ledger.json"
    reservation = "license-sources:" + str(uuid4())
    if budget_path.exists():
        budget = json.loads(budget_path.read_text())
        if budget["received_bytes"] + sum(budget["reservations"].values()) + LIMIT > 32_000_000_000:
            raise RuntimeError("Approved cumulative GPU download budget cannot cover license sources")
        budget["reservations"][reservation] = LIMIT
        atomic_json(budget_path, budget)
    target = root / "tools/licenses"
    target.mkdir(parents=True, exist_ok=True)
    received, sources = 0, []

    def read(url):
        nonlocal received
        with urllib.request.urlopen(url, timeout=30) as response:
            result = response.read(LIMIT - received)
        received += len(result)
        if received >= LIMIT:
            raise RuntimeError("License-source capture exceeded its 512 KB download ceiling")
        return result

    def save(name, url, body, revision):
        path = target / (revision + "--" + name)
        if path.exists() and path.read_bytes() != body:
            raise RuntimeError("A captured source changed at its pinned revision; original retained")
        if not path.exists():
            path.write_bytes(body)
        sources.append(
            {
                "path": path.relative_to(root).as_posix(),
                "url": url,
                "revision": revision,
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
            }
        )

    proposal = json.loads((root / "ops/evidence/gpu-download-proposal.json").read_text())
    converted_revision = proposal["revisions"]["DeepBeepMeep/Flux2"]
    if isinstance(converted_revision, dict):
        converted_revision = converted_revision["sha"]
    model_sources = [
        ("black-forest-labs/FLUX.2-klein-4B", None),
        ("Qwen/Qwen3-4B", None),
        ("Qwen/Qwen2.5-0.5B-Instruct-GGUF", "9217f5db79a29953eb74d5343926648285ec7e67"),
        ("DeepBeepMeep/Flux2", converted_revision),
    ]
    report = {
        "status": "SOURCE_CAPTURE_ONLY_NOT_CLEARED",
        "sources": sources,
        "models": [],
        "limit_bytes": LIMIT,
    }
    try:
        for repo, revision in model_sources:
            suffix = f"/revision/{revision}" if revision else ""
            info = json.loads(read(f"https://huggingface.co/api/models/{repo}{suffix}?blobs=true"))
            revision = info["sha"]
            files = {f["rfilename"] for f in info["siblings"]}
            license_file = next(
                (name for name in ["LICENSE", "LICENSE.md", "LICENSE.txt"] if name in files), None
            )
            model = {
                "repo": repo,
                "revision": revision,
                "declaration": info.get("cardData", {}).get("license"),
                "upstream_notice_found": bool(license_file),
            }
            report["models"].append(model)
            for name in ["README.md", license_file]:
                if name in files:
                    url = f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
                    save(repo.replace("/", "--") + "--" + name, url, read(url), revision)
            if repo == "black-forest-labs/FLUX.2-klein-4B":
                vae = next(
                    (
                        f
                        for f in info["siblings"]
                        if f["rfilename"] == "vae/diffusion_pytorch_model.safetensors"
                    ),
                    None,
                )
                model["upstream_vae_sha256"] = vae.get("lfs", {}).get("sha256") if vae else None
                installed = next(f for f in proposal["files"] if f["file"] == "flux2_vae.safetensors")
                model["installed_vae_sha256"] = installed["sha256"]
                model["vae_hash_matches_upstream"] = bool(
                    model["upstream_vae_sha256"] and model["upstream_vae_sha256"] == installed["sha256"]
                )
        url = "https://raw.githubusercontent.com/ggml-org/llama.cpp/b11558/LICENSE"
        save("llama.cpp--b11558--LICENSE", url, read(url), "b11558")
    except Exception as error:
        report["status"] = "PARTIAL_SOURCE_CAPTURE"
        report["error"] = str(error)[:500]
        raise
    finally:
        report["received_bytes"] = received
        atomic_json(root / "ops/evidence/model-license-sources.json", report)
        if budget_path.exists():
            budget = json.loads(budget_path.read_text())
            budget["reservations"].pop(reservation, None)
            budget["received_bytes"] += received
            budget.setdefault("license_source_captures", {})[reservation] = {
                "received_bytes": received,
                "status": report["status"],
            }
            atomic_json(budget_path, budget)
    print(json.dumps({"status": report["status"], "received_bytes": received, "sources": len(sources)}))


if __name__ == "__main__":
    capture()
