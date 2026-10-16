import io
import struct
from pathlib import Path

import pytest

from scripts.inspect_encoder_header import inspect_header


def number(code, value):
    return struct.pack("<" + code, value)


def text(value):
    raw = value.encode()
    return number("Q", len(raw)) + raw


def fixture(path, *, names=("token_embd.weight",), dimensions=2, offset=0, metadata=None):
    metadata = metadata or [("general.architecture", 8, text("qwen3"))]
    raw = b"GGUF" + number("I", 3) + number("Q", len(names)) + number("Q", len(metadata))
    for key, kind, value in metadata:
        raw += text(key) + number("I", kind) + value
    for name in names:
        raw += text(name) + number("I", dimensions)
        raw += number("Q", 4) * dimensions + number("I", 0) + number("Q", offset)
    path.write_bytes(raw + b"\0" * ((-len(raw)) % 32) + b"PAYLOAD_MUST_NOT_BE_READ")
    return len(raw)


def test_inventory_never_reads_payload_or_imports_runtime(tmp_path, monkeypatch):
    path = tmp_path / "sample.gguf"
    end = fixture(path)
    stream = io.BytesIO(path.read_bytes())

    class HeaderOnly(io.BytesIO):
        def read(self, count=-1):
            assert count >= 0 and self.tell() + count <= end
            return super().read(count)

    monkeypatch.setattr(Path, "open", lambda *_args, **_kw: HeaderOnly(stream.getvalue()))
    result = inspect_header(path)
    assert result["header_bytes_read"] == end
    assert result["metadata"] == {"general.architecture": "qwen3"}
    assert result["tensors"]["token_embd.weight"]["gguf_dimensions"] == [4, 4]
    assert "payload unread" in result["scope"]


@pytest.mark.parametrize(
    "names,dimensions,offset", [(("same", "same"), 2, 0), (("x",), 5, 0), (("x",), 2, 1), (("x",), 2, 4096)]
)
def test_invalid_tensor_directory_rejected(tmp_path, names, dimensions, offset):
    path = tmp_path / "sample.gguf"
    fixture(path, names=names, dimensions=dimensions, offset=offset)
    with pytest.raises(ValueError):
        inspect_header(path)


@pytest.mark.parametrize(
    "raw",
    [
        b"GGUF",
        b"GGUF" + number("I", 2),
        b"FUGG" + number("I", 3),
        b"GGUF" + number("I", 3) + number("Q", 2**63) + number("Q", 0),
    ],
)
def test_truncation_endianness_versions_and_huge_counts_rejected(tmp_path, raw):
    path = tmp_path / "sample.gguf"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        inspect_header(path)


def test_metadata_budget_and_duplicate_keys_rejected(tmp_path):
    path = tmp_path / "sample.gguf"
    for metadata in [
        [("array", 9, number("I", 8) + number("Q", 2**63))],
        [("key", 4, number("I", 1)), ("key", 4, number("I", 2))],
        [("general.alignment", 4, number("I", 3))],
        [("key", 99, b"")],
    ]:
        fixture(path, metadata=metadata)
        with pytest.raises(ValueError):
            inspect_header(path)


def test_token_arrays_are_discarded_and_explicit_output_preserved(tmp_path):
    path = tmp_path / "sample.gguf"
    fixture(
        path,
        names=("token_embd.weight", "output.weight"),
        metadata=[("tokenizer.ggml.tokens", 9, number("I", 8) + number("Q", 2) + text("a") + text("b"))],
    )
    result = inspect_header(path)
    assert result["metadata"] == {}
    assert "output.weight" in result["tensors"]
