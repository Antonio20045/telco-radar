"""Das Tor der Angebotszählung: robots.txt samt Crawl-delay und Visit-time, Abstand
zwischen Seitenaufrufen und das Erkennen einer Schutzseite (CLAUDE.md Regel 4).

Eigener Code, unabhängig vom Sammler: robots.txt wird mit derselben ehrlichen Kennung
abgerufen wie die Seiten (``hole_robots`` liefert ``(status, text)``), geprüft mit
``urllib.robotparser``; ``Visit-time`` (``HHMM-HHMM`` UTC) liest das Tor selbst.
404/410 heißt „keine Regeln“, 401/403 „nicht anfassen“, alles andere ohne 200 „nicht
lesbar“ und damit ebenfalls kein Abruf. Eine Schutzseite (403, 429, 503, Captcha,
Bot-Manager) wird nie umgangen: ``Gesperrt`` beendet die Zählung des Anbieters
benannt.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

AGENT = "TelcoRadar"
SCHUTZ_STATUS = frozenset({401, 403, 429, 503})
SCHUTZ_TEXT = re.compile(
    r"captcha|access denied|zugriff verweigert|bot manager|radware|"
    r"are you a (?:human|robot)|sicherheitsüberprüfung|request unsuccessful|"
    r"verify you are human",
    re.I,
)


class Gesperrt(Exception):
    """Der Anbieter verweigert den Abruf (robots.txt oder Schutzseite); benannt."""


def schutzgrund(status: int | None, titel: str, text: str) -> str | None:
    """Der Grund, wenn die geladene Seite eine Schutzseite ist; sonst ``None``."""
    if status in SCHUTZ_STATUS:
        return f"Schutzantwort des Anbieters (HTTP {status}), nicht umgangen"
    probe = f"{titel}\n{(text or '')[:3000]}"
    treffer = SCHUTZ_TEXT.search(probe)
    if treffer:
        return f"Schutzseite des Anbieters („{treffer.group(0)}“), nicht umgangen"
    return None


def besuchszeit(robots_text: str) -> list[tuple[int, int]]:
    """``Visit-time: 0100-0645`` als Minutenfenster (UTC) für ``User-agent: *`` oder
    die eigene Kennung."""
    fenster, gilt = [], False
    for zeile in (robots_text or "").splitlines():
        schluessel, _, wert = zeile.partition(":")
        schluessel, wert = schluessel.strip().lower(), wert.split("#")[0].strip()
        if schluessel == "user-agent":
            gilt = wert == "*" or wert.lower().startswith(AGENT.lower())
        elif schluessel == "visit-time" and gilt:
            treffer = re.fullmatch(r"(\d{2})(\d{2})\s*-\s*(\d{2})(\d{2})", wert)
            if treffer:
                a, b, c, d = (int(x) for x in treffer.groups())
                fenster.append((a * 60 + b, c * 60 + d))
    return fenster


class Regeln:
    """Die gelesenen Regeln eines Hosts."""

    def __init__(self, status: int, text: str) -> None:
        """``status``/``text`` der robots.txt-Antwort."""
        self.status = status
        self.parser = RobotFileParser()
        self.parser.parse((text or "").splitlines() if status == 200 else [])
        self.fenster = besuchszeit(text) if status == 200 else []

    def verbot(self, url: str, jetzt_utc: datetime) -> str | None:
        """Warum ``url`` jetzt nicht abgerufen werden darf; ``None`` = erlaubt."""
        if self.status in (401, 403):
            return f"robots.txt verweigert (HTTP {self.status}), nicht abgerufen"
        if self.status not in (200, 404, 410):
            return f"robots.txt nicht lesbar (HTTP {self.status}), nicht abgerufen"
        if self.status == 200 and not self.parser.can_fetch(AGENT, url):
            return f"robots.txt verbietet {urlsplit(url).path}"
        minute = jetzt_utc.hour * 60 + jetzt_utc.minute
        if self.fenster and not any(a <= minute <= b for a, b in self.fenster):
            return "außerhalb der Besuchszeit laut robots.txt"
        return None

    def crawl_delay(self) -> float:
        """Crawl-delay für die eigene Kennung, sonst 0."""
        wert = self.parser.crawl_delay(AGENT) if self.status == 200 else None
        return float(wert or 0.0)


class Tor:
    """Vor jedem Seitenaufruf: Regeln prüfen, Abstand halten (``schlafe``)."""

    def __init__(
        self,
        hole_robots: Callable[[str], tuple[int, str]],
        uhr: Callable[[], datetime],
        mono: Callable[[], float],
        schlafe: Callable[[float], None],
        abstand: float,
    ) -> None:
        """``abstand`` ist der Mindestabstand aus Konfiguration und Modulkonstante."""
        self.hole_robots, self.uhr, self.mono, self.schlafe = (
            hole_robots,
            uhr,
            mono,
            schlafe,
        )
        self.abstand = abstand
        self.regeln: dict[str, Regeln] = {}
        self.zuletzt: dict[str, float] = {}

    def _regeln(self, url: str) -> Regeln:
        teile = urlsplit(url)
        host = teile.netloc
        if host not in self.regeln:
            status, text = self.hole_robots(f"{teile.scheme}://{host}/robots.txt")
            self.regeln[host] = Regeln(status, text)
        return self.regeln[host]

    def passiere(self, url: str) -> None:
        """Wirft ``Gesperrt`` bei Verbot; wartet sonst den Abstand ab."""
        regeln = self._regeln(url)
        grund = regeln.verbot(url, self.uhr())
        if grund:
            raise Gesperrt(grund)
        host = urlsplit(url).netloc
        abstand = max(self.abstand, regeln.crawl_delay())
        if host in self.zuletzt:
            rest = self.zuletzt[host] + abstand - self.mono()
            if rest > 0:
                self.schlafe(rest)
        self.zuletzt[host] = self.mono()
