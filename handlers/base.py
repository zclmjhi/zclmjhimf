"""Base class for all coverage source handlers."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NormalisedItem:
    title: str
    url: str
    source: str
    published_at: datetime
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "summary": self.summary,
            "source": self.source,
            "published_at": self.published_at.isoformat(),
        }


class BaseHandler(ABC):
    """
    Inherit from this class to add a new coverage source.

    Implement `fetch()` to return a list of NormalisedItem objects.
    The orchestrator calls `fetch()` on every registered handler each run.
    """

    #: Human-readable name used in logs and as the item's `source` field.
    name: str = "base"

    def __init__(self, config: dict):
        """
        Args:
            config: The full parsed registry.json dict. Handlers pull
                    whatever keys they need from it.
        """
        self.config = config

    @abstractmethod
    def fetch(self) -> list[NormalisedItem]:
        """Fetch items from the source and return them normalised."""
        ...
