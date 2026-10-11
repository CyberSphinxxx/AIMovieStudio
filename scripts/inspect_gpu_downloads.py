"""Read official metadata only. Never download model weights or install a runtime."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

SOURCES = {
    "DeepBeepMeep/Flux2": ["flux-2-klein-4b_quanto_bf16_int8.safetensors", "flux2_vae.safetensors"],
    "DeepBeepMeep/Z-Image": ["Qwen3/qwen3_quanto_bf16_int8.safetensors"],
    "DeepBeepMeep/Wan2.2": ["wan2.2_text2video_5B_quanto_mbf16_int8.safetensors", "Wan2.2_VAE.safetensors"],
    "DeepBeepMeep/Wan2.1": ["umt5-xxl/models_t5_umt5-xxl-enc-quanto_int8.safetensors"],
}
TOKENIZERS = {
    "DeepBeepMeep/Z-Image": (
        "Qwen3/",
        {
            "config.json",
            "generation_config.json",
            "added_tokens.json",
            "chat_template.jinja",
            "merges.txt",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json",
        },
    ),
    "DeepBeepMeep/Wan2.1": (
        "umt5-xxl/",
        {"special_tokens_map.json", "spiece.model", "tokenizer.json", "tokenizer_config.json"},
    ),
}


def metadata(url):
    with urllib.request.urlopen(url, timeout=45) as response:
        return json.load(response)


def main():
    files = []
    revisions = {}
    for repo, names in SOURCES.items():
        data = metadata(f"https://huggingface.co/api/models/{repo}?blobs=true")
        revisions[repo] = data["sha"]
        siblings = {s["rfilename"]: s for s in data["siblings"]}
        if repo in TOKENIZERS:
            prefix, tokens = TOKENIZERS[repo]
            names = names + [prefix + name for name in sorted(tokens)]
        for name in names:
            item = siblings[name]
            files.append(
                {
                    "repo": repo,
                    "revision": data["sha"],
                    "file": name,
                    "bytes": item["size"],
                    "sha256": item.get("lfs", {}).get("sha256"),
                    "git_blob": item.get("blobId"),
                    "url": f"https://huggingface.co/{repo}/resolve/{data['sha']}/{name}",
                }
            )
    vendor = metadata("https://api.github.com/repos/deepbeepmeep/Wan2GP/commits/main")
    report = {
        "status": "PROPOSAL_ONLY_NOT_APPROVED_NOT_INSTALLED",
        "wan_gp_revision": vendor["sha"],
        "models": {"image": "flux2_klein_4b", "video": "ti2v_2_2"},
        "files": files,
        "revisions": revisions,
        "model_bytes": sum(f["bytes"] for f in files),
        "download_ceiling_gb": 32,
        "disk_growth_ceiling_gb": 40,
        "runtime": "Separate app-owned Python 3.11, PyTorch 2.10 cu130, pinned WanGP. Dependencies not installed or fully resolved yet.",
        "hardware_proof": "NOT TESTED; image gate first, video installation/inference only if memory and disk gates pass. No guaranteed 6GB/16GB fit.",
        "system_changes": "None authorized: no driver, CUDA toolkit, paging, firewall, power or global Python changes.",
        "rights": "Private local use proposal. WanGP Community License 2.0; Flux Klein 4B, Qwen3 4B, Wan2.2 upstream cards Apache-2.0. Preserve all vendor notices; no paid embedding or redistribution authorization.",
    }
    path = Path(__file__).resolve().parents[1] / "ops" / "evidence" / "gpu-download-proposal.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"status": report["status"], "model_bytes": report["model_bytes"], "report": str(path)}, indent=2
        )
    )


if __name__ == "__main__":
    main()
