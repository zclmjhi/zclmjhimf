"""
Shared data structures for delivery modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AlertItem:
    """One coverage item ready for delivery."""
    brief_id: str
    client_name: str
    keyword_matched: str
    headline: str
    url: str
    source_name: str
    published_at: str | None
    is_update: bool = False
    is_priority: bool = False
    summary: str = ""


@dataclass
class DigestBundle:
    """A collection of AlertItems for scheduled digest delivery."""
    brief_id: str
    brief_title: str
    user_id: str
    user_email: str | None
    delivery_channel: str      # 'teams' | 'email'
    items: list[AlertItem] = field(default_factory=list)
    period_label: str = "today"  # e.g. "today", "this morning"
