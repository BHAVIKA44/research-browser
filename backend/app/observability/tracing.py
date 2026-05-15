from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from app.core.settings import settings

try:
    from langsmith import trace as ls_trace
except Exception:  # pragma: no cover
    ls_trace = None


SENSITIVE_KEYS = {"authorization", "api_key", "token", "password", "secret"}


def redact_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in SENSITIVE_KEYS:
            clean[key] = "***REDACTED***"
        else:
            clean[key] = value
    return clean


@contextmanager
def trace_span(name: str, metadata: dict[str, Any] | None = None):
    if settings.langsmith_tracing and ls_trace is not None:
        with ls_trace(name=name, project_name=settings.langsmith_project, metadata=redact_payload(metadata or {})):
            yield
    else:
        yield
