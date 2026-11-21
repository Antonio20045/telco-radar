"""Testhilfe: Gegenprobe über mehrere Nächte mit der echten ``Lauf``-Klasse.

Vom Prüfer zu PR 200 (dritte Prüfung, 21.11.2026): der Browser ist gespielt (eine
Lesung oder ``NichtPruefbar``), Auswahl, Reihenfolge, Seitenbesuche und Lauf sind echt.
``nacht`` spielt eine Nacht und gibt den Lauf, seine neuen Zeilen und die Auswahl
zurück; die Uhr zählt je Besuch 3 und je Bündel 1 Einheit, ``kapazitaet`` ist die
Frist des Laufs in diesen Einheiten. ``kaputt`` ist eine Menge (Formfehler ``FORM``)
oder je Bündel der Fehlertext (Schlussprüfung: ``TIMEOUT``); mit ``je_url`` teilen
sich Bündel mit derselben ``quelle_url`` einen Seitenbesuch.
"""

from __future__ import annotations

from datetime import date, timedelta

from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_bilanz as bz
from telco_radar import gegenprobe_fenster as gf
from telco_radar.collect.geraete import gegenprobe_browser as gb

SKRIPT = lade_skript("gegenprobe")
TIMEOUT = "Browser: Page.goto: Timeout 45000ms exceeded."
FORM = "Auswahl nicht gefunden: Tarif"


class Args:
    """Was ``Lauf`` von den Aufrufargumenten liest."""

    aufnehmen = None
    gemessen_um = None


def satz(n, anbieter="o2", first_seen="2026-11-01", seite=None, **extra):
    """Ein angezeigtes Bündel mit vollständigem Preis."""
    s = {
        "id": f"buendel--{anbieter}--geraet-{n}-256gb-schwarz--tarif--24m",
        "anbieter": anbieter,
        "sku_id": f"geraet-{n}-256gb-schwarz",
        "tarif_name": "Tarif",
        "laufzeit_monate": 24,
        "quelle_url": seite or f"https://{anbieter}.example/{n}",
        "first_seen": first_seen,
        "abgerufen_am": first_seen,
        "tarif_monatlich": 10.0,
        "geraet_monatsrate": 5.0,
        "geraet_zuzahlung": 1.0,
        "anschlusspreis": 0.0,
    }
    s.update(extra)
    return s


def zeile(s, datum, status, grund=""):
    """Eine Zeile der Tagesdatei zu ``s``."""
    if status == gp.NICHT_PRUEFBAR and not grund:
        grund = "Auswahl nicht gefunden: x"
    return gp.Ergebnis(
        datum=datum,
        buendel_id=s["id"],
        anbieter=s["anbieter"],
        status=status,
        anlass="fenster",
        grund=grund if grund else None,
        gesamt_gespeichert=bz.gesamt_von(s),
    )


def nacht(datum, saetze, rows, kaputt, kapazitaet=10_000, aenderungen=(), je_url=False):
    """Eine Nacht: (Lauf, neue Zeilen, Auswahl). ``saetze``: Schlüssel → Satz."""
    uhr = [0.0]
    texte = kaputt if isinstance(kaputt, dict) else dict.fromkeys(kaputt, FORM)

    def lies_gruppe(browser, schluessel, gruppe, kennung, vor_laden, aufnehmen):
        uhr[0] += 3
        for b in gruppe:
            uhr[0] += 1
            if b["id"] in texte:
                yield b, gb.NichtPruefbar(texte[b["id"]])
            else:
                yield b, gb.Lesung(text="", seite=b["quelle_url"])

    def pruefe(lesen, s, anlass, d, gemessen_um=None):
        if s["id"] in texte:
            return zeile(s, d, gp.NICHT_PRUEFBAR, texte[s["id"]]), None
        return zeile(s, d, gp.BESTAETIGT), None

    SKRIPT.lies_gruppe = lies_gruppe
    SKRIPT.pruefe = pruefe
    proben = gf.Gegenproben(rows)
    wahl = gf.kandidaten(
        datum, list(saetze.values()), bz.gesamt_von, proben, list(aenderungen)
    )
    gruppen = gf.plane(wahl, lambda bid: saetze[bid]["quelle_url"] if je_url else bid)
    lauf = SKRIPT.Lauf(Args(), None, saetze, datum, {}, kapazitaet, None)
    lauf.uhr = lambda: uhr[0]
    lauf.alle(gruppen)
    return lauf, lauf.zeilen(gruppen), wahl


def tag(start, i):
    """Der ``i``-te Tag ab ``start``."""
    return str(date.fromisoformat(start) + timedelta(i))
