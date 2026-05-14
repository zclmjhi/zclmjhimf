"""
Financial Times API source.

Uses the FT Developer API (developer.ft.com) to fetch recent articles.
Requires an API key from the FT Developer Portal.

To activate:
  1. Set the FT_API_KEY secret:
       claude agent secrets set FT_API_KEY your-key-here
  2. Add one line to sources/__init__.py:
       from .financial_times import FinancialTimesSource
  3. Append FinancialTimesSource to REGISTERED_SOURCES

API docs: https://developer.ft.com/portal/docs-api-v1-reference-search-search
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx

import config
from sources.base import FeedItem


_API_BASE = "https://api.ft.com"
_SEARCH_PATH = "/content/search/v1"
_CONTENT_PATH = "/content"
_PAGE_SIZE = 25


class FinancialTimesSource:

    SOURCE_NAME = "Financial Times"

    @classmethod
    async def fetch(cls) -> list[FeedItem]:
        if not config.FT_API_KEY:
            print("[FT] No API key configured — skipping")
            return []

        # Fetch the most recent articles published in the last hour.
        # The monitoring loop deduplicates by URL, so fetching a broad
        # recent window on every poll is safe — seen items are silently skipped.
        query = {
            "queryString": "lastPublishDateTime:>now-1h",
            "queryContext": {"curations": ["ARTICLES"]},
            "resultContext": {
                "maxResults": _PAGE_SIZE,
                "sortOrder": "DESC",
                "sortField": "lastPublishDateTime",
                "aspects": ["title", "summary", "lifecycle", "location"],
            },
        }

        try:
            async with httpx.AsyncClient(
                timeout=30,
                headers={
                    "X-Api-Key": config.FT_API_KEY,
                    "Accept": "application/json",
                    "User-Agent": "MontfortCoverageAgent/1.0",
                },
            ) as client:
                response = await client.post(
                    f"{_API_BASE}{_SEARCH_PATH}",
                    json=query,
                )
                response.raise_for_status()
                data = response.json()

            return cls._parse_response(data)

        except Exception as exc:
            print(f"[FT] Fetch failed: {exc}")
            return []

    @classmethod
    def _parse_response(cls, data: dict) -> list[FeedItem]:
        items: list[FeedItem] = []

        results = (
            data.get("results", [{}])[0]
            .get("results", [])
        )

        for result in results:
            # FT API uses aspect objects keyed by aspect name
            location = result.get("aspects", {}).get("location", {})
            url = location.get("location", "")
            if not url:
                continue

            title_aspect = result.get("aspects", {}).get("title", {})
            headline = title_aspect.get("title", "").strip()

            summary_aspect = result.get("aspects", {}).get("summary", {})
            summary = summary_aspect.get("excerpt", "").strip()

            lifecycle = result.get("aspects", {}).get("lifecycle", {})
            published_raw = lifecycle.get("lastPublishDateTime", "")
            published_at: str | None = None
            if published_raw:
                try:
                    dt = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                    published_at = dt.isoformat()
                except ValueError:
                    pass

            content_hash = hashlib.sha256(
                (headline + summary).encode()
            ).hexdigest()

            items.append(FeedItem(
                url=url,
                headline=headline,
                source_name=cls.SOURCE_NAME,
                summary=summary,
                published_at=published_at,
                content_hash=content_hash,
                raw_url=url,
            ))

        return items
