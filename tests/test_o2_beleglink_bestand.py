"""Der Quell-Link eines o2-Preises öffnet die gezeigte Konfiguration (03.11.2026).

Alle o2-Links trugen ``ratenzahlung=36``, obwohl der Betrag 24 Raten meint; fünf
trugen den Tarif der Seite (``unlimited-m``) statt den gerechneten. Der Bestand ist
älter als die Korrektur: der Link folgt der Zeile beim Lesen, ohne neuen Messlauf.
Kennt der Satz seinen Tarif nicht, steht kein Tarif im Link. Synthetisch.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlsplit

from telco_radar.analyze.klick_tarifslug import klick_beleglink
from telco_radar.analyze.tco_store import TcoDB

SEITE = (
    "https://www.o2online.de/e-shop/apple/apple-iphone-18-pro-256gb-burgunder-details"
    "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36&vertragsart=ratenzahlung"
    "&tarif=o2-mobile-unlimited-m"
)


def _satz(**mehr) -> dict:
    satz = {
        "id": "buendel--o2--apple-iphone-18-pro-256gb-schwarz--on-demand-m--24",
        "sku_id": "apple-iphone-18-pro-256gb-schwarz",
        "anbieter": "o2",
        "tarif_name": "O2 Mobile on Demand M mit 50 GB+ (24 Mon.)",
        "tarif_id": "o2:o2-mobile-on-demand-m",
        "tarif_monatlich": 19.99,
        "geraet_zuzahlung": 7.0,
        "geraet_monatsrate": 65.0,
        "laufzeit_monate": 24,
        "quelle_url": SEITE,
        "abgerufen_am": "2026-11-02",
        "zustand": "neu",
        "quelle_art": "klick",
    }
    satz.update(mehr)
    return satz


def _frage(link: str) -> dict:
    return dict(parse_qsl(urlsplit(link).query, keep_blank_values=True))


def _gelesen(tmp_path, *saetze: dict) -> list[dict]:
    datei = tmp_path / "geraete_tco.json"
    datei.write_text(
        json.dumps({"updated": "2026-11-02", "buendel": list(saetze), "sim_only": []}),
        encoding="utf-8",
    )
    return TcoDB(datei).buendel()


def test_gespeicherter_o2_link_folgt_beim_lesen_tarif_und_raten_der_zeile(tmp_path):
    (b,) = _gelesen(tmp_path, _satz())
    frage = _frage(b["quelle_url"])
    assert frage["ratenzahlung"] == "24"
    assert frage["tarif"] == "o2-mobile-on-demand-m"
    assert urlsplit(b["quelle_url"]).path == urlsplit(SEITE).path


def test_plus_zeile_behaelt_plus_im_tarif_des_links(tmp_path):
    name = "O2 Mobile Unlimited M Plus mit 100 MBit/s (24 Mon.)"
    (b,) = _gelesen(tmp_path, _satz(tarif_name=name))
    assert _frage(b["quelle_url"])["tarif"] == "o2-mobile-unlimited-m-plus"


def test_gegenprobe_fremde_anbieter_und_adapter_saetze_bleiben_wie_gespeichert(
    tmp_path,
):
    adapter = _satz(quelle_art="adapter", id=_satz()["id"] + "x")
    telekom = _satz(
        anbieter="Telekom",
        tarif_name="MagentaMobil M",
        id="buendel--telekom--apple-iphone-18-pro-256gb-schwarz--magentamobil-m--24",
    )
    gelesen = _gelesen(tmp_path, adapter, telekom)
    assert {b["quelle_url"] for b in gelesen} == {SEITE}


def test_unbekannter_tarif_gibt_keinen_falschen_tarif_im_link():
    link = klick_beleglink(_satz(tarif_name=""))
    frage = _frage(link)
    assert "tarif" not in frage
    assert frage["ratenzahlung"] == "36", "ohne Slug bleibt die Seite unverändert"
    assert urlsplit(link).path == urlsplit(SEITE).path
