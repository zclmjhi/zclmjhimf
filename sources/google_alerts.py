"""
Google Alerts RSS source.

Google Alerts delivers results as RSS feeds. Each feed URL corresponds to
one alert query. The feed entries wrap the real article URL in a Google
redirect; this module always unwraps to the destination URL.

Feed URLs are stored in the google_alert_feeds table and associated with
a client name. The monitoring loop uses that association to tell which
client a match belongs to — but this module is oblivious to that: it
simply returns everything it finds in all registered feeds.
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
from datetime import timezone

import xml.etree.ElementTree as ET
import httpx

import storage
from sources.base import FeedItem


# XML namespaces used in Atom feeds (Google Alerts uses Atom)
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
}


def _unwrap_google_url(raw_url: str) -> str:
    """
    Google Alerts RSS entries have URLs like:
      https://news.google.com/rss/articles/...?url=<encoded>&...
    or redirect chains via:
      https://www.google.com/url?q=<encoded>&...

    Extract the real destination URL.
    """
    parsed = urllib.parse.urlparse(raw_url)

    # Direct ?url= parameter (common in newer feeds)
    params = urllib.parse.parse_qs(parsed.query)
    if "url" in params:
        return params["url"][0]

    # ?q= parameter (google.com/url redirect style)
    if "q" in params:
        return params["q"][0]

    # Fall back to the raw URL
    return raw_url


def _parse_feed_xml(xml_text: str, source_name: str, client_name: str, feed_url: str) -> list[FeedItem]:
    """Parse Atom or RSS XML into FeedItem list."""
    items: list[FeedItem] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    # Detect format: Atom has <feed>, RSS has <rss> or <channel>
    tag = root.tag.lower()
    is_atom = "atom" in tag or root.tag == "{http://www.w3.org/2005/Atom}feed"

    if is_atom:
        entries = root.findall("{http://www.w3.org/2005/Atom}entry")
        for entry in entries:
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            raw_url = (link_el.get("href") or "") if link_el is not None else ""

            title_el = entry.find("{http://www.w3.org/2005/Atom}title")
            headline = (title_el.text or "").strip() if title_el is not None else ""

            summary_el = entry.find("{http://www.w3.org/2005/Atom}summary")
            summary_raw = (summary_el.text or "").strip() if summary_el is not None else ""

            pub_el = entry.find("{http://www.w3.org/2005/Atom}published")
            published_at = (pub_el.text or "").strip() if pub_el is not None else None

            items.append(_make_item(raw_url, headline, summary_raw, published_at, source_name, client_name, feed_url))
    else:
        # RSS 2.0
        channel = root.find("channel") or root
        for item_el in channel.findall("item"):
            link_el = item_el.find("link")
            raw_url = (link_el.text or "").strip() if link_el is not None else ""

            title_el = item_el.find("title")
            headline = (title_el.text or "").strip() if title_el is not None else ""

            desc_el = item_el.find("description")
            summary_raw = (desc_el.text or "").strip() if desc_el is not None else ""

            pub_el = item_el.find("pubDate")
            published_at = (pub_el.text or "").strip() if pub_el is not None else None

            items.append(_make_item(raw_url, headline, summary_raw, published_at, source_name, client_name, feed_url))

    return items


def _make_item(
    raw_url: str,
    headline: str,
    summary_raw: str,
    published_at: str | None,
    source_name: str,
    client_name: str,
    feed_url: str,
) -> FeedItem:
    clean_url = _unwrap_google_url(raw_url)
    summary = re.sub(r"<[^>]+>", " ", summary_raw).strip()
    summary = re.sub(r"\s+", " ", summary)
    content_hash = hashlib.sha256((headline + summary).encode()).hexdigest()
    return FeedItem(
        url=clean_url,
        headline=headline,
        source_name=source_name,
        summary=summary,
        published_at=published_at,
        content_hash=content_hash,
        raw_url=raw_url,
        extra={"client_name": client_name, "feed_url": feed_url},
    )


class GoogleAlertsSource:
    """Polls all Google Alerts RSS feeds registered in the database."""

    SOURCE_NAME = "Google Alerts"

    @classmethod
    async def fetch(cls) -> list[FeedItem]:
        feeds = storage.list_google_alert_feeds()
        if not feeds:
            return []

        items: list[FeedItem] = []

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "MontfortCoverageAgent/1.0"},
        ) as client:
            for feed in feeds:
                url = feed["feed_url"]
                label = feed.get("label") or feed.get("client_name", cls.SOURCE_NAME)
                client_name = feed["client_name"]
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    feed_items = _parse_feed_xml(response.text, label, client_name, url)
                    items.extend(feed_items)
                except Exception as exc:
                    print(f"[GoogleAlertsSource] Failed to fetch {url}: {exc}")

        return items
