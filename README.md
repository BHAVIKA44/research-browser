# Research Browser

Research Browser is a web-grounded AI research application that answers user questions with cited evidence from live web sources.  
It uses a lightweight multi-agent workflow, provider/model routing, and first-class observability for run, tool, and LLM execution.

## System Overview

### Product flow
1. User submits a query from the Ask tab.
2. Workflow runs through planner, research, synthesizer, and validator nodes.
3. Research node calls two tools only: `web_search` and `page_extract`.
4. Evidence is normalized and persisted.
5. Final response is returned with references.
6. Run and call telemetry is available in Runs and Observability views.

### Architecture
- Backend: FastAPI, Pydantic v2, SQLAlchemy async, Alembic
- Workflow engine: LangGraph-style node orchestration with explicit state
- LLM gateway: provider abstraction with manual model mode and auto-route mode
- Tools: non-RAG evidence pipeline using only `web_search` + `page_extract`
- Storage: Postgres for runs, steps, tool calls, llm calls, evidence, citations
- Frontend: React app with `Ask`, `Runs`, and `Observability` tabs

## Repository Layout

```text
backend/app/
  api/
  core/
  db/
  workflow/
  llm_gateway/
  tools/
  observability/
  services/
  schemas/
  utils/
  main.py
frontend/
```

## Local Setup

### 1) Prerequisites
- Docker + Docker Compose
- A valid Groq API key (current active provider)

### 2) Configure environment
Create `.env` from `.env.example` and set required values.

### 3) Start services
```bash
docker compose up --build
```

### 4) Access
- Frontend: `http://localhost:5173`
- Backend API + OpenAPI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## Environment Variables

Defined in `.env.example`. Core settings include:
- `DATABASE_URL`
- `GROQ_API_KEY`
- `REQUEST_TIMEOUT_SECONDS`
- `CORS_ALLOW_ORIGINS`

Provider adapters for OpenAI/Ollama are kept modular in codebase but currently disabled in exposed runtime model list.

## API Contract

### Core endpoints
- `GET /health`
- `POST /api/v1/query`
- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/events` (SSE)
- `GET /api/v1/metrics/summary`
- `GET /api/v1/metrics/timeseries`
- `GET /api/v1/models`

### Error contract
All error responses follow:

```json
{
  "code": "STRING_CODE",
  "message": "Human readable message",
  "details": {},
  "request_id": "uuid"
}
```

### Query example
```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-001" \
  -d '{
    "query": "Compare top approaches for LLM agent reliability in production.",
    "mode": "manual",
    "provider": "groq",
    "model": "llama-3.3-70b-versatile"
  }'
```

## Multi-Agent Workflow

Implemented as four explicit nodes:
1. `planner_node`
2. `research_node`
3. `synthesizer_node`
4. `validator_node`

Execution characteristics:
- Per-node retries
- Failure recording with contextual errors
- Event streaming for live run progress
- Step-level persistence in `workflow_steps`

## Evidence & Citation Grounding

- Search results are deduplicated by URL.
- Extracted page text is attached to evidence records.
- Final response must include references.
- Validator enforces minimum grounding checks before marking run complete.

## Observability

Persisted telemetry:
- Run status timeline (`workflow_runs`, `workflow_steps`)
- Tool inputs/outputs and latency (`tool_calls`)
- LLM metadata: provider, model, tokens, latency, estimated cost (`llm_calls`)

Metrics endpoints expose:
- Total runs
- P50/P95 latency
- Average estimated cost
- Retry/error/fallback counters
- Model usage distribution

## Testing

Run tests:
```bash
docker compose exec backend pytest -q
```

Coverage focus:
- Workflow happy path
- Retry behavior
- Fallback and routing logic
- Manual model selection enforcement
- Citation grounding checks
- Error contract consistency

## Operations Runbook

### Useful log commands
```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs backend --tail=200
```

### Restart services
```bash
docker compose restart backend frontend
```

### Rebuild backend after code changes
```bash
docker compose up -d --build backend
```

## Limitations

- Web extraction quality depends on source accessibility and page structure.
- Some sources block scraping or require JS/paywalls, which may reduce evidence quality.
- Validator is rule-based and intentionally lightweight; it is not a formal fact-checking system.

## Roadmap

- Re-enable additional providers via existing adapter interfaces.
- Improve evidence relevance scoring and citation precision.
- Expand run-level debugging UX for tool and prompt traces.
- Add stricter claim-to-citation mapping checks.

## Design Decisions

- Chose a lightweight multi-agent workflow over heavier orchestration to keep latency and operational complexity low.
- Kept strict boundaries between API, services, workflow, tools, and gateway layers for maintainability.
- Restricted tool surface to two explicit web evidence tools to reduce hidden behavior and improve auditability.
