"""Eine Gegenprobe eines Bündels: Lesung des Seitenbesuchs, Leser, Vergleich, Zeile.

``pruefe`` macht aus der Lesung eines Seitenbesuchs (``gegenprobe_wege.lies_gruppe``)
und dem Bestandssatz die Zeile der Tagesdatei (``gegenprobe.Ergebnis``) und wirft nie:
eine Sperre oder ein abgebrochener Kundenweg wird ``nicht_pruefbar`` mit Grund, der
Adresse der Seite und, wenn der Browser es aufnahm, einem Bild (``mit_beleg``).
Gelesen und verglichen werden die Posten und der sichtbare Versand
(``gegenprobe.VERGLEICHSFELDER``); eine Lücke des Bestands, die die Seite füllt,
steht in ``luecken``. Aufrufer: ``scripts/gegenprobe.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import gegenprobe as gp
from .collect.geraete.gegenprobe_browser import Gesperrt, Lesung, NichtPruefbar
from .collect.geraete.gegenprobe_sicht import LESER
from .gegenprobe_bilanz import gesamt_von as gesamt


def _norm(text: str) -> str:
    return "".join(z for z in text.lower() if z.isalnum())


def anderer_tarif(gespeichert: str, gelesen: str | None) -> bool:
    """Zeigt die Seite einen anderen Tarif als den des Bündels?"""
    if not gelesen:
        return False
    a, b = _norm(gespeichert), _norm(gelesen)
    return not (a.startswith(b) or b.startswith(a))


def mit_gelesenen(satz: dict, gelesen: dict) -> dict:
    """Der Satz mit den gelesenen Posten; weicht der Tarif ab, gelten keine Phasen."""
    neu = {**satz, **gelesen}
    tarif = gelesen.get("tarif_monatlich")
    alt = satz.get("tarif_monatlich")
    if tarif is not None and alt is not None and not gp.gleich(tarif, alt):
        neu["tarif_phasen"] = None
    return neu


Lesen = Callable[[str, dict], Lesung]
"""(Anbieter-Schlüssel, Bestandssatz) -> Lesung; im Lauf die Lesung des Seitenbesuchs
(``gegenprobe_wege.lies_gruppe``)."""


def pruefe(
    lesen: Lesen,
    satz: dict,
    anlass: str,
    datum: str,
    gemessen_um: str | None,
    geprueft_um: str,
) -> tuple[gp.Ergebnis, Lesung | None]:
    """Eine Gegenprobe: Kundenweg, Leser, Vergleich. Nie eine Ausnahme nach außen.
    ``geprueft_um`` gibt der Aufrufer (die Uhr steht im Skript, nicht hier)."""
    schluessel = gp.anbieter_aus_id(satz["id"])
    basis: dict[str, Any] = {
        "datum": datum,
        "buendel_id": satz["id"],
        "anbieter": satz.get("anbieter") or "",
        "anlass": anlass,
        "sku_id": satz.get("sku_id") or "",
        "tarif_name": satz.get("tarif_name") or "",
        "laufzeit_monate": satz.get("laufzeit_monate"),
        "gespeichert": gp.gespeicherte_werte(satz),
        "gesamt_gespeichert": gesamt(satz),
        "geprueft_um": geprueft_um,
        "gemessen_um": gemessen_um,
    }
    leser = LESER.get(schluessel)
    if leser is None:
        return gp.Ergebnis(
            **basis, status=gp.NICHT_PRUEFBAR, grund=gp.GRUND_KEIN_LESER
        ), None
    try:
        lesung = lesen(schluessel, satz)
    except (Gesperrt, NichtPruefbar) as fehler:
        grund = str(fehler)
        if isinstance(fehler, Gesperrt):
            grund = f"{gp.GRUND_GESPERRT} ({fehler})"
        seite = fehler.seite or str(satz.get("quelle_url") or "")
        ergebnis = gp.Ergebnis(
            **basis, status=gp.NICHT_PRUEFBAR, grund=grund, seite=seite
        )
        beleg = Lesung("", seite, fehler.bild) if fehler.bild else None
        return ergebnis, beleg
    sicht = leser(lesung.text)
    gelesen: dict = sicht.werte()
    if sicht.versand is not None:
        gelesen[gp.VERSAND] = sicht.versand
    extra: dict[str, Any] = {
        "seite": lesung.seite,
        "text": lesung.text[: gp.TEXT_HOECHSTENS],
        "gelesen": {**gelesen, "tarif_name": sicht.tarif_name, "roh": sicht.roh},
        "bild_fehlt": lesung.bild_fehlt,
    }
    if anderer_tarif(satz.get("tarif_name") or "", sicht.tarif_name):
        anders = f"Die Seite zeigt einen anderen Tarif: {sicht.tarif_name}"
        ergebnis = gp.Ergebnis(**basis, **extra, status=gp.NICHT_PRUEFBAR, grund=anders)
        return ergebnis, lesung
    status, abweichungen, _, befund = gp.vergleiche(basis["gespeichert"], gelesen)
    nicht_gelesen = [
        f for f in gp.FELDER if satz.get(f) is not None and f not in gelesen
    ]
    ergebnis = gp.Ergebnis(
        **basis,
        **extra,
        status=status,
        grund=befund,
        abweichungen=abweichungen,
        luecken=gp.luecken_von(basis["gespeichert"], gelesen),
        nicht_gelesen=nicht_gelesen,
        gesamt_gelesen=gesamt(mit_gelesenen(satz, gelesen))
        if status != gp.NICHT_PRUEFBAR
        else None,
    )
    return ergebnis, lesung


def ohne_lauf(satz: dict, anlass: str, datum: str, grund: str) -> gp.Ergebnis:
    """Die Zeile eines Bündels, dessen Seite nicht geöffnet wurde (mit Grund)."""
    return gp.Ergebnis(
        datum=datum,
        buendel_id=satz["id"],
        anbieter=satz.get("anbieter") or "",
        status=gp.NICHT_GEGENGEPRUEFT,
        anlass=anlass,
        grund=grund,
        sku_id=satz.get("sku_id") or "",
        tarif_name=satz.get("tarif_name") or "",
        laufzeit_monate=satz.get("laufzeit_monate"),
        gespeichert=gp.gespeicherte_werte(satz),
        gesamt_gespeichert=gesamt(satz),
    )
