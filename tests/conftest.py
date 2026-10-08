from collections.abc import Callable, Iterator
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

Upload = Callable[[str, bytes], httpx2.Response]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at a database that exists only for this test."""
    return Settings(database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def upload(client: TestClient) -> Upload:
    """Post a file to the upload endpoint the way a real client does."""

    def post(filename: str, content: bytes) -> httpx2.Response:
        return client.post("/api/files/", files={"file": (filename, content)})

    return post
