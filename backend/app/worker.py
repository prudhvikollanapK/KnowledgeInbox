import asyncio
from urllib.parse import urlsplit

from .ai import AIProvider
from .chunking import chunk_text
from .database import Database
from .errors import AppError
from .fetcher import fetch_page
from .logging import log


class IngestionWorker:
    def __init__(self, db: Database, provider: AIProvider):
        self.db = db
        self.provider = provider
        self.wake = asyncio.Event()

    async def process(self, item: dict) -> None:
        log("ingestion.started", item_id=item["id"], source_type=item["source_type"])
        try:
            title = item["title"]
            raw = item["raw_content"]
            text = item["text_content"]
            resolved_url = item["resolved_url"]
            content_type = item["content_type"] or "text/plain"
            if item["source_type"] == "url" and not text:
                page = await fetch_page(item["url"])
                raw, text, resolved_url, content_type = (
                    page.raw_content,
                    page.text,
                    page.resolved_url,
                    page.content_type,
                )
                if title == urlsplit(item["url"]).hostname:
                    title = page.title
            await self.db.run(
                "save_content", item["id"], title, raw, text, resolved_url, content_type
            )
            chunks = chunk_text(text)
            if not chunks:
                raise AppError("empty_content", "No readable content was found.")
            async with asyncio.timeout(180):
                # Titles carry meaning for short notes such as city -> Vizag.
                vectors = await self.provider.embed([f"{title}\n{chunk.text}" for chunk in chunks])
            await self.db.run("complete", item["id"], chunks, vectors, self.provider.index_key)
            log("ingestion.completed", item_id=item["id"], chunks=len(chunks))
        except Exception as exc:
            if isinstance(exc, AppError):
                message = exc.message
            elif isinstance(exc, TimeoutError):
                message = "Indexing took too long. Please retry this item."
            else:
                message = "This item could not be indexed. Please retry it."
            await self.db.run("fail", item["id"], message)
            log("ingestion.failed", item_id=item["id"], error_type=type(exc).__name__)

    async def run(self) -> None:
        while True:
            self.wake.clear()
            try:
                item = await self.db.run("claim_next")
                if item:
                    await self.process(item)
                    continue
            except Exception as exc:
                # Keep the worker alive after a transient database error.
                log("worker.error", error_type=type(exc).__name__)
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=2)
            except TimeoutError:
                pass
