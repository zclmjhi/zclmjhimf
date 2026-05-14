"""
Google News RSS source — automatic, no manual setup required.

Constructs Google News search RSS URLs from the keywords already in the
client registry and active briefs. Every registered client and every brief
extra_keyword is monitored automatically — no feed URLs to configure.

Google News RSS format:
  https://news.google.com/rss/search?q=QUERY&hl=en-GB&gl=GB&ceid=GB:en

Results are deduplicated by URL in the monitoring loop, so the same article
appearing across multiple keyword searches is only ever delivered once.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timezone

import httpx

import storage
from sources.base import FeedItem
from sources.google_alerts import _unwrap_google_url


_BASE_URL = "https://news.google.com/rss/search"
_REGION = "en-GB"
_GL = "GB"
_CEID = "GB:en"


def _feed_url_for_query(query: str) -> str:
    params = urllib.parse.urlencode({
        "q": query,
        "hl": _REGION,
        "gl": _GL,
        "ceid": _CEID,
    })
    return f"{_BASE_URL}?{params}"


def _collect_keywords() -> dict[str, str]:
    """
    Return a mapping of keyword → source label for every keyword that
    should currently be monitored.

    Sources:
    - Every keyword for every registered client
    - Every extra_keyword across all active briefs

    Deduplicates so the same keyword is only fetched once even if it
    appears in multiple clients or briefs.
    """
    keywords: dict[str, str] = {}  # keyword → label

    for client in storage.list_clients():
        for kw in json.loads(client["keywords"]):
            kw = kw.strip()
            if kw and kw.lower() not in {k.lower() for k in keywords}:
                keywords[kw] = client["name"]

    for brief in storage.list_active_briefs():
        for kw in json.loads(brief["extra_keywords"]):
            kw = kw.strip()
            if kw and kw.lower() not in {k.lower() for k in keywords}:
                keywords[kw] = kw  # label is the keyword itself

    return keywords


def _parse_rss(xml_text: str, source_label: str, keyword: str) -> list[FeedItem]:
    items: list[FeedItem] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    channel = root.find("channel") or root
    for item_el in channel.findall("item"):
        link_el = item_el.find("link")
        raw_url = (link_el.text or "").strip() if link_el is not None else ""
        clean_url = _unwrap_google_url(raw_url)

        title_el = item_el.find("title")
        headline = (title_el.text or "").strip() if title_el is not None else ""

        desc_el = item_el.find("description")
        summary_raw = (desc_el.text or "").strip() if desc_el is not None else ""
        summary = re.sub(r"<[^>]+>", " ", summary_raw).strip()
        summary = re.sub(r"\s+", " ", summary)

        pub_el = item_el.find("pubDate")
        published_at = (pub_el.text or "").strip() if pub_el is not None else None

        # Source name often appears in <source> child element
        src_el = item_el.find("source")
        source_name = (src_el.text or source_label).strip() if src_el is not None else source_label

        content_hash = hashlib.sha256((headline + summary).encode()).hexdigest()

        items.append(FeedItem(
            url=clean_url,
            headline=headline,
            source_name=source_name,
            summary=summary,
            published_at=published_at,
            content_hash=content_hash,
            raw_url=raw_url,
            extra={"search_keyword": keyword},
        ))

    return items


class GoogleNewsSource:
    """
    Polls Google News RSS for every keyword in the client registry and
    active briefs. Requires no manual configuration — keywords drive it.
    """

    SOURCE_NAME = "Google News"

    @classmethod
    async def fetch(cls) -> list[FeedItem]:
        keywords = _collect_keywords()
        if not keywords:
            return []

        all_items: list[FeedItem] = []

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "MontfortCoverageAgent/1.0"},
        ) as client:
            for keyword, label in keywords.items():
                url = _feed_url_for_query(keyword)
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    items = _parse_rss(response.text, label, keyword)
                    all_items.extend(items)
                except Exception as exc:
                    print(f"[GoogleNewsSource] Failed for '{keyword}': {exc}")

        return all_items
