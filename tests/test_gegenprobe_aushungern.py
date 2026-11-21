"""Gegenprobe: Dauerausfälle verdrängen keine fälligen, prüfbaren Bündel.

Prüferbefund zu PR 200 (21.11.2026): nie gelesene Bündel (``letzte`` leer, jeden
Besuch ``nicht_pruefbar``) standen jede Nacht vor den fälligen Bündeln mit alternder
echter Prüfung; die ersten Besuche scheiterten gleichartig, der Schutzschalter schaltete
den ganzen Anbieter ab, und prüfbare Bündel liefen aus dem 7-Tage-Fenster. Real: 240
1&1-Bündel (``tarifaufschlag_aus_tarifraster``) nennen eine Tarif-Übersicht als Quelle.
Nachprüfung: auch nie geöffnete Bündel (o2, Herleitung überall leer) und ein einzelner
Timeout schoben fällige Bündel hinaus, und „bestätigt, danach gescheitert“ zählte als
überfällig. Seitdem gilt EINE Regel: früheste Frist zuerst (gute Prüfung + 7 Tage,
ohne gute Prüfung erste Anzeige + 7), ein gescheiterter Versuch ändert die Frist nicht,
und „im Fenster“ hängt nur an der letzten guten Prüfung (``gegenprobe_fenster``).
"""

from __future__ import annotations

import itertools

from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp
from telco_radar import gegenprobe_bilanz as bz
from telco_radar import gegenprobe_fenster as gf
from telco_radar.collect.geraete import gegenprobe_browser as gb

SKRIPT = lade_skript("gegenprobe")
HEUTE = "2026-11-22"


class _Args:
    aufnehmen = None
    gemessen_um = None


def _satz(n: int, anbieter: str = "congstar") -> dict:
    return {
        "id": f"buendel--{anbieter}--geraet-{n}-256gb-schwarz--tarif--24m",
        "anbieter": anbieter,
        "sku_id": f"geraet-{n}-256gb-schwarz",
        "tarif_name": "Tarif",
        "laufzeit_monate": 24,
        "quelle_url": f"https://{anbieter}.example/{n}",
        "abgerufen_am": HEUTE,
        "tarif_monatlich": 10.0,
        "geraet_monatsrate": 5.0,
        "geraet_zuzahlung": 1.0,
        "anschlusspreis": 0.0,
    }


def _zeile(satz: dict, datum: str, status: str, grund: str = "") -> gp.Ergebnis:
    if status == gp.NICHT_PRUEFBAR and not grund:
        grund = "Auswahl nicht gefunden: x"
    return gp.Ergebnis(
        datum=datum,
        buendel_id=satz["id"],
        anbieter=satz["anbieter"],
        status=status,
        anlass="fenster",
        grund=grund if grund else None,
        gesamt_gespeichert=bz.gesamt_von(satz),
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
        HEUTE, list(saetze.values()), bz.gesamt_von, gf.Gegenproben(zeilen), []
    )
    assert {k.buendel_id for k in wahl if k.faellig} >= {s["id"] for s in gut}
    lauf = _lauf(monkeypatch, saetze, {s["id"] for s in kaputt})
    lauf.alle(gf.plane(wahl, lambda bid: bid))
    ungeoeffnet = [s["id"] for s in gut if s["id"] not in lauf.ergebnisse]
    assert not ungeoeffnet, (
        f"{len(ungeoeffnet)} von {len(gut)} fälligen, prüfbaren Bündeln nicht "
        f"geöffnet; Ausfall: {lauf.schutz.aus}"
    )


def test_neue_unpruefbare_buendel_verdraengen_keine_faelligen(monkeypatch):
    """o2: nie geöffnete Bündel, deren Seite nicht lesbar ist, und vor 6 Tagen
    bestätigte, die morgen ablaufen (Prüfer-Reproduktion ``test_neu_ungeprueft``)."""
    neu = [_satz(n, "o2") for n in range(8)]
    alt = [_satz(n, "o2") for n in range(100, 108)]
    saetze = {s["id"]: s for s in neu + alt}
    zeilen = [_zeile(s, "2026-11-16", gp.BESTAETIGT) for s in alt]
    wahl = gf.kandidaten(
        HEUTE, list(saetze.values()), bz.gesamt_von, gf.Gegenproben(zeilen), []
    )
    lauf = _lauf(monkeypatch, saetze, {s["id"] for s in neu})
    lauf.alle(gf.plane(wahl, lambda bid: bid))
    offen = [s["id"] for s in alt if s["id"] not in lauf.ergebnisse]
    assert not offen, f"{len(offen)} von {len(alt)} nicht geöffnet; {lauf.laeufe()}"


def test_einmal_gescheitert_rutscht_nicht_hinter_weniger_dringende():
    zufall = _satz(1, "o2")
    andere = [_satz(n, "o2") for n in range(10, 15)]
    zeilen = [
        _zeile(zufall, "2026-11-16", gp.BESTAETIGT),
        _zeile(zufall, "2026-11-21", gp.NICHT_PRUEFBAR, "Timeout beim Laden"),
        *(_zeile(s, "2026-11-17", gp.BESTAETIGT) for s in andere),
    ]
    wahl = gf.kandidaten(
        HEUTE, [zufall, *andere], bz.gesamt_von, gf.Gegenproben(zeilen), []
    )
    erste = [k.buendel_id for k in wahl if k.faellig]
    assert erste[0] == zufall["id"]


def test_bestaetigt_vor_2_tagen_dann_nicht_pruefbar_zaehlt_im_fenster():
    s = _satz(1, "o2")
    proben = gf.Gegenproben(
        [
            _zeile(s, "2026-11-20", gp.BESTAETIGT),
            _zeile(s, "2026-11-21", gp.NICHT_PRUEFBAR, "Timeout beim Laden"),
        ]
    )
    e = bz.zusammenfassung(HEUTE, [s], proben, [])["anbieter"]["o2"]
    assert (e["im_fenster"], e["ueberfaellig"], e["nicht_pruefbar"]) == (1, 0, 0)
    wahl = gf.kandidaten(HEUTE, [s], bz.gesamt_von, proben, [])
    assert [k.faellig for k in wahl] == [False]
