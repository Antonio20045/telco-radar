"""Aenderungsradar: was auf einer Tarifseite still anders wird.

Warum das mehr bringt als weitere Newsquellen
---------------------------------------------
Die wichtigsten Preisbewegungen im Endkundengeschaeft werden NIE per
Pressemitteilung kommuniziert. Eine geaenderte Option, ein neuer
Anschlusspreis, ein still verschwundener Aktionstarif - das steht nur auf der
Seite. Newsmonitoring erwischt es strukturell nicht, egal wie viele Feeds
dazukommen.

Warum NICHT auf rohem HTML gediffed wird
----------------------------------------
Ein Diff auf Markup meldet jeden rotierenden Werbebanner, jede Session-ID und
jeden Zaehlerstand. Visualping gibt an, mit KI-Klassifizierung rund 83 % der
erkannten Aenderungen als irrelevant auszusortieren - das ist die
Groessenordnung des Rauschens, gegen die hier gearbeitet wird. Ein System,
das jede Woche vierzig Falschmeldungen liefert, wird nach zwei Wochen
ignoriert; dann ist es schlechter als keines.

Deshalb drei Stufen, und die mittlere ist der eigentliche Trick:

  1. **Extrahieren.** Nur der Inhaltsbereich, notfalls die ganze Seite ohne
     Skript, Stil, Navigation, Fusszeile.
  2. **Auf WERTE reduzieren.** Was zaehlt, ist nicht der Text, sondern der
     Preis: jede Zahl mit Einheit (EUR, GB, Mbit/s, Monate, %) zusammen mit
     dem Etikett davor. Ein Anbieter, der seine Kacheln neu anordnet, aendert
     dieselbe Wertmenge - und loest deshalb nichts aus. Ein Anbieter, der
     39,99 EUR durch 0 EUR ersetzt, aendert sie.
  3. **Mengen vergleichen.** Was dazukam, was wegfiel. Reihenfolge ist keine
     Aenderung.

Was ausdruecklich ignoriert wird, steht in `_RAUSCHEN` - Datumsangaben,
Uhrzeiten, Zaehlerstaende, Sitzungsnummern. Sie sind der Grund, warum ein
naiver Diff jeden Abruf meldet.

Der Rahmen, in dem das stattfindet
----------------------------------
Wenige oeffentliche Produktseiten, niedrige Frequenz (zwei Abrufe die Woche),
keine Login-Bereiche, keine Umgehung von Bot-Schutz mit verschleierter
Identitaet, robots.txt wird respektiert, die Daten bleiben intern. Der BGH
hat 2014 (I ZR 224/12) entschieden, dass automatisiertes Auslesen oeffentlich
zugaenglicher Daten keine unlautere Behinderung ist, solange keine
technischen Schutzmassnahmen umgangen werden; der EuGH hat parallel
(Ryanair/PR Aviation, C-30/14) klargestellt, dass AGB vertraglich trotzdem
ein Verbot begruenden koennen. In dieser Ausgestaltung ist das gut
vertretbar. Ein breiter Scrape des gesamten Sortiments waere eine andere
Frage - dort greift potenziell das Datenbankherstellerrecht nach § 87b UrhG.
Keine Rechtsberatung; die Ausgestaltung oben ist die Antwort darauf.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

from ..models import Item
from .http import fetch

log = logging.getLogger(__name__)

# Wie viele Wertfragmente eine Seite hoechstens beisteuert. Eine
# Tarifuebersicht hat ein paar Dutzend Preise; wer tausend liefert, liefert
# eine Preisliste des ganzen Shops - und dann ist der Diff wieder Rauschen.
MAX_WERTE = 400

# Wie viele Werte eine Seite mindestens hergeben muss, damit ihr Diff etwas
# bedeutet. GEMESSEN am 08.08.2026 ueber alle 16 konfigurierten Seiten: eine
# Tarifuebersicht, die ihre Preistabelle wirklich im HTML ausliefert, bringt
# 16 bis 54 Werte (o2 54, 1&1 29, blau 28, klarmobil 16). Wo nur eine
# Handvoll herauskommt, stammen sie aus dem FLIESSTEXT drumherum
# ("...sparst du 10 %", "...bis zu 1 GB") - die Preistabelle selbst baut
# JavaScript auf. Ein Diff darauf meldet Textaenderungen als
# Preisaenderungen, und das ist genau die Falschmeldung, die den Kanal
# unbrauchbar macht.
MIND_WERTE = 10

# Ab wie vielen Aenderungen eine Seite als "umgebaut" gilt und NICHT gemeldet
# wird. Ein Relaunch ist keine Preisaenderung; ihn als vierzig Meldungen
# auszugeben ist die sicherste Art, den Kanal unbrauchbar zu machen.
MAX_AENDERUNGEN_JE_SEITE = 12

_ENTFERNEN = ("script", "style", "noscript", "nav", "footer", "header",
              "svg", "iframe", "form")

# Zahlenwerte, auf die es ankommt. Bewusst mit Einheit: eine nackte Zahl auf
# einer Webseite ist eine Artikelnummer, ein Zaehler oder eine Jahreszahl.
_WERT = re.compile(
    r"(\d{1,4}(?:[.,]\d{1,2})?)\s?"
    r"(€|EUR|Euro|GB|MB|TB|Mbit/s|MBit/s|GBit/s|Gbit/s|Monate?|Tage?|%)",
    re.I)

# Was NIE eine Aenderung im Sinne dieses Radars ist. Ohne diese Liste meldet
# jeder Abruf eine Aenderung, weil die Seite die Uhrzeit ausgibt.
_RAUSCHEN = (
    re.compile(r"\b\d{1,2}[.:]\d{2}\s*(Uhr|h)\b", re.I),
    re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b"),
    re.compile(r"\b(20\d{2})-\d{2}-\d{2}\b"),
    re.compile(r"\b(sess|sid|cid|tid|uid)[=:][A-Za-z0-9_-]{6,}", re.I),
    re.compile(r"\bnoch \d+ (Tage?|Stunden?|Minuten?)\b", re.I),
    re.compile(r"\b\d+ (Kunden|Bewertungen|Aufrufe)\b", re.I),
)

_EINHEIT_NORM = {"euro": "€", "eur": "€", "mbit/s": "mbit/s", "gbit/s": "gbit/s"}


@dataclass
class Tarifseite:
    marke: str
    was: str
    url: str
    selector: str = ""


@dataclass
class Aenderung:
    """Eine belegte Wertaenderung auf einer Seite."""

    seite: Tarifseite
    dazu: list[str] = field(default_factory=list)
    weg: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.dazu) + len(self.weg)

    def kennung(self) -> str:
        """Stabil ueber Laeufe, verschieden je Aenderung.

        Aus der URL UND dem Inhalt der Aenderung - nie aus dem Seitentitel.
        Eine ID aus dem Titel ist beim naechsten Lauf eine andere, sobald der
        Anbieter seine Ueberschrift dreht; denselben Fehler hat der
        Promo-Zweig schon einmal bezahlt.
        """
        stoff = self.seite.url + "|" + "|".join(sorted(self.dazu + self.weg))
        return hashlib.sha256(stoff.encode("utf-8")).hexdigest()[:16]


def lade_seiten(root: Path) -> list[Tarifseite]:
    pfad = Path(root) / "config" / "tarif_seiten.yaml"
    if not pfad.exists():
        return []
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    return [Tarifseite(marke=str(s.get("marke") or ""),
                       was=str(s.get("was") or ""),
                       url=str(s.get("url") or ""),
                       selector=str(s.get("selector") or ""))
            for s in (daten.get("seiten") or []) if s.get("url")]


def _text(html: str, selector: str = "") -> str:
    """Der Inhalt der Seite, mit den BLOCKGRENZEN als Zeilenumbruch.

    Die Grenzen sind der Punkt, nicht ein Nebeneffekt: das Etikett eines
    Preises darf nicht aus der Nachbarkachel stammen. Ohne sie las das
    Etikett von "19,99 €" in `<div>Mobile M 39,99 €</div><div>Mobile S
    19,99 €</div>` als "mobile s mobile m" - und eine bloss umsortierte Seite
    meldete eine Preisaenderung.
    """
    suppe = BeautifulSoup(html, "html.parser")
    for tag in suppe.find_all(_ENTFERNEN):
        tag.decompose()
    bereich = suppe.select_one(selector) if selector else None
    roh = (bereich or suppe).get_text("\n", strip=True)
    return "\n".join(z.strip() for z in roh.split("\n") if z.strip())


def werte(text: str, max_werte: int = MAX_WERTE) -> set[str]:
    """Die Wertmenge einer Seite: Etikett + Zahl + Einheit, normalisiert.

    Das Etikett sind bis zu vier Woerter VOR der Zahl - aber nur aus DERSELBEN
    Zeile. Ohne Etikett waeren "9,99 €" an zwei Stellen derselbe Wert, und
    eine Preisaenderung beim Anschlusspreis saehe aus wie eine beim
    Monatspreis; ohne die Zeilengrenze saugte das Etikett den Nachbartext auf
    und jede Umsortierung waere eine Aenderung.
    """
    out: set[str] = set()
    for zeile in (text or "").split("\n"):
        sauber = zeile
        for muster in _RAUSCHEN:
            sauber = muster.sub(" ", sauber)
        sauber = " ".join(sauber.split())
        for treffer in _WERT.finditer(sauber):
            davor = sauber[:treffer.start()]
            etikett = " ".join(re.findall(r"[A-Za-zÄÖÜäöüß][\wÄÖÜäöüß.-]*",
                                          davor)[-4:]).lower()
            zahl = treffer.group(1).replace(".", "").replace(",", ".")
            einheit = treffer.group(2).lower()
            einheit = _EINHEIT_NORM.get(einheit, einheit)
            out.add(f"{etikett}|{zahl}{einheit}")
            if len(out) >= max_werte:
                return out
    return out


class Snapshotspeicher:
    """Die zuletzt gesehene Wertmenge je Seite.

    Bewusst die MENGE und nicht der Text: der Speicher ist damit klein
    (ein paar Kilobyte je Seite statt hunderter), und er kann gar nicht erst
    dazu verleiten, Darstellungsaenderungen zu diffen.
    """

    def __init__(self, pfad: Path):
        self.pfad = pfad
        self.daten: dict = {}
        if pfad.exists():
            try:
                self.daten = json.loads(pfad.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log.warning("tarif_snapshots.json unlesbar - beginne neu")

    def hole(self, url: str) -> set[str]:
        return set((self.daten.get(url) or {}).get("werte") or [])

    def setze(self, url: str, w: set[str], stand: str) -> None:
        self.daten[url] = {"werte": sorted(w), "stand": stand}

    def kennt(self, url: str) -> bool:
        return url in self.daten

    def speichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.pfad.write_text(
            json.dumps(self.daten, ensure_ascii=False, indent=1),
            encoding="utf-8")


def vergleiche(alt: set[str], neu: set[str]) -> tuple[list[str], list[str]]:
    """(dazugekommen, weggefallen). Reihenfolge ist keine Aenderung."""
    return sorted(neu - alt), sorted(alt - neu)


def _lesbar(fragment: str) -> str:
    etikett, _, wert = fragment.partition("|")
    return f"{etikett.strip()} {wert}".strip() if etikett else wert


def als_item(a: Aenderung, stand: datetime) -> Item:
    """Die Aenderung als Meldung - damit sie denselben Weg nimmt wie alles
    andere: Analyst, CTM-Linse, Bericht, Suche.

    Die `id` wird ausdruecklich gesetzt. Sonst leitete `Item` sie aus der URL
    ab, und die ist bei jeder Aenderung derselben Seite dieselbe - der
    Seen-Store haette die zweite Preisaenderung fuer eine schon berichtete
    gehalten.
    """
    titel = (f"{a.seite.marke}: Preise auf der Seite {a.seite.was} geändert"
             if a.n else f"{a.seite.marke}: {a.seite.was}")
    teile = []
    if a.dazu:
        teile.append("neu: " + "; ".join(_lesbar(f) for f in a.dazu[:8]))
    if a.weg:
        teile.append("entfallen: " + "; ".join(_lesbar(f) for f in a.weg[:8]))
    return Item(
        title=titel,
        url=a.seite.url,
        source_name=f"{a.seite.marke} (Tarifseite)",
        region="europe",
        operator=a.seite.marke,
        published=stand,
        summary=("Auf der Tarifseite haben sich Werte geändert, ohne dass es "
                 "dazu eine Pressemitteilung gibt. " + " · ".join(teile))[:900],
        origin="tarif_change",
        source_url=a.seite.url,
        id=a.kennung(),
    )


def sammle(root: Path, http_cfg: dict, *, heute: datetime | None = None
           ) -> tuple[list[Item], dict]:
    """Alle Tarifseiten abrufen, vergleichen, Aenderungen als Items liefern.

    Der ERSTE Abruf einer Seite meldet nie etwas - er legt die Grundlinie.
    Ohne diese Regel bestuende die erste Ausgabe nach dem Einbau aus vierzig
    "neuen" Preisen, die alle schon immer so dastanden.
    """
    heute = heute or datetime.now(timezone.utc)
    seiten = lade_seiten(root)
    speicher = Snapshotspeicher(Path(root) / "data" / "state" /
                                "tarif_snapshots.json")
    bilanz = {"seiten": len(seiten), "gelesen": 0, "grundlinie": 0,
              "geaendert": 0, "umgebaut": 0, "fehler": 0, "ohne_werte": 0,
              "meldungen": 0}
    items: list[Item] = []

    for seite in seiten:
        try:
            antwort = fetch(seite.url, http_cfg)
            aktuell = werte(_text(antwort.text, seite.selector))
        except Exception as exc:  # noqa: BLE001
            bilanz["fehler"] += 1
            log.info("Tarifseite %s nicht lesbar: %s", seite.url,
                     str(exc)[:120])
            continue
        if len(aktuell) < MIND_WERTE:
            # Zu wenige Werte heisst: die Preistabelle baut JavaScript auf,
            # und was hier ankommt, ist der Fliesstext drumherum. Die Seite
            # als "alles entfallen" zu melden waere die teuerste
            # Falschmeldung, die dieser Radar produzieren kann; ihren
            # Prosa-Diff zu melden die zweitteuerste.
            bilanz["ohne_werte"] += 1
            log.info("Tarifseite %s liefert nur %d Werte (Preistabelle "
                     "vermutlich per JavaScript) - uebersprungen",
                     seite.url, len(aktuell))
            continue
        bilanz["gelesen"] += 1

        if not speicher.kennt(seite.url):
            bilanz["grundlinie"] += 1
            speicher.setze(seite.url, aktuell, heute.date().isoformat())
            continue

        dazu, weg = vergleiche(speicher.hole(seite.url), aktuell)
        speicher.setze(seite.url, aktuell, heute.date().isoformat())
        if not (dazu or weg):
            continue
        a = Aenderung(seite=seite, dazu=dazu, weg=weg)
        if a.n > MAX_AENDERUNGEN_JE_SEITE:
            # Ein Relaunch ist keine Preisaenderung.
            bilanz["umgebaut"] += 1
            log.info("Tarifseite %s: %d Wertaenderungen - sieht nach Umbau "
                     "aus, nicht gemeldet", seite.url, a.n)
            continue
        bilanz["geaendert"] += 1
        items.append(als_item(a, heute))

    speicher.speichern()
    bilanz["meldungen"] = len(items)
    log.info("Aenderungsradar: %d Seiten, %d gelesen, %d Grundlinie, "
             "%d geaendert, %d Umbau, %d ohne Werte (JavaScript), %d Fehler",
             bilanz["seiten"], bilanz["gelesen"], bilanz["grundlinie"],
             bilanz["geaendert"], bilanz["umgebaut"], bilanz["ohne_werte"],
             bilanz["fehler"])
    return items, bilanz
