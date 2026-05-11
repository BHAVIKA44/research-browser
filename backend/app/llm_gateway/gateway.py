import time
from dataclasses import dataclass

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


class LLMGateway:
    registry = {
        "openai": ["gpt-4o-mini", "gpt-4.1"],
        "groq": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"],
        "ollama": ["llama3.1", "qwen2.5"],
    }

    @staticmethod
    def _resolve(mode: str, provider: str | None, model: str | None, prompt: str) -> tuple[str, str]:
        if mode == "manual":
            if not provider or not model or model not in LLMGateway.registry.get(provider, []):
                raise ValidationError(code="INVALID_MODEL_SELECTION", message="Manual model selection invalid", details={"provider": provider, "model": model}, status_code=400)
            return provider, model
        return ("openai", "gpt-4.1") if len(prompt.split()) > 10 else ("groq", "llama-3.1-8b-instant")

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(0.2), reraise=True)
    async def _openai_like(self, base_url: str, api_key: str | None, model: str, prompt: str) -> tuple[str, int, int]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return text, int(usage.get("prompt_tokens", max(1, len(prompt) // 4))), int(usage.get("completion_tokens", 120))

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(0.2), reraise=True)
    async def _ollama(self, model: str, prompt: str) -> tuple[str, int, int]:
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["message"]["content"], max(1, len(prompt) // 4), 120

    async def _attempt(self, provider: str, model: str, prompt: str) -> tuple[str, int, int]:
        if provider == "openai":
            return await self._openai_like("https://api.openai.com/v1", settings.openai_api_key, model, prompt)
        if provider == "groq":
            return await self._openai_like("https://api.groq.com/openai/v1", settings.groq_api_key, model, prompt)
        return await self._ollama(model, prompt)

    async def complete(self, prompt: str, mode: str, provider: str | None, model: str | None) -> LLMResult:
        selected_provider, selected_model = self._resolve(mode, provider, model, prompt)
        start = time.perf_counter()

        fallback_chain = [(selected_provider, selected_model)]
        if ("groq", "llama-3.1-8b-instant") not in fallback_chain:
            fallback_chain.append(("groq", "llama-3.1-8b-instant"))
        if ("openai", "gpt-4o-mini") not in fallback_chain:
            fallback_chain.append(("openai", "gpt-4o-mini"))
        if ("ollama", "llama3.1") not in fallback_chain:
            fallback_chain.append(("ollama", "llama3.1"))

        last_exc = None
        for p, m in fallback_chain:
            try:
                text, pt, ct = await self._attempt(p, m, prompt)
                latency = (time.perf_counter() - start) * 1000
                return LLMResult(text=text, prompt_tokens=pt, completion_tokens=ct, latency_ms=latency, provider=p, model=m, attempted_provider=p, attempted_model=m)
            except Exception as exc:
                last_exc = exc
                continue

        raise InfraError(code="LLM_CALL_FAILED", message="Provider call failed after fallback", details={"selected_provider": selected_provider, "selected_model": selected_model}, status_code=502) from last_exc
