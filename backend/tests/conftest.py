import time

import pytest
from fastapi.testclient import TestClient

from backend.app.ai import DemoProvider
from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "test.sqlite3", ai_provider="demo", _env_file=None)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, DemoProvider())) as client:
        yield client


def wait_for_item(client, item_id, expected="ready"):
    for _ in range(100):
        item = client.get(f"/items/{item_id}").json()
        if item["status"] == expected:
            return item
        if item["status"] == "failed" and expected != "failed":
            pytest.fail(item["error"])
        time.sleep(0.03)
    pytest.fail(f"Item never reached {expected}: {item}")
