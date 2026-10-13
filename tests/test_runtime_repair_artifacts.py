from scripts import prepare_gpu_runtime


def test_exact_vendor_smplfitter_wheel_is_not_replaced_by_pypi(monkeypatch):
    def network(*args):
        raise AssertionError("Custom approved artifact must not resolve a different package")

    monkeypatch.setattr(prepare_gpu_runtime, "read", network)
    result = prepare_gpu_runtime.choose("smplfitter==0.2.10")
    assert result["url"].startswith("https://github.com/deepbeepmeep/smplfitter/releases/download/v0.2.10/")
    assert result["sha256"] == "bd33a3f854b50770e37a66db05a4b75c66b45fdd88ec1aa40e56784df9df7b54"
    assert result["bytes"] == 61979 and result["filename"].endswith("py3-none-any.whl")


def test_whisper_only_admits_the_pure_source_build_not_a_system_compiler():
    assert "openai-whisper" in prepare_gpu_runtime.PURE_BUILD
    assert "flash-attn" not in prepare_gpu_runtime.PURE_BUILD
