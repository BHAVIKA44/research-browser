import asyncio
import re
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InfraError, NotFoundError
from app.core.settings import settings
from app.db.models import ChatSession, LLMCall, WorkflowRun, WorkflowStep
from app.workflow.engine import WorkflowState, run_graph


class QueryService:
    async def create_session(self, db: AsyncSession, title: str) -> ChatSession:
        s = ChatSession(title=title)
        db.add(s)
        await db.commit()
        await db.refresh(s)
        return s

    async def list_sessions(self, db: AsyncSession):
        return (await db.execute(select(ChatSession).order_by(ChatSession.created_at.desc()))).scalars().all()

    @staticmethod
    def _clean_answer_text(text: str) -> str:
        cleaned = re.sub(r"References:[\s\S]*$", "", text, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"Evidence IDs:[\s\S]*$", "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned[:500]

    async def _build_memory_context(self, db: AsyncSession, session_id: str | None) -> str:
        if not session_id:
            return ""
        runs = (await db.execute(select(WorkflowRun).where(WorkflowRun.session_id == session_id, WorkflowRun.status == "completed").order_by(WorkflowRun.created_at.desc()).limit(5))).scalars().all()
        runs = list(reversed(runs))
        if not runs:
            return ""
        lines = []
        for r in runs:
            ans = self._clean_answer_text(r.final_answer or "")
            if ans:
                lines.append(f"Previous Q: {r.query}\nPrevious A: {ans}")
        return "\n".join(lines)

    async def create_run(self, db: AsyncSession, query: str, mode: str, provider: str | None, model: str | None, request_id: str, idempotency_key: str | None, session_id: str | None):
        if idempotency_key:
            existing = await db.scalar(select(WorkflowRun).where(WorkflowRun.idempotency_key == idempotency_key))
            if existing:
                return existing

        if session_id:
            session = await db.scalar(select(ChatSession).where(ChatSession.id == session_id))
            if session is None:
                raise NotFoundError("Session not found", {"session_id": session_id})
        memory_context = await self._build_memory_context(db, session_id)
        effective_query = query if not memory_context else f"{query}\n\nConversation context:\n{memory_context}"

        run = WorkflowRun(session_id=session_id, query=query, mode=mode, provider=provider, model=model, status="running", request_id=request_id, idempotency_key=idempotency_key)
        db.add(run)
        await db.commit()
        await db.refresh(run)

        try:
            state = await asyncio.wait_for(run_graph(WorkflowState(run_id=str(run.id), query=effective_query, mode=mode, provider=provider, model=model), db), timeout=settings.request_timeout_seconds)
            run.final_answer = state.answer
            run.status = "completed"
        except asyncio.TimeoutError as exc:
            run.status = "failed"
            await db.commit()
            raise InfraError(code="WORKFLOW_TIMEOUT", message="Workflow timed out", details={"timeout_seconds": settings.request_timeout_seconds}, status_code=504) from exc
        except asyncio.CancelledError as exc:
            run.status = "failed"
            await db.commit()
            raise InfraError(code="WORKFLOW_CANCELLED", message="Workflow cancelled", details={"run_id": str(run.id)}, status_code=499) from exc
        except Exception:
            run.status = "failed"
            await db.commit()
            raise

        await db.commit()
        await db.refresh(run)
        return run

    async def list_runs(self, db: AsyncSession, session_id: str | None = None):
        q = select(WorkflowRun)
        if session_id:
            q = q.where(WorkflowRun.session_id == session_id)
        return (await db.execute(q.order_by(WorkflowRun.created_at.desc()).limit(100))).scalars().all()

    async def get_run(self, db: AsyncSession, run_id: str) -> WorkflowRun:
        run = await db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id))
        if run is None:
            raise NotFoundError("Run not found", {"run_id": run_id})
        return run

    async def summary(self, db: AsyncSession):
        total_runs = await db.scalar(select(func.count()).select_from(WorkflowRun))
        avg_cost = await db.scalar(select(func.coalesce(func.avg(LLMCall.estimated_cost_usd), 0.0)))
        retry_count = await db.scalar(select(func.coalesce(func.sum(WorkflowStep.retries), 0)).select_from(WorkflowStep))
        error_count = await db.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.status == "failed"))
        fallback_count = await db.scalar(select(func.count()).select_from(LLMCall).where(LLMCall.provider == "openai", LLMCall.model == "gpt-4o-mini"))
        latencies = list((await db.execute(select(LLMCall.latency_ms).order_by(LLMCall.latency_ms))).scalars().all())
        p50 = latencies[int((len(latencies) - 1) * 0.5)] if latencies else 0.0
        p95 = latencies[int((len(latencies) - 1) * 0.95)] if latencies else 0.0
        usage_rows = (await db.execute(select(LLMCall.provider, LLMCall.model, func.count()).group_by(LLMCall.provider, LLMCall.model))).all()
        usage = [{"provider": p, "model": m, "count": c} for p, m, c in usage_rows]
        return {"total_runs": int(total_runs or 0), "p50_latency_ms": float(p50), "p95_latency_ms": float(p95), "avg_cost_usd": float(avg_cost or 0.0), "fallback_count": int(fallback_count or 0), "retry_count": int(retry_count or 0), "error_count": int(error_count or 0), "cache_hit_rate": 0.0, "model_usage": usage}
