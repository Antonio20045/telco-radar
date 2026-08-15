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
    origin: str = "operator"  # "operator" | "industry_news" | "tech_watch"
    # URL der QUELLE (nicht der Meldung). source_name traegt nur den
    # Anzeigenamen, und der ist bei einem Betreiber mit mehreren Kanaelen fuer
    # alle gleich - die Trefferquote je Kanal waere ohne dieses Feld nicht
    # berechenbar. Wird zentral in collect/_collect_source gestempelt, damit
    # kein Collector es vergessen kann.
    source_url: str = ""
    # Bild-URL aus dem Feed-Eintrag (media:content, media:thumbnail,
    # enclosure oder erstes <img> im Text). Kostet keinen zusaetzlichen
    # Abruf und funktioniert auch bei Seiten, die einen direkten Aufruf mit
    # 403 abweisen. Leer ist der Normalfall - report/bilder.py versucht dann
    # og:image, und ein Layout ohne Bild muss trotzdem tragen.
    image_url: str = ""
    # Der ARTIKELTEXT, wenn er beschafft werden konnte - ungekappt.
    #
    # Bewusst ein eigenes Feld neben `summary`, nicht dessen Verlaengerung:
    # `summary` bleibt bei 600 Zeichen und ist das, was der Bericht und die
    # Karten zeigen.
    #
    # **Seit dem 15.08.2026 liest der Analyst dieses Feld mit** -
    # `agents.analyst_text()` nimmt den laengeren von `volltext` und
    # `summary` und kappt bei 2500 Zeichen. Bis dahin stand hier, ein
    # Volltext in den Stapel-Prompts waere "der Nebeneffekt, den niemand
    # bestellt hat"; er ist jetzt ausdruecklich bestellt, weil 52 der 164
    # crawlbaren Quellen kein `summary` liefern und der Analyst dort allein
    # aus der Ueberschrift bewertet hat. Die Entscheidung hat ihre eigene
    # Token-Rechnung, und sie steht in `ANALYST_TEXT_ZEICHEN`.
    #
    # Gemessen am 13.08.2026 ueber 1329 Feed-Eintraege: 40,6 % tragen ihren
    # Volltext schon im Feed (meist in content:encoded, das bis dahin
    # niemand gelesen hat), die anderen 59,4 % brauchen den Abruf der
    # Artikelseite. **Nur der Feed-Weg fuellt dieses Feld** -
    # `collect/newsroom.py` setzt es nicht, der Abruf der Artikelseite
    # geschieht erst in der Uebersetzungsstufe und damit NACH der Analyse.
    # Fuer die textlosen Newsroom-Quellen bleibt es deshalb beim Titel.
    volltext: str = ""
    # Die erkannte Sprache des Originals als ISO-639-1-Kuerzel, oder "" wenn
    # sie sich nicht sicher bestimmen liess. NIE auf dem Titel gemessen -
    # eine Ueberschrift besteht groesstenteils aus Eigennamen, und darauf
    # raet jede Erkennung: "AT&T, Ericsson demonstrate drone-sensing 5G
    # capabilities" gilt titelweise als franzoesisch.
    sprache: str = ""
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
            source_url=d.get("source_url", ""),
            # `image_url` fehlte hier bis zum 13.08.2026: ein aus einem Dict
            # wiederhergestelltes Item verlor sein Feed-Bild lautlos, und
            # `to_dict` hatte es korrekt geschrieben. Kein Test hat das
            # gemeldet, weil beide Richtungen nur einzeln geprueft wurden.
            image_url=d.get("image_url", ""),
            volltext=d.get("volltext", ""),
            sprache=d.get("sprache", ""),
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
