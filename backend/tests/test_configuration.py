from fastapi.testclient import TestClient

from backend.app.ai import DemoProvider
from backend.app.config import Settings
from backend.app.main import create_app
from backend.tests.conftest import wait_for_item


def test_city_note_is_retrievable_by_its_title(client):
    response = client.post(
        "/ingest",
        json={
            "source_type": "note",
            "title": "city",
            "content": "vizag",
        },
    )
    wait_for_item(client, response.json()["id"])
    result = client.post("/query", json={"question": "what my city"}).json()
    assert not result["insufficient_context"]
    assert "vizag" in result["answer"].lower()
    assert result["sources"][0]["title"] == "city"
    assert result["sources"][0]["snippet"] == "vizag"


def test_public_names_load_from_dotenv_without_exposing_secrets(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "APP_NAME=Research\nAPP_TITLE=Research Inbox\nASSISTANT_NAME=Atlas\n"
        "ASSISTANT_TITLE=What would you like to explore?\n"
        "OPENAI_API_KEY=not-a-real-key\nAI_PROVIDER=demo\n",
        encoding="utf-8",
    )
    settings = Settings(database_path=tmp_path / "config.sqlite3", _env_file=env)
    with TestClient(create_app(settings, DemoProvider())) as client:
        config = client.get("/config")
        assert config.json()["app_name"] == "Research"
        assert config.json()["assistant_name"] == "Atlas"
        assert "not-a-real-key" not in config.text
        health = client.get("/health")
        assert health.json()["ui"]["app_title"] == "Research Inbox"
        assert health.json()["api_key_configured"]
        assert "not-a-real-key" not in health.text
        assert "openai_api_key" not in config.text.lower()


def test_runtime_key_change_requests_restart_and_public_names_refresh(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    base = f"AI_PROVIDER=auto\nDATABASE_PATH={tmp_path.as_posix()}/runtime.sqlite3\n"
    env.write_text(base + "OPENAI_API_KEY=\nAPP_TITLE=First title\n", encoding="utf-8")
    monkeypatch.setitem(Settings.model_config, "env_file", env)
    with TestClient(create_app(provider=DemoProvider())) as client:
        assert not client.get("/health").json()["restart_required"]
        env.write_text(base + "OPENAI_API_KEY=\nAPP_TITLE=Second title\n", encoding="utf-8")
        assert client.get("/config").json()["app_title"] == "Second title"
        env.write_text(base + "OPENAI_API_KEY=changed-test-key\n", encoding="utf-8")
        result = client.get("/health").json()
        assert result["restart_required"]
        assert "Restart" in result["warning"]
        assert "changed-test-key" not in client.get("/health").text


def test_failed_indexing_has_an_actionable_health_warning(client, monkeypatch):
    async def fail(texts):
        from backend.app.errors import AppError

        raise AppError("ai_configuration", "OpenAI rejected OPENAI_API_KEY.", 503)

    monkeypatch.setattr(client.app.state.ai, "embed", fail)
    response = client.post("/ingest", json={"source_type": "note", "content": "test note"})
    wait_for_item(client, response.json()["id"], "failed")
    result = client.get("/health").json()
    assert result["stats"]["failed"] == 1
    assert result["warning"] == "OpenAI rejected OPENAI_API_KEY."
