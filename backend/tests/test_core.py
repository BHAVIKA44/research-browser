import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.llm_gateway.gateway import LLMGateway


@pytest.mark.asyncio
async def test_manual_model_respected():
    g = LLMGateway()
    with pytest.raises(ValidationError):
        await g.complete("hello", "manual", "openai", "nonexistent")


@pytest.mark.asyncio
async def test_auto_router_decision_logic():
    g = LLMGateway()
    p1, m1 = g._resolve("auto", None, None, "short query")
    p2, m2 = g._resolve("auto", None, None, "this is a long complex query that should route to stronger model")
    assert (p1, m1) == ("groq", "llama-3.1-8b-instant")
    assert (p2, m2) == ("groq", "llama-3.3-70b-versatile")


def test_not_found_error_contract_fields():
    err = NotFoundError("Run not found", {"run_id": "abc"})
    assert err.code == "NOT_FOUND"
    assert err.status_code == 404
    assert err.details == {"run_id": "abc"}


def test_validation_error_shape():
    err = ValidationError(code="VALIDATION_ERROR", message="bad", details={"f": "x"}, status_code=400)
    assert err.code == "VALIDATION_ERROR"
    assert err.status_code == 400
