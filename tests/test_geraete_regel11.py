"""Regel 11 (Vortagsvergleich): Schutz für frische Zeilen mit veraltetem Nachbarn.

Der Prüfer von PR 84 (10.11.2026, „Sollte 1“) fand drei Wege, auf denen ein falsch
billiger Gerätepreis durchkam: ein Gerätepreis -27 % gegen gestern (die Gesamtsumme
bleibt unter 15 %), ein seit Tagen gleich falscher Preis (auch gegen einen beliebig
alten Vorgänger) und ein schleichendes Sinken, bei dem jeder Tagessprung klein ist.
Aufbau: 128 GB veraltet (13 Tage), 256 GB frisch mit Rate 22 € statt 30 €. Feste
Bezugstage, nie das heutige Datum.
"""

from __future__ import annotations

import datetime as dt
import json

from telco_radar.analyze.geraete_pruefstatus import (
    GUELTIG,
    QUARANTAENE,
    Kontext,
)
from telco_radar.analyze.geraete_regeln import pruefe_bestand, sim_only_tabelle
from telco_radar.collect.geraete.klicktext import volumen_aus_zeile
from telco_radar.report.geraete_tco_karten import ALT_AB_TAGEN
from telco_radar.tco_model import buendel_id

HEUTE = dt.date(2026, 11, 9)
TARIF = "O2 Mobile M 50 GB"
TARIF_ID = "o2-mobile-m"
SKU = {128: "pruefer-phone-128-schwarz", 256: "pruefer-phone-256-schwarz"}


def _tag(vor_tagen: int) -> str:
    return (HEUTE - dt.timedelta(days=vor_tagen)).isoformat()


def _satz(speicher: int = 128, rate: float = 30.0, vor_tagen: int = 0) -> dict:
    satz = {
        "sku_id": SKU[speicher],
        "anbieter": "o2",
        "tarif_name": TARIF,
        "tarif_id": TARIF_ID,
        "tarif_monatlich": 30.0,
        "tarif_bindung_monate": 24,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": rate,
        "laufzeit_monate": 24,
        "anschlusspreis": 39.99,
        "quelle_url": "https://example.org/o2",
        "abgerufen_am": _tag(vor_tagen),
        "zustand": "neu",
        "echo": {"werte": {"ratenzahl": 24}, "befunde": []},
        "beleg_variante": {"laufzeit": 24, "tarif": TARIF, "speicher": speicher},
    }
    satz["geraet_summe"] = round(1.0 + rate * 24, 2)
    satz["id"] = buendel_id(satz["sku_id"], "o2", TARIF, 24)
    return satz


def _messung(satz: dict, rate: float, vor_tagen: int) -> dict:
    """Eine Historienzeile des Bündels: gleiche Posten, andere Rate und anderer Tag."""
    return {"id": satz["id"], "datum": _tag(vor_tagen), "geraet_monatsrate": rate}


def _lauf(
    frisch: dict, vortag: dict | None = None, verlauf: list[dict] | None = None
) -> dict:
    """Prüft 128 GB (veraltet) und das frische 256 GB; gibt dessen Feld zurück.

    Ein Stand ohne Referenz (ohne Feld ``verlauf``) bekommt den Verlauf nicht: so
    scheitert der Test dort an der Aussage, nicht am Aufbau."""
    alt = _satz(128, vor_tagen=13)
    saetze = (alt, frisch)
    mehr = {}
    if "verlauf" in Kontext.__dataclass_fields__:
        mehr = {"verlauf": {frisch["id"]: verlauf} if verlauf else {}}
    k = Kontext(
        heute=HEUTE.isoformat(),
        frisch=lambda abgerufen, heute, _herleitung="": abgerufen >= _tag(3),
        geraet_von=lambda sku: ("pruefer-phone", int(sku.split("-")[2])),
        volumen_im_namen=volumen_aus_zeile,
        sim_only=sim_only_tabelle(
            [
                {
                    "anbieter": "o2",
                    "tarif_name": TARIF,
                    "tarif_id": TARIF_ID,
                    "tarif_sim_only_monatlich": 30.0,
                }
            ]
        ),
        uvp={s["sku_id"]: s["geraet_summe"] for s in saetze},
        volumen={TARIF_ID: 50.0},
        vortag={frisch["id"]: vortag} if vortag else {},
        **mehr,
    )
    return pruefe_bestand(saetze, k)[frisch["id"]].als_feld()


def _gruende(feld: dict) -> dict[int, str]:
    return {g["regel"]: g["satz"] for g in feld["gruende"]}


def _stabil(frisch: dict, rate: float, tage: tuple[int, ...]) -> list[dict]:
    return [_messung(frisch, rate, t) for t in sorted(tage, reverse=True)]


def test_grundfall_stimmiger_preis_mit_stabilem_verlauf_ist_gueltig():
    frisch = _satz(256, rate=30.0)
    verlauf = _stabil(frisch, 30.0, (5, 3, 1))
    feld = _lauf(frisch, verlauf[-1], verlauf)
    assert feld["status"] == GUELTIG, feld
    assert 11 not in feld["nicht_pruefbar"]


def test_geraetepreis_minus_27_prozent_gegen_gestern_ist_quarantaene():
    """Rate 30 -> 22: Gerätepreis 721 -> 529 (-27 %), die Gesamtsumme nur -13 %."""
    frisch = _satz(256, rate=22.0)
    gestern = _messung(frisch, 30.0, 1)
    feld = _lauf(frisch, gestern)
    assert feld["status"] == QUARANTAENE, feld
    assert _gruende(feld)[11] == (
        "Gerätepreis 529,00 € statt 721,00 € am 08.11.2026 (27%), "
        "Quarantäne bis zum zweiten Abruf"
    )


def test_geraetepreis_minus_9_prozent_gegen_gestern_bleibt_gueltig():
    """Gegenprobe: unter der Schwelle von 10 % ist es kein Sprung."""
    frisch = _satz(256, rate=27.5)
    feld = _lauf(frisch, _messung(frisch, 30.0, 1))
    assert feld["status"] == GUELTIG, feld


def test_seit_tagen_gleich_falscher_preis_haelt_die_referenz_der_woche():
    """Heute und gestern Rate 22, davor eine Woche lang 30: der Vortag bestätigt den
    falschen Preis, die Referenz (Höchstwert der sieben Tage davor) nicht. Zwei
    gleiche Abruftage sind weniger als ``STABIL_TAGE``, die Zeile bleibt gesperrt."""
    frisch = _satz(256, rate=22.0)
    verlauf = _stabil(frisch, 30.0, (7, 6, 5, 4)) + _stabil(frisch, 22.0, (1,))
    feld = _lauf(frisch, verlauf[-1], verlauf)
    assert feld["status"] == QUARANTAENE, feld
    assert _gruende(feld)[11] == (
        "Gerätepreis 529,00 €, in den 7 Tagen davor bis zu 721,00 € (27% darunter), "
        "Quarantäne bis zu 3 gleichen Abruftagen in Folge"
    )


def test_drei_gleiche_abruftage_heben_die_referenz_auf():
    """Heute, gestern und vorgestern derselbe Gerätepreis: eine echte Senkung (Rate
    30 -> 22, Vodafone Black Week) bleibt nicht wegen des Höchstwerts gesperrt."""
    frisch = _satz(256, rate=22.0)
    verlauf = _stabil(frisch, 30.0, (7, 6, 5, 4)) + _stabil(frisch, 22.0, (2, 1))
    feld = _lauf(frisch, verlauf[-1], verlauf)
    assert feld["status"] == GUELTIG, feld
    assert 11 not in feld["nicht_pruefbar"], feld


def test_rueckgang_ueber_der_obergrenze_bleibt_trotz_drei_gleicher_tage_gesperrt():
    """Auflage 1 der Prüfung von PR 95: Drei gleiche Abruftage heben die Referenz nur
    bis ``STABIL_MAX_RUECKGANG`` auf. Rate 30 -> 18 ist ein Gerätepreis 721 -> 433,
    also -40 % und damit über der Grenze; so lag der falsch gelesene Motorola-Preis
    (-39,7 % und -49,2 % an drei gleichen Tagen). Die Zeile bleibt Quarantäne."""
    frisch = _satz(256, rate=18.0)
    verlauf = _stabil(frisch, 30.0, (7, 6, 5, 4)) + _stabil(frisch, 18.0, (2, 1))
    feld = _lauf(frisch, verlauf[-1], verlauf)
    assert feld["status"] == QUARANTAENE, feld
    assert _gruende(feld)[11] == (
        "Gerätepreis 433,00 €, in den 7 Tagen davor bis zu 721,00 € (40% darunter), "
        "Rückgang über 35%, gleiche Abruftage heben die Quarantäne nicht auf"
    )


def test_rueckgang_unter_der_obergrenze_wird_nach_drei_gleichen_tagen_frei():
    """Gegenstück: Rate 30 -> 24 ist ein Gerätepreis 721 -> 577, also -20 % und damit
    unter ``STABIL_MAX_RUECKGANG``. Nach drei gleichen Abruftagen wird die Zeile frei,
    wie es die echten Vodafone-Senkungen der Black Week verlangen."""
    frisch = _satz(256, rate=24.0)
    verlauf = _stabil(frisch, 30.0, (7, 6, 5, 4)) + _stabil(frisch, 24.0, (2, 1))
    feld = _lauf(frisch, verlauf[-1], verlauf)
    assert feld["status"] == GUELTIG, feld
    assert 11 not in feld["nicht_pruefbar"], feld


def test_luecke_am_vorvortag_haelt_die_quarantaene():
    """Gegenprobe: dieselben drei Messwerte, aber der Vorvortag fehlt. Zwei Tage in
    Folge und ein älterer gleicher Wert genügen nicht."""
    frisch = _satz(256, rate=22.0)
    verlauf = _stabil(frisch, 30.0, (7, 6, 5, 4)) + _stabil(frisch, 22.0, (3, 1))
    assert _lauf(frisch, verlauf[-1], verlauf)["status"] == QUARANTAENE


def test_abweichender_preis_am_vorvortag_haelt_die_quarantaene():
    """Gegenprobe: vorgestern 21,50 € Rate statt 22 €. Die drei Tage sind nicht
    gleich gelesen, also bleibt die Referenz scharf."""
    frisch = _satz(256, rate=22.0)
    verlauf = _stabil(frisch, 30.0, (7, 6, 5, 4))
    verlauf += [_messung(frisch, 21.5, 2), _messung(frisch, 22.0, 1)]
    assert _lauf(frisch, verlauf[-1], verlauf)["status"] == QUARANTAENE


def test_zweite_messung_eines_tages_mit_anderem_preis_haelt_die_quarantaene():
    """Fail-closed: hat ein Tag zwei Messungen und nur eine passt, zählt der Tag
    nicht als gleich gelesen."""
    frisch = _satz(256, rate=22.0)
    verlauf = _stabil(frisch, 30.0, (7, 6, 5, 4))
    verlauf += [_messung(frisch, 22.0, 2), _messung(frisch, 25.0, 2)]
    verlauf += [_messung(frisch, 22.0, 1)]
    assert _lauf(frisch, verlauf[-1], verlauf)["status"] == QUARANTAENE


def test_stabile_tage_heben_den_tagessprung_nicht_auf():
    """Nirgends lockerer: ein Sprung zum Vortag bleibt Quarantäne, auch wenn die
    Tage davor denselben neuen Preis trugen (die Stabilität gilt nur der Referenz)."""
    frisch = _satz(256, rate=22.0)
    verlauf = _stabil(frisch, 22.0, (3, 2)) + _stabil(frisch, 30.0, (1,))
    feld = _lauf(frisch, verlauf[-1], verlauf)
    assert feld["status"] == QUARANTAENE, feld
    assert "Quarantäne bis zum zweiten Abruf" in _gruende(feld)[11]


def test_gleich_falsch_gegen_30_tage_alten_vorgaenger_ist_nicht_anwendbar():
    """Der Vorgänger trägt denselben falschen Preis, ist aber 30 Tage alt: Regel 11
    ist nicht anwendbar, also Quarantäne 5 beim veralteten Nachbarn (Fall 3b)."""
    frisch = _satz(256, rate=22.0)
    feld = _lauf(frisch, _messung(frisch, 22.0, 30))
    assert feld["status"] == QUARANTAENE, feld
    assert 11 in feld["nicht_pruefbar"]
    assert _gruende(feld)[5].endswith("kein Vortagsvergleich als Ersatz")


def test_schleichendes_sinken_wird_vor_dem_siebten_tag_gefangen():
    """4 % weniger je Tag: jeder Tagessprung liegt weit unter 10 %. Die Referenz
    fängt es, sobald der Preis über 10 % unter dem Höchstwert der Woche liegt; die
    ersten Tage bleiben gültig."""
    raten = [30.0 * 0.96**tag for tag in range(9)]
    status = []
    for heute_tag in range(1, 9):
        frisch = _satz(256, rate=raten[heute_tag])
        verlauf = [_messung(frisch, raten[t], heute_tag - t) for t in range(heute_tag)]
        status.append(_lauf(frisch, verlauf[-1], verlauf)["status"])
    assert status[:2] == [GUELTIG, GUELTIG], status
    assert QUARANTAENE in status[:5], status


def test_schleichendes_sinken_ohne_referenz_wuerde_durchkommen():
    """Kontrolle des Falls: gegen den Vortag allein ist jeder Schritt klein."""
    frisch = _satz(256, rate=30.0 * 0.96**5)
    gestern = _messung(frisch, 30.0 * 0.96**4, 1)
    assert _lauf(frisch, gestern)["status"] == GUELTIG


def test_legitimer_preissturz_endet_mit_dem_referenzfenster():
    """Ein dauerhaft gesenkter Preis bleibt höchstens sieben Tage in Quarantäne: die
    Messungen, die älter als sieben Tage sind, zählen nicht mehr."""
    frisch = _satz(256, rate=22.0)
    verlauf = _stabil(frisch, 30.0, (10, 9, 8)) + _stabil(frisch, 22.0, (7, 4, 2, 1))
    feld = _lauf(frisch, verlauf[-1], verlauf)
    assert feld["status"] == GUELTIG, feld


def test_referenz_braucht_drei_messungen():
    frisch = _satz(256, rate=22.0)
    verlauf = _stabil(frisch, 30.0, (3,)) + _stabil(frisch, 22.0, (1,))
    assert _lauf(frisch, verlauf[-1], verlauf)["status"] == GUELTIG


def test_vorgaenger_hoechstalter_ist_die_frischegrenze_der_seite():
    from telco_radar.analyze.geraete_regel11 import VORTAG_MAX_ALTER_TAGE

    assert VORTAG_MAX_ALTER_TAGE == ALT_AB_TAGEN


def test_vorgaenger_am_hoechstalter_gilt_einen_tag_darueber_nicht():
    from telco_radar.analyze.geraete_regel11 import VORTAG_MAX_ALTER_TAGE

    frisch = _satz(256, rate=30.0)
    am_rand = _lauf(frisch, _messung(frisch, 30.0, VORTAG_MAX_ALTER_TAGE))
    assert am_rand["status"] == GUELTIG and 11 not in am_rand["nicht_pruefbar"]
    zu_alt = _lauf(frisch, _messung(frisch, 30.0, VORTAG_MAX_ALTER_TAGE + 1))
    assert zu_alt["status"] == QUARANTAENE and 11 in zu_alt["nicht_pruefbar"]


def test_zu_alter_vorgaenger_ohne_veralteten_nachbarn_bleibt_gueltig():
    """Regel 11 ist dann nur „nicht prüfbar“, kein Grund: sonst läge sie über main."""
    frisch = _satz(256, rate=30.0)
    k = Kontext(
        heute=HEUTE.isoformat(),
        frisch=lambda abgerufen, heute, _herleitung="": True,
        vortag={frisch["id"]: _messung(frisch, 30.0, 20)},
    )
    feld = pruefe_bestand([frisch], k)[frisch["id"]].als_feld()
    assert feld["status"] == GUELTIG and 11 in feld["nicht_pruefbar"], feld


def test_gesamtsprung_gegen_zu_alten_vorgaenger_bleibt_quarantaene_wie_auf_main():
    """Nirgends lockerer: ein Sprung der Gesamtsumme über 15 % gilt auch gegen einen
    alten Vorgänger (Galaxy S26 256 „ohne Farbe“ o2: 14.10. gegen 06.11. hatte so
    einen Sprung und stand auf main in Quarantäne)."""
    frisch = _satz(256, rate=30.0)
    feld = _lauf(frisch, _messung(frisch, 10.0, 23))
    assert feld["status"] == QUARANTAENE
    assert 11 in _gruende(feld), feld


def test_historie_liefert_vortag_und_die_woche_davor(tmp_path):
    from telco_radar.analyze.geraete_pruefstelle import historie_vor_stand

    bid = "buendel--o2--phone--tarif--24m"
    zeilen = [
        {"id": bid, "datum": _tag(d), "geraet_monatsrate": 30.0 - d}
        for d in (30, 8, 6, 2)
    ]
    zeilen += [{"id": bid, "datum": _tag(0)}, {"id": "anderes", "datum": _tag(1)}]
    historie = tmp_path / "geraete_tco_historie.jsonl"
    historie.write_text("\n".join(json.dumps(z) for z in zeilen) + "\n")
    vortag, verlauf = historie_vor_stand(historie, {bid: _tag(0)})
    assert vortag[bid]["datum"] == _tag(2)
    assert [z["datum"] for z in verlauf[bid]] == [_tag(6), _tag(2)]
    assert "anderes" not in vortag


def test_ohne_vorgaenger_bleibt_es_quarantaene_5():
    """Zeile ohne Vorgänger: Quarantäne 5, wie bisher (Gegenprobe zum Höchstalter)."""
    frisch = _satz(256, rate=30.0)
    feld = _lauf(frisch)
    assert feld["status"] == QUARANTAENE
    assert 11 in feld["nicht_pruefbar"]
