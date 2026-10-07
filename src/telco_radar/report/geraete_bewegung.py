"""P4 (28.09.2026): der wöchentliche BEWEGUNGSBLOCK für den Newsletter.

Die Frage, die er beantwortet: Hat sich in der letzten Woche der Abstand
eines Wettbewerbers zu Vodafone bei einem Gerät spürbar verändert?

Gemessen wird je (Modell, Band, Wettbewerber) die Änderung des ABSTANDS
    A(t) = Leitzahl Wettbewerber(t) - Leitzahl Vodafone(t)
zwischen dem Stichtag und sieben Tage davor. Gemeldet wird, was die
Schwelle überschreitet (`BEWEGUNG_EURO` ODER `BEWEGUNG_PROZENT` der
Vodafone-Leitzahl am Stichtag).

DIE WERTE KOMMEN AUS DER ZEITREIHE (`geraete_zeitreihe._messungen`), nicht
aus einer zweiten Lesung der Historie: dieselbe Zahl, die der Graph an
diesem Tag zeigt, und derselbe Deep-Link führt dorthin (Clean Code 1).

DIE EINE REGEL, AN DER DIESER BLOCK HÄNGT: verglichen wird nur DASSELBE
Angebot an beiden Tagen, auf beiden Seiten. Die Zeitreihe führt je Tag das
günstigste gemessene Bündel. Fehlt an einem Tag ein Tarif (Vodafone liest
Mobil S nicht jeden Tag), springt das günstigste Bündel auf einen anderen
Tarif - eine Stufe von 240 EUR, ohne dass irgendwer seinen Preis geändert
hätte. Am echten Bestand vom 27.09.2026 waren das alle sechs Treffer der
naiven Rechnung. Dieselbe Lehre wie P0-A2 (`_bewegung`): die Differenz
zweier Angebote ist keine Preisänderung. Ein Angebotswechsel ist deshalb
„ohne Aussage" und wird gezählt, nie gemeldet (Clean Code 4).

Ebenso ohne Aussage: ein Bruch der Rechenweise (`rechenweise`) auf einer Seite -
dieselbe Antwort anders gelesen ist keine Preisänderung; ist er der einzige Grund,
nennt der Ausfall ihn (`AUSFALL_RECHENWEISE`). Ebenso eine Seite ohne Messung im
Toleranzfenster um einen der beiden Tage, eine Messung, deren Bündel nicht zählt
(Notbremse: Schätzung oder abgelaufene Aktion, `zaehlt` aus `_messungen`), und eine
Leitzahl über einen anderen Zeitraum als den ihrer Ratenlaufzeit (sie ist mit
Vodafones nicht vergleichbar). Seit Datenkonzept Geräte Schritt 2 ist
jede Reihe eine Ratenlaufzeit (Schlüssel `(modell, band, laufzeit)`): 24
Raten werden nur mit Vodafones 24 Raten verglichen.

WAS DER BLOCK NICHT SIEHT: `wert` ist die Leitzahl nach dem HEUTIGEN
Tarifstamm (A1, `_messungen`). Eine Aenderung des Tarifgrundpreises
zwischen den beiden Tagen erscheint deshalb nicht als Bewegung; gemessen
werden Geraeteraten, Zuzahlung und Anschlusspreis des Buendels.

Ist KEIN Vergleich pruefbar, ist das ein benannter Ausfall und kein
„keine Bewegung" (Clean Code 4) - sonst meldete die Mail Ruhe, waehrend
der Vodafone-Adapter wochenlang nichts liest.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta

from .. import rechenweise
from ..tco_model import TCO_HORIZONT, zeitraum_vergleichbar
from . import geraete_notbremse as notbremse
from .geraete_laufzeit import zeitraum

BEWEGUNG_EURO = 50.0
BEWEGUNG_PROZENT = 5.0
FENSTER_TAGE = 7
TOLERANZ_TAGE = 3
MAX_ZEILEN = 5

EIGEN = "Vodafone"

log = logging.getLogger(__name__)

AUSFALL_KEINE_MESSUNG = "keine Messung in der Gerätehistorie"
AUSFALL_NICHT_PRUEFBAR = "kein Vergleich mit Vodafone war prüfbar"
AUSFALL_AUFBEREITUNG = "die Gerätedaten ließen sich nicht aufbereiten"
AUSFALL_VERALTET = "die letzte Vodafone-Messung vom {tag} ist veraltet"
AUSFALL_RECHENWEISE = (
    f"{rechenweise.BRUCH}: im Wochenfenster kein Vergleich mit gleicher Rechnung"
)

GRUND_MESSUNG = "messung_fehlt"
GRUND_WECHSEL = "angebotswechsel"
GRUND_ZEITRAUM = "anderer_zeitraum"
GRUND_ZAEHLT_NICHT = "zaehlt_nicht"
GRUND_RECHENWEISE = "rechenweise_geaendert"


def _messung_um(slot: dict, tag: str) -> dict | None:
    """Die jüngste Messung am Tag oder bis `TOLERANZ_TAGE` davor."""
    t = date.fromisoformat(tag)
    for k in range(TOLERANZ_TAGE + 1):
        m = slot.get((t - timedelta(days=k)).isoformat())
        if m is not None:
            return m
    return None


def stichtag_aus(messungen: dict, anbieter: str | None = None) -> str | None:
    """Der jüngste Messtag der Historie - aller Anbieter oder eines."""
    tage = {
        d
        for reihen in messungen.values()
        for name, slot in reihen.items()
        if anbieter is None or name == anbieter
        for d in slot
    }
    return max(tage) if tage else None


def _band_label(band_katalog: dict, band: str, laufzeit: int | None) -> str:
    """Das Band, wie Seite und Mail es nennen - mit der Ratenlaufzeit."""
    label = (band_katalog.get(band) or {}).get("label", band)
    return label if laufzeit is None else f"{label} · {laufzeit} Raten"


def _link(modell: str, band: str, laufzeit: int | None) -> str:
    """Der Deep-Link auf genau das Paar, dessen Zahl die Zeile nennt."""
    link = f"geraete.html?modell={modell}&band={band}"
    return link if laufzeit is None else f"{link}&laufzeit={laufzeit}"


def ist_bewegung(delta: float, eigen_wert: float) -> bool:
    """Überschreitet die Abstandsänderung die Schwelle? ODER, nicht UND."""
    betrag = abs(delta)
    return betrag > BEWEGUNG_EURO or betrag > eigen_wert * BEWEGUNG_PROZENT / 100


def _ohne_aussage(
    seiten: tuple[dict, dict, dict, dict], schluessel, h: int
) -> str | None:
    """Warum der Vergleich (Vodafone vorher, nachher, Wettbewerber vorher, nachher)
    keine Aussage trägt - None, wenn er sie trägt."""
    v0, v1, c0, c1 = seiten
    if not all(notbremse.zaehlt(m) for m in seiten):
        return GRUND_ZAEHLT_NICHT
    if schluessel(c0["satz"]) != schluessel(c1["satz"]) or schluessel(
        v0["satz"]
    ) != schluessel(v1["satz"]):
        return GRUND_WECHSEL
    if not (
        rechenweise.gleich(v0["satz"], v1["satz"])
        and rechenweise.gleich(c0["satz"], c1["satz"])
    ):
        return GRUND_RECHENWEISE
    if not all(zeitraum_vergleichbar(m["monate"], h) for m in seiten):
        return GRUND_ZEITRAUM
    return None


def bewegungen(
    messungen: dict,
    erlaubt: dict,
    titel: dict,
    band_katalog: dict,
    schluessel,
    stichtag: str | None = None,
) -> dict:
    """Der Block als reines Dict - so steht er im Berichts-JSON.

    `messungen` ist `geraete_zeitreihe._messungen()`, `erlaubt` die
    Wahl-Menge der Zeitreihe (nur Paare, die der Deep-Link auch öffnet),
    `schluessel` die Bündel-ID eines Historiensatzes
    (`geraete_zeitreihe.buendel_schluessel`).
    """
    bis = stichtag or stichtag_aus(messungen)
    if bis is None:
        return ausfall(AUSFALL_KEINE_MESSUNG)
    von = (date.fromisoformat(bis) - timedelta(days=FENSTER_TAGE)).isoformat()
    treffer: list[dict] = []
    ohne: Counter = Counter()
    geprueft = 0
    for paar, anbieter in sorted(messungen.items()):
        modell, band = paar[0], paar[1]
        laufzeit = paar[2] if len(paar) > 2 else None
        if band not in (erlaubt.get(modell) or []):
            continue
        h = TCO_HORIZONT if laufzeit is None else zeitraum(laufzeit)
        v0 = _messung_um(anbieter.get(EIGEN) or {}, von)
        v1 = _messung_um(anbieter.get(EIGEN) or {}, bis)
        for name in sorted(anbieter):
            if name == EIGEN:
                continue
            c0 = _messung_um(anbieter[name], von)
            c1 = _messung_um(anbieter[name], bis)
            if v0 is None or v1 is None or c0 is None or c1 is None:
                ohne[GRUND_MESSUNG] += 1
                continue
            grund = _ohne_aussage((v0, v1, c0, c1), schluessel, h)
            if grund:
                ohne[grund] += 1
                continue
            geprueft += 1
            fremd_delta = round(c1["wert"] - c0["wert"], 2)
            eigen_delta = round(v1["wert"] - v0["wert"], 2)
            delta = round(fremd_delta - eigen_delta, 2)
            if not ist_bewegung(delta, v1["wert"]):
                continue
            treffer.append(
                {
                    "modell": modell,
                    "band": band,
                    "geraet": titel.get(modell) or modell,
                    "laufzeit": laufzeit,
                    "band_label": _band_label(band_katalog, band, laufzeit),
                    "anbieter": name,
                    "abstand_vorher": round(c0["wert"] - v0["wert"], 2),
                    "abstand_jetzt": round(c1["wert"] - v1["wert"], 2),
                    "delta": delta,
                    "fremd_delta": fremd_delta,
                    "eigen_delta": eigen_delta,
                    "fremd_wert": c1["wert"],
                    "eigen_wert": v1["wert"],
                    "quelle_url": c1["satz"].get("quelle_url") or "",
                    "eigen_quelle_url": v1["satz"].get("quelle_url") or "",
                    "link": _link(modell, band, laufzeit),
                }
            )
    treffer.sort(key=lambda t: (-abs(t["delta"]), t["geraet"], t["anbieter"]))
    if not geprueft:
        log.error("Bewegungsblock: kein Vergleich pruefbar (%s)", dict(ohne))
        grund = AUSFALL_RECHENWEISE if set(ohne) == {GRUND_RECHENWEISE} else None
        return dict(
            ausfall(grund or AUSFALL_NICHT_PRUEFBAR),
            ohne_aussage=dict(sorted(ohne.items())),
        )
    return {
        "error": None,
        "stichtag": bis,
        "vergleichstag": von,
        "eigen_stichtag": stichtag_aus(messungen, EIGEN),
        "zeilen": treffer[:MAX_ZEILEN],
        "weitere": max(0, len(treffer) - MAX_ZEILEN),
        "geprueft": geprueft,
        "ohne_aussage": dict(sorted(ohne.items())),
    }


def ausfall(grund: str) -> dict:
    """Der benannte Ausfall: die Mail sagt ihn, statt „nichts" zu melden."""
    return {
        "error": grund,
        "zeilen": [],
        "weitere": 0,
        "geprueft": 0,
        "ohne_aussage": {},
    }


def erste_ausgabe_der_woche(reports_dir, heute: date) -> bool:
    """Ist `heute` die erste Radar-Ausgabe seiner ISO-Woche?

    Der Block ist wöchentlich, der Radar-Lauf zweimal (Mi und Fr). Gerechnet
    wird er in jedem Lauf (er steht in jedem Berichts-JSON); die Mail zeigt
    ihn nur in der ersten Ausgabe der Woche.
    """
    woche = heute.isocalendar()[:2]
    for pfad in reports_dir.glob("*.json"):
        try:
            tag = date.fromisoformat(pfad.stem)
        except ValueError:
            continue
        if tag < heute and tag.isocalendar()[:2] == woche:
            return False
    return True


def fuer_bericht(root, heute: date, reports_dir) -> dict:
    """Der Block für das Berichts-JSON des Radar-Laufs.

    Liest dieselbe Aufbereitung wie die Geräteseite (`geraete_view`), damit
    Zahl und Link der Mail genau das zeigen, was die Seite zeigt. Jeder
    Ausfall wird benannt (Regel 9), nie als „keine Bewegung" ausgegeben.
    """
    from pathlib import Path

    from ..geraete_config import lade_katalog, lade_quellen
    from . import geraete_view

    root = Path(root)
    try:
        geraete = geraete_view.aufbereiten(
            root / "data" / "state",
            lade_quellen(root),
            lade_katalog(root),
            heute=heute.isoformat(),
        )
        block = dict(
            (geraete.get("zeitreihe") or {}).get("bewegung_woche")
            or ausfall(AUSFALL_AUFBEREITUNG)
        )
    except Exception as exc:  # noqa: BLE001
        log.error(
            "Bewegungsblock: Geraetedaten nicht aufbereitbar: %s: %s",
            type(exc).__name__,
            exc,
        )
        block = ausfall(AUSFALL_AUFBEREITUNG)
    eigen = block.get("eigen_stichtag")
    if not block.get("error") and (
        not eigen or date.fromisoformat(eigen) < heute - timedelta(days=TOLERANZ_TAGE)
    ):
        log.error("Bewegungsblock: letzte Vodafone-Messung %s", eigen)
        tag = date.fromisoformat(eigen).strftime("%d.%m.%Y") if eigen else "?"
        block = ausfall(AUSFALL_VERALTET.replace("{tag}", tag))
    block["im_newsletter"] = erste_ausgabe_der_woche(Path(reports_dir), heute)
    return block
