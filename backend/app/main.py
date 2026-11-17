import asyncio
import hashlib
import re
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from .ai import AIProvider, create_provider
from .config import ROOT, Settings
from .database import Database
from .errors import AppError
from .logging import configure_logging, log, request_id
from .middleware import RequestSizeLimit
from .schemas import IngestRequest, Item, ItemDetail, ItemList, QueryRequest, QueryResponse
from .worker import IngestionWorker


def create_app(settings: Settings | None = None, provider: AIProvider | None = None) -> FastAPI:
    uses_runtime_settings = settings is None
    settings = settings or Settings()
    db = Database(settings.database_path)
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ai = provider or create_provider(settings)
        await db.run("initialize", ai.index_key)
        worker = IngestionWorker(db, ai)
        app.state.ai = ai
        app.state.worker = worker
        app.state.query_slots = asyncio.Semaphore(4)
        task = asyncio.create_task(worker.run(), name="ingestion-worker")
        log("app.started", provider=ai.mode)
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await ai.close()

    app = FastAPI(title=settings.app_title, version="1.0.0", lifespan=lifespan)
    app.state.db = db
    app.add_middleware(RequestSizeLimit)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
        ],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def instrument(request: Request, call_next):
        token = request_id.set(str(uuid.uuid4()))
        started = time.monotonic()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                log("http.error", error_type=type(exc).__name__, path=request.url.path)
                response = error_response(
                    "internal_error", "An unexpected server error occurred. Please try again.", 500
                )
            response.headers["X-Request-ID"] = request_id.get()
            response.headers["X-Content-Type-Options"] = "nosniff"
            log(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
            return response
        finally:
            request_id.reset(token)

    def error_response(code: str, message: str, status: int, **extra) -> JSONResponse:
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": request_id.get(),
                    **extra,
                },
            },
        )

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return error_response(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(str(loc) for loc in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return error_response("validation_error", "Please check your input.", 422, fields=fields)

    @app.exception_handler(HTTPException)
    async def handle_http_error(request: Request, exc: HTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        response = error_response(code, str(exc.detail), exc.status_code)
        response.headers.update(exc.headers or {})
        return response

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        log("http.error", error_type=type(exc).__name__, path=request.url.path)
        return error_response(
            "internal_error", "An unexpected server error occurred. Please try again.", 500
        )

    router = APIRouter()

    def current_settings() -> Settings:
        return Settings() if uses_runtime_settings else settings

    @router.get("/config")
    async def public_config():
        return current_settings().public_config()

    @router.get("/health")
    async def health():
        current = current_settings()
        stats = await db.run("stats")
        restart_required = (
            current.provider != settings.provider
            or current.openai_api_key != settings.openai_api_key
            or current.openai_embedding_model != settings.openai_embedding_model
            or current.openai_chat_model != settings.openai_chat_model
        )
        warning = None
        if restart_required:
            warning = "AI configuration changed. Restart the backend to apply your .env settings."
        elif app.state.ai.mode == "demo":
            warning = (
                "Offline demo is selected by AI_PROVIDER=demo."
                if settings.ai_provider == "demo"
                else "No OpenAI key was loaded. Set OPENAI_API_KEY in the root .env file "
                "and restart the backend for AI answers."
            )
        if not restart_required and not stats["ready"] and stats["failed"]:
            warning = await db.run("last_error") or warning
        return {
            "status": "ok",
            "mode": app.state.ai.mode,
            "stats": stats,
            "ui": current.public_config(),
            "warning": warning,
            "restart_required": restart_required,
            "api_key_configured": bool(settings.openai_api_key.get_secret_value()),
        }

    @router.post("/ingest", response_model=Item, status_code=202)
    async def ingest(payload: IngestRequest):
        title = payload.title or (
            urlsplit(payload.content).hostname
            if payload.source_type == "url"
            else payload.content.splitlines()[0][:100]
        )
        fingerprint = hashlib.sha256(
            f"{payload.source_type}:{payload.content}".encode()
        ).hexdigest()
        item = await db.run("create_item", payload.source_type, payload.content, title, fingerprint)
        app.state.worker.wake.set()
        return item

    @router.get("/items", response_model=ItemList)
    async def items(
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0)] = 0,
        search: Annotated[str, Query(max_length=200)] = "",
        source_type: Literal["note", "url"] | None = None,
    ):
        return await db.run("list_items", limit, offset, search.strip(), source_type)

    @router.get("/items/{item_id}", response_model=ItemDetail)
    async def item_detail(item_id: uuid.UUID):
        return await db.run("get_item", str(item_id))

    @router.delete("/items/{item_id}", status_code=204)
    async def delete_item(item_id: uuid.UUID):
        await db.run("delete_item", str(item_id))
        return Response(status_code=204)

    @router.post("/items/{item_id}/retry", response_model=Item, status_code=202)
    async def retry_item(item_id: uuid.UUID):
        item = await db.run("retry_item", str(item_id))
        app.state.worker.wake.set()
        return item

    @router.post("/query", response_model=QueryResponse)
    async def query(payload: QueryRequest):
        started = time.monotonic()
        ai = app.state.ai
        # Refuse excess work immediately rather than allowing unbounded AI request queues.
        if app.state.query_slots.locked():
            raise AppError(
                "query_busy", "Other questions are being answered. Please try again shortly.", 429
            )
        async with app.state.query_slots:
            stats = await db.run("stats")
            if not stats["ready"]:
                raise AppError(
                    "no_ready_content",
                    "Save a note or link and wait for indexing before asking a question.",
                    409,
                )
            try:
                async with asyncio.timeout(90):
                    vectors = await ai.embed([payload.question])
                    matches = await db.run(
                        "search", vectors[0], ai.index_key, payload.top_k, ai.min_score
                    )
                    sources = [dict(match, citation=i + 1) for i, match in enumerate(matches)]
                    if not sources:
                        log("query.no_context", mode=ai.mode, retrieved=0)
                        return QueryResponse(
                            answer=(
                                "I couldn’t find enough relevant information "
                                "in your saved content. "
                                "Try a more specific question or save a related note."
                            ),
                            sources=[],
                            mode=ai.mode,
                            insufficient_context=True,
                            duration_ms=round((time.monotonic() - started) * 1000),
                        )
                    result = await ai.answer(payload.question, sources)
            except TimeoutError:
                raise AppError(
                    "query_timeout", "Your question took too long to answer. Please try again.", 504
                ) from None
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", result.answer)}
        used_sources = (
            [] if result.insufficient_context else [s for s in sources if s["citation"] in cited]
        )
        log("query.completed", retrieved=len(matches), cited=len(used_sources), mode=ai.mode)
        return QueryResponse(
            answer=result.answer,
            sources=used_sources,
            mode=ai.mode,
            insufficient_context=result.insufficient_context,
            duration_ms=round((time.monotonic() - started) * 1000),
        )

    app.include_router(router)
    app.include_router(router, prefix="/api", include_in_schema=False)

    # Optional single-origin production serving, after `npm run build`.
    dist: Path = ROOT / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
