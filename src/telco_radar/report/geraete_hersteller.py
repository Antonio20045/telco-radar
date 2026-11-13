"""Preisposition je Hersteller: wo steht Vodafone gegenüber den Wettbewerbern.

Antonio, 05.11.2026: die erste Übersichtsgrafik der Geräteseite zeigt
Hersteller (Apple, Samsung, Google, ...) statt einzelner Modelle, mit
wählbarem Zeitraum (aktuell, 7 Tage, 30 Tage, eigener Zeitraum).

KENNZAHL
  Abstand(Modell, Wettbewerber, Tag) = (TCO Vodafone - TCO Wettbewerber)
                                       / TCO Wettbewerber * 100
  TCO ist die Leitzahl der Seite (`LAUFZEIT` Monate, Band `BAND`); plus heißt:
  Vodafone ist teurer. Eine Zelle (Hersteller x Wettbewerber) ist das Mittel
  dieser Abstände über die aktuellen Modelle des Herstellers, die Vodafone
  UND der Wettbewerber mit einem echten Preis führen (je Modell vorher das
  Mittel über die Messtage des Zeitraums); die Zahl der Modelle steht dabei.
  Fehlt ein Preis, fehlt die Zelle - nie ein Wert 0.

ZEITRAUM
  aktuell    die Karten, die die Seite heute zeigt (`preise_je_anbieter`)
  7 / 30     Messtage der letzten 7 / 30 Kalendertage bis zum Stand
  eigen      von/bis, vom Browser gerechnet

Nichts wird fest verdrahtet: Modelle, Anbieter, Preise und Messtage kommen zur
Bauzeit aus den Daten. Wenn ein Anbieter (o2: 24 Raten) neue Preise
bekommt, füllen sich seine Zellen ohne Eingriff. Der Server rechnet und
zeichnet die Ansicht „aktuell“ (ohne JavaScript lesbar); die Tageswerte
liegen als JSON im Dokument, `app.js` schaltet den Zeitraum um. Ein Ausfall
steht als `fehler` im Bild, nie als leeres Bild.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

from .. import rechenweise
from ..geraete_model import serie_aus_modell
from ..tco_model import zeitraum_vergleichbar
from . import geraete_notbremse, geraete_rechenweg, geraete_zeitreihe
from .anbieter_farben import legendenname, slug_fuer
from .geraete_hersteller_text import (
    EIGEN,
    GLEICHAUF,
    KLEIN,
    NBSP,
    erklaerung,
    modell_wort,
    prozent_text,
    richtung,
)
from .geraete_preisposition_preise import BAND, LAUFZEIT, preise_je_anbieter
from .geraete_tco_karten import ist_frisch

log = logging.getLogger(__name__)

WETTBEWERBER = tuple(a for a in geraete_rechenweg.ANBIETER_FOLGE if a != EIGEN)
HERSTELLER_VORAN = ("Apple", "Samsung", "Google")
GESAMT = "Alle"
FENSTER = (7, 30)
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
    """{Anbieter: {Tag: TCO}} - nur an ihrem Tag zählende, frische Messungen der
    Standardlaufzeit; je Tag gilt die jüngste Rechenweise."""
    aus: dict[str, dict[str, float]] = {}
    for anbieter, werte in je_anbieter.items():
        reihe: dict[str, float] = {}
        for tag, m in rechenweise.juengste(werte).items():
            if not geraete_notbremse.zaehlt_am_tag(m) or m.get("wert") is None:
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


def _wert_je_anbieter(karten: dict) -> dict[str, float]:
    return {a: k["gesamt"] for a, k in karten.items() if k.get("gesamt")}


def _abstaende(preise: dict[str, float]) -> list:
    """Abstand zu jedem Wettbewerber (None, wo ein Preis fehlt)."""
    vf = preise.get(EIGEN)
    return [
        round(abstand(vf, preise[w]), 2) if vf and preise.get(w) else None
        for w in WETTBEWERBER
    ]


def _mittel(zeilen: list[list], j: int) -> tuple[float | None, int]:
    werte = [z[j] for z in zeilen if z[j] is not None]
    return (sum(werte) / len(werte), len(werte)) if werte else (None, 0)


def berechne(
    messungen: dict, tco: dict, katalog, heute: str, stand: str | None = None
) -> dict:
    """Alle Zahlen: Modelle, Tageswerte, Werte „aktuell“ (reine Rechnung).

    `tage` sind nur die Tage mit mindestens einem Abstand. Ein Tag ohne eine
    einzige Zelle zeigt nichts, zählte aber in „Mittel aus N Messtagen“ mit
    und schob das früheste wählbare Datum des eigenen Zeitraums nach vorn.
    """
    modelle, ohne = modelle_waehlen(katalog, tco, messungen)
    modell_je_id = {m.get("id"): m for m in tco.get("modelle") or []}
    je_modell = {
        m["id"]: tageswerte(messungen.get((m["id"], BAND, LAUFZEIT)) or {})
        for m in modelle
    }
    gemessen = sorted({t for tw in je_modell.values() for r in tw.values() for t in r})
    alle: dict[str, list] = {}
    for tag in gemessen:
        alle[tag] = [
            _abstaende({a: r[tag] for a, r in je_modell[m["id"]].items() if tag in r})
            for m in modelle
        ]
    tage = [t for t in gemessen if any(w is not None for z in alle[t] for w in z)]
    pct = {t: alle[t] for t in tage}
    stand = stand or heute or (tage[-1] if tage else "")
    aktuell = [
        _abstaende(_wert_je_anbieter(preise_je_anbieter(modell_je_id.get(m["id"]))))
        for m in modelle
    ]
    tarife: dict[str, set[str]] = {}
    for m in modelle:
        karten = preise_je_anbieter(modell_je_id.get(m["id"]))
        for anbieter, karte in karten.items():
            if karte.get("tarif"):
                tarife.setdefault(anbieter, set()).add(karte["tarif"])
    return {
        "stand": stand,
        "modelle": modelle,
        "ohne": ohne,
        "tarife": {a: sorted(t) for a, t in tarife.items()},
        "tage": tage,
        "pct": pct,
        "aktuell": aktuell,
    }


def mittel_ueber_tage(rechnung: dict, von: str, bis: str) -> tuple[list[list], int]:
    """Je Modell und Wettbewerber das Mittel der Messtage von..bis, plus Tageszahl.
    Die Referenz der Browser-Rechnung in `app.js` (Tests vergleichen beide)."""
    tage = [t for t in rechnung["tage"] if von <= t <= bis]
    zeilen = []
    for i in range(len(rechnung["modelle"])):
        zeile = []
        for j in range(len(WETTBEWERBER)):
            werte = [
                rechnung["pct"][t][i][j]
                for t in tage
                if rechnung["pct"][t][i][j] is not None
            ]
            zeile.append(sum(werte) / len(werte) if werte else None)
        zeilen.append(zeile)
    return zeilen, len(tage)


def zeitraum(rechnung: dict, tage: int) -> tuple[list[list], int]:
    """Werte der letzten `tage` Kalendertage bis zum Stand."""
    bis = date.fromisoformat(rechnung["stand"])
    von = (bis - timedelta(days=tage - 1)).isoformat()
    return mittel_ueber_tage(rechnung, von, bis.isoformat())


def zellen(rechnung: dict, werte: list[list]) -> dict[str, list]:
    """{Hersteller (und GESAMT): [(Mittel, Modelle) je Wettbewerber]}."""
    aus: dict[str, list[list]] = {}
    for m, zeile in zip(rechnung["modelle"], werte, strict=True):
        aus.setdefault(m["hersteller"], []).append(zeile)
        aus.setdefault(GESAMT, []).append(zeile)
    return {
        h: [_mittel(zeilen, j) for j in range(len(WETTBEWERBER))]
        for h, zeilen in aus.items()
    }


def reihenfolge(rechnung: dict) -> list[str]:
    """Hersteller der Zeilen: die großen drei zuerst, dann nach Modellzahl."""
    zahl: dict[str, int] = {}
    for m in rechnung["modelle"]:
        zahl[m["hersteller"]] = zahl.get(m["hersteller"], 0) + 1
    voran = [h for h in HERSTELLER_VORAN if h in zahl]
    rest = sorted((h for h in zahl if h not in voran), key=lambda h: (-zahl[h], h))
    return voran + rest


def _zelle(w: str, mittel: float | None, n: int) -> dict:
    """Eine Zelle fürs Template; ohne Preis: benannte Lücke, kein Wert."""
    zelle = {"slug": slug_fuer(w), "name": w, "legende": legendenname(w)}
    if mittel is None:
        return {
            **zelle,
            "leer": True,
            "duenn": False,
            "text": "–",
            "n_text": "kein Preis",
            "n": 0,
        }
    breite = min(abs(mittel), SKALA) / SKALA * 50
    return {
        **zelle,
        "leer": False,
        "duenn": n < KLEIN,
        "wert": f"{mittel:.2f}",
        "n": n,
        "text": prozent_text(mittel),
        "richtung": richtung(mittel),
        "n_text": modell_wort(n),
        "links": f"{50 if mittel >= 0 else 50 - breite:.2f}",
        "breite": f"{breite:.2f}",
    }


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
    aktuell = zellen(rechnung, rechnung["aktuell"])
    belegt = [
        j
        for j in range(len(WETTBEWERBER))
        if aktuell[GESAMT][j][0] is not None
        or any(z[j] is not None for t in rechnung["tage"] for z in rechnung["pct"][t])
    ]
    spalten = [WETTBEWERBER[j] for j in belegt]
    ohne_wb = [w for w in WETTBEWERBER if w not in spalten]
    zeilen = [
        {
            "hersteller": h,
            "name": "Alle Hersteller" if h == GESAMT else h,
            "gesamt": h == GESAMT,
            "zellen": [_zelle(WETTBEWERBER[j], *aktuell[h][j]) for j in belegt],
        }
        for h in [*reihenfolge(rechnung), GESAMT]
    ]
    nur_ohne = sorted(
        set(rechnung["ohne"])
        - {m["hersteller"] for m in rechnung["modelle"]}
        - set(geraete_rechenweg.ANBIETER_FOLGE)
    )
    daten = {
        "stand": rechnung["stand"],
        "w": list(WETTBEWERBER),
        "h": [m["hersteller"] for m in rechnung["modelle"]],
        "tage": rechnung["tage"],
        "pct": [rechnung["pct"][t] for t in rechnung["tage"]],
        "aktuell": rechnung["aktuell"],
        "skala": SKALA,
        "fenster": list(FENSTER),
        "gleichauf": GLEICHAUF,
        "klein": KLEIN,
    }
    return {
        "fehler": "",
        "leer": False,
        "stand": rechnung["stand"],
        "wettbewerber": [
            {"name": w, "slug": slug_fuer(w), "legende": legendenname(w)}
            for w in spalten
        ],
        "einheit": (
            f"Vodafone gegenüber dem Wettbewerber · Gesamtkosten {LAUFZEIT}{NBSP}Monate"
        ),
        "ohne_spalte": [
            {"name": w, "text": f"{legendenname(w)}: kein {LAUFZEIT}-Monats-Preis"}
            for w in ohne_wb
        ],
        "zeilen": zeilen,
        "modelle": len(rechnung["modelle"]),
        "erklaerung": erklaerung(rechnung["tarife"], spalten, ohne_wb, nur_ohne),
        "json": json.dumps(daten, ensure_ascii=False, separators=(",", ":")).replace(
            "</", "<\\/"
        ),
        "tage_von": rechnung["tage"][0] if rechnung["tage"] else "",
        "tage_bis": rechnung["tage"][-1] if rechnung["tage"] else "",
    }
