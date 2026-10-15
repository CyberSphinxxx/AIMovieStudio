import pytest

from studio.domain import ProjectInput
from studio.storage import Store


@pytest.fixture(autouse=True)
def isolated_native_ownership(tmp_path, monkeypatch):
    # Contract fixtures must not block a real Studio job in the user's profile.
    # Cross-process tests explicitly pass a shared test path/simulated profile.
    monkeypatch.setattr("studio.inference_lock.lock_path", lambda: tmp_path / "native-model-test.lock")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "content with spaces")


@pytest.fixture
def spec():
    return ProjectInput(
        idea="A lighthouse remembers a vanished ship.", idempotency_key="fixture-unique-key", target_seconds=5
    )
