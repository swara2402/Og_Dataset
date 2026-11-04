"""Extensible source-provider interface for the originality module.

The default provider uses DuckDuckGo's public HTML endpoint. It is deliberately
conservative: it only runs when the user explicitly starts a source check, it
only sends individual sentences/phrases (never the full document), and it
reports its scope honestly.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import List
from urllib.parse import parse_qs, unquote, urlparse

import httpx

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


@dataclass
class SourceResult:
    title: str
    url: str
    snippet: str = ""
    provider: str = "duckduckgo"


class SourceProvider:
    name = "base"

    async def search(self, query: str, max_results: int = 5) -> List[SourceResult]:
        raise NotImplementedError

    async def fetch_text(self, url: str, max_chars: int = 120_000) -> str:
        return ""


def _clean_url(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        params = parse_qs(parsed.query)
        if params.get("uddg"):
            return unquote(params["uddg"][0])
    return href


def _strip_html(html: str) -> str:
    if BS4_AVAILABLE:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text(" ")
    else:
        text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class DuckDuckGoProvider(SourceProvider):
    name = "duckduckgo"

    def __init__(
        self,
        timeout: float = 12.0,
        user_agent: str = "Mozilla/5.0",
        max_pages: int = 2,
    ):
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_pages = max_pages
        self._lock = asyncio.Lock()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={
                "User-Agent": self.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml",
            },
            follow_redirects=True,
        )

    async def search(self, query: str, max_results: int = 5) -> List[SourceResult]:
        # Be polite to the public endpoint.
        async with self._lock:
            await asyncio.sleep(0.4)
            async with self._client() as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query, "kl": "us-en"},
                )
        if response.status_code >= 400:
            return []
        return self._parse_results(response.text, max_results)

    def _parse_results(self, html: str, max_results: int) -> List[SourceResult]:
        results: List[SourceResult] = []
        if BS4_AVAILABLE:
            soup = BeautifulSoup(html, "html.parser")
            for node in soup.select(".result"):
                anchor = node.select_one("a.result__a")
                if not anchor:
                    continue
                title = anchor.get_text(" ", strip=True)
                href = _clean_url(anchor.get("href", ""))
                snippet_node = node.select_one(".result__snippet")
                snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""
                if href and title:
                    results.append(SourceResult(title, href, snippet, self.name))
                if len(results) >= max_results:
                    break
        else:
            pattern = re.compile(
                r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I
            )
            for href, title_html in pattern.findall(html):
                title = _strip_html(title_html)
                results.append(SourceResult(title, _clean_url(href), "", self.name))
                if len(results) >= max_results:
                    break
        return results

    async def fetch_text(self, url: str, max_chars: int = 120_000) -> str:
        if not url.startswith(("http://", "https://")):
            return ""
        try:
            async with self._client() as client:
                response = await client.get(url)
            if response.status_code >= 400:
                return ""
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type and "text" not in content_type:
                return ""
            return _strip_html(response.text)[:max_chars]
        except Exception:
            return ""


class NullProvider(SourceProvider):
    name = "none"

    async def search(self, query: str, max_results: int = 5) -> List[SourceResult]:
        return []
