import json

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AsyncOpenAI

from backend.app.ai import OpenAIProvider
from backend.app.config import Settings
from backend.app.errors import AppError
from backend.app.main import create_app
from backend.tests.conftest import wait_for_item

SOURCES = [{"citation": 1, "title": "Reading", "snippet": "Read every morning."}]


def make_provider(handler):
    client = AsyncOpenAI(
        api_key="test-not-a-real-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return OpenAIProvider(Settings(_env_file=None), client)


async def test_openai_embeddings_and_grounded_structured_answer():
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json={
                    "data": [{"index": 0, "embedding": [3.0, 4.0]}],
                    "model": "test",
                    "object": "list",
                    "usage": {"prompt_tokens": 3, "total_tokens": 3},
                },
            )
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        assert json.loads(body["input"])["saved_passages"][0]["text"] == "Read every morning."
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "gpt-4.1-mini",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "answer": "Read every morning. [1]",
                                        "insufficient_context": False,
                                    }
                                ),
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    provider = make_provider(handler)
    vectors = await provider.embed(["Read every morning."])
    assert vectors == [[0.6, 0.8]]
    result = await provider.answer("When should I read?", SOURCES)
    assert result.answer.endswith("[1]")
    assert len(calls) == 2
    await provider.close()


@pytest.mark.parametrize(
    ("status", "code"), [(401, "ai_configuration"), (429, "ai_rate_limit"), (500, "ai_unavailable")]
)
async def test_provider_errors_are_actionable_and_do_not_leak_secrets(status, code):
    def handler(request):
        return httpx.Response(
            status, json={"error": {"message": "secret-provider-details", "type": "test"}}
        )

    provider = make_provider(handler)
    with pytest.raises(AppError) as caught:
        await provider.embed(["test"])
    assert caught.value.code == code
    assert "secret-provider-details" not in caught.value.message
    assert caught.value.status >= 500
    await provider.close()


async def test_invalid_citation_is_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "gpt-4.1-mini",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "answer": "Invented claim. [99]",
                                        "insufficient_context": False,
                                    }
                                ),
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    provider = make_provider(handler)
    with pytest.raises(AppError, match="uncited"):
        await provider.answer("Question?", SOURCES)
    await provider.close()


@pytest.mark.parametrize("code", ["insufficient_quota", "credit_balance_exhausted"])
async def test_exhausted_api_credits_are_not_reported_as_a_transient_rate_limit(code):
    def handler(request):
        return httpx.Response(
            429,
            json={
                "error": {
                    "message": "Provider detail",
                    "type": "insufficient_quota",
                    "code": code,
                }
            },
        )

    provider = make_provider(handler)
    with pytest.raises(AppError) as caught:
        await provider.embed(["test"])
    assert caught.value.code == "ai_quota"
    assert "API credits" in caught.value.message
    assert "retry indexing" in caught.value.message
    await provider.close()


def test_openai_ingest_to_cited_city_answer_uses_title(tmp_path):
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(
                200,
                json={
                    "data": [{"index": 0, "embedding": [1.0, 0.0]}],
                    "model": "text-embedding-3-small",
                    "object": "list",
                    "usage": {"prompt_tokens": 3, "total_tokens": 3},
                },
            )
        context = json.loads(payload["input"])
        assert context["saved_passages"][0]["title"] == "city"
        assert context["saved_passages"][0]["text"] == "vizag"
        return httpx.Response(
            200,
            json={
                "id": "resp_city",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "gpt-4.1-mini",
                "output": [
                    {
                        "id": "msg_city",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "annotations": [],
                                "text": json.dumps(
                                    {
                                        "answer": "Your city is Vizag. [1]",
                                        "insufficient_context": False,
                                    }
                                ),
                            }
                        ],
                    }
                ],
            },
        )

    settings = Settings(database_path=tmp_path / "openai-city.sqlite3", _env_file=None)
    with TestClient(create_app(settings, make_provider(handler))) as client:
        created = client.post(
            "/ingest", json={"source_type": "note", "title": "city", "content": "vizag"}
        )
        wait_for_item(client, created.json()["id"])
        result = client.post("/query", json={"question": "what my city"}).json()
        assert result["mode"] == "openai"
        assert not result["insufficient_context"]
        assert result["answer"] == "Your city is Vizag. [1]"
        assert result["sources"][0]["item_id"] == created.json()["id"]
        assert calls[0]["input"] == ["city\nvizag"]
