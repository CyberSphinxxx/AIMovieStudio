"""Select and checksum-download locked Windows artifacts before offline installation."""

from __future__ import annotations

import concurrent.futures
import json
import re
import urllib.parse
import urllib.request

from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import parse_wheel_filename
from packaging.version import Version

from scripts.setup_gpu import ROOT, TARGET, fetch, reserve
from studio.storage import atomic_json

TAGS = list(cpython_tags((3, 11), abis=["cp311"], platforms=["win_amd64"]))
TAGS += list(compatible_tags((3, 11), interpreter="cp311", platforms=["win_amd64"]))
RANKS = {tag: i for i, tag in enumerate(TAGS)}
PURE_BUILD = {"moviepy", "antlr4-python3-runtime", "docopt"}


def read(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def choose(requirement):
    name, version = requirement.split("==")
    if name in {"torch", "torchvision", "torchaudio"}:
        source = read(f"https://download.pytorch.org/whl/cu130/{name}/").decode()
        candidates = []
        for raw in re.findall(r'href="([^"]+)"', source):
            url, _, fragment = raw.partition("#")
            filename = urllib.parse.unquote(urllib.parse.urlparse(url).path.split("/")[-1])
            if not filename.endswith(".whl"):
                continue
            _, candidate_version, _, tags = parse_wheel_filename(filename)
            rank = min((RANKS[t] for t in tags if t in RANKS), default=100000)
            if candidate_version == Version(version) and rank < 100000:
                candidates.append((rank, filename, url, fragment.removeprefix("sha256=")))
        if not candidates:
            raise RuntimeError(f"No official Windows artifact for {requirement}")
        _, filename, url, sha = sorted(candidates)[0]
        if not url.startswith("https://"):
            url = urllib.parse.urljoin(f"https://download.pytorch.org/whl/cu130/{name}/", url)
        print(f"Inspecting official runtime artifact: {filename}", flush=True)
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Range": "bytes=0-0", "User-Agent": "pip/26.2.1"}), timeout=60
        ) as response:
            size = int(response.headers.get("Content-Range", "").split("/")[-1] or response.headers["Content-Length"])
    else:
        metadata = json.loads(read(f"https://pypi.org/pypi/{name}/{version}/json"))
        options = []
        for item in metadata["urls"]:
            if item["filename"].endswith(".whl"):
                _, _, _, tags = parse_wheel_filename(item["filename"])
                rank = min((RANKS[t] for t in tags if t in RANKS), default=100000)
                if rank < 100000:
                    options.append((rank, item))
            elif item["packagetype"] == "sdist" and name in PURE_BUILD:
                options.append((99999, item))
        if not options:
            raise RuntimeError(
                f"No prebuilt Windows wheel for {requirement}; system compilers are not approved"
            )
        _, item = sorted(options, key=lambda p: p[0])[0]
        filename, url, sha, size = item["filename"], item["url"], item["digests"]["sha256"], item["size"]
    return {"requirement": requirement, "filename": filename, "url": url, "sha256": sha, "bytes": size}


def main():
    lock = ROOT / "ops/evidence/wan-runtime-lock.txt"
    requirements = [
        line.strip() for line in lock.read_text().splitlines() if re.fullmatch(r"[\w.-]+==[^\s]+", line)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        artifacts = list(pool.map(choose, requirements))
    total = sum(a["bytes"] for a in artifacts)
    if total > 7_000_000_000:
        raise RuntimeError(
            "Runtime artifacts exceed 7 GB; remaining 1 GB reserved for metadata/build overhead"
        )
    atomic_json(
        ROOT / "ops/evidence/wan-runtime-artifacts.json",
        {"status": "SELECTED_NOT_INSTALLED", "bytes": total, "artifacts": artifacts},
    )
    print(
        f"Selected {len(artifacts)} pinned artifacts, {total:,} bytes; downloading with checksum and budget gates.",
        flush=True,
    )
    reserve("runtime-and-resolution", 8_000_000_000)
    for artifact in artifacts:
        fetch(
            artifact["url"],
            TARGET / "wheelhouse" / artifact["filename"],
            artifact["bytes"],
            artifact["sha256"],
            reservation="runtime-and-resolution",
        )


if __name__ == "__main__":
    main()
