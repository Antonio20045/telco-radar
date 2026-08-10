"""robots.txt - fuer das Geraeteradar zum ersten Mal wirklich umgesetzt.

Bis heute stand die Zusage "robots.txt wird respektiert" ausgerechnet in dem
Dokument, das die Rechtsposition dieses Projekts begruendet
(`collect/aenderungen.py`, Modul-Docstring) - und im Code stand nichts davon.
Dieses Radar fragt Produktseiten fremder Shops ab; hier wird die Zusage
eingeloest.

DREI DIREKTIVEN, NICHT EINE
---------------------------
Der uebliche Fehler ist, nur `Disallow` zu lesen. Beim ersten gemessenen
Anbieter dieses Radars war genau das die falsche Haelfte: medimax.de und
ep.de erlauben die ganze Produktstrecke, schreiben aber woertlich

    Request-rate: 1/10
    Crawl-delay: 10
    Visit-time: 0200-0800          # only visit between 02:00 and 08:00 UTC

Der Wochenlauf startet um 08:30 UTC. Wer nur `Disallow` prueft, haelt sich
fuer regelkonform und laeuft trotzdem jedes Mal ausserhalb des Fensters, mit
64 Workern und ohne Abstand. Deshalb liest dieser Waechter alle drei
Direktiven, und `darf()` gibt den GRUND mit zurueck - er steht woertlich auf
/geraete-quellen.html.

Die zweite Haelfte der Regel steht nicht hier, sondern beim Aufrufer: ein
Anbieter, der wegen seines Besuchsfensters uebersprungen wurde, darf NICHT
gealtert werden. Sonst schoebe jeder Tageslauf seine Geraete einen Schritt
Richtung "ausgelistet", und das Protokoll saehe dabei normal aus.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

_VISIT_RE = re.compile(r"^\s*(\d{4})\s*-\s*(\d{4})\s*$")


def host_von(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc


def _pfad_von(url: str) -> str:
    teile = urlparse(url)
    pfad = teile.path or "/"
    if teile.query:
        pfad += "?" + teile.query
    return pfad


def _als_regex(muster: str) -> re.Pattern:
    """robots-Muster -> Regex. `*` ist beliebig, `$` verankert das Ende."""
    ende = muster.endswith("$")
    if ende:
        muster = muster[:-1]
    teile = [re.escape(t) for t in muster.split("*")]
    quelle = "^" + ".*".join(teile) + ("$" if ende else "")
    return re.compile(quelle)


@dataclass
class Regelwerk:
    """Die fuer uns geltenden Regeln EINES Hosts."""
    disallow: list = field(default_factory=list)
    allow: list = field(default_factory=list)
    crawl_delay: Optional[float] = None
    visit_von: Optional[int] = None       # Minuten seit Mitternacht UTC
    visit_bis: Optional[int] = None
    abrufbar: bool = True                 # robots.txt selbst erreichbar?
    fehler: str = ""

    def erlaubt(self, url: str) -> bool:
        """Laengster Treffer gewinnt - so steht es im Entwurf und so machen
        es Google und die Bibliothek von Python. Bei Gleichstand gewinnt
        `Allow`, sonst koennte eine allgemeine Sperre eine ausdrueckliche
        Freigabe ueberstimmen."""
        pfad = _pfad_von(url)
        laengstes_disallow = max(
            (len(m) for m in self.disallow if _als_regex(m).match(pfad)), default=-1)
        if laengstes_disallow < 0:
            return True
        laengstes_allow = max(
            (len(m) for m in self.allow if _als_regex(m).match(pfad)), default=-1)
        return laengstes_allow >= laengstes_disallow

    def im_fenster(self, jetzt: datetime) -> bool:
        if self.visit_von is None or self.visit_bis is None:
            return True
        minute = jetzt.hour * 60 + jetzt.minute
        if self.visit_von <= self.visit_bis:
            return self.visit_von <= minute < self.visit_bis
        # ueber Mitternacht, z.B. 2200-0600
        return minute >= self.visit_von or minute < self.visit_bis

    @property
    def fenster_text(self) -> str:
        if self.visit_von is None or self.visit_bis is None:
            return ""
        return (f"{self.visit_von // 60:02d}:{self.visit_von % 60:02d}-"
                f"{self.visit_bis // 60:02d}:{self.visit_bis % 60:02d} UTC")


def lies_robots(text: str) -> Regelwerk:
    """Nur der Block, der fuer UNS gilt.

    Gesucht wird der `User-agent: *`-Block. Ein Shop, der uns unter unserem
    eigenen Namen etwas anderes erlaubt, ist die Ausnahme; ihn hier
    mitzulesen waere die Sorte Feinheit, die man falsch implementiert und
    dann nicht merkt. `*` ist die strengere und immer gueltige Lesart.
    """
    regeln = Regelwerk()
    trifft_uns = False
    gruppenkopf = False        # stehen wir gerade in einer Folge von User-agent-Zeilen?
    for rohzeile in (text or "").splitlines():
        zeile = rohzeile.split("#", 1)[0].strip()
        if not zeile or ":" not in zeile:
            continue
        feld, _, wert = zeile.partition(":")
        feld = feld.strip().lower()
        wert = wert.strip()
        if feld == "user-agent":
            if not gruppenkopf:
                trifft_uns = False
            gruppenkopf = True
            if wert == "*":
                trifft_uns = True
            continue
        gruppenkopf = False
        if not trifft_uns:
            continue
        if feld == "disallow":
            if wert:                       # "Disallow:" ohne Wert erlaubt alles
                regeln.disallow.append(wert)
        elif feld == "allow":
            if wert:
                regeln.allow.append(wert)
        elif feld == "crawl-delay":
            try:
                regeln.crawl_delay = float(wert.replace(",", "."))
            except ValueError:
                pass
        elif feld == "request-rate":
            # "1/10" = eine Seite je 10 Sekunden. Wirkt wie eine Crawl-delay
            # und wird als solche gefuehrt; der groessere Wert gewinnt.
            m = re.match(r"^\s*(\d+)\s*/\s*(\d+)", wert)
            if m and int(m.group(1)) > 0:
                abstand = float(m.group(2)) / float(m.group(1))
                if regeln.crawl_delay is None or abstand > regeln.crawl_delay:
                    regeln.crawl_delay = abstand
        elif feld == "visit-time":
            m = _VISIT_RE.match(wert)
            if m:
                von, bis = m.group(1), m.group(2)
                regeln.visit_von = int(von[:2]) * 60 + int(von[2:])
                regeln.visit_bis = int(bis[:2]) * 60 + int(bis[2:])
    return regeln


class RobotsWaechter:
    """Fragt je Host genau EINMAL nach und merkt sich die Antwort."""

    def __init__(self, hole: Callable[[str], tuple], ):
        """`hole(url) -> (status, text)`. Bewusst eine Attrappe statt eines
        direkten httpx-Aufrufs: der Waechter ist die eine Stelle, die ohne
        Netz vollstaendig testbar sein muss."""
        self._hole = hole
        self._cache: dict[str, Regelwerk] = {}

    def regeln(self, url: str) -> Regelwerk:
        host = host_von(url)
        if host in self._cache:
            return self._cache[host]
        teile = urlparse(url)
        robots_url = f"{teile.scheme or 'https'}://{teile.netloc}/robots.txt"
        try:
            status, text = self._hole(robots_url)
        except Exception as exc:                       # noqa: BLE001
            # Kein Ergebnis heisst nicht "erlaubt". Ein Netzfehler an dieser
            # Stelle darf nicht dazu fuehren, dass wir loslaufen.
            regeln = Regelwerk(abrufbar=False,
                               fehler=f"{type(exc).__name__}: {str(exc)[:120]}")
            self._cache[host] = regeln
            return regeln
        if status in (401, 403):
            # Wer uns die robots.txt verweigert, verweigert uns die Seite.
            regeln = Regelwerk(abrufbar=False,
                               fehler=f"robots.txt nicht lesbar (HTTP {status})")
        elif status == 404 or status == 410:
            # Keine robots.txt = keine Einschraenkung. So steht es im Entwurf.
            regeln = Regelwerk()
        elif 200 <= status < 300:
            regeln = lies_robots(text)
        else:
            regeln = Regelwerk(abrufbar=False,
                               fehler=f"robots.txt nicht lesbar (HTTP {status})")
        self._cache[host] = regeln
        return regeln

    def darf(self, url: str, jetzt: Optional[datetime] = None) -> tuple[bool, str]:
        """(darf abgerufen werden, Grund). Der Grund steht auf der
        Quellenseite - er ist kein Log-Text, sondern Anzeige."""
        jetzt = jetzt or datetime.now(timezone.utc)
        regeln = self.regeln(url)
        if not regeln.abrufbar:
            return (False, regeln.fehler or "robots.txt nicht lesbar")
        if not regeln.erlaubt(url):
            return (False, f"per robots.txt gesperrt: {_pfad_von(url)}")
        if not regeln.im_fenster(jetzt):
            return (False, "ausserhalb der Besuchszeit laut robots.txt "
                           f"({regeln.fenster_text}, Lauf um "
                           f"{jetzt.hour:02d}:{jetzt.minute:02d} UTC)")
        return (True, "")

    def abstand(self, url: str, mindestens: float = 0.0) -> float:
        """Der einzuhaltende Abstand zweier Abrufe: der GROESSERE Wert aus
        eigener Konfiguration und Crawl-delay des Hosts."""
        regeln = self.regeln(url)
        if regeln.crawl_delay is None:
            return mindestens
        return max(mindestens, float(regeln.crawl_delay))
