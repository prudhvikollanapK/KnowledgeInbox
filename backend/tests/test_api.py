from fastapi.testclient import TestClient

from backend.app.ai import DemoProvider
from backend.app.errors import AppError
from backend.app.fetcher import FetchedPage
from backend.app.main import create_app
from backend.tests.conftest import wait_for_item


def save_note(
    client, content="Daily reading habits improve focus. Read for ten minutes after breakfast."
):
    response = client.post("/ingest", json={"source_type": "note", "content": content})
    assert response.status_code == 202
    assert response.headers["x-request-id"]
    return wait_for_item(client, response.json()["id"])


def test_ingest_query_citations_and_delete(client):
    item = save_note(client)
    assert item["word_count"] > 0
    assert item["chunk_count"] == 1
    listed = client.get("/items").json()
    assert listed["total"] == 1
    assert "content" not in listed["items"][0]
    response = client.post("/query", json={"question": "What helps build reading habits?"})
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "demo"
    assert not result["insufficient_context"]
    assert "[1]" in result["answer"]
    assert result["sources"][0]["item_id"] == item["id"]
    assert result["sources"][0]["snippet"] in item["content"]
    assert client.delete(f"/items/{item['id']}").status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404
    assert client.post("/query", json={"question": "reading habits"}).status_code == 409


def test_persistence_and_provider_change_reindex(settings):
    with TestClient(create_app(settings, DemoProvider())) as first:
        item = save_note(first)
    with TestClient(create_app(settings, DemoProvider())) as second:
        assert second.get("/items").json()["total"] == 1
        assert second.get(f"/items/{item['id']}").json()["status"] == "ready"
    changed = DemoProvider()
    changed.index_key = "demo:changed-model"
    with TestClient(create_app(settings, changed)) as third:
        assert wait_for_item(third, item["id"])["status"] == "ready"
        with third.app.state.db.connect() as db:
            assert db.execute("SELECT index_key FROM items").fetchone()[0] == changed.index_key


def test_server_side_url_extraction_is_persisted(client, monkeypatch):
    async def fetch(url):
        return FetchedPage(
            "A useful article", "<html>raw</html>", "Reading habits start small.", url, "text/html"
        )

    monkeypatch.setattr("backend.app.worker.fetch_page", fetch)
    response = client.post(
        "/ingest", json={"source_type": "url", "content": "https://example.com/article"}
    )
    assert response.status_code == 202
    item = wait_for_item(client, response.json()["id"])
    assert item["title"] == "A useful article"
    assert item["source_type"] == "url"
    assert item["resolved_url"] == "https://example.com/article"
    with client.app.state.db.connect() as db:
        row = db.execute("SELECT raw_content,content_type FROM items").fetchone()
        assert row["raw_content"] == "<html>raw</html>"
        assert row["content_type"] == "text/html"


def test_failure_and_retry_preserve_item(client, monkeypatch):
    async def fail(url):
        raise AppError("fetch_failed", "Website returned HTTP 403.")

    monkeypatch.setattr("backend.app.worker.fetch_page", fail)
    response = client.post("/ingest", json={"source_type": "url", "content": "https://example.com"})
    item_id = response.json()["id"]
    failed = wait_for_item(client, item_id, "failed")
    assert "403" in failed["error"]

    async def success(url):
        return FetchedPage("Recovered", "Recovered text", "Recovered text", url, "text/plain")

    monkeypatch.setattr("backend.app.worker.fetch_page", success)
    assert client.post(f"/items/{item_id}/retry").status_code == 202
    assert wait_for_item(client, item_id)["error"] is None
    assert client.post(f"/items/{item_id}/retry").status_code == 409


def test_no_evidence_returns_honest_answer(client):
    save_note(client)
    result = client.post(
        "/query", json={"question": "Xylophone quasars volcanic zeppelins?"}
    ).json()
    assert result["insufficient_context"]
    assert result["sources"] == []


def test_validation_duplicates_filters_and_pagination(client):
    invalid_payloads = [
        {},
        {"source_type": "note", "content": "  "},
        {"source_type": "pdf", "content": "text"},
        {"source_type": "url", "content": "file:///etc/passwd"},
        {"source_type": "url", "content": "http://127.0.0.1"},
        {"source_type": "url", "content": "http://localhost"},
        {"source_type": "url", "content": "https://example.com:9000"},
        {"source_type": "note", "content": "x" * 100001},
        {"source_type": "note", "content": "test", "unexpected": True},
    ]
    for payload in invalid_payloads:
        response = client.post("/ingest", json=payload)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["message"]
    save_note(client, "Reading 100% helps.")
    duplicate = client.post(
        "/ingest", json={"source_type": "note", "content": "Reading 100% helps."}
    )
    assert duplicate.status_code == 409
    save_note(client, "Another note about gardening.")
    first = client.get("/items?limit=1").json()
    assert first["total"] == 2 and first["has_more"]
    second = client.get("/items?limit=1&offset=1").json()
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert client.get("/items?search=100%25").json()["total"] == 1
    assert client.get("/items?source_type=url").json()["total"] == 0
    assert client.get("/items?limit=101").status_code == 422
    assert client.post("/query", json={"question": "", "top_k": 99}).status_code == 422
    assert client.get("/items/not-a-uuid").status_code == 422


def test_query_busy_is_bounded(client):
    # Four active requests exhaust capacity; the API refuses excess work.
    import asyncio

    client.app.state.query_slots = asyncio.Semaphore(0)
    response = client.post("/query", json={"question": "Anything?"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "query_busy"


def test_oversized_and_chunked_bodies_are_rejected(client):
    response = client.post(
        "/ingest", content=b"x" * 530000, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    response = client.post("/ingest", content=iter([b"x" * 300000, b"x" * 300000]))
    assert response.status_code == 413


def test_unexpected_errors_are_logged_without_leaking_details(client, monkeypatch):
    def broken_stats():
        raise RuntimeError("secret-api-key-do-not-expose")

    monkeypatch.setattr(client.app.state.db, "stats", broken_stats)
    response = client.get("/health")
    assert response.status_code == 500
    assert "secret-api-key" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_api_prefix_works_for_single_origin_frontend(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/items").json()["items"] == []
    response = client.post(
        "/api/ingest", json={"source_type": "note", "content": "A prefixed note."}
    )
    assert response.status_code == 202
    wait_for_item(client, response.json()["id"])
    assert client.post("/api/query", json={"question": "prefixed note"}).status_code == 200
