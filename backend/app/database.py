import asyncio
import math
import sqlite3
import uuid
from array import array
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .chunking import Chunk
from .errors import AppError

ITEM_COLUMNS = """
id, title, source_type, url, created_at, status, error,
substr(text_content, 1, 300) AS preview, word_count, chunk_count
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    async def run(self, operation: str, *args, **kwargs):
        return await asyncio.to_thread(getattr(self, operation), *args, **kwargs)

    def initialize(self, index_key: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, source_type TEXT NOT NULL,
                    url TEXT, resolved_url TEXT, raw_content TEXT NOT NULL DEFAULT '',
                    text_content TEXT NOT NULL DEFAULT '', content_type TEXT,
                    created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    error TEXT, word_count INTEGER NOT NULL DEFAULT 0,
                    chunk_count INTEGER NOT NULL DEFAULT 0, index_key TEXT,
                    fingerprint TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL, text TEXT NOT NULL, start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL, embedding BLOB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_items_status ON items(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_chunks_item ON chunks(item_id);
                PRAGMA user_version=1;
            """)
            # A single worker is supported. Interrupted jobs and model changes are re-indexed.
            db.execute(
                """UPDATE items SET status='pending', error=NULL
                WHERE status='processing' OR (
                    (status='ready' OR (status='failed' AND text_content!=''))
                    AND coalesce(index_key, '') != ?
                )""",
                (index_key,),
            )

    def create_item(self, source_type: str, content: str, title: str, fingerprint: str) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            duplicate = db.execute(
                "SELECT id FROM items WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            if duplicate:
                raise AppError("duplicate_item", "This content is already in your library.", 409)
            queued = db.execute(
                "SELECT count(*) FROM items WHERE status IN ('pending','processing')"
            ).fetchone()[0]
            if queued >= 100:
                raise AppError(
                    "queue_full", "The inbox is busy. Wait for current items to finish.", 429
                )
            item_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO items
                (id,title,source_type,url,raw_content,text_content,created_at,fingerprint)
                VALUES (?,?,?,?,?,?,?,?)""",
                (
                    item_id,
                    title,
                    source_type,
                    content if source_type == "url" else None,
                    content if source_type == "note" else "",
                    content if source_type == "note" else "",
                    datetime.now(UTC).isoformat(),
                    fingerprint,
                ),
            )
            return dict(
                db.execute(f"SELECT {ITEM_COLUMNS} FROM items WHERE id=?", (item_id,)).fetchone()
            )

    def list_items(self, limit: int, offset: int, search: str, source_type: str | None) -> dict:
        pattern = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        condition = "(title LIKE ? ESCAPE '\\' OR text_content LIKE ? ESCAPE '\\')"
        params: list = [pattern, pattern]
        if source_type:
            condition += " AND source_type=?"
            params.append(source_type)
        with self.connect() as db:
            total = db.execute(f"SELECT count(*) FROM items WHERE {condition}", params).fetchone()[
                0
            ]
            rows = db.execute(
                f"""SELECT {ITEM_COLUMNS} FROM items WHERE {condition}
                ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?""",
                [*params, limit, offset],
            ).fetchall()
        return {
            "items": [dict(row) for row in rows],
            "total": total,
            "has_more": offset + len(rows) < total,
        }

    def get_item(self, item_id: str) -> dict:
        with self.connect() as db:
            row = db.execute(
                f"""SELECT {ITEM_COLUMNS}, text_content AS content, resolved_url
                FROM items WHERE id=?""",
                (item_id,),
            ).fetchone()
        if not row:
            raise AppError("item_not_found", "This item could not be found.", 404)
        return dict(row)

    def delete_item(self, item_id: str) -> None:
        with self.connect() as db:
            if not db.execute("DELETE FROM items WHERE id=?", (item_id,)).rowcount:
                raise AppError("item_not_found", "This item could not be found.", 404)

    def retry_item(self, item_id: str) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            queued = db.execute(
                "SELECT count(*) FROM items WHERE status IN ('pending','processing')"
            ).fetchone()[0]
            if queued >= 100:
                raise AppError(
                    "queue_full", "The inbox is busy. Wait for current items to finish.", 429
                )
            changed = db.execute(
                "UPDATE items SET status='pending',error=NULL WHERE id=? AND status='failed'",
                (item_id,),
            ).rowcount
        if not changed:
            self.get_item(item_id)
            raise AppError("not_failed", "Only failed items can be retried.", 409)
        return self.get_item(item_id)

    def claim_next(self) -> dict | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM items WHERE status='pending' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            db.execute("UPDATE items SET status='processing' WHERE id=?", (row["id"],))
            return dict(row)

    def save_content(
        self,
        item_id: str,
        title: str,
        raw: str,
        text: str,
        resolved_url: str | None,
        content_type: str,
    ) -> None:
        # Persist fetched content before calling AI so it survives provider failures/restarts.
        with self.connect() as db:
            db.execute(
                """UPDATE items SET title=?,raw_content=?,text_content=?,resolved_url=?,
                content_type=?,word_count=? WHERE id=?""",
                (title, raw, text, resolved_url, content_type, len(text.split()), item_id),
            )

    def complete(
        self, item_id: str, chunks: list[Chunk], vectors: list[list[float]], index_key: str
    ) -> None:
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone():
                return  # Deletion while embedding was in flight must stay deleted.
            db.execute("DELETE FROM chunks WHERE item_id=?", (item_id,))
            db.executemany(
                "INSERT INTO chunks VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        str(uuid.uuid4()),
                        item_id,
                        n,
                        chunk.text,
                        chunk.start,
                        chunk.end,
                        array("f", vector).tobytes(),
                    )
                    for n, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
                ],
            )
            db.execute(
                "UPDATE items SET status='ready',error=NULL,chunk_count=?,index_key=? WHERE id=?",
                (len(chunks), index_key, item_id),
            )

    def fail(self, item_id: str, message: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE items SET status='failed',error=? WHERE id=?", (message, item_id))

    def stats(self) -> dict:
        with self.connect() as db:
            row = db.execute("""SELECT count(*) AS total,
                coalesce(sum(source_type='note'),0) AS notes,
                coalesce(sum(source_type='url'),0) AS urls,
                coalesce(sum(status='ready'),0) AS ready,
                coalesce(sum(status IN ('pending','processing')),0) AS pending,
                coalesce(sum(status='failed'),0) AS failed,
                coalesce(sum(CASE WHEN status='ready' THEN chunk_count ELSE 0 END),0) AS chunks
                FROM items""").fetchone()
        return dict(row)

    def last_error(self) -> str | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT error FROM items WHERE status='failed' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def search(
        self, vector: list[float], index_key: str, top_k: int, min_score: float
    ) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT c.id AS chunk_id,c.item_id,c.text AS snippet,c.embedding,
                i.title,i.source_type,i.url FROM chunks c JOIN items i ON i.id=c.item_id
                WHERE i.status='ready' AND i.index_key=?""",
                (index_key,),
            ).fetchall()
        matches = []
        for row in rows:
            stored = array("f")
            stored.frombytes(row["embedding"])
            if len(stored) != len(vector):
                continue
            # Both vectors are normalized at insertion/query, so dot product is cosine.
            score = math.fsum(a * b for a, b in zip(vector, stored, strict=True))
            if score >= min_score:
                matches.append(
                    {k: row[k] for k in row.keys() if k != "embedding"} | {"score": round(score, 4)}
                )
        matches.sort(key=lambda item: item["score"], reverse=True)
        # Bound repetitions from a long page; diversify the context across saved items.
        selected = []
        per_item: dict[str, int] = {}
        for match in matches:
            count = per_item.get(match["item_id"], 0)
            if count < 2:
                selected.append(match)
                per_item[match["item_id"]] = count + 1
            if len(selected) == top_k:
                break
        return selected
