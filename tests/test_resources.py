import pytest

from studio.providers import require_resources


@pytest.mark.parametrize(
    "ram,used,temp,code",
    [
        (0.77, 2036, 78, "RESOURCE_BUSY"),
        (7, 2500, 60, "RESOURCE_BUSY"),
        (7, 1000, 85, "RESOURCE_HOT"),
    ],
)
def test_provider_preflight_refuses_low_resources(monkeypatch, ram, used, temp, code):
    monkeypatch.setattr(
        "studio.diagnostics.hardware",
        lambda refresh: {
            "memory": {"available": True, "free_gb": ram},
            "gpu": {"available": True, "used_mb": used, "total_mb": 6144, "temperature_c": temp},
        },
    )
    with pytest.raises(RuntimeError, match=code):
        require_resources()


def test_provider_preflight_accepts_headroom_without_claiming_inference(monkeypatch):
    report = {
        "memory": {"available": True, "free_gb": 6},
        "gpu": {
            "available": True,
            "used_mb": 1500,
            "total_mb": 6144,
            "temperature_c": 70,
        },
    }
    monkeypatch.setattr("studio.diagnostics.hardware", lambda refresh: report)
    assert require_resources() == report
