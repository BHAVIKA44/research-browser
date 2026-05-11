import re
import time
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.core.exceptions import InfraError
from app.core.settings import settings


class MCPTools:
    @staticmethod
    def _condense_query(query: str) -> str:
        q = query.split("Conversation context:")[0].strip()
        lines = [ln.strip() for ln in q.splitlines() if ln.strip()]
        if not lines:
            return ""

        candidate = ""
        for i, line in enumerate(lines):
            lowered = line.lower()
            if lowered.startswith("research question:") or lowered.startswith("question:"):
                after = re.sub(r"^(research question:|question:)\s*", "", line, flags=re.IGNORECASE).strip()
                if after:
                    candidate = after
                    break
                if i + 1 < len(lines):
                    candidate = lines[i + 1].strip()
                    break
            if lowered.startswith("requirements:"):
                continue
            if lowered[:2].isdigit() and lowered[1:2] == ")":
                continue
            if lowered[:2].isdigit() and lowered[1:2] == ".":
                continue
            candidate = line
            break

        if not candidate:
            candidate = q

        candidate = re.sub(r"[^\w\s\-\?]", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if not candidate:
            # Last-resort fallback so we never send an empty search query.
            candidate = re.sub(r"\s+", " ", re.sub(r"[^\w\s\-\?]", " ", q)).strip()
        return candidate[:180]

    async def web_search(self, query: str) -> dict:
        start = time.perf_counter()
        clean_query = self._condense_query(query)
        if not clean_query:
            # Hard guard: avoid empty searches by extracting signal words from original query.
            tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]{2,}", query or "")
            clean_query = " ".join(tokens[:24]).strip()
        if not clean_query:
            raise InfraError(code="WEB_SEARCH_FAILED", message="web_search query is empty after normalization", details={"query": ""}, status_code=502)
        for url in ["https://duckduckgo.com/html/", "https://html.duckduckgo.com/html/"]:
            try:
                async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
                    resp = await client.get(url, params={"q": clean_query}, headers={"User-Agent": "Mozilla/5.0"})
                    resp.raise_for_status()
                items = self._parse_duckduckgo_results(resp.text)
                if items:
                    return {"items": items, "latency_ms": (time.perf_counter() - start) * 1000, "search_query": clean_query}
            except Exception:
                continue
        raise InfraError(code="WEB_SEARCH_FAILED", message="web_search returned no parsable results", details={"query": clean_query}, status_code=502)

    @staticmethod
    def _normalize_result_url(link: str) -> str:
        link = unescape(link)
        if link.startswith("//"):
            link = "https:" + link
        parsed = urlparse(link)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            q = parse_qs(parsed.query)
            uddg = q.get("uddg", [None])[0]
            if uddg:
                return unquote(uddg)
        return link

    def _parse_duckduckgo_results(self, html: str) -> list[dict]:
        pattern = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
        snippet_pattern = re.compile(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>|<div[^>]*class="result__snippet"[^>]*>(.*?)</div>', re.IGNORECASE | re.DOTALL)
        links = pattern.findall(html)
        snippets = snippet_pattern.findall(html)
        items = []
        for idx, (link, title_html) in enumerate(links[:8]):
            norm_link = self._normalize_result_url(link)
            title = unescape(re.sub(r"<.*?>", "", title_html)).strip()
            snippet_src = snippets[idx][0] or snippets[idx][1] if idx < len(snippets) else ""
            snippet = unescape(re.sub(r"<.*?>", "", snippet_src)).strip()
            if title and norm_link.startswith("http"):
                items.append({"url": norm_link, "title": title, "snippet": snippet})
        return items

    async def page_extract(self, url: str) -> dict:
        start = time.perf_counter()
        safe_url = self._normalize_result_url(url)
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds, follow_redirects=True) as client:
            resp = await client.get(safe_url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        raw = resp.text
        text = re.sub(r"<script[\\s\\S]*?</script>", " ", raw, flags=re.IGNORECASE)
        text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(re.sub(r"\\s+", " ", text)).strip()
        return {"url": safe_url, "text": text[:8000], "latency_ms": (time.perf_counter() - start) * 1000}
