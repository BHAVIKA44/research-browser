import pytest

from app.core.exceptions import InfraError, ValidationError
from app.llm_gateway.gateway import LLMGateway
from app.workflow.engine import WorkflowState, _execute_with_retry, validator_node


class _DummyDB:
    def add(self, _):
        return None

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_validator_rejects_missing_references():
    state = WorkflowState(run_id="r1", query="q", mode="manual", provider="groq", model="llama-3.1-8b-instant", evidence=[{"evidence_id": "E1"}], answer="No refs")
    with pytest.raises(ValidationError) as exc:
        await validator_node(state)
    assert exc.value.code == "CITATION_GROUNDING_FAILED"


@pytest.mark.asyncio
async def test_node_retry_records_failure_after_limit():
    state = WorkflowState(run_id="r2", query="q", mode="manual", provider="groq", model="llama-3.1-8b-instant")

    async def always_fail(_state):
        raise InfraError(code="X", message="boom", details={}, status_code=500)

    with pytest.raises(InfraError):
        await _execute_with_retry("test_node", state, always_fail, _DummyDB())
    assert state.failures
    assert state.failures[-1]["node"] == "test_node"


@pytest.mark.asyncio
async def test_gateway_fallback_when_primary_fails(monkeypatch):
    gateway = LLMGateway()
    primary = ("groq", "llama-3.3-70b-versatile")
    fallback = ("groq", "llama-3.1-8b-instant")
    gateway.fallback_chain = [fallback]

    calls = []

    async def fake_complete(model: str, prompt: str):
        calls.append(model)
        if model == primary[1]:
            raise RuntimeError("primary failed")
        return ("ok", 10, 5)

    monkeypatch.setattr(gateway.adapters["groq"], "complete", fake_complete)
    result = await gateway.complete(
        "this is a long complex query requiring stronger model and fallback with citations reliability retries and validation controls",
        "auto",
        None,
        None,
    )
    assert result.model == fallback[1]
    assert calls[0] == primary[1]
