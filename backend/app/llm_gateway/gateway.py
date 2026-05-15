from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

from app.core.exceptions import InfraError, ValidationError
from app.core.settings import settings


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    provider: str
    model: str
    attempted_provider: str
    attempted_model: str


class ProviderAdapter(Protocol):
    async def complete(self, model: str, prompt: str) -> tuple[str, int, int]:
        ...


class RoutingPolicy:
    def select(self, prompt: str) -> tuple[str, str]:
        if len(prompt.split()) >= 12:
            return "groq", "llama-3.3-70b-versatile"
        return "groq", "llama-3.1-8b-instant"


class GroqAdapter:
    @retry(stop=stop_after_attempt(2), wait=wait_fixed(0.2), reraise=True)
    async def complete(self, model: str, prompt: str) -> tuple[str, int, int]:
        headers = {"Content-Type": "application/json"}
        if settings.groq_api_key:
            headers["Authorization"] = f"Bearer {settings.groq_api_key}"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        pt = int(usage.get("prompt_tokens", max(1, len(prompt) // 4)))
        ct = int(usage.get("completion_tokens", 120))
        return text, pt, ct


class OpenAICompatibleAdapter:
    async def complete(self, model: str, prompt: str) -> tuple[str, int, int]:
        raise InfraError(code="PROVIDER_DISABLED", message="OpenAI adapter is disabled in current runtime", details={"provider": "openai", "model": model}, status_code=400)


class OllamaAdapter:
    async def complete(self, model: str, prompt: str) -> tuple[str, int, int]:
        raise InfraError(code="PROVIDER_DISABLED", message="Ollama adapter is disabled in current runtime", details={"provider": "ollama", "model": model}, status_code=400)


class LLMGateway:
    registry = {
        "groq": {"models": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"], "capabilities": {"chat"}},
        "openai": {"models": [], "capabilities": {"chat"}},
        "ollama": {"models": [], "capabilities": {"chat"}},
    }

    def __init__(self) -> None:
        self.adapters: dict[str, ProviderAdapter] = {
            "groq": GroqAdapter(),
            "openai": OpenAICompatibleAdapter(),
            "ollama": OllamaAdapter(),
        }
        self.routing_policy = RoutingPolicy()
        self.fallback_chain = [("groq", "llama-3.1-8b-instant")]

    @classmethod
    def active_models(cls) -> list[dict]:
        return [{"name": "groq", "models": cls.registry["groq"]["models"], "capabilities": ["chat"]}]

    def _resolve(self, mode: str, provider: str | None, model: str | None, prompt: str) -> tuple[str, str]:
        if mode == "manual":
            if provider != "groq" or not model or model not in self.registry["groq"]["models"]:
                raise ValidationError(code="INVALID_MODEL_SELECTION", message="Only Groq models are enabled right now", details={"provider": provider, "model": model}, status_code=400)
            return provider, model
        return self.routing_policy.select(prompt)

    async def complete(self, prompt: str, mode: str, provider: str | None, model: str | None) -> LLMResult:
        selected_provider, selected_model = self._resolve(mode, provider, model, prompt)
        attempts = [(selected_provider, selected_model)] + [p for p in self.fallback_chain if p != (selected_provider, selected_model)]
        last_exc: Exception | None = None
        for attempted_provider, attempted_model in attempts:
            start = time.perf_counter()
            try:
                adapter = self.adapters[attempted_provider]
                text, pt, ct = await adapter.complete(attempted_model, prompt)
                latency = (time.perf_counter() - start) * 1000
                return LLMResult(
                    text=text,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    latency_ms=latency,
                    provider=attempted_provider,
                    model=attempted_model,
                    attempted_provider=attempted_provider,
                    attempted_model=attempted_model,
                )
            except Exception as exc:
                last_exc = exc
                continue
        raise InfraError(code="LLM_CALL_FAILED", message="All provider attempts failed", details={"selected_provider": selected_provider, "selected_model": selected_model}, status_code=502) from last_exc
