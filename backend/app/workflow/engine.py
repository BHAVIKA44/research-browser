from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.db.models import Citation, EvidenceItem, LLMCall, ToolCall, WorkflowStep
from app.llm_gateway.gateway import LLMGateway
from app.observability.tracing import redact_payload, trace_span
from app.tools.mcp_tools import MCPTools

EVENTS: dict[str, list[dict[str, Any]]] = defaultdict(list)
MAX_NODE_RETRIES = 1
CHECKPOINTER = MemorySaver()


@dataclass
class WorkflowState:
    run_id: str
    query: str
    mode: str
    provider: str | None
    model: str | None
    request_id: str | None = None
    trace_id: str | None = None
    plan: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    failures: list[dict[str, Any]] = field(default_factory=list)


class GraphState(TypedDict):
    workflow: WorkflowState


def emit(run_id: str, event: dict[str, Any]) -> None:
    EVENTS[run_id].append(event)


async def _record_step(db: AsyncSession, run_id: str, node_name: str, status: str, retries: int, started_at: datetime, finished_at: datetime | None = None, error: dict | None = None) -> None:
    db.add(WorkflowStep(run_id=run_id, node_name=node_name, status=status, retries=retries, started_at=started_at, finished_at=finished_at, error=error))
    await db.commit()


def _estimate_cost(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = {"openai": (0.15, 0.60), "groq": (0.05, 0.10), "ollama": (0.0, 0.0)}
    in_rate, out_rate = rates.get(provider, (0.2, 0.8))
    return ((prompt_tokens / 1_000_000) * in_rate) + ((completion_tokens / 1_000_000) * out_rate)


async def planner_node(state: WorkflowState, llm: LLMGateway, db: AsyncSession) -> WorkflowState:
    with trace_span("planner_node", {"run_id": state.run_id, "request_id": state.request_id}):
        r = await llm.complete(f"Create short research plan for: {state.query}", state.mode, state.provider, state.model)
        db.add(LLMCall(run_id=state.run_id, provider=r.provider, model=r.model, prompt_tokens=r.prompt_tokens, completion_tokens=r.completion_tokens, latency_ms=r.latency_ms, estimated_cost_usd=_estimate_cost(r.provider, r.prompt_tokens, r.completion_tokens), success=True))
        await db.commit()
        state.plan = r.text
        emit(state.run_id, {"node": "planner_node", "status": "completed"})
        return state


async def research_node(state: WorkflowState, tools: MCPTools, db: AsyncSession) -> WorkflowState:
    with trace_span("research_node", {"run_id": state.run_id, "request_id": state.request_id}):
        search = await tools.web_search(state.query)
        db.add(ToolCall(run_id=state.run_id, tool_name="web_search", input_payload=redact_payload({"query": state.query}), output_payload=redact_payload(search), latency_ms=search["latency_ms"]))
        dedup = {i["url"]: i for i in search.get("items", [])}.values()
        evidence = []
        for item in dedup:
            try:
                ext = await tools.page_extract(item["url"])
            except Exception as exc:
                emit(state.run_id, {"node": "research_node", "status": "source_skipped", "url": item["url"], "error": str(exc)})
                continue
            db.add(ToolCall(run_id=state.run_id, tool_name="page_extract", input_payload={"url": item["url"]}, output_payload=redact_payload(ext), latency_ms=ext["latency_ms"]))
            ev = {"evidence_id": f"E{len(evidence)+1}", **item, "extracted_text": ext["text"]}
            evidence.append(ev)
            db.add(EvidenceItem(run_id=state.run_id, evidence_id=ev["evidence_id"], url=ev["url"], title=ev["title"], snippet=ev.get("snippet"), extracted_text=ev.get("extracted_text")))
        await db.commit()
        if not evidence:
            raise ValidationError(code="INSUFFICIENT_EVIDENCE", message="Could not find sufficient web evidence for this question", details={"query": state.query}, status_code=422)
        state.evidence = evidence
        emit(state.run_id, {"node": "research_node", "status": "completed", "evidence_count": len(evidence)})
        return state


async def synthesizer_node(state: WorkflowState, llm: LLMGateway, db: AsyncSession) -> WorkflowState:
    with trace_span("synthesizer_node", {"run_id": state.run_id, "request_id": state.request_id}):
        context = "\n".join([f"{e['evidence_id']} {e['title']} {e['url']}" for e in state.evidence])
        r = await llm.complete(f"Answer the question directly using only relevant evidence. Do not mention internal IDs like E1/E2. If evidence is insufficient, say exactly: I don't know based on available evidence. Q: {state.query}\nEvidence:\n{context}", state.mode, state.provider, state.model)
        db.add(LLMCall(run_id=state.run_id, provider=r.provider, model=r.model, prompt_tokens=r.prompt_tokens, completion_tokens=r.completion_tokens, latency_ms=r.latency_ms, estimated_cost_usd=_estimate_cost(r.provider, r.prompt_tokens, r.completion_tokens), success=True))
        q_terms = {t.lower() for t in state.query.split() if len(t) > 2}
        scored: list[tuple[int, dict[str, Any]]] = []
        seen = set()
        for e in state.evidence:
            key = e["url"]
            if key in seen:
                continue
            seen.add(key)
            text_blob = f"{e.get('title','')} {e.get('snippet','')} {e.get('extracted_text','')[:800]}".lower()
            score = sum(1 for t in q_terms if t in text_blob)
            scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [e for score, e in scored if score > 0][:3] or [e for _, e in scored[:3]]
        citation_lines = [f"[{i}] {e['title']} - {e['url']}" for i, e in enumerate(top, start=1)]
        clean_text = r.text.replace("(E1)", "").replace("(E2)", "").replace("(E3)", "")
        clean_text = clean_text.replace("E1", "").replace("E2", "").replace("E3", "")
        state.answer = clean_text.strip() + "\n\nReferences:\n" + "\n".join(citation_lines)
        for e in state.evidence:
            db.add(Citation(run_id=state.run_id, section="final_answer", evidence_id=e["evidence_id"], url=e["url"]))
        await db.commit()
        emit(state.run_id, {"node": "synthesizer_node", "status": "completed"})
        return state


async def validator_node(state: WorkflowState) -> WorkflowState:
    with trace_span("citation_validator_node", {"run_id": state.run_id, "request_id": state.request_id}):
        if not state.evidence:
            raise ValidationError(code="INSUFFICIENT_EVIDENCE", message="No evidence found", details={}, status_code=422)
        if "References:" not in state.answer:
            raise ValidationError(code="CITATION_GROUNDING_FAILED", message="Answer missing references", details={}, status_code=422)
        emit(state.run_id, {"node": "validator_node", "status": "completed"})
        return state


async def _execute_with_retry(node_name: str, state: WorkflowState, func, db: AsyncSession) -> WorkflowState:
    retries = 0
    started_at = datetime.utcnow()
    await _record_step(db, state.run_id, node_name, "started", retries, started_at)
    while True:
        try:
            result = await func(state)
            await _record_step(db, state.run_id, node_name, "completed", retries, started_at, datetime.utcnow())
            return result
        except Exception as exc:
            retries += 1
            failure = {"node": node_name, "retries": retries, "error": str(exc)}
            state.failures.append(failure)
            emit(state.run_id, {"status": "retry", **failure})
            if retries > MAX_NODE_RETRIES:
                await _record_step(db, state.run_id, node_name, "failed", retries, started_at, datetime.utcnow(), {"error": str(exc)})
                emit(state.run_id, {"status": "failed", "node": node_name, "error": str(exc)})
                raise
            await asyncio.sleep(0.05)


def _build_graph(db: AsyncSession, llm: LLMGateway, tools: MCPTools):
    graph = StateGraph(GraphState)

    async def planner(graph_state: GraphState) -> GraphState:
        graph_state["workflow"] = await _execute_with_retry("planner_node", graph_state["workflow"], lambda s: planner_node(s, llm, db), db)
        return graph_state

    async def research(graph_state: GraphState) -> GraphState:
        graph_state["workflow"] = await _execute_with_retry("research_node", graph_state["workflow"], lambda s: research_node(s, tools, db), db)
        return graph_state

    async def synthesizer(graph_state: GraphState) -> GraphState:
        graph_state["workflow"] = await _execute_with_retry("synthesizer_node", graph_state["workflow"], lambda s: synthesizer_node(s, llm, db), db)
        return graph_state

    async def validator(graph_state: GraphState) -> GraphState:
        graph_state["workflow"] = await _execute_with_retry("validator_node", graph_state["workflow"], validator_node, db)
        return graph_state

    graph.add_node("planner", planner)
    graph.add_node("research", research)
    graph.add_node("synthesizer", synthesizer)
    graph.add_node("citation_validator", validator)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "research")
    graph.add_edge("research", "synthesizer")
    graph.add_edge("synthesizer", "citation_validator")
    graph.add_edge("citation_validator", END)
    return graph.compile(checkpointer=CHECKPOINTER)


async def run_graph(state: WorkflowState, db: AsyncSession, thread_id: str | None = None) -> WorkflowState:
    llm = LLMGateway()
    tools = MCPTools()
    app = _build_graph(db, llm, tools)
    config = {"configurable": {"thread_id": thread_id or state.run_id}}
    with trace_span("workflow_run", {"run_id": state.run_id, "request_id": state.request_id, "provider": state.provider, "model": state.model}):
        result = await app.ainvoke({"workflow": state}, config=config)
    return result["workflow"]
