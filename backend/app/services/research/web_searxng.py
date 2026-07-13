# backend/app/services/research/web_searxng.py
"""Web search via a self-hosted SearXNG instance (privacy-first).

Reads SEARXNG_URL from env. Falls back to [] (logged) if unreachable so the
academic adapter still works. fetch_full_text pulls readable page text on keep.
"""
from __future__ import annotations
import hashlib
import logging
import os
from typing import List

import httpx

from .base import SearchAdapter, ResearchResult

log = logging.getLogger("atlas.research.web")

SEARXNG_URL = (os.getenv("SEARXNG_URL") or "http://searxng:8080").rstrip("/")
TIMEOUT = float(os.getenv("RESEARCH_HTTP_TIMEOUT") or "12")


def _hid(s: str) -> str:
    return "w_" + hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


class SearxngAdapter(SearchAdapter):
    name = "web"

    def search(self, query: str, limit: int = 8) -> List[ResearchResult]:
        try:
            r = httpx.get(
                f"{SEARXNG_URL}/search",
                params={"q": query, "format": "json", "safesearch": 1},
                timeout=TIMEOUT,
                headers={
                    "Accept": "application/json",
                    "X-Real-IP": "127.0.0.1",
                    "X-Forwarded-For": "127.0.0.1"
                },
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:                       # noqa: BLE001
            log.warning("web search unavailable: %s", e)
            return []

        out: List[ResearchResult] = []
        for item in (data.get("results") or [])[:limit]:
            url = item.get("url") or ""
            if not url:
                continue
            domain = url.split("/")[2] if "://" in url else url
            out.append(ResearchResult(
                id=_hid(url),
                type="web",
                title=(item.get("title") or domain)[:300],
                url=url,
                snippet=(item.get("content") or "")[:600],
                source_label="Web",
                domain=domain,
                date=item.get("publishedDate"),
            ))
        return out

    def fetch_full_text(self, result: ResearchResult) -> str:
        try:
            r = httpx.get(result.url, timeout=TIMEOUT, follow_redirects=True,
                          headers={"User-Agent": "AtlasLM-Research/1.0"})
            r.raise_for_status()
            html = r.text
        except Exception as e:                       # noqa: BLE001
            log.warning("full-text fetch failed for %s: %s", result.url, e)
            return result.snippet

        # Lightweight readable-text extraction (no extra heavy deps required).
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ").split())
            return text[:20000] or result.snippet
        except Exception:                            # noqa: BLE001
            return result.snippet
