"""Bounded offline GGUF inventory: no tensor payload, runtime imports or inference.

This diagnostic deliberately supports only little-endian GGUF v3. It does not
validate tensor contents or establish that an inference engine can load them.
Format: https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from uuid import uuid4

from scripts.encoder_experiment import FILENAME, ROOT, SIZE
from studio.storage import atomic_json

MAX_HEADER = 16 * 1024 * 1024
MAX_ITEMS = 1_000_000
SCALARS = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
KEEP = {"general.architecture", "general.alignment", "qwen3.embedding_length", "qwen3.block_count"}


def inspect_header(path: Path) -> dict:
    with path.open("rb") as source:
        header_hash = hashlib.sha256()
        remaining = MAX_ITEMS

        def read(count: int) -> bytes:
            if count < 0 or source.tell() + count > MAX_HEADER:
                raise ValueError("GGUF header exceeds the bounded inspection limit")
            data = source.read(count)
            if len(data) != count:
                raise ValueError("Truncated GGUF header")
            header_hash.update(data)
            return data

        def scalar(code: str):
            return struct.unpack("<" + code, read(struct.calcsize("<" + code)))[0]

        def string(maximum: int = 1_048_576) -> str:
            length = scalar("Q")
            if length > maximum:
                raise ValueError("GGUF string exceeds the bounded inspection limit")
            return read(length).decode("utf-8")

        def value(kind: int, depth: int = 0):
            nonlocal remaining
            remaining -= 1
            if remaining < 0 or depth > 4:
                raise ValueError("GGUF metadata exceeds the bounded inspection limit")
            if kind in SCALARS:
                return scalar(SCALARS[kind])
            if kind == 8:
                return string()
            if kind == 9:
                element, count = scalar("I"), scalar("Q")
                if count > remaining:
                    raise ValueError("GGUF metadata exceeds the bounded inspection limit")
                for _ in range(count):
                    value(element, depth + 1)
                return {"array_length": count, "element_type": element}
            raise ValueError("Unsupported GGUF metadata type")

        if read(4) != b"GGUF" or scalar("I") != 3:
            raise ValueError("Only little-endian GGUF v3 inspection is supported")
        tensor_count, metadata_count = scalar("Q"), scalar("Q")
        if not 0 < tensor_count <= 100_000 or metadata_count > 100_000:
            raise ValueError("GGUF directory exceeds the bounded inspection limit")
        metadata, seen = {}, set()
        for _ in range(metadata_count):
            key = string(65_535)
            if key in seen:
                raise ValueError("Duplicate GGUF metadata key")
            seen.add(key)
            item = value(scalar("I"))
            if key in KEEP:
                metadata[key] = item
        alignment = metadata.get("general.alignment", 32)
        if type(alignment) is not int or not 0 < alignment <= 65_536 or alignment & (alignment - 1):
            raise ValueError("Invalid GGUF alignment")
        tensors = {}
        for _ in range(tensor_count):
            name, dimensions = string(64), scalar("I")
            if not name or name in tensors or not 0 < dimensions <= 4:
                raise ValueError("Invalid or duplicate GGUF tensor entry")
            shape = [scalar("Q") for _ in range(dimensions)]
            if any(not 0 < dimension <= 2**32 for dimension in shape):
                raise ValueError("Invalid GGUF tensor dimensions")
            kind, offset = scalar("I"), scalar("Q")
            if offset % alignment:
                raise ValueError("Invalid GGUF tensor alignment")
            tensors[name] = {"gguf_dimensions": shape, "type": kind, "offset": offset}
        header_bytes = source.tell()
        data_start = (header_bytes + alignment - 1) // alignment * alignment
        size = source.seek(0, 2)
        if any(data_start + item["offset"] >= size for item in tensors.values()):
            raise ValueError("GGUF tensor offset is outside the file")
        return {
            "scope": "Header and tensor directory only; payload unread, contents/load/fit/quality unverified",
            "version": 3,
            "file_bytes": size,
            "header_bytes_read": header_bytes,
            "header_sha256": header_hash.hexdigest(),
            "metadata": metadata,
            "tensors": tensors,
        }


def main():
    path = ROOT / "tools/wan-gp/ckpts/Qwen3" / FILENAME
    if path.stat().st_size != SIZE:
        raise ValueError("Installed candidate size differs from its pinned receipt")
    report = inspect_header(path)
    config = json.loads((path.parent / "config.json").read_bytes())
    report.update(
        {
            "status": "OFFLINE_DIRECTORY_INSPECTED_NOT_INFERENCE",
            "candidate": FILENAME,
            "configuration_tie_word_embeddings": config.get("tie_word_embeddings"),
            "has_output_weight": "output.weight" in report["tensors"],
            "has_token_embedding": "token_embd.weight" in report["tensors"],
        }
    )
    output = ROOT / f"ops/evidence/encoder-header-{uuid4().hex}.json"
    atomic_json(output, report)
    print(
        json.dumps({key: item for key, item in report.items() if key != "tensors"} | {"report": str(output)})
    )


if __name__ == "__main__":
    main()
