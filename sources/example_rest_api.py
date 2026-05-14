"""
Example: adding a new source module using a generic REST API.

This file demonstrates the full pattern for a publication REST API source.
It is not registered by default — to activate it:
  1. Fill in the API details below
  2. Add `from .example_rest_api import PublicationRestApiSource` to sources/__init__.py
  3. Append `PublicationRestApiSource` to REGISTERED_SOURCES

The monitoring loop will then call fetch() on this source on every poll.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import httpx

from sources.base import FeedItem


# ---------------------------------------------------------------------------
# Configuration — set these as environment variables or extend config.py
# ---------------------------------------------------------------------------

API_BASE_URL = os.environ.get("PUBLICATION_API_BASE_URL", "https://api.example-publication.com/v1")
API_KEY = os.environ.get("PUBLICATION_API_KEY", "")
SOURCE_NAME = os.environ.get("PUBLICATION_SOURCE_NAME", "Example Publication")

# Maximum articles to fetch per poll
PAGE_SIZE = 50


# ---------------------------------------------------------------------------
# Source class
# ---------------------------------------------------------------------------

class PublicationRestApiSource:
    """
    Fetches recent articles from a publication REST API.

    Assumes a JSON response like:
      {
        "articles": [
          {
            "id": "abc123",
            "title": "Article headline",
            "summary": "Brief description",
            "url": "https://example-publication.com/article/abc123",
            "published_at": "2026-05-14T09:00:00Z",
            "source": "Example Publication"
          },
          ...
        ]
      }

    Adapt _parse_response() for your publication's actual response shape.
    """

    SOURCE_NAME = SOURCE_NAME

    @classmethod
    async def fetch(cls) -> list[FeedItem]:
        if not API_KEY:
            print(f"[{cls.SOURCE_NAME}] No API key configured — skipping")
            return []

        try:
            async with httpx.AsyncClient(
                timeout=30,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Accept": "application/json",
                    "User-Agent": "MontfortCoverageAgent/1.0",
                },
            ) as client:
                response = await client.get(
                    f"{API_BASE_URL}/articles",
                    params={"limit": PAGE_SIZE, "sort": "published_desc"},
                )
                response.raise_for_status()
                data = response.json()

            return cls._parse_response(data)

        except Exception as exc:
            print(f"[{cls.SOURCE_NAME}] Fetch failed: {exc}")
            return []

    @classmethod
    def _parse_response(cls, data: dict) -> list[FeedItem]:
        items: list[FeedItem] = []

        for article in data.get("articles", []):
            url = article.get("url", "")
            if not url:
                continue

            headline = article.get("title", "").strip()
            summary = article.get("summary", "").strip()
            published_at = article.get("published_at")

            # Normalise published_at to ISO format if needed
            if published_at and not published_at.endswith("+00:00"):
                try:
                    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    published_at = dt.isoformat()
                except ValueError:
                    published_at = None

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
