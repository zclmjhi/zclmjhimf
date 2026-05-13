"""
Example handler: Generic REST API source.

Use this as the template when adding a new API-based source (e.g. Green Street News).

Steps to add a real source:
  1. Copy this file to handlers/<source_name>.py
  2. Set `name` to a short snake_case identifier
  3. Fill in _BASE_URL and the request logic in `_fetch_page()`
  4. Map the API response fields to NormalisedItem in `_parse_item()`
  5. In agent.py, import your class and append it to HANDLER_CLASSES
  6. Add any config keys your handler needs to registry.json
  7. Add any credentials to .env

That's it — no other files change.
"""
import logging
import os
from datetime import datetime, timezone

import requests

from handlers.base import BaseHandler, NormalisedItem

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.example.com/v1/articles"
_REQUEST_TIMEOUT = 15


class RestApiExampleHandler(BaseHandler):
    """
    Fetches articles from a REST API that returns JSON.

    Expected registry.json additions per client (optional):
        "rest_api_categories": ["infrastructure", "private-equity"]

    Expected .env additions:
        REST_API_KEY=your-api-key
    """

    name = "rest_api_example"

    def fetch(self) -> list[NormalisedItem]:
        api_key = os.environ.get("REST_API_KEY", "")
        if not api_key:
            logger.warning("REST_API_KEY not set — skipping %s handler", self.name)
            return []

        items: list[NormalisedItem] = []
        clients = self.config.get("clients", [])

        for client in clients:
            categories = client.get("rest_api_categories", [])
            for category in categories:
                items.extend(self._fetch_page(api_key, category))

        return items

    def _fetch_page(self, api_key: str, category: str) -> list[NormalisedItem]:
        logger.info("Fetching %s articles from REST API for category '%s'", self.name, category)
        try:
            response = requests.get(
                _BASE_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                params={"category": category, "limit": 50},
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("REST API fetch failed for category '%s': %s", category, exc)
            return []

        data = response.json()
        # Adapt the key names below to match the real API response shape
        articles = data.get("articles") or data.get("results") or data.get("data") or []
        return [self._parse_item(a) for a in articles if self._parse_item(a)]

    def _parse_item(self, raw: dict) -> NormalisedItem | None:
        title = raw.get("title") or raw.get("headline", "")
        url = raw.get("url") or raw.get("link", "")
        if not title or not url:
            return None

        summary = raw.get("summary") or raw.get("description") or raw.get("abstract", "")
        pub_raw = raw.get("published_at") or raw.get("publishedAt") or raw.get("date", "")
        try:
            published_at = datetime.fromisoformat(pub_raw)
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            published_at = datetime.now(timezone.utc)

        return NormalisedItem(
            title=title,
            url=url,
            summary=summary,
            source=self.name,
            published_at=published_at,
        )
