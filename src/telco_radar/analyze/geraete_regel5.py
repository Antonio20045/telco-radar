"""Regel 5 der Prüfstelle: Preis steigt mit dem Speicher, nur zwischen frischen Bündeln.

Eigenes Modul, weil ``geraete_regeln`` die Dateigrenze der Leiter (400 Zeilen, Basis
``pruef/riesendateien.txt``) nicht überschreiten darf. Die Regeln 5 und 11 hängen so
zusammen: ein veralteter Speicher-Nachbar ist kein Vergleichspartner (Regel 16); ein
frisches Bündel mit solchem Nachbarn bleibt nur gültig, wenn Regel 11 es ersatzweise
prüft (``vortag_geprueft``), sonst Quarantäne 5.
"""

from __future__ import annotations

from ..geraete_model import normalisiere
from ..tco_model import Buendel
from .geraete_pruefstatus import (
    CENT,
    NICHT_PRUEFBAR,
    VERLETZT,
    Befund,
    Kontext,
    datum,
    eur,
    geraetepreis,
)

ZUSTAND_UNBEKANNT = ("", "unbekannt")
"""Zustände, die Regel 5 nicht vergleicht (``Buendel.zustand`` ohne Angabe)."""
REGEL = 5


def _verletzt(satz: str) -> Befund:
    return Befund(REGEL, VERLETZT, satz)


def _nicht(satz: str) -> Befund:
    return Befund(REGEL, NICHT_PRUEFBAR, satz)


Stufen = dict[int, list[tuple[str, float, str | None]]]
"""Je Speicher (GB) die Bündel einer Reihe: ID, Gerätepreis und, wenn veraltet, das
Abrufdatum (sonst ``None``)."""


def speicherstufen(
    lesbar: list[tuple[str, Buendel]], k: Kontext, vortag_geprueft: frozenset[str]
) -> dict[str, Befund]:
    """Regel 5 über den Bestand: beim selben Anbieter, Tarif, Laufzeit, Gerät und
    Zustand kostet mehr Speicher nie weniger. Beide Bündel eines verletzten Paars sind
    Quarantäne. Ein unbekannter Zustand fällt aus dem Vergleich (CLAUDE.md, Clean
    Code 4): ein generalüberholtes Gerät darf weniger kosten als ein neues.

    Ein veraltetes Bündel (Regel 16) ist kein Vergleichspartner und bekommt keinen
    Befund 5. Hat ein frisches Bündel einen veralteten Speicher-Nachbarn, fehlt ihm
    dieser Vergleich: es bleibt nur gültig, wenn Regel 11 es ersatzweise prüft
    (``vortag_geprueft``: Vorgänger vorhanden und bestanden). Sonst Quarantäne 5, also
    fail-closed: lieber ein Preis weniger als ein falscher."""
    befunde: dict[str, Befund] = {}
    reihen: dict[tuple, Stufen] = {}
    for bid, b in lesbar:
        geraet, speicher = k.geraet_von(b.sku_id) if k.geraet_von else ("", None)
        preis = geraetepreis(b)
        if not geraet or speicher is None or preis is None:
            befunde[bid] = _nicht("Gerät, Speicher oder Gerätepreis fehlt")
            continue
        if b.zustand in ZUSTAND_UNBEKANNT:
            befunde[bid] = _nicht("Zustand des Geräts unbekannt")
            continue
        veraltet = k.frisch is not None and not k.frisch(
            b.abgerufen_am, k.heute, b.herleitung
        )
        tarif = b.tarif_id or normalisiere(b.tarif_name)
        reihe = (normalisiere(b.anbieter), tarif, b.laufzeit_monate, geraet, b.zustand)
        stufe = reihen.setdefault(reihe, {}).setdefault(speicher, [])
        stufe.append((bid, preis, b.abgerufen_am if veraltet else None))
    for stufen in reihen.values():
        _frische_paare(stufen, befunde)
        _ohne_partner(stufen, vortag_geprueft, befunde)
    return befunde


def _frische_paare(stufen: Stufen, befunde: dict[str, Befund]) -> None:
    """Beide Bündel eines frischen Paars, dessen größerer Speicher weniger kostet."""
    groessen = sorted(stufen)
    for i, klein in enumerate(groessen):
        for gross in groessen[i + 1 :]:
            for kid, kp, kalt in stufen[klein]:
                for gid, gp, galt in stufen[gross]:
                    if kalt is None and galt is None and gp < kp - CENT:
                        text = f"{gross} GB für {eur(gp)}, {klein} GB für {eur(kp)}"
                        befunde.setdefault(kid, _verletzt(text))
                        befunde.setdefault(gid, _verletzt(text))


def _ohne_partner(
    stufen: Stufen, vortag_geprueft: frozenset[str], befunde: dict[str, Befund]
) -> None:
    """Frische Bündel mit veraltetem Nachbarn, die Regel 11 nicht ersatzweise prüft."""
    for speicher, zeilen in stufen.items():
        for bid, _preis, abgerufen in zeilen:
            if abgerufen is not None or bid in vortag_geprueft:
                continue
            for andere, nachbarn in sorted(stufen.items()):
                stand = [a for _, _, a in nachbarn if a is not None]
                if andere != speicher and stand:
                    text = (
                        f"{andere} GB nur veraltet (abgerufen am {datum(max(stand))}), "
                        "kein Vortagsvergleich als Ersatz"
                    )
                    befunde.setdefault(bid, _verletzt(text))
                    break
