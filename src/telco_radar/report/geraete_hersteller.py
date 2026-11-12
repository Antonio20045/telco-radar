"""Preisposition je Hersteller: wo steht Vodafone gegenüber den Wettbewerbern.

Antonio, 05.11.2026: die erste Übersichtsgrafik der Geräteseite zeigt
Hersteller (Apple, Samsung, Google, ...) statt einzelner Modelle, mit
wählbarem Zeitraum.

Antonio, 12.12.2026: aus der Tafel (eine Zahl je Hersteller x Wettbewerber)
UND der Punktwolke je Modell wird EIN Liniendiagramm - eine Linie je
Hersteller über die Zeit, plus die Leitlinie „Alle Hersteller". Die
Modellgrafik ist gefallen, die Erklärabsätze darunter auch. Gezeichnet wird
in `geraete_hersteller_grafik`; hier stehen die Zahlen.

KENNZAHL
  Abstand(Modell, Wettbewerber, Tag) = (TCO Vodafone - TCO Wettbewerber)
                                       / TCO Wettbewerber * 100
  TCO ist die Leitzahl der Seite (`LAUFZEIT` Monate, Band `BAND`); plus heißt:
  Vodafone ist teurer. Fehlt ein Preis, fehlt der Wert - nie eine 0.

ZEITRAUM
  7 / 30     Messtage der letzten 7 / 30 Kalendertage bis zum Stand
  eigen      von/bis, vom Browser gerechnet

Nichts wird fest verdrahtet: Modelle, Anbieter, Preise und Messtage kommen zur
Bauzeit aus den Daten. Der Server rechnet und zeichnet den Vorgabe-Zeitraum
(ohne JavaScript lesbar); die Tageswerte liegen als JSON im Dokument, `app.js`
schaltet den Zeitraum um und rechnet nach derselben Regel (ein Browsertest
hält beide zusammen). Ein Ausfall steht als `fehler` im Bild, nie als leeres
Bild.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from .. import rechenweise
from ..geraete_model import serie_aus_modell
from ..tco_model import zeitraum_vergleichbar
from . import geraete_hersteller_grafik as grafik
from . import geraete_rechenweg, geraete_zeitreihe
from .anbieter_farben import legendenname, slug_fuer
from .geraete_hersteller_text import (
    EIGEN,
    GLEICHAUF,
    KLEIN,
)
from .geraete_preisposition_preise import BAND, LAUFZEIT
from .geraete_tco_karten import ist_frisch

log = logging.getLogger(__name__)

WETTBEWERBER = tuple(a for a in geraete_rechenweg.ANBIETER_FOLGE if a != EIGEN)
HERSTELLER_VORAN = ("Apple", "Samsung", "Google")
GESAMT = "Alle"
FENSTER = (7, 30)
VORGABE_FENSTER = 30
SKALA = 40


def abstand(vodafone: float, wettbewerber: float) -> float:
    """Prozent, um die Vodafone über (+) oder unter (-) dem Wettbewerber liegt."""
    return (vodafone - wettbewerber) / wettbewerber * 100


def _familie(g) -> str:
    """Erstes Wort des Modellnamens („iPhone“, „Galaxy“, „Pixel“)."""
    return (g.modell or "").split(" ")[0]


def aktuelle_geraete(katalog) -> list:
    """Katalogeinträge, die in ihrer (Hersteller, Reihe) die höchste Generation
    tragen; nur handgepflegte (`auto` leer), nur mit Generation.

    Eine Reihe ohne Zahl im Namen („iPhone Air“) ist keine eigene Zählung: sie
    trägt die Generation des Jahrgangs, in dem sie erschien, und wird an den
    nummerierten Reihen derselben Familie („iPhone 18 Pro“) gemessen. Ist dort
    eine höhere Generation da, ist sie nicht mehr aktuell (Antonio: das
    iPhone 17 ist nicht mehr relevant)."""
    geraete = [
        g
        for g in getattr(katalog, "geraete", None) or []
        if g.generation is not None and not g.auto
    ]
    beste: dict[tuple[str, str], int] = {}
    familie: dict[tuple[str, str], int] = {}
    for g in geraete:
        reihe = (g.hersteller, serie_aus_modell(g.modell))
        beste[reihe] = max(beste.get(reihe, 0), g.generation)
        if any(z.isdigit() for z in g.modell or ""):
            f = (g.hersteller, _familie(g))
            familie[f] = max(familie.get(f, 0), g.generation)
    aus = []
    for g in geraete:
        reihe = (g.hersteller, serie_aus_modell(g.modell))
        if g.generation != beste[reihe]:
            continue
        if not any(z.isdigit() for z in g.modell or "") and g.generation < familie.get(
            (g.hersteller, _familie(g)), 0
        ):
            continue
        aus.append(g)
    return aus


def tageswerte(je_anbieter: dict) -> dict[str, dict[str, float]]:
    """{Anbieter: {Tag: TCO}} - nur zählende, frische Messungen der
    Standardlaufzeit; je Tag gilt die jüngste Rechenweise."""
    aus: dict[str, dict[str, float]] = {}
    for anbieter, werte in je_anbieter.items():
        reihe: dict[str, float] = {}
        for tag, m in rechenweise.juengste(werte).items():
            if not m.get("zaehlt") or m.get("wert") is None:
                continue
            if not zeitraum_vergleichbar(m.get("monate"), LAUFZEIT):
                continue
            abgerufen = ((m.get("satz") or {}).get("abgerufen_am") or "")[:10]
            if not ist_frisch(abgerufen, tag):
                continue
            reihe[tag] = m["wert"]
        aus[anbieter] = reihe
    return aus


def modelle_waehlen(
    katalog, tco: dict, messungen: dict
) -> tuple[list[dict], list[str]]:
    """(gewählte Modelle, Hersteller ohne Vodafone-Preis in einem aktuellen Gerät).

    Je aktuellem Gerät der kleinste Speicher, zu dem Vodafone je einen Preis
    gemessen hat. Ohne solchen Speicher bleibt das Gerät eine Lücke."""
    tco_ids = {m.get("id") for m in tco.get("modelle") or []}
    gewaehlt: list[dict] = []
    ohne: list[str] = []
    for geraet in aktuelle_geraete(katalog):
        treffer = None
        for speicher in sorted(geraet.speicher or []):
            mid = f"{geraet.device_id}-{speicher}"
            if mid not in tco_ids:
                continue
            je = messungen.get((mid, BAND, LAUFZEIT)) or {}
            if tageswerte({EIGEN: je.get(EIGEN, {})})[EIGEN]:
                treffer = mid
                break
        if treffer is None:
            ohne.append(geraet.hersteller)
        else:
            gewaehlt.append(
                {"id": treffer, "hersteller": geraet.hersteller, "name": geraet.modell}
            )
    return gewaehlt, ohne


def _abstaende(preise: dict[str, float]) -> list:
    """Abstand zu jedem Wettbewerber (None, wo ein Preis fehlt)."""
    vf = preise.get(EIGEN)
    return [
        round(abstand(vf, preise[w]), 2) if vf and preise.get(w) else None
        for w in WETTBEWERBER
    ]


def berechne(
    messungen: dict, tco: dict, katalog, heute: str, stand: str | None = None
) -> dict:
    """Alle Zahlen: Modelle und ihre Tageswerte (reine Rechnung)."""
    modelle, ohne = modelle_waehlen(katalog, tco, messungen)
    je_modell = {
        m["id"]: tageswerte(messungen.get((m["id"], BAND, LAUFZEIT)) or {})
        for m in modelle
    }
    tage = sorted({t for tw in je_modell.values() for r in tw.values() for t in r})
    stand = stand or heute or (tage[-1] if tage else "")
    pct: dict[str, list] = {}
    for tag in tage:
        pct[tag] = [
            _abstaende({a: r[tag] for a, r in je_modell[m["id"]].items() if tag in r})
            for m in modelle
        ]
    return {
        "stand": stand,
        "modelle": modelle,
        "ohne": ohne,
        "tage": tage,
        "pct": pct,
    }


def reihenfolge(rechnung: dict) -> list[str]:
    """Hersteller der Zeilen: die großen drei zuerst, dann nach Modellzahl."""
    zahl: dict[str, int] = {}
    for m in rechnung["modelle"]:
        zahl[m["hersteller"]] = zahl.get(m["hersteller"], 0) + 1
    voran = [h for h in HERSTELLER_VORAN if h in zahl]
    rest = sorted((h for h in zahl if h not in voran), key=lambda h: (-zahl[h], h))
    return voran + rest


def fenster_tage(tage: list[str], stand: str, fenster: int) -> list[str]:
    """Die Vergleichstage der letzten `fenster` Kalendertage bis `stand`."""
    if not tage:
        return []
    von = (date.fromisoformat(stand) - timedelta(days=fenster - 1)).isoformat()
    gewaehlt = [t for t in tage if von <= t <= stand]
    return gewaehlt


def ansicht(state_dir, tco: dict, katalog, tarifbestand, heute: str) -> dict:
    """`aufbereiten` mit den Messungen der Historie, die dieses Modul selbst
    liest (`geraete_zeitreihe._messungen`, dieselben wie die Zeitreihe)."""
    try:
        messungen = geraete_zeitreihe._messungen(
            Path(state_dir), tco, tarifbestand.je_id_aktuell, heute
        )
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as exc:
        log.exception("Messungen der Herstellergrafik nicht lesbar")
        return {"fehler": f"{type(exc).__name__}: {exc}", "leer": False}
    return aufbereiten(messungen, tco, katalog, heute)


def aufbereiten(messungen: dict | None, tco: dict, katalog, heute: str) -> dict:
    """Der Teil-Kontext der Seite: `leer`, `fehler` oder die Zeilen und das JSON.

    Der Ausfall wird gemeldet (`fehler`), nicht verschluckt."""
    if messungen is None:
        return {"fehler": "Messungen nicht lesbar", "leer": False}
    try:
        rechnung = berechne(messungen, tco, katalog, heute)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        log.exception("Herstellergrafik nicht aufbereitbar")
        return {"fehler": f"{type(exc).__name__}: {exc}", "leer": False}
    if not rechnung["modelle"]:
        return {"fehler": "", "leer": True}
    belegt = [
        j
        for j in range(len(WETTBEWERBER))
        if any(z[j] is not None for t in rechnung["tage"] for z in rechnung["pct"][t])
    ]
    spalten = [WETTBEWERBER[j] for j in belegt]
    alle_tage = grafik.vergleichstage(rechnung, belegt)
    if not alle_tage:
        return {"fehler": "", "leer": True}
    ordnung = reihenfolge(rechnung)
    stand = alle_tage[-1]
    tage = fenster_tage(alle_tage, stand, VORGABE_FENSTER)
    reihen = grafik.reihen(rechnung, belegt, tage, ordnung)
    titel = grafik.achsentitel(LAUFZEIT)
    titel_kurz = grafik.achsentitel(LAUFZEIT, kurz=True)
    daten = {
        "stand": stand,
        "w": list(WETTBEWERBER),
        "belegt": belegt,
        "h": [m["hersteller"] for m in rechnung["modelle"]],
        "ordnung": ordnung,
        "gesamtname": grafik.GESAMT_NAME,
        "tage": alle_tage,
        "pct": [rechnung["pct"][t] for t in alle_tage],
        "fenster": list(FENSTER),
        "vorgabe": VORGABE_FENSTER,
        "gleichauf": GLEICHAUF,
        "klein": KLEIN,
        "stile": grafik.stile(ordnung),
        "geo": grafik.geometrie(),
        "titel": titel,
        "titel_kurz": titel_kurz,
    }
    return {
        "fehler": "",
        "leer": False,
        "stand": stand,
        "wettbewerber": [
            {"name": w, "slug": slug_fuer(w), "legende": legendenname(w)}
            for w in spalten
        ],
        "einheit": titel,
        "reihen": reihen,
        "legende": [
            {
                "name": r["name"],
                "farbe": r["farbe"],
                "muster": r["muster"],
                "breite": r["breite"],
                "gesamt": r["gesamt"],
            }
            for r in reihen
        ],
        "svg_breit": grafik.svg(reihen, tage, True, titel),
        "svg_schmal": grafik.svg(reihen, tage, False, titel_kurz),
        "modelle": len(rechnung["modelle"]),
        "json": json.dumps(daten, ensure_ascii=False, separators=(",", ":")).replace(
            "</", "<\\/"
        ),
        "tage_von": alle_tage[0],
        "tage_bis": alle_tage[-1],
    }
