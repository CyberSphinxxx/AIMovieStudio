import pytest

from studio.domain import ProjectInput
from studio.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "content with spaces")


@pytest.fixture
def spec():
    return ProjectInput(
        idea="A lighthouse remembers a vanished ship.", idempotency_key="fixture-unique-key", target_seconds=5
    )
