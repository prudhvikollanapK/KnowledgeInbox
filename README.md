# AI Knowledge Inbox

A single-user knowledge inbox built with **React + TypeScript, FastAPI, SQLite, and OpenAI**. Save notes or public webpages, then ask questions with citations back to the exact retrieved passages. No account, containers, or hosted database required.
<img width="1917" height="1017" alt="image" src="https://github.com/user-attachments/assets/da4ac130-0fb9-42e4-a8dd-b49d1b066590" />
<img width="761" height="745" alt="image" src="https://github.com/user-attachments/assets/3515958c-18b2-42e3-8937-6e005fc49d3e" />

I have taken UI design inspiration from the Turium AI website. Please refer above screenshots
The project title is **Knowledge Inbox** and the AI assistant is named **KIN (Knowledge Inbox)**.
We can modify the `.env` file content as needed. I have shared the `.env` file via email.

## Run locally

Requires **Python 3.12+** and **Node.js 22.12+** (tested with Python 3.12 / Node 24). Run all commands from the project root.

### 1. Backend

Windows PowerShell (activation is unnecessary):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8765
```

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-lock.txt
test -f .env || cp .env.example .env
.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8765
```

### 2. Frontend — in another terminal

```bash
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. On PowerShell systems that block npm.ps1, use `npm.cmd ci` and `npm.cmd run dev`. FastAPI documentation is at **http://127.0.0.1:8765/docs**. Vite proxies `/api/*` to the backend; no browser API key is used.

If Windows reports `WinError 10013` or `10048`, the requested port may be blocked or already in use. The commands above explicitly use port **8765** rather than Uvicorn's default 8000. If you choose a different backend port, also set `API_PROXY_TARGET=http://127.0.0.1:<port>` in `.env` and restart Vite. Changing this proxy setting does not change Uvicorn's listening port; pass the matching `--port` argument when starting the backend.

### 3. Enable real semantic search and AI answers

Set `OPENAI_API_KEY` in the root `.env`, then restart the backend. `AI_PROVIDER=auto` selects OpenAI when the key is present. Default models are `text-embedding-3-small` and `gpt-4.1-mini`; both are configurable. To require OpenAI and fail startup without a key, set `AI_PROVIDER=openai`.

A `401 invalid_api_key` means OpenAI rejected the configured value. Replace it with a valid OpenAI API key in `.env`, then stop and start the backend. The chat displays provider errors and a restart notice when AI settings have changed. Failed indexing with retained text is retried at startup when its index is out of date; failed items can also be retried individually.

An OpenAI `429` with `credit_balance_exhausted` or `insufficient_quota` means the API project has no available credits/quota. The key may be valid even though generation is blocked. Check that project's API billing, then retry failed items once credits are available. A transient rate limit is reported separately.

### App and assistant text

Configure the public names and chat text in the same root `.env`:

```dotenv
APP_NAME=INBOX
APP_TITLE=Knowledge inbox
ASSISTANT_NAME=KIN
ASSISTANT_TITLE=How can I help you today?
ASSISTANT_PLACEHOLDER=Ask anything about your saved content…
ASSISTANT_SUGGESTIONS=["What is my city?","What do you know about me?","Summarize my notes"]
```

The backend returns only these public fields through `/config` and `/health`; the API key stays on the server. Public text refreshes with the normal health polling. AI key/provider/model changes require a backend restart. The ask bar expands on focus and collapses with its header control or Escape. Enter sends; Shift+Enter adds a newline. Questions and cited answers stay in browser memory during the session. Each question is retrieved independently; earlier chat turns are not sent to the model.

Without a key, the app works in an explicitly labeled **offline demo**: deterministic feature-hashed keyword vectors and extractive answers. This mode demonstrates the ingestion, storage, retrieval, citations, and UI, but **does not provide semantic embeddings or an LLM**. No external AI request or model download occurs. No content is seeded automatically.

HTTPS fetching uses system trust plus the bundled public CA roots. For a corporate certificate authority, configure `SSL_CERT_FILE` with a trusted CA bundle before starting the backend. TLS verification stays enabled.

Changing provider or embedding model automatically queues previously ready items for re-indexing on startup. Questions never mix embedding spaces. Open a saved item to retry a failed ingestion. Notes and URL content survive restart in `data/inbox.sqlite3`; `.env` and runtime data are ignored by Git.

### One-process serving

```bash
npm run build
# Windows: use .\.venv\Scripts\python.exe in place of .venv/bin/python
.venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765
```

FastAPI serves the built UI at **http://127.0.0.1:8765** and exposes both `/api/*` and the direct API routes below. Build before starting the backend. Use **one Uvicorn worker**: restart recovery assumes one ingestion-worker owner. `--reload` is for development only.

## API

| Method | Endpoint | Behavior |
| --- | --- | --- |
| POST | `/ingest` | `{ "source_type": "note" \| "url", "content": "...", "title": "optional" }` → **202**, queued item |
| GET | `/items` | Paginated `{ items, total, has_more }`; `limit=30` (max 100), `offset`, `search`, `source_type` |
| POST | `/query` | `{ "question": "...", "top_k": 5 }` → answer, cited sources, mode, duration, insufficient-context flag |
| GET | `/items/{id}` | Full extracted text, metadata, indexing status/error |
| DELETE | `/items/{id}` | Delete item and its chunks → **204** |
| POST | `/items/{id}/retry` | Retry a failed ingestion → **202** |
| GET | `/health` | Active provider, indexing counts, public UI settings, configuration warnings |
| GET | `/config` | Public app/assistant text only; excludes API keys |

```bash
curl -X POST http://127.0.0.1:8765/ingest -H 'Content-Type: application/json' \
  -d '{"source_type":"note","content":"Release reviews happen every Friday at 3 pm.","title":"Team rituals"}'
# Wait until the item is ready (GET /items), then:
curl -X POST http://127.0.0.1:8765/query -H 'Content-Type: application/json' \
  -d '{"question":"When are release reviews?"}'
```

An answer includes `sources: [{ citation, item_id, chunk_id, title, source_type, url, snippet, score }]`. Inline `[n]` markers refer to source citation numbers; snippets contain the full retrieved chunk. Only sources actually cited in the answer are returned. An unsupported question returns **200**, `insufficient_context: true`, and no sources; an empty/unindexed library returns **409**.

Errors have a consistent shape:

```json
{"error":{"code":"duplicate_item","message":"This content is already in your library.","request_id":"..."}}
```

Validation uses **422**, missing items **404**, duplicates/state conflicts **409**, oversized bodies **413**, local saturation **429**, upstream AI failure **502/503**, and timeout **504**. Validation errors also include `fields`. Each response has `X-Request-ID`; application events are JSON logs with request/item IDs, durations, and event names, without note bodies, questions, or API keys.

## Design decisions and tradeoffs

**Async ingestion.** `POST /ingest` commits a pending item before returning. A lifespan task claims jobs from SQLite, fetches URLs, persists raw and extracted content, chunks, embeds, then atomically replaces chunks and marks the item ready. Network calls are asynchronous and database work runs in a thread, keeping the event loop responsive. Interrupted jobs are recovered at startup. The persisted queue is bounded to 100 active jobs; query concurrency is limited to four. This avoids a separate broker for a small app. Jobs fail visibly and require explicit retry rather than retrying indefinitely.

**Chunking.** Sliding windows up to 1,200 characters with 200-character overlap prefer paragraph, then sentence, then whitespace boundaries. Overlap reduces lost context at boundaries; exact character offsets are stored. Each chunk is embedded with its item title, so a note titled “city” with body “vizag” can answer a city question. Returned snippets remain the original body text. The index version changes when this embedding format changes, triggering re-indexing. Character sizing is deterministic, dependency-light, and safely small for the default embedding model, including multilingual text. It is not tokenizer-aware and may split unusually long words or code. Embeddings are batched in groups of 32.

**Vectors in SQLite.** Raw content, extracted text, source metadata, status, chunks, and normalized float32 embedding blobs live in one WAL-mode database with foreign-key cascade deletion. Retrieval performs an exact cosine scan in a thread; there is no ANN service or ORM. Top-k is bounded to eight, with at most two chunks from one item to diversify sources. Cosine cutoffs (OpenAI 0.22, demo 0.12) are heuristics, not calibrated confidence scores; domain-specific evaluation should tune them. This is appropriate for a personal library of hundreds or a few thousand chunks, not a large corpus.

**Grounding.** The query embedding retrieves relevant chunks, then a separate LLM call receives only those passages and the question. The system prompt treats saved text as untrusted data, asks for citations on factual claims, and instructs the model to abstain when evidence is missing. Structured JSON output and citation-ID validation reject incomplete answers and invented source IDs. This checks citation structure, not factual entailment; a model can still misinterpret a passage. The UI makes the original passages inspectable. Responses are not requested to be stored by OpenAI (`store=false`). Saved content is sent to OpenAI for embeddings and relevant passages for answering when that provider is active.

**URL ingestion.** A custom connection resolver validates actual resolved addresses and connects to those validated addresses, maintaining TLS hostname verification. Private/reserved IPs, credentials, nonstandard ports, and unsafe redirects are blocked. Downloads have timeouts, a 2 MB decompressed byte limit, and a 100,000-character extraction limit. JSON bodies are bounded to 512 KiB, including chunked bodies. HTML chrome is stripped with BeautifulSoup. JavaScript rendering, PDFs, paywalls, and authenticated pages are intentionally unsupported. Some websites block automated requests.

**What breaks at scale / production changes.** Exact scans cost O(chunks × dimensions), read vectors into memory for each question, and compete for CPU. SQLite serializes writes, one worker limits ingestion throughput, and the three-second UI polling adds traffic. Before multi-user/public deployment, add authentication and user-scoped retrieval, global rate/cost limits, a proper leased job queue with backoff/dead-letter handling, schema migrations/backups, a vector index (e.g. pgvector), retrieval/grounding evaluations, and metrics/tracing. Run behind TLS and a reverse proxy with request/time limits and outbound network restrictions. This intentionally unauthenticated app binds to loopback by default.

## Structure and verification

The interface uses Turium's published font and visual palette as its reference. See the [UI notes in the developer guide](docs/DEVELOPER_GUIDE.md#frontend-and-chat-logic) for how it is applied to the app.

```text
backend/app/       API, schemas, config, database, worker, chunking, fetcher, AI providers
backend/tests/     Integration and unit tests, including mocked OpenAI HTTP requests
src/components/   Saved-item list, inline ingestion form, questions, item detail
src/hooks.ts       Request cancellation, polling, debounced library search
```

```bash
# Windows: .\.venv\Scripts\python.exe -m pytest -q
.venv/bin/python -m pytest -q
npm test
npm run build
```

Optional full browser checks run against the built UI and a temporary demo database:

```bash
npm run test:e2e
```

The browser suite uses an installed Microsoft Edge. On a machine without Edge, run `npx playwright install msedge` first, or change `channel: 'msedge'` in `playwright.config.ts` to a locally available Playwright Chromium configuration. Screenshots and failure traces go to the ignored `artifacts/` directory. The server is stopped automatically after tests.


API references: [OpenAI embeddings](https://developers.openai.com/api/docs/guides/embeddings), [OpenAI Responses](https://developers.openai.com/api/reference/python/resources/responses/methods/create), [aiohttp custom resolvers](https://docs.aiohttp.org/en/stable/client_advanced.html#resolving-using-custom-nameservers).
