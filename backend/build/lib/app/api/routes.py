from fastapi import APIRouter, Depends, Header, Query, Request, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.api import ChatSessionCreate, ChatSessionOut, ErrorResponse, MetricsSummary, QueryRequest, QueryResponse, RunDetail, RunSummary
from app.services.query_service import QueryService
from app.workflow.engine import EVENTS

router = APIRouter(prefix="/api/v1")
svc = QueryService()


@router.post("/sessions", response_model=ChatSessionOut)
async def create_session(payload: ChatSessionCreate, db: AsyncSession = Depends(get_db)):
    s = await svc.create_session(db, payload.title)
    return ChatSessionOut(id=str(s.id), title=s.title, created_at=s.created_at.isoformat())


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    rows = await svc.list_sessions(db)
    return [ChatSessionOut(id=str(s.id), title=s.title, created_at=s.created_at.isoformat()) for s in rows]


@router.post("/query", response_model=QueryResponse, responses={status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse}})
async def create_query(payload: QueryRequest, request: Request, db: AsyncSession = Depends(get_db), idempotency_key: str | None = Header(None)):
    run = await svc.create_run(db, payload.query, payload.mode, payload.provider, payload.model, request.state.request_id, idempotency_key, payload.session_id)
    return QueryResponse(run_id=str(run.id), status=run.status, session_id=str(run.session_id) if run.session_id else None)


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(session_id: str | None = Query(default=None), db: AsyncSession = Depends(get_db)):
    runs = await svc.list_runs(db, session_id=session_id)
    return [RunSummary(run_id=str(r.id), session_id=str(r.session_id) if r.session_id else None, query=r.query, status=r.status, created_at=r.created_at.isoformat()) for r in runs]


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    r = await svc.get_run(db, run_id)
    return RunDetail(run_id=run_id, session_id=str(r.session_id) if r.session_id else None, query=r.query, status=r.status, answer=r.final_answer)


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str):
    async def gen():
        for event in EVENTS.get(run_id, []):
            yield {"event": "step", "data": str(event)}
    return EventSourceResponse(gen())


@router.get("/metrics/summary", response_model=MetricsSummary)
async def metrics_summary(db: AsyncSession = Depends(get_db)):
    return await svc.summary(db)


@router.get("/metrics/timeseries")
async def metrics_timeseries(db: AsyncSession = Depends(get_db)):
    runs = await svc.list_runs(db)
    return {"points": [{"ts": r.created_at.isoformat(), "status": r.status} for r in runs]}


@router.get("/models")
async def models():
    return {"providers": [{"name": "openai", "models": ["gpt-4o-mini", "gpt-4.1"], "capabilities": ["chat", "json"]}, {"name": "groq", "models": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"], "capabilities": ["chat"]}, {"name": "ollama", "models": ["llama3.1", "qwen2.5"], "capabilities": ["chat"]}]}
