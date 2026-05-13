"""Google Alerts RSS/Atom feed handler — uses stdlib xml.etree only."""
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import requests

from handlers.base import BaseHandler, NormalisedItem

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15
_ATOM = "http://www.w3.org/2005/Atom"
_RSS_DATE_FMTS = (
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S GMT",
)


def _parse_date(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    raw = raw.strip()
    # ISO 8601 (Atom)
    for suffix in ("Z", ""):
        try:
            cleaned = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    # RFC 2822 (RSS)
    for fmt in _RSS_DATE_FMTS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _unwrap_google_url(url: str) -> str:
    """Extract the real destination from a Google redirect URL.

    Google Alerts wraps every link as https://www.google.com/url?...&url=<real>&...
    We pull the `url` query parameter and URL-decode it.
    """
    if not url or "google.com/url" not in url:
        return url
    params = parse_qs(urlparse(url).query)
    real = params.get("url", [""])[0]
    return unquote(real) if real else url


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return unescape(el.text or "").strip()


def _parse_atom(root: ET.Element) -> list[dict]:
    """Parse an Atom feed (Google Alerts default format)."""
    entries = []
    for entry in root.findall(f"{{{_ATOM}}}entry"):
        title_el = entry.find(f"{{{_ATOM}}}title")
        link_el = entry.find(f"{{{_ATOM}}}link")
        summary_el = entry.find(f"{{{_ATOM}}}summary") or entry.find(f"{{{_ATOM}}}content")
        published_el = entry.find(f"{{{_ATOM}}}published") or entry.find(f"{{{_ATOM}}}updated")

        link = _unwrap_google_url(link_el.get("href", "") if link_el is not None else "")
        entries.append(
            {
                "title": _text(title_el),
                "url": link,
                "summary": _text(summary_el),
                "published": _text(published_el),
            }
        )
    return entries


def _parse_rss(root: ET.Element) -> list[dict]:
    """Parse an RSS 2.0 feed."""
    entries = []
    channel = root.find("channel") or root
    for item in channel.findall("item"):
        entries.append(
            {
                "title": _text(item.find("title")),
                "url": _text(item.find("link")),
                "summary": _text(item.find("description")),
                "published": _text(item.find("pubDate")),
            }
        )
    return entries


class GoogleAlertsHandler(BaseHandler):
    """Fetches items from one Google Alerts RSS/Atom feed URL per client."""

    name = "google_alerts"

    def fetch(self) -> list[NormalisedItem]:
        items: list[NormalisedItem] = []
        for client in self.config.get("clients", []):
            for url in client.get("google_alerts_feeds", []):
                items.extend(self._fetch_feed(url))
        return items

    def _fetch_feed(self, url: str) -> list[NormalisedItem]:
        logger.info("Fetching Google Alerts feed: %s", url)
        try:
            response = requests.get(url, timeout=_REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to fetch feed %s: %s", url, exc)
            return []

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            logger.error("Failed to parse XML from %s: %s", url, exc)
            return []

        # Detect Atom vs RSS by namespace / tag
        tag = root.tag
        if "atom" in tag.lower() or tag == f"{{{_ATOM}}}feed":
            raw_entries = _parse_atom(root)
        else:
            raw_entries = _parse_rss(root)

        results = []
        for e in raw_entries:
            if not e["title"] or not e["url"]:
                continue
            results.append(
                NormalisedItem(
                    title=e["title"],
                    url=e["url"],
                    summary=e["summary"],
                    source=self.name,
                    published_at=_parse_date(e["published"]),
                )
            )

        logger.info("Found %d items in feed %s", len(results), url)
        return results
