"""Reproduktionen des Prüfers zu PR 205 (``/tmp/pruefer/k205/test_k205.py``),
übernommen. Sie brauchen nur Module, die es vor der Nachbesserung gab, und sind
gegen den Stand ``e31048fd6`` rot.

Abweichung von der Vorlage: im Test „zwei verschiedene Tarife“ ist das Soll der
Seite „O2 Mobile L mit 150 GB“ jetzt ``o2-mobile-l-mit-150-gb`` (die Kachel nennt
das Volumen; erst der alte Grundtarif machte daraus ``o2-mobile-l``).
"""

from __future__ import annotations

import test_geraete_angebot as base

from telco_radar import geraete_angebot as ga
from telco_radar import geraete_soll_waechter as waechter
from telco_radar.geraete_angebot import einhaengen as ein
from telco_radar.geraete_vollstaendigkeit import (
    SichtbareAuswahl,
    Signale,
    baue,
    haenge_kombinationen_ein,
)
from telco_radar.report import geraete_vollstaendigkeit as seite

TAG = base.TAG
T_NETZ = "Saturn/MediaMarkt · Telekom-Netz"
SKU = "apple-iphone-17-256gb-schwarz"


def _katalog():
    return base.Katalog(geraete=[base.Geraet("Apple", "iPhone 17")])


def _zeile(voll: dict, name: str) -> dict:
    zeilen = seite.zeilen({"vollstaendigkeit": voll}, TAG)["zeilen"]
    return next(x for x in zeilen if x["name"] == name)


def _b(sku, tarif_slug, laufzeit=24, anbieter="o2", **preise):
    return {
        "id": f"buendel--x--{sku}--{tarif_slug}--{laufzeit}m",
        "sku_id": sku,
        "anbieter": anbieter,
        "tarif_id": tarif_slug,
        "laufzeit_monate": laufzeit,
        "abgerufen_am": TAG,
        **preise,
    }


def test_uebersicht_nennt_95_geraete_gelesen_wurde_eines_trotzdem_vollstaendig(
    tmp_path,
):
    z = base._congstar()
    z.genannt = 95
    zeilen, voll = base._voll(tmp_path, [z], _katalog())
    k = zeilen["congstar"]["ebenen"]["kombinationen"]
    assert (k["soll"], k["erfasst"], k["luecken_zahl"]) == (32, 32, 0)
    cong = _zeile(voll, "congstar")
    assert "vollständig" not in cong["marke"]
    assert "Übersicht nennt 95, gelesen 1" in str(cong)


def test_ist_ohne_soll_darf_nicht_vollstaendig_heissen(tmp_path):
    z = base._congstar(("256 GB",))
    zeilen, voll = base._voll(tmp_path, [z], _katalog())
    k = zeilen["congstar"]["ebenen"]["kombinationen"]
    assert k["nicht_im_soll_zahl"] == 16 and k["soll"] == k["erfasst"]
    cong = _zeile(voll, "congstar")
    assert "vollständig" not in cong["marke"]
    assert "16 Preise ohne Angebot auf der Seite" in cong["marke"]
    befunde = waechter.pruefe({"datum": TAG, "vollstaendigkeit": voll}, TAG)
    assert any("16 erfasste Preise ohne Angebot auf der Seite" in b for b in befunde)


def test_zwei_verschiedene_tarife_mit_mit_im_namen_werden_nicht_zusammengelegt():
    sku = "apple-iphone-17-256gb-schwarz"
    buendel = [_b(sku, "o2-mobile-l-mit-150-gb"), _b(sku, "o2-mobile-l-mit-300-gb")]
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", buendel, {}, Signale())
    a = SichtbareAuswahl(
        anbieter="o2",
        modell="apple-iphone-17",
        seite="https://x",
        speicher=("256gb",),
        tarife=("o2-mobile-l-mit-150-gb",),
        laufzeiten=(24,),
        gezaehlt_um=f"{TAG}T00:20:00+00:00",
    )
    haenge_kombinationen_ein(
        voll, "o2", [a], buendel, Signale(), quelle={"art": "browser_auswahl"}
    )
    k = next(z for z in voll["anbieter"] if z["name"] == "o2")["ebenen"][
        "kombinationen"
    ]
    assert (k["erfasst"], k["nicht_im_soll_zahl"]) == (1, 1)
    assert k["nicht_im_soll"][0]["schluessel"].endswith("o2-mobile-l-mit-300gb--24m")


def test_tarifwelt_aktionstarif_hat_einen_benennbaren_grund(tmp_path):
    s = ga.Seite(
        "https://tarife.mediamarkt.de/smartphones/apple/iphone-17/",
        "Apple iPhone 17",
        status=ga.GELESEN,
        speicher=[ga.Option("256 GB", "256 GB")],
        kombinationen=[
            ["256 GB", "Magenta Mobil XL 5G", 24, "telekom"],
            ["256 GB", "Magenta Mobil L 5G Aktion", 24, "telekom"],
        ],
    )
    z = ga.Zaehlung("tarifwelt", TAG, f"{TAG}T23:10:00+00:00", seiten=[s])
    z.kacheln = [ga.Kachel(s.url, s.titel)]
    ga.schreibe(tmp_path, z)
    ist = [_b(SKU, "magenta-mobil-xl-5g", anbieter=T_NETZ)]
    voll = baue(TAG, f"{TAG}T04:00:00+00:00", ist, {}, Signale())
    ein.haenge_ein(voll, tmp_path, TAG, ist, Signale(), _katalog())
    zeilen = {x["name"]: x for x in voll["anbieter"]}
    k = zeilen[T_NETZ]["ebenen"]["kombinationen"]
    assert k["luecken_zahl"] == 1
    assert k["luecken"][0]["grund"] == (
        "Tarif mit Sonderbedingung (Aktion), nicht im Vergleich"
    )
