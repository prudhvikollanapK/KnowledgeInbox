import hashlib
import math

import pytest

from backend.app.ai import DemoProvider, normalize
from backend.app.chunking import chunk_text
from backend.app.database import Database
from backend.app.errors import AppError
from backend.app.worker import IngestionWorker


def test_chunk_boundaries_offsets_overlap_and_unicode():
    text = ("A paragraph about reading and learning. " * 50 + "\n\n") * 3 + "最后一段。"
    chunks = chunk_text(text)
    assert len(chunks) > 3
    assert all(chunk.text == text[chunk.start : chunk.end] for chunk in chunks)
    assert all(len(chunk.text) <= 1200 for chunk in chunks)
    assert all(left.end >= right.start for left, right in zip(chunks, chunks[1:], strict=False))
    assert chunks[-1].end == len(text)
    assert chunks[0].start == 0
    assert chunk_text("  ") == []
    with pytest.raises(ValueError):
        chunk_text(text, overlap=1200)


async def test_vectors_retrieve_correct_source_and_ignore_deleted(tmp_path):
    db = Database(tmp_path / "vectors.sqlite3")
    ai = DemoProvider()
    db.initialize(ai.index_key)
    for content in ["Reading habits improve with practice.", "Tomatoes need sunshine and water."]:
        item = db.create_item(
            "note", content, content, hashlib.sha256(content.encode()).hexdigest()
        )
        await IngestionWorker(db, ai).process(db.claim_next())
        assert db.get_item(item["id"])["status"] == "ready"
    query = (await ai.embed(["How do reading habits improve?"]))[0]
    matches = db.search(query, ai.index_key, 5, ai.min_score)
    assert "Reading" in matches[0]["title"]
    assert all("Tomatoes" not in match["title"] for match in matches)
    db.delete_item(matches[0]["item_id"])
    assert db.search(query, ai.index_key, 5, ai.min_score) == []
    with db.connect() as connection:
        assert connection.execute("SELECT count(*) FROM chunks").fetchone()[0] == 1


async def test_inflight_deleted_item_stays_deleted(tmp_path):
    db = Database(tmp_path / "deleted.sqlite3")
    ai = DemoProvider()
    db.initialize(ai.index_key)
    item = db.create_item("note", "A note.", "A note", "unique")
    claimed = db.claim_next()
    db.delete_item(item["id"])
    await IngestionWorker(db, ai).process(claimed)
    assert db.stats()["total"] == 0
    with db.connect() as connection:
        assert connection.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0


def test_interrupted_job_is_recovered(tmp_path):
    db = Database(tmp_path / "recovery.sqlite3")
    db.initialize("test-model")
    item = db.create_item("note", "Persistent note", "Persistent", "fingerprint")
    assert db.claim_next()["id"] == item["id"]
    assert db.get_item(item["id"])["status"] == "processing"
    db.initialize("test-model")
    assert db.get_item(item["id"])["status"] == "pending"


def test_vector_normalization_rejects_invalid_provider_output():
    normalized = normalize([3, 4])
    assert math.isclose(sum(n * n for n in normalized), 1)
    for vector in [[], [float("nan")], [float("inf")]]:
        with pytest.raises(AppError):
            normalize(vector)
