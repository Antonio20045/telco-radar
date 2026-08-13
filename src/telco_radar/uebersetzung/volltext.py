"""Den Artikeltext beschaffen - Feed zuerst, dann die Artikelseite.

Gemessen am 13.08.2026 ueber 1329 Eintraege aus 140 RSS-Quellen:

    Volltext schon im Feed          40,6 %   (kostet nichts)
    braucht den Artikelabruf        59,4 %

Das Konzept hatte den Artikelabruf als "Rueckfallweg fuer die Minderheit"
geplant. Er ist der HAUPTWEG - bei den fremdsprachigen Eintraegen brauchen
ihn 57 %. Deshalb ist er hier kein Anhaengsel, sondern die Stufe mit den
meisten Sicherungen.

Zwoelf echte fremdsprachige Artikel aus zwoelf Quellen gegengeprueft:
12x HTTP 200 (keine Sperre), 11x brauchbarer Fliesstext, 0x Navigation oder
Cookie-Banner im Extrakt, 0x abweichende Sprache zwischen Teaser und
Volltext.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..collect.http import fetch

log = logging.getLogger(__name__)

# Ab wie vielen Zeichen ein Text als Artikel gilt. Absolut gemessen, nicht
# als Vielfaches des Teasers: digi.no lieferte 141 Zeichen hinter einer
# Paywall gegen 45 Zeichen Teaser - als Faktor waeren das "3,1x laenger"
# und damit ein Treffer, absolut sind es zwei Saetze. Genau daran stirbt
# das Feature laut Premortem 1: Antonio klickt, bekommt drei Saetze, klickt
# nie wieder.
MINDESTLAENGE = 1200

# UND er muss deutlich mehr bieten als das, was ohnehin schon auf der Karte
# steht. Ein Extrakt, der den Teaser nur wiederholt, ist kein Angebot.
MINDESTFAKTOR = 1.5

# Ein Artikel jenseits dieser Groesse ist fast immer eine Sammelseite
# (Liveticker, Jahresrueckblick, Themenarchiv) und keine Meldung. Ihn zu
# uebersetzen kostet ein Vielfaches und liefert nichts, was ein Leser will.
HOECHSTLAENGE = 60000


@dataclass
class VolltextErgebnis:
    """Was der Beschaffungsversuch ergeben hat."""

    text: str = ""
    herkunft: str = ""      # "feed" | "artikel"
    grund: str = ""         # warum es NICHTS gab (leer, wenn text gesetzt)
    status: int = 0         # HTTP-Status des Artikelabrufs, 0 = nicht abgerufen

    @property
    def erfolg(self) -> bool:
        return bool(self.text)


def _extrahiere(html: str) -> str:
    """Fliesstext aus einer Artikelseite - mit einer erprobten Bibliothek.

    Bewusst kein Eigenbau: eine selbstgeschriebene Heuristik ueber tausend
    fremde Layouts liefert irgendwann Navigation und Cookie-Banner statt
    des Artikels, und das ist Premortem 2 - es beschaedigt das Vertrauen in
    die ganze Seite, nicht nur in diese eine Uebersetzung.

    `favor_precision=True` ist die Einstellung, die in der Messung ueber
    fuenf Sprachen sauberen Artikelanfang lieferte: sie laesst im Zweifel
    einen Randabsatz weg, statt einen Menuepunkt aufzunehmen.
    """
    try:
        import trafilatura
    except ImportError:  # pragma: no cover - haengt an der Installation
        log.warning("trafilatura ist nicht installiert - der Artikelabruf "
                    "faellt aus, der Feed-Weg laeuft weiter.")
        return ""
    try:
        text = trafilatura.extract(
            html, include_comments=False, include_tables=False,
            favor_precision=True) or ""
    except Exception as exc:  # noqa: BLE001 - eine Bibliothek darf nichts kosten
        log.debug("trafilatura scheiterte: %s", exc)
        return ""
    return text.strip()


def _taugt(text: str, teaser: str) -> tuple[bool, str]:
    if len(text) < MINDESTLAENGE:
        return False, f"zu kurz ({len(text)} < {MINDESTLAENGE} Zeichen)"
    if teaser and len(text) < MINDESTFAKTOR * len(teaser):
        return False, (f"kaum mehr als der Teaser ({len(text)} gegen "
                       f"{len(teaser)} Zeichen)")
    if len(text) > HOECHSTLAENGE:
        return False, f"zu lang ({len(text)} Zeichen), vermutlich Sammelseite"
    return True, ""


def hole_volltext(item, http_cfg: dict, artikelabruf: bool = True
                  ) -> VolltextErgebnis:
    """Den Artikeltext beschaffen, billigster Weg zuerst.

    Ruft die ARTIKELSEITE ab - den Weg also, den sonst kein Collector geht.
    Er laeuft ueber dasselbe `collect/http.py` wie alles andere und damit
    durch dieselbe Host-Drosselung, denselben User-Agent-Rueckfall und
    dieselben Fristen. Ein zweiter HTTP-Weg daneben waere eine zweite
    Hoeflichkeitsregel, die niemand pflegt.
    """
    teaser = (item.summary or "").strip()

    # 1. Was der Feed schon mitgebracht hat (collect/rss.py, content:encoded).
    if item.volltext and len(item.volltext) >= MINDESTLAENGE:
        if len(item.volltext) <= HOECHSTLAENGE:
            return VolltextErgebnis(text=item.volltext, herkunft="feed")
        return VolltextErgebnis(
            grund=f"Feedtext zu lang ({len(item.volltext)} Zeichen)")

    if not artikelabruf:
        return VolltextErgebnis(grund="kein Volltext im Feed, Abruf ist aus")
    if not item.url:
        return VolltextErgebnis(grund="keine Artikeladresse")

    # 2. Die Artikelseite selbst.
    try:
        resp = fetch(item.url, http_cfg)
    except Exception as exc:  # noqa: BLE001
        return VolltextErgebnis(grund=f"Abruf fehlgeschlagen: "
                                      f"{type(exc).__name__}")
    if resp.status_code >= 400:
        return VolltextErgebnis(grund=f"HTTP {resp.status_code}",
                                status=resp.status_code)

    text = _extrahiere(resp.text)
    if not text:
        return VolltextErgebnis(grund="kein Fliesstext erkannt",
                                status=resp.status_code)
    passt, grund = _taugt(text, teaser)
    if not passt:
        return VolltextErgebnis(grund=grund, status=resp.status_code)
    return VolltextErgebnis(text=text, herkunft="artikel",
                            status=resp.status_code)
