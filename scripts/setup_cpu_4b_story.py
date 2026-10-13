"""Prepare only the separately approved4B weights/notices using the existing CPU runtime."""

import argparse
import json
import re
from pathlib import Path

from scripts.setup_cpu_story import fetch
from studio.storage import atomic_json

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved", action="store_true")
    args = parser.parse_args(argv)
    if not args.approved:
        parser.error("Separate human approval required: docs/CPU_4B_STORY_INSTALL_PROPOSAL.md")
    target = ROOT / "tools/story"
    if not (target / "llama-server.exe").is_file():
        raise RuntimeError("Existing CPU runtime required; this installation adds no executable")
    proposal = json.loads((ROOT / "ops/evidence/cpu-4b-story-download-proposal.json").read_text())
    files = proposal["files"]
    for item in files:
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,100}", item["target"]):
            raise ValueError("CPU artifact name must stay inside the reviewed model folder")
    if (
        sum(f["bytes"] for f in files) + proposal["preapproval_metadata_received_bytes"]
        > proposal["network_cap_bytes"]
    ):
        raise RuntimeError("Proposed artifact set exceeds approved network budget")
    ledger = target / "qwen4b-download-ledger.json"
    if not ledger.exists():
        atomic_json(
            ledger,
            {
                "scope": "CPU_4B_STORY_INSTALL_PROPOSAL.md",
                "received_bytes": proposal["preapproval_metadata_received_bytes"],
                "completed": {},
            },
        )
    names = [f["target"] for f in files]
    names += [name + ".partial" for name in names] + [ledger.name]
    for item in files:
        used = sum((target / name).stat().st_size for name in names if (target / name).is_file())
        partial = target / (item["target"] + ".partial")
        existing = target / item["target"]
        remaining = (
            0
            if existing.exists()
            else max(0, item["bytes"] - (partial.stat().st_size if partial.exists() else 0))
        )
        if used + remaining > proposal["disk_cap_bytes"]:
            raise RuntimeError("CPU artifacts exceed approved additional disk budget")
        fetch(item["url"], existing, item["bytes"], item["sha256"], ledger, proposal["network_cap_bytes"])
    print(
        "4B files verified; writing quality/RAM fit are still unproven. No default or system setting changed."
    )


if __name__ == "__main__":
    main()
