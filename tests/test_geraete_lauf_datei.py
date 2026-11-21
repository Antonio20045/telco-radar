"""Die Lauf-Datei des Gerätelaufs (Abnahmekriterium 1, Stufe 1, 21.11.2026).

Gegen den alten Stand fachlich rot: ``geraete_pipeline.main`` gab die Bilanz von
``run_geraete_stage`` nur ins Log und schrieb keine Datei; ``data/state/geraete_lauf/``
gab es nicht. Der Test fährt ``main`` mit einer Ersatzstufe (schreibt einen Auszug des
echten Bestands vom 21.11.2026 mit dem Datum, das ``main`` ihr gibt) und gespeicherten
Antworten der Anbieterlisten statt Netz; er importiert nur Module, die es vorher schon
gab, damit der alte Stand an der Aussage scheitert und nicht am Import.
"""

from __future__ import annotations

import gzip
import json
import shutil
import sys
from pathlib import Path

from telco_radar import geraete_abruf, geraete_pipeline

WURZEL = Path(__file__).resolve().parents[1]
FIXTURES = WURZEL / "tests" / "fixtures" / "geraete_soll"
TAG = "2026-11-21"
STOERUNG = "1&1 nicht erfasst: Lesen gestört (HTTP 502, 21.11.2026)"
ERWARTET = [
    "Telekom",
    "Vodafone",
    "o2",
    "1&1",
    "congstar",
    "Saturn/MediaMarkt · Telekom-Netz",
    "Saturn/MediaMarkt · Vodafone-Netz",
    "Saturn/MediaMarkt · o2-Netz",
]


def _auszug() -> list[dict]:
    daten = json.loads((FIXTURES / "ist_auszug_20261121.json").read_text("utf-8"))
    return daten["buendel"]


def _zeilen(voll: dict) -> dict:
    return {z["name"]: z for z in voll["anbieter"]}


class _Antwort(tuple):
    schutz = False


def _netz(antworten: dict[str, str]):
    def hole(url, kopf=None, **_):
        for anfang, datei in antworten.items():
            if url.startswith(anfang):
                return _Antwort(
                    (200, gzip.decompress((FIXTURES / datei).read_bytes()).decode())
                )
        return _Antwort((404, ""))

    return hole


ANTWORTEN = {
    "https://www.telekom.de/content/robots/sitemap": "telekom_sitemap_20261121.xml.gz",
    "https://api.vodafone.de/glados": "vodafone_hardware_20261121.json.gz",
    "https://www.o2online.de/e-shop/rest": "o2_katalog_20261121.json.gz",
    "https://mobile.1und1.de/smartphones": "einsundeins_smartphones_20261121.html.gz",
    "https://www.congstar.de/sitemap": "congstar_devices_20261121.xml.gz",
    "https://tarife.mediamarkt.de/sitemap": "tarifwelt_sitemap_20261121.xml.gz",
}


def test_der_nachtlauf_schreibt_die_lauf_datei_mit_bilanz_und_vollstaendigkeit(
    tmp_path, monkeypatch
):
    """Gegen den alten Stand rot: ``main`` warf die Bilanz weg, es gab keine Datei."""
    shutil.copytree(WURZEL / "config", tmp_path / "config")
    (tmp_path / "data" / "state").mkdir(parents=True)
    gesehen: dict = {}

    def stufe(root, http, heute, **_):
        gesehen["heute"] = heute
        buendel = [
            {**b, "abgerufen_am": heute} for b in _auszug() if b["abgerufen_am"] == TAG
        ]
        tco = {"updated": heute, "buendel": buendel, "erfassung": {"1&1": STOERUNG}}
        (Path(root) / "data" / "state" / "geraete_tco.json").write_text(
            json.dumps(tco), "utf-8"
        )
        return {"status": "ok", "tarifwelt": {"status": "ok", "ungelesen": []}}

    monkeypatch.setattr(geraete_pipeline, "run_geraete_stage", stufe)
    monkeypatch.setattr(geraete_abruf, "hole_fabrik", lambda http: _netz(ANTWORTEN))
    monkeypatch.setattr(sys, "argv", ["geraete_pipeline", "--root", str(tmp_path)])
    geraete_pipeline.main()
    datei = tmp_path / "data" / "state" / "geraete_lauf" / f"{gesehen['heute']}.json"
    assert datei.is_file(), "keine Lauf-Datei des Gerätelaufs"
    lauf = json.loads(datei.read_text("utf-8"))
    assert lauf["bilanz"]["status"] == "ok"
    z = _zeilen(lauf["vollstaendigkeit"])
    assert list(z)[: len(ERWARTET)] == ERWARTET
    assert z["Telekom"]["ist"]["buendel"] == 42
    assert z["Telekom"]["soll_quelle"]["art"] == "sitemap"
    assert z["Telekom"]["soll_quelle"]["gleiche_quelle_wie_sammler"] is False
    assert z["Vodafone"]["soll_quelle"]["art"] == "uebersicht_api"
    assert z["1&1"]["soll_quelle"]["art"] == "uebersichtsseite"
    einsundeins = z["1&1"]["ebenen"]["modelle"]
    assert einsundeins["soll"] is not None and einsundeins["erfasst"] == 2
    gruende = {lu["grund"] for lu in einsundeins["luecken"]}
    assert STOERUNG in gruende
    assert gruende <= {STOERUNG, "beim Anbieter gelistet, nicht im Katalog"}
    assert (
        z[ERWARTET[5]]["soll_quelle"]["quelle"]
        == "https://tarife.mediamarkt.de/sitemap.xml"
    )
