from typing import Any
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str


class QueryRequest(BaseModel):
    query: str = Field(..., examples=["What are latest AI agent reliability techniques?"])
    mode: str = Field("manual", examples=["manual", "auto"])
    provider: str | None = Field(default=None, examples=["openai"])
    model: str | None = Field(default=None, examples=["gpt-4.1"])
    session_id: str | None = None


class QueryResponse(BaseModel):
    run_id: str
    status: str
    session_id: str | None = None


class ChatSessionCreate(BaseModel):
    title: str = "New Chat"


class ChatSessionOut(BaseModel):
    id: str
    title: str
    created_at: str


class RunSummary(BaseModel):
    run_id: str
    session_id: str | None
    query: str
    status: str
    created_at: str


class RunDetail(BaseModel):
    run_id: str
    session_id: str | None
    query: str
    status: str
    answer: str | None


class ModelUsagePoint(BaseModel):
    provider: str
    model: str
    count: int


class MetricsSummary(BaseModel):
    total_runs: int
    p50_latency_ms: float
    p95_latency_ms: float
    avg_cost_usd: float
    fallback_count: int
    retry_count: int
    error_count: int
    cache_hit_rate: float
    model_usage: list[ModelUsagePoint] = []
