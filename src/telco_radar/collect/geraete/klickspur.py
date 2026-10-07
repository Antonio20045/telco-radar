"""Spur der Klick-Erkundung: jede Anfrage der Seite, ihre Antwort und der Mitschnitt.

``Spur`` hängt an den Ereignissen der Seite (``binde``) und hält je Anfrage Methode,
Adresse, Art, HTTP-Status oder Abbruchgrund; laufende Anfragen machen die Ruhe aus
(keine läuft, keine neue seit der letzten Lesung). ``sammle`` liest die Körper der seit
dem letzten Aufruf eingegangenen Antworten, nur JSON (``MITSCHNITT_TYPEN``; Seiten und
anderer Text bleiben draußen), je Antwort höchstens ``HOECHSTE_ANTWORT`` Bytes, gekürzt
mit Vermerk. Kopfzeilen werden nie gespeichert, also auch kein Cookie und kein
Set-Cookie; jede Adresse verliert die Werte geheimer Parameter (``ohne_geheimnisse``).
``schwaerze_text`` ersetzt in beliebigem Text die Werte geheimer Parameter, geheimer
JSON-Schlüssel (``GEHEIM``), JSON Web Tokens und Bearer-Kennungen. ``geheime_werte``
nennt diese Werte selbst, damit die Ablage sie überall schwärzt, wo sie wieder
auftauchen (im Pfad, unter einem harmlosen Namen, in der Seite).

``bot_verdacht`` nennt den Grund, wenn eine Antwort der eigenen Website (dieselben
letzten zwei Namensteile wie die Seite) nach Bot-Schutz aussieht: HTTP 403 oder 429 auf
eine Daten- oder Dokumentanfrage oder ein Challenge-Muster im Körper
(``klicklauf.CHALLENGE_MUSTER``). Die Erkundung endet dann als gestört (CLAUDE.md
Regel 4). Dieses Modul ruft kein Netz.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightFehler

from .klicklauf import CHALLENGE_MUSTER
from .klicktor import kurz

if TYPE_CHECKING:
    from playwright.sync_api import Page, Request, Response

log = logging.getLogger(__name__)

HOECHSTE_ANTWORT = 200_000
MITSCHNITT_TYPEN = re.compile(r"json", re.I)
DATENARTEN = frozenset({"xhr", "fetch", "document"})
BOT_STATUS = frozenset({403, 429})
GEHEIM = re.compile(
    r"token|secret|passw|session|^sid$|auth(?!or)|signature|^sig$|api[_-]?key|^key$"
    r"|jwt|csrf|xsrf|nonce|tntid|thirdpartyid|^umid$|visitor_?id|^mcid$|^ecid$"
    r"|cart|basket|warenkorb",
    re.I,
)
"""Namen geheimer Parameter und JSON-Felder. Dazu die Besucherkennungen der
Werbe- und Messdienste: Adobe Target schrieb am 07.10.2026 die ``tntId`` des
Runners in eine Vodafone-Antwort. Und Warenkorb-Kennungen (``cartId``, ``basketId``,
``warenkorb``): der Weiter-Klick der Folgeseite legt einen Warenkorb an."""
ENTFERNT = "ENTFERNT"
GESCHWAERZT = "[Cookie entfernt]"
"""Platzhalter der Ablage für einen gemerkten Wert; steht er hinter einem geheimen
Parameter, wird er wie jeder Wert zu ``ENTFERNT``."""
_PARAMETER = re.compile(
    r"(?<![\w.\[\]-])([\w.\[\]-]{1,80})=("
    + re.escape(GESCHWAERZT)
    + r"|[^&#;,\s\"'<>\\]*)"
)
_JSON_FELD = re.compile(r'"([^"\\]{1,80})"(\s*:\s*)("(?:[^"\\]|\\.)*"|-?\d[\d.eE+-]*)')
_JWT = re.compile(r"eyJ[\w-]{4,}\.eyJ[\w-]{4,}\.[\w-]*")
_BEARER = re.compile(r"(?i)\b(bearer\s+)(?!ENTFERNT\b)[\w.~+/=-]{4,}")
_LEERRAUM = re.compile(r"\s")
WEB_SCHEMA = ("http", "https")
NAMENSTEILE_SITE = 2


def ohne_geheimnisse(url: str) -> str:
    """Die Adresse ohne Werte geheimer Parameter und ohne Zugangsdaten im Host.

    Eine relative Adresse behält Pfad und Parameter, ohne Fragment.
    """
    teile = urlsplit(url)
    if teile.scheme and teile.scheme not in WEB_SCHEMA:
        return teile.scheme + ":"
    paare = parse_qsl(teile.query, keep_blank_values=True)
    sauber = [(k, ENTFERNT if GEHEIM.search(k) else v) for k, v in paare]
    host = teile.hostname or ""
    ort = f"{host}:{teile.port}" if teile.port else host
    return urlunsplit((teile.scheme, ort, teile.path, urlencode(sauber), ""))


def schwaerze_text(text: str) -> str:
    """Text ohne Werte geheimer Parameter und JSON-Felder, ohne Tokens."""
    text = _JWT.sub(ENTFERNT, text)
    text = _BEARER.sub(lambda m: m[1] + ENTFERNT, text)
    text = _PARAMETER.sub(_ohne_wert, text)
    return _JSON_FELD.sub(_ohne_feldwert, text)


def geheime_werte(text: str) -> set[str]:
    """Die Werte geheimer Parameter und JSON-Felder in ``text``, roh und URL-dekodiert.

    Ein Wert mit Leerraum oder schon ``ENTFERNT`` ist keine Kennung.
    """
    roh = [t[2] for t in _PARAMETER.finditer(text) if GEHEIM.search(t[1])]
    roh += [t[3].strip('"') for t in _JSON_FELD.finditer(text) if GEHEIM.search(t[1])]
    werte = {form for wert in roh for form in (wert, unquote(wert))}
    return {w for w in werte if w and w != ENTFERNT and not _LEERRAUM.search(w)}


def _ohne_wert(treffer: re.Match[str]) -> str:
    schluessel, wert = treffer[1], treffer[2]
    if not wert or not GEHEIM.search(schluessel):
        return treffer[0]
    return f"{schluessel}={ENTFERNT}"


def _ohne_feldwert(treffer: re.Match[str]) -> str:
    if not GEHEIM.search(treffer[1]):
        return treffer[0]
    return f'"{treffer[1]}"{treffer[2]}"{ENTFERNT}"'


def gleiche_site(url: str, seite: str) -> bool:
    """Wahr, wenn beide Adressen dieselben letzten zwei Namensteile im Host tragen."""
    a = (urlsplit(url).hostname or "").split(".")[-NAMENSTEILE_SITE:]
    b = (urlsplit(seite).hostname or "").split(".")[-NAMENSTEILE_SITE:]
    return bool(a) and a == b


@dataclass
class Eintrag:
    """Eine Anfrage der Seite und was aus ihr wurde."""

    nummer: int
    methode: str
    url: str
    art: str
    status: int | None = None
    typ: str | None = None
    abbruch: str | None = None
    laufend: bool = True


@dataclass
class Spur:
    """Alle Anfragen einer Seite, laufende und beantwortete, und der Mitschnitt."""

    eintraege: list[Eintrag] = field(default_factory=list)
    mitschnitt: list[dict] = field(default_factory=list)
    _offen: list[tuple[Request, Eintrag]] = field(default_factory=list)
    _antworten: list[tuple[Response, Eintrag]] = field(default_factory=list)

    def binde(self, seite: Page) -> None:
        """Hängt die Spur an die Anfrage-Ereignisse der Seite."""
        seite.on("request", self._anfrage)
        seite.on("response", self._antwort)
        seite.on("requestfinished", self._fertig)
        seite.on("requestfailed", self._gescheitert)

    def marke(self) -> int:
        """Zahl der bisher gestellten Anfragen, die Marke vor einem Schritt."""
        return len(self.eintraege)

    def seit(self, marke: int) -> list[Eintrag]:
        """Die Anfragen seit ``marke``."""
        return self.eintraege[marke:]

    def ruhe(self) -> int | None:
        """Zahl aller Anfragen, wenn keine läuft; sonst ``None``."""
        return None if self._offen else len(self.eintraege)

    def sammle(self, seite_url: str) -> str | None:
        """Liest die neuen Antworten in den Mitschnitt; Grund bei Bot-Verdacht."""
        verdacht = None
        neu, self._antworten = self._antworten, []
        for antwort, eintrag in neu:
            grund = self._nimm(antwort, eintrag, seite_url)
            verdacht = verdacht or grund
        return verdacht

    def _nimm(self, antwort: Response, eintrag: Eintrag, seite_url: str) -> str | None:
        typ = eintrag.typ or ""
        if not MITSCHNITT_TYPEN.search(typ):
            return bot_verdacht(eintrag, "", seite_url)
        satz: dict = {
            "nummer": eintrag.nummer,
            "methode": eintrag.methode,
            "url": eintrag.url,
            "art": eintrag.art,
            "status": eintrag.status,
            "typ": typ,
        }
        try:
            koerper = antwort.body()
        except PlaywrightFehler as fehler:
            satz["koerper"], satz["grund"] = (
                None,
                f"Körper nicht lesbar: {kurz(fehler)}",
            )
            self.mitschnitt.append(satz)
            return bot_verdacht(eintrag, "", seite_url)
        text = koerper[:HOECHSTE_ANTWORT].decode("utf-8", errors="replace")
        satz["groesse"] = len(koerper)
        satz["gekuerzt"] = len(koerper) > HOECHSTE_ANTWORT
        satz["koerper"] = text
        self.mitschnitt.append(satz)
        return bot_verdacht(eintrag, text, seite_url)

    def _anfrage(self, anfrage: Request) -> None:
        eintrag = Eintrag(
            nummer=len(self.eintraege) + 1,
            methode=anfrage.method,
            url=ohne_geheimnisse(anfrage.url),
            art=anfrage.resource_type,
        )
        self.eintraege.append(eintrag)
        self._offen.append((anfrage, eintrag))

    def _antwort(self, antwort: Response) -> None:
        eintrag = self._eintrag(antwort.request)
        if eintrag is None:
            return
        eintrag.status = antwort.status
        eintrag.typ = antwort.headers.get("content-type", "")
        self._antworten.append((antwort, eintrag))

    def _fertig(self, anfrage: Request) -> None:
        eintrag = self._eintrag(anfrage)
        if eintrag is not None:
            eintrag.laufend = False
        self._offen = [(a, e) for a, e in self._offen if a is not anfrage]

    def _gescheitert(self, anfrage: Request) -> None:
        eintrag = self._eintrag(anfrage)
        if eintrag is not None:
            eintrag.abbruch = anfrage.failure or "abgebrochen"
        self._fertig(anfrage)

    def _eintrag(self, anfrage: Request) -> Eintrag | None:
        return next((e for a, e in self._offen if a is anfrage), None)


def bot_verdacht(eintrag: Eintrag, koerper: str, seite_url: str) -> str | None:
    """Grund, wenn eine Antwort der eigenen Website nach Bot-Schutz aussieht."""
    if not gleiche_site(eintrag.url, seite_url):
        return None
    if eintrag.status in BOT_STATUS and eintrag.art in DATENARTEN:
        return f"Abruf gestört (HTTP {eintrag.status} auf {eintrag.url})"
    treffer = CHALLENGE_MUSTER.search(koerper)
    if treffer is not None:
        return f"Abruf gestört (Challenge „{treffer[0]}“ in {eintrag.url})"
    return None


def als_daten(eintraege: list[Eintrag]) -> list[dict]:
    """Die Anfragen als JSON-fähige Liste."""
    return [
        {
            "nummer": e.nummer,
            "methode": e.methode,
            "url": e.url,
            "art": e.art,
            "status": e.status,
            "abbruch": e.abbruch,
        }
        for e in eintraege
    ]
