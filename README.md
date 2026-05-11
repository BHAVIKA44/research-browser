# Research Browser MVP

Production-grade MVP for cited web-grounded AI research with lightweight multi-agent workflow.

## Architecture
- Backend: FastAPI, Pydantic v2, SQLAlchemy async, Alembic
- Workflow: planner -> research -> synthesizer -> validator
- Tools: `web_search`, `page_extract` only (non-RAG)
- LLM gateway: OpenAI-compatible, Groq, Ollama with manual model mode and auto-route mode
- Observability: run/step/tool/llm persistence and metrics endpoints
- Frontend: React tabs (`Ask`, `Runs`, `Observability`)

## Setup
```bash
docker compose up --build
```

## Environment variables
See `.env.example`.

## API Endpoints
- `GET /health`
- `POST /api/v1/query`
- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/events`
- `GET /api/v1/metrics/summary`
- `GET /api/v1/metrics/timeseries`
- `GET /api/v1/models`

## Reliability/Safety
- Standard error contract:
  - `{ "code": "...", "message": "...", "details": {...}, "request_id": "..." }`
- Request timeout and cancellation mapping
- Idempotency key support on query creation
- Redaction-aware structured logging

## Data Model
- `workflow_runs`
- `workflow_steps`
- `tool_calls`
- `llm_calls`
- `evidence_items`
- `citations`
- `semantic_cache_entries` (feature-flagged default off)

## Tests
- workflow happy path scaffolding
- retry/fallback/manual-vs-auto routing logic
- citation/error-contract invariants

## Limitations
- Frontend is intentionally minimal for MVP UX flow.
- Live provider calls require valid provider API keys and network access.

## Design tradeoffs
- Kept architecture strict and modular first, while keeping multi-agent workflow lightweight.
- Prioritized explicit observability records over hidden implicit behavior.
