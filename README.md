# Research Browser

Research Browser is a web-grounded AI research application that generates cited answers from live web evidence.
It uses a lightweight multi-agent workflow orchestrated with LangGraph, provider-aware LLM gateway routing, and dual observability (local DB metrics + LangSmith traces).

## What It Does

1. Accepts user research queries from UI/API.
2. Runs a workflow: planner -> research -> synthesizer -> citation validator.
3. Calls exactly two evidence tools:
   - `web_search`
   - `page_extract`
4. Produces a final answer with references.
5. Persists execution artifacts for auditability and metrics.

## Architecture

### Backend
- FastAPI
- Pydantic v2 + pydantic-settings
- SQLAlchemy async + Alembic
- LangGraph `StateGraph`
- LangSmith (feature-flagged tracing)

### Frontend
- React (single-page app)
- Tabs: `Ask`, `Runs`, `Observability`

### Storage
- PostgreSQL for:
  - workflow runs
  - workflow steps
  - tool calls
  - LLM calls
  - evidence items
  - citations
  - chat sessions

## Workflow Model (LangGraph)

Graph nodes:
1. `planner`
2. `research`
3. `synthesizer`
4. `citation_validator`

Execution properties:
- Explicit typed state object
- Per-node retry with failure metadata capture
- Step timeline persistence (`started/completed/failed`)
- Event emission for live run progress in UI

## LLM Gateway

Implemented with adapter + policy boundaries:
- Provider adapter interface
- Routing policy class (manual vs auto route)
- Fallback chain
- Token/latency/cost accounting persistence

Current runtime exposure is Groq-only in `/api/v1/models` while keeping OpenAI/Ollama adapter slots for future enablement.

## Memory Behavior

Short-term memory is implemented using:
- LangGraph checkpointer (`MemorySaver`) with `thread_id` tied to session.
- Session-aware query context construction from recent completed runs.

Follow-up query handling includes coreference/topic anchoring logic to improve pronoun-based continuity in multi-turn chats.

## Observability

### Local (DB-backed)
- Run/step/tool/LLM telemetry via API:
  - `GET /api/v1/metrics/summary`
  - `GET /api/v1/metrics/timeseries`

### LangSmith (trace-backed)
- Optional trace visibility via:
  - `GET /api/v1/metrics/langsmith`
- Captures workflow + node spans when enabled.

Observability UI shows both local metrics and LangSmith section.

## API Surface

- `GET /health`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions`
- `POST /api/v1/query`
- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/events`
- `GET /api/v1/metrics/summary`
- `GET /api/v1/metrics/timeseries`
- `GET /api/v1/metrics/langsmith`
- `GET /api/v1/models`

### Error Contract

All domain/infrastructure API errors follow:

```json
{
  "code": "STRING_CODE",
  "message": "Human readable message",
  "details": {},
  "request_id": "uuid"
}
```

## Local Setup

### Prerequisites
- Docker + Docker Compose

### Environment
Copy `.env.example` to `.env` and set values.

Key variables:
- `DATABASE_URL`
- `GROQ_API_KEY`
- `REQUEST_TIMEOUT_SECONDS`
- `CORS_ORIGINS`
- `LANGSMITH_TRACING`
- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT`

### Start

```bash
docker compose up -d --build backend frontend
```

### Access
- Frontend: `http://localhost:5173`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## Testing

Run backend tests:

```bash
docker compose exec -T backend bash -lc 'python -m pytest -q tests'
```

Current suite covers:
- routing policy decisions
- manual model enforcement
- fallback behavior
- retry/failure handling
- citation validator checks
- core error contract invariants

## Operations Runbook

### Logs
```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs backend --tail=200
```

### Restart
```bash
docker compose restart backend frontend
```

### Rebuild
```bash
docker compose up -d --build backend frontend
```

## Security Notes

- `.env` and `.env.*` are gitignored.
- `.env.example` remains tracked as a template.
- Structured logging includes redaction logic for sensitive keys.

## Known Limits

- Web extraction quality depends on target site accessibility/content structure.
- Some sites block scraping or serve limited payloads.
- Citation validator is intentionally lightweight (rule-based gate), not a formal fact-verification system.

## Roadmap

1. Persistent LangGraph checkpoint backend (database-backed) beyond in-process saver.
2. Stronger entity memory model (explicit session topic/entity fields).
3. Better source quality heuristics and claim-to-citation alignment.
4. Richer LangSmith trace-to-UI mapping (business-span filtering and deep links).
