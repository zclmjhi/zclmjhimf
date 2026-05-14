"""
Abstract base class for all coverage sources.

To add a new source:
1. Create sources/my_source.py with a class that inherits BaseSource.
2. Implement fetch() to return a list of FeedItem.
3. Append the class to REGISTERED_SOURCES in sources/__init__.py.

That is the entire contract. The monitoring loop calls fetch() on every
registered source without knowing anything else about it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class FeedItem:
    url: str                      # clean, redirect-unwrapped destination URL
    headline: str
    source_name: str              # publication or feed name
    summary: str = ""
    published_at: str | None = None   # ISO timestamp string
    content_hash: str = ""        # sha256 of headline+summary for update detection
    last_modified: str | None = None  # value of Last-Modified header if available
    raw_url: str = ""             # original URL before cleaning (for debugging)
    extra: dict = field(default_factory=dict)


@runtime_checkable
class BaseSource(Protocol):
    @classmethod
    async def fetch(cls) -> list[FeedItem]:
        """
        Fetch all available items from this source.
        Must be idempotent — safe to call repeatedly.
        Should not filter by keyword; that is the monitoring loop's job.
        """
        ...
