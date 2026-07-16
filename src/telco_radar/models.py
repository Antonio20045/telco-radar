"""Core data model: a single intelligence item (press release, news article)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Query params that never identify content (tracking noise)
_TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|source$)", re.I)


def normalize_url(url: str) -> str:
    """Normalize a URL so the same article always hashes to the same id."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    scheme = "https"
    netloc = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAMS.match(k)]
    )
    return urlunsplit((scheme, netloc, path, query, ""))


@dataclass
class Item:
    """One collected item from any source."""

    title: str
    url: str
    source_name: str
    region: str = "global"
    operator: Optional[str] = None
    published: Optional[datetime] = None
    summary: str = ""
    origin: str = "operator"  # "operator" | "industry_news"
    id: str = field(default="")

    def __post_init__(self) -> None:
        self.title = " ".join(self.title.split())
        if not self.id:
            basis = normalize_url(self.url) if self.url else self.title.lower()
            self.id = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published"] = self.published.isoformat() if self.published else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        published = d.get("published")
        if isinstance(published, str):
            published = datetime.fromisoformat(published)
        return cls(
            title=d["title"],
            url=d.get("url", ""),
            source_name=d.get("source_name", ""),
            region=d.get("region", "global"),
            operator=d.get("operator"),
            published=published,
            summary=d.get("summary", ""),
            origin=d.get("origin", "operator"),
            id=d.get("id", ""),
        )

    def age_days(self, now: Optional[datetime] = None) -> Optional[float]:
        if self.published is None:
            return None
        now = now or datetime.now(timezone.utc)
        pub = self.published
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        return (now - pub).total_seconds() / 86400.0
