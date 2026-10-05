"""DIE EINE Quelle der Anbieterfarben (Phase P2, Paket D1).

Vorher gab es DREI, und sie widersprachen sich:

  1. `geraete_verlauf.farbe_fuer()` - eine HASH-PALETTE. Sie vergab die
     Farbe nach `md5(anbietername) % 7` aus sieben neutralen Toenen. Die
     Telekom bekam damit das gruene `#217a3c` und stand im Preisverlauf
     (Reiter 3) GRUEN, waehrend dieselbe Telekom in der TCO-Zeitreihe
     MAGENTA war. Eine Hash-Palette kennt keine Marke; sie ratet eine
     Farbe, und Raten ist auf dieser Seite verboten (Clean Code 3).
  2. `geraete_zeitreihe.ANB_FARBE` - eine eigene Tabelle mit fuenf
     Eintraegen, deren Kommentar behauptete, sie sei "dieselbe wie --anb
     in style.css". Sie war es nur teilweise: 1&1 stand hier auf
     `#00589e`, nicht auf der Markenfarbe.
  3. `style.css` `.gr-anb--*` - zehn handgeschriebene Regeln. Wer einen
     Anbieter ergaenzte, musste sie an allen drei Orten ergaenzen und tat
     es nie.

Jetzt steht die Zuordnung GENAU HIER. Python liefert die Farbe fertig an
`geraete_verlauf` (Reiter 3, App-JS zeichnet die Kurve) und an
`geraete_zeitreihe` (die TCO-Zeitreihe, serverseitig als SVG); das
Stylesheet bekommt seinen Block aus `css_block()` eingesetzt
(`in_stylesheet()`), statt ihn von Hand zu fuehren - er bedient weiterhin
`geraete_tco_grafik.anbieter_slug()` und dessen `.gr-anb--<slug>`-Klassen.

Die Farbe ist NICHT der einzige Unterschied
--------------------------------------------
Vodafone-Rot `#e60000` und Telekom-Magenta `#e20074` sind die zwei
Marken, die auf dieser Seite am haeufigsten nebeneinander stehen - und
sie sind zugleich das schwierigste Paar der Palette: gemessen mit dem
Validator der `dataviz`-Skill (`scripts/validate_palette.js`, Modus
`light`, `--pairs all`) liegt Vodafone/Telekom bei ΔE 9,8 unter
simulierter Deuteranopie (PASS, ueber der Zielschwelle 8) aber bei ΔE
11,5 unter NORMALEM Sehen (FAIL, unter der harten Schwelle 15) - selbst
mit voller Farbwahrnehmung sind Rot und Magenta einander nahe genug, um
zu verwechseln. Deshalb traegt jede Reihe DREI Merkmale: Farbe,
STRICHART und MARKERFORM (plus, bei Vodafone, die groessere Strichstaerke
BREITE_EIGEN). Wer die Farben nicht unterscheiden kann, unterscheidet die
Linien an Muster und Form - dieselbe Antwort auf Farbfehlsichtigkeit UND
auf den Schwarzweissdruck.

Numerisch schwieriger als Vodafone/Telekom ist sogar das Graupaar
GRAU_HAENDLER/LUECKE_FARBE (ΔE 8,2 protan, unter der Normalsicht-Schwelle
15) - zwei blasse, absichtlich zurueckhaltende Neutraltoene lassen sich
per Farbe allein kaum weiter auseinanderziehen, ohne entweder zu dunkel
(Kontrast) oder zu hell (unsichtbar auf Papier) zu werden. Auch dieses
Paar traegt deshalb UNTERSCHIEDLICHE Strichart (Haendler "voll",
Luecke "luecke") und Markerform (Haendler Raute/Dreieck, Luecke
ausschliesslich Kreuz) - keins der beiden Merkmale teilt sich ein
anderer Eintrag dieser Tabelle.

Warum das hier steht und nicht in `config/*.yaml`
--------------------------------------------------
Eine Markenfarbe ist kein Betriebsparameter. Sie haengt an der Marke, an
den CSS-Klassennamen (`gr-anb--<slug>`) und an Tests, die sie im Browser
nachmessen - nicht an einem Lauf. Was hier tatsaechlich konfigurierbar
waere (welche Quellen ein Anbieter hat), steht laengst in
`config/geraete_quellen.yaml`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

BREITE_EIGEN = 3
BREITE_ANDERE = 2

STRICHMUSTER = {
    "voll": "none",
    "gestrichelt": "7 4",
    "gepunktet": "2 4",
    "luecke": "1 6",
}


@dataclass(frozen=True)
class Anbieterstil:
    """Alles, was eine Anbieterlinie zum Aussehen braucht - an einem Ort.

    `bekannt=False` heisst: fuer diesen Anbieter ist KEINE Farbe
    hinterlegt. Der Stil ist dann die benannte Luecke (`LUECKE`), nicht
    eine geratene Farbe - `name_zusatz` traegt den Grund bis in die
    Legende.
    """

    slug: str
    farbe: str
    marker_farbe: str
    marker_rand: str
    strich: str
    marker: str
    breite: int
    eigen: bool
    bekannt: bool
    name_zusatz: str = ""

    @property
    def muster(self) -> str:
        """Das `stroke-dasharray` dieser Strichart."""
        return STRICHMUSTER[self.strich]


def _stil(
    slug, farbe, strich, marker, *, marker_farbe="", marker_rand="none", eigen=False
) -> Anbieterstil:
    return Anbieterstil(
        slug=slug,
        farbe=farbe,
        marker_farbe=marker_farbe or farbe,
        marker_rand=marker_rand,
        strich=strich,
        marker=marker,
        breite=BREITE_EIGEN if eigen else BREITE_ANDERE,
        eigen=eigen,
        bekannt=True,
    )


GRAU_SERVICE = "#4a463e"
GRAU_HAENDLER = "#a8a297"

LUECKE_FARBE = "#c2bcaf"
LUECKE_NAME_ZUSATZ = "Farbe nicht hinterlegt"

LUECKE = Anbieterstil(
    slug="ohne-farbe",
    farbe=LUECKE_FARBE,
    marker_farbe=LUECKE_FARBE,
    marker_rand="none",
    strich="luecke",
    marker="kreuz",
    breite=BREITE_ANDERE,
    eigen=False,
    bekannt=False,
    name_zusatz=LUECKE_NAME_ZUSATZ,
)


ANBIETER_FARBE: dict[str, Anbieterstil] = {
    "vodafone": _stil("vodafone", "#e60000", "voll", "kreis", eigen=True),
    "telekom": _stil("telekom", "#e20074", "voll", "quadrat"),
    "o2": _stil("o2", "#0019a5", "voll", "dreieck"),
    "1&1": _stil("1-1", "#2f7fd1", "gestrichelt", "raute"),
    "congstar": _stil(
        "congstar",
        "#121212",
        "voll",
        "sechseck",
        marker_farbe="#ffed00",
        marker_rand="#121212",
    ),
    "mobilcom-debitel": _stil("mobilcom-debitel", GRAU_SERVICE, "gepunktet", "ring"),
    "freenet": _stil("freenet", GRAU_SERVICE, "gepunktet", "dreieck--runter"),
    "aldi talk": _stil("aldi-talk", GRAU_SERVICE, "gepunktet", "sechseck"),
    "medimax": _stil("medimax", GRAU_HAENDLER, "voll", "raute"),
    "electronicpartner": _stil("electronicpartner", GRAU_HAENDLER, "voll", "dreieck"),
    "saturn": _stil("saturn", GRAU_HAENDLER, "voll", "sechseck"),
}


def _schluessel(anbieter) -> str:
    return (anbieter or "").strip().lower()


def stil_fuer(anbieter: str) -> Anbieterstil:
    """Der Stil eines Anbieters - oder die benannte Luecke.

    Nie `None` und nie eine geratene Farbe: ein unbekannter Anbieter
    bekommt `LUECKE`, sein Name traegt in der Legende den Zusatz
    "Farbe nicht hinterlegt", und der Fall steht im Protokoll. Wer ihn
    sehen will, sieht ihn - im Bild UND im Log.
    """
    stil = ANBIETER_FARBE.get(_schluessel(anbieter))
    if stil is None:
        log.warning(
            "Anbieter ohne hinterlegte Farbe: %r - gezeichnet als benannte Luecke (%s)",
            anbieter,
            LUECKE_FARBE,
        )
        return LUECKE
    return stil


def ist_bekannt(anbieter: str) -> bool:
    return _schluessel(anbieter) in ANBIETER_FARBE


def farbe_fuer(anbieter: str) -> str:
    """Nur die Linienfarbe - fuer Aufrufer, die kein `style`-Attribut bauen."""
    return stil_fuer(anbieter).farbe


def slug_fuer(anbieter: str) -> str:
    """Der CSS-Klassenteil: `gr-anb--<slug>`.

    Fuer einen unbekannten Anbieter ist das `ohne-farbe` und damit
    dieselbe Klasse fuer alle - genau so, wie es aussehen soll.
    """
    return stil_fuer(anbieter).slug


def legendenname(anbieter: str) -> str:
    """Der Name, wie ihn die Legende zeigt - mit dem Luecken-Zusatz."""
    stil = stil_fuer(anbieter)
    return f"{anbieter} ({stil.name_zusatz})" if stil.name_zusatz else anbieter


MARKE = "/* @@ANBIETER-FARBEN@@ */"


class AnbieterfarbenFehlen(RuntimeError):
    """`style.css` hat den Platzhalter nicht - der Block kaeme nie an."""


def _regel(stil: Anbieterstil) -> str:
    return (
        f".gr-anb--{stil.slug}{{--anb:{stil.farbe};"
        f"--anb-marker:{stil.marker_farbe};"
        f"--anb-marker-rand:{stil.marker_rand};"
        f"--anb-strich:{stil.muster};"
        f"--anb-breite:{stil.breite}}}"
    )


def css_block() -> str:
    """Der ganze Anbieterfarben-Teil des Stylesheets, aus dieser Tabelle.

    Je Anbieter eine `.gr-anb--<slug>`-Regel, die `--anb` (Basisfarbe,
    von `geraete_tco_grafik` und den `.gr-tband-*`/`.gr-g0-*`-Regeln
    gelesen) und die drei Zusatzmerkmale setzt. Nichts davon steht noch
    von Hand im Stylesheet.
    """
    alle = list(ANBIETER_FARBE.values()) + [LUECKE]
    zeilen = [
        "/* ERZEUGT AUS report/anbieter_farben.py - NICHT VON HAND AENDERN.",
        "   Die Tabelle dort ist die einzige Quelle der Anbieterfarben;",
        "   dieser Block wird beim Rendern eingesetzt (in_stylesheet()). */",
    ]
    zeilen += [_regel(s) for s in alle]
    return "\n".join(zeilen)


def in_stylesheet(css: str) -> str:
    """Den erzeugten Block an die Stelle des Platzhalters setzen."""
    if MARKE not in css:
        raise AnbieterfarbenFehlen(
            f"style.css enthaelt {MARKE!r} nicht - ohne den Platzhalter "
            f"stuenden alle Anbieterlinien grau auf der Seite"
        )
    return css.replace(MARKE, css_block())
