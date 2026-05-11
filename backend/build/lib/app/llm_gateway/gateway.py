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
    # Keep registry shape extensible so OpenAI/Ollama can be re-enabled later.
    registry = {
        "groq": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"],
    }

    @staticmethod
    def _resolve(mode: str, provider: str | None, model: str | None, prompt: str) -> tuple[str, str]:
        if mode == "manual":
            if provider != "groq" or not model or model not in LLMGateway.registry["groq"]:
                raise ValidationError(code="INVALID_MODEL_SELECTION", message="Only Groq models are enabled right now", details={"provider": provider, "model": model}, status_code=400)
            return provider, model
        return ("groq", "llama-3.3-70b-versatile") if len(prompt.split()) > 40 else ("groq", "llama-3.1-8b-instant")

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(0.2), reraise=True)
    async def _groq(self, model: str, prompt: str) -> tuple[str, int, int]:
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
        return text, int(usage.get("prompt_tokens", max(1, len(prompt) // 4))), int(usage.get("completion_tokens", 120))

    async def complete(self, prompt: str, mode: str, provider: str | None, model: str | None) -> LLMResult:
        selected_provider, selected_model = self._resolve(mode, provider, model, prompt)
        start = time.perf_counter()
        try:
            text, pt, ct = await self._groq(selected_model, prompt)
        except Exception as exc:
            raise InfraError(code="LLM_CALL_FAILED", message="Groq call failed", details={"model": selected_model}, status_code=502) from exc

        latency = (time.perf_counter() - start) * 1000
        return LLMResult(text=text, prompt_tokens=pt, completion_tokens=ct, latency_ms=latency, provider="groq", model=selected_model, attempted_provider="groq", attempted_model=selected_model)
