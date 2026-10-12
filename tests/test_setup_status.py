import json

import pytest

from studio.setup_status import classify, read_runtime_status


def provider(id, installed=True):
    return {"id": id, "available": installed, "is_mock": id == "demo", "message": "Base provider diagnostic."}


@pytest.mark.parametrize(
    "memory,label",
    [
        ({"available": True, "free_gb": 2.44}, "Needs free RAM"),
        ({"available": True, "free_gb": 5}, "Installed · untested"),
        ({"available": False}, "RAM not measured"),
    ],
)
def test_installed_cpu_is_not_reported_as_proven_inference(memory, label):
    p = classify([provider("cpu-1-5b")], memory)[0]
    assert p["status"] == label
    assert p["available"] is True  # discovery only; status expresses readiness/unknown proof
    assert "verified" not in p
    missing = classify([provider("cpu-1-5b", False)], memory)[0]
    assert missing["status"] == "Setup needed"


def test_previous_runtime_block_is_explicit_and_does_not_apply_to_other_install(tmp_path):
    installation = str(tmp_path / "wan")
    evidence = {"code": "OS_POLICY_BLOCKED", "checked_at": 123, "installation": installation}
    p = classify([provider("local-video")], {}, evidence, installation)[0]
    assert p["status"] == "Last check blocked" and p["attention"]
    assert "stopped before inference" in p["message"]
    other = classify([provider("local-video")], {}, evidence, str(tmp_path / "other"))[0]
    assert other["status"] == "Installed" and "last_check_at" not in other
    evidence["code"] = "RUNTIME_DISCOVERED_NOT_INFERENCE"
    p = classify([provider("local-video")], {}, evidence, installation)[0]
    assert "inference remains untested" in p["message"]


def test_absent_malformed_or_unbounded_evidence_never_becomes_success(tmp_path):
    p = tmp_path / "tools/gpu/runtime-status.json"
    p.parent.mkdir(parents=True)
    assert read_runtime_status(tmp_path) is None
    for content in [
        "{bad",
        "[]",
        json.dumps({"code": "PASS", "checked_at": 123, "installation": "fixture"}),
        json.dumps({"code": "FAILED", "checked_at": float("nan"), "installation": "fixture"}),
        " " * 65537,
    ]:
        p.write_text(content)
        assert read_runtime_status(tmp_path) is None
    p.write_text(json.dumps({"code": "OS_POLICY_BLOCKED", "checked_at": 123, "installation": "fixture"}))
    assert read_runtime_status(tmp_path)["code"] == "OS_POLICY_BLOCKED"


def test_demo_speech_and_feasibility_have_distinct_statuses():
    result = classify(
        [provider("demo"), provider("windows-speech"), provider("small-cpu"), provider("ollama", False)], {}
    )
    assert [p["status"] for p in result] == ["Available", "Available", "Feasibility only", "Setup needed"]
