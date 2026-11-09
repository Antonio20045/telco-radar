"""Die Bildfolge eines Belegs: mehrere Bilder entlang des Klickwegs, in Reihenfolge.

Ein Beleg ist entweder ein Bild (Normalfall, ``url``) oder eine Bildfolge: eine Liste
von ``{datei, schritt, text}`` im Manifest-Eintrag (``beleg_manifest``) plus die Liste
``bildfolge_fehlt`` der Schritte ohne veröffentlichtes Bild (``"<schritt>: <Grund>"``).
``datei`` ist die vollständige Adresse eines Anhangs der Belege-Releases
(``adresse_gueltig``); ein Dateiname ohne Adresse, ein Pfad oder eine fremde Adresse
fällt weg, denn aus einem bloßen Namen wüsste die Seite nicht, ob die Datei
veröffentlicht ist (fail-closed: lieber kein Bild als ein kaputter Link).
``schritt`` benennt den Schritt des Wegs, ``text`` ist die Beschriftung der Erfassung.

Ergebnis ist die Reihenfolge der Seite: die Bilder in der Reihenfolge der Liste, jede
Lücke an der Stelle ihres Schritts (``SCHRITTE``) mit ihrem Grund statt eines Bilds.
Es wird nie ein Bild ergänzt, das nicht in der Liste steht, und „Schritt i von N“
zählt Bilder und Lücken, also den ganzen Weg.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .beleg_regeln import ENDUNG, REPO, TAG_TAG, zerlege_folgename

PREIS = "preis"
SCHRITTE = {
    "geraet_speicher": "Gerät und Speicher gewählt",
    "tarif": "Tarif gewählt",
    "laufzeit": "Laufzeit und Raten gewählt",
    PREIS: "Zuzahlung und Monatsrate",
}
ADRESSE_ANFANG = f"https://github.com/{REPO}/releases/download/{TAG_TAG}"
"""Jedes veröffentlichte Belegbild hat eine Adresse, die so beginnt."""


def adresse_gueltig(datei: str) -> bool:
    """Ist ``datei`` die Adresse eines Anhangs der Belege-Releases?"""
    rest = datei.removeprefix(ADRESSE_ANFANG)
    if rest == datei or not datei.endswith(ENDUNG):
        return False
    tag_und_name = rest.split("/")
    return len(tag_und_name) == 2 and all(tag_und_name) and ".." not in rest


def kennung_der_adresse(adresse: str) -> str | None:
    """Die Kennung der Position im Namen einer Adresse; ``None`` bei einem Namen ohne
    Kennung (altes Einzelbild ``<geraet>__<anbieter>__<Tag>.webp``)."""
    folge = zerlege_folgename(str(adresse).rsplit("/", 1)[-1])
    return None if folge is None else folge.kennung


def fremd_zur_kennung(
    url: str, bildfolge: Iterable[Mapping[str, str]], kennung: str
) -> str:
    """Grund, warum Einzelbild oder Folge nicht zur Position ``kennung`` gehören;
    leer, wenn sie dazugehören (der Beweis ist der Name, nicht die Annahme).

    Das Einzelbild darf ohne Kennung sein (alter Bestand: nicht beweisbar, aber nie
    Teil einer Folge). Jeder Schritt einer Folge muss dagegen die Kennung der Zeile
    tragen und im Namen seinen Schritt nennen; ein einziger fremder Schritt verwirft
    alles (kein Mischbild)."""
    eigene = kennung_der_adresse(url)
    if eigene is not None and eigene != kennung:
        return f"Einzelbild gehört zur Messung {eigene}, die Zeile zu {kennung}"
    for schritt in bildfolge:
        if not schritt.get("url"):
            continue
        folge = zerlege_folgename(str(schritt["url"]).rsplit("/", 1)[-1])
        if folge is None or folge.schritt != schritt.get("schritt"):
            return f"Schritt {schritt.get('schritt')} ohne passenden Namen"
        if folge.kennung != kennung:
            return (
                f"Schritt {folge.schritt} gehört zur Messung {folge.kennung}, "
                f"die Zeile zu {kennung}"
            )
    return ""


def _eintrag(schritt: str, url: str, text: str, grund: str) -> dict[str, str]:
    return {
        "url": url,
        "schritt": schritt,
        "name": SCHRITTE.get(schritt, schritt),
        "text": text,
        "fehlt": grund,
    }


def _luecken(roh: Any) -> list[dict[str, str]]:
    """Die Lücken ``"<schritt>: <Grund>"`` als Einträge ohne Adresse."""
    if not isinstance(roh, list | tuple):
        return []
    luecken = []
    for zeile in roh:
        schritt, trenner, grund = str(zeile).partition(": ")
        if trenner and schritt.strip() and grund.strip():
            luecken.append(_eintrag(schritt.strip(), "", "", grund.strip()))
    return luecken


def _stelle(fertig: list[dict[str, str]], schritt: str) -> int:
    """Wo die Lücke ``schritt`` einzufügen ist: vor dem ersten Bild eines späteren
    Schritts, sonst am Ende; ein fremder Schritt steht am Ende."""
    folge = list(SCHRITTE)
    if schritt not in folge:
        return len(fertig)
    platz = folge.index(schritt)
    for nr, bild in enumerate(fertig):
        if bild["schritt"] in folge and folge.index(bild["schritt"]) > platz:
            return nr
    return len(fertig)


def normalisiere(roh: Any, fehlt: Any = None) -> tuple[dict[str, str], ...]:
    """``roh`` als Liste von ``{url, schritt, name, text, fehlt}``.

    Ein Bild hat ``url`` und ein leeres ``fehlt``; eine Lücke hat leere ``url`` und
    ihren Grund in ``fehlt``. Keine Liste gibt ``()``; ohne ein einziges lesbares
    Bild gibt es keine Folge (auch keine Lücken), die Seite zeigt dann das Einzelbild.
    Nennen die Adressen mehr als eine Kennung, ist es eine Mischfolge: ``()``.
    """
    if not isinstance(roh, list | tuple):
        return ()
    fertig = []
    for eintrag in roh:
        if not isinstance(eintrag, dict):
            continue
        datei = str(eintrag.get("datei") or "").strip()
        if not adresse_gueltig(datei):
            continue
        schritt = str(eintrag.get("schritt") or "").strip()
        text = str(eintrag.get("text") or "").strip()
        fertig.append(_eintrag(schritt, datei, text, ""))
    if not fertig:
        return ()
    if len({k for f in fertig if (k := kennung_der_adresse(f["url"]))}) > 1:
        return ()
    gezeigt = {f["schritt"] for f in fertig}
    for luecke in _luecken(fehlt):
        if luecke["schritt"] not in gezeigt:
            fertig.insert(_stelle(fertig, luecke["schritt"]), luecke)
    return tuple(fertig)
