"""Gegenprobe: Dauerausfälle verdrängen keine fälligen, prüfbaren Bündel.

Prüferbefund zu PR 200 (21.11.2026): nie gelesene Bündel (``letzte`` leer, jeden
Besuch ``nicht_pruefbar``) standen jede Nacht vor den fälligen Bündeln mit alternder
echter Prüfung; die ersten Besuche scheiterten gleichartig, der Schutzschalter schaltete
den ganzen Anbieter ab, und prüfbare Bündel liefen aus dem 7-Tage-Fenster. Real: 240
1&1-Bündel (``tarifaufschlag_aus_tarifraster``) nennen eine Tarif-Übersicht als Quelle.
Seitdem stehen belegt gescheiterte Bündel hinter den fälligen prüfbaren, und der
Schutzschalter schaltet nur die Art ab, die scheitert (Herleitung), nicht den Anbieter.
"""

from __future__ import annotations

import itertools

from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_fenster as gf
from telco_radar.collect.geraete import gegenprobe_browser as gb
from telco_radar.gegenprobe_reihe import SCHUTZ_GLEICHE_FEHLER

SKRIPT = lade_skript("gegenprobe")
HEUTE = "2026-11-22"


class _Args:
    aufnehmen = None
    gemessen_um = None


def _satz(n: int, herleitung: str = "") -> dict:
    return {
        "id": f"buendel--congstar--geraet-{n}-256gb-schwarz--tarif--24m",
        "anbieter": "congstar",
        "sku_id": f"geraet-{n}-256gb-schwarz",
        "tarif_name": "Tarif",
        "laufzeit_monate": 24,
        "quelle_url": f"https://congstar.example/{n}",
        "herleitung": herleitung,
    }


def _zeile(satz: dict, datum: str, status: str) -> gp.Ergebnis:
    grund = "Auswahl nicht gefunden: x" if status == gp.NICHT_PRUEFBAR else None
    return gp.Ergebnis(
        datum=datum,
        buendel_id=satz["id"],
        anbieter="congstar",
        status=status,
        anlass="fenster",
        grund=grund,
        gesamt_gespeichert=50.0,
    )


def _lauf(monkeypatch, saetze: dict, kaputt: set[str]):
    def lies_gruppe(browser, schluessel, gruppe, kennung, vor_laden, aufnehmen):
        for b in gruppe:
            if b["id"] in kaputt:
                yield b, gb.NichtPruefbar("Auswahl nicht gefunden: Tarif")
            else:
                yield b, gb.Lesung(text="", seite=b["quelle_url"])

    monkeypatch.setattr(SKRIPT, "lies_gruppe", lies_gruppe)
    lauf = SKRIPT.Lauf(_Args(), None, saetze, HEUTE, {}, float("inf"), None)
    uhr = itertools.count(0.0, 4.0)
    lauf.uhr = lambda: next(uhr)
    return lauf


def test_dauerausfaelle_verdraengen_keine_faelligen_buendel(monkeypatch):
    kaputt = [_satz(n) for n in range(8)]
    gut = [_satz(n) for n in range(100, 108)]
    saetze = {s["id"]: s for s in kaputt + gut}
    zeilen = [_zeile(s, "2026-11-21", gp.NICHT_PRUEFBAR) for s in kaputt]
    zeilen += [_zeile(s, "2026-11-16", gp.BESTAETIGT) for s in gut]
    wahl = gf.kandidaten(
        HEUTE, list(saetze.values()), lambda s: 50.0, gf.Gegenproben(zeilen), []
    )
    assert {k.buendel_id for k in wahl if k.faellig} == set(saetze)
    lauf = _lauf(monkeypatch, saetze, {s["id"] for s in kaputt})
    lauf.alle(gf.plane(wahl, lambda bid: bid))
    ungeoeffnet = [s["id"] for s in gut if s["id"] not in lauf.ergebnisse]
    assert not ungeoeffnet, (
        f"{len(ungeoeffnet)} von {len(gut)} fälligen, prüfbaren Bündeln nicht "
        f"geöffnet; Ausfall: {lauf.schutz.aus}"
    )


def test_schutzschalter_schaltet_nur_die_scheiternde_art_ab(monkeypatch):
    """Nie versuchte Bündel zweier Herleitungen gemischt: die Übersichts-Bündel
    scheitern alle, die Produktseiten-Bündel lesen; alle Produktseiten werden besucht,
    von den Übersichts-Bündeln nur ``SCHUTZ_GLEICHE_FEHLER``."""
    uebersicht = [_satz(n, "tarifaufschlag_aus_tarifraster") for n in range(10)]
    produkt = [_satz(n) for n in range(100, 110)]
    saetze = {s["id"]: s for s in uebersicht + produkt}
    gruppen = [
        [(s["id"], gp.ANLASS_FENSTER)]
        for paar in zip(uebersicht, produkt, strict=True)
        for s in paar
    ]
    gruppen = sorted(
        gruppen, key=lambda g: g[0][0] not in {s["id"] for s in uebersicht}
    )
    lauf = _lauf(monkeypatch, saetze, {s["id"] for s in uebersicht})
    lauf.alle(gruppen)
    assert all(s["id"] in lauf.ergebnisse for s in produkt)
    besucht = [s for s in uebersicht if s["id"] in lauf.ergebnisse]
    assert len(besucht) == SCHUTZ_GLEICHE_FEHLER
    (eintrag,) = lauf.laeufe()
    assert "tarifaufschlag_aus_tarifraster" in eintrag["ausfall"]
