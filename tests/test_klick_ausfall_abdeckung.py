"""Ein Klick-Ausfall des Messtags ist eine belegte Lücke der Bündelabdeckung.

Klick-Lauf 44840854026 (21.11.2026): der Eintrag ``1und1`` bekam auf der ersten
Tarifdetail-Seite HTTP 502 und las keine Seite, seine 21 Produktseiten blieben
``nicht_besucht``; der Job stand trotzdem auf „success“. Der Wächter
(``scripts/geraete_abdeckungswaechter.py``) las die Klick-Datei nicht und meldete
„1&1: 14 Pflichtmodelle ohne Bündel und ohne belegte Lücke“, zehn davon Seiten genau
dieses Eintrags. Erwartet: jedes Gerät einer heute nicht gelesenen Seite eines
ausgefallenen Laufs ist am Messtag belegt, mit dem Grund aus der Datei; ein Gerät
ohne Seite in diesem Lauf bleibt Befund. Gegenproben: eine Datei vom Vortag belegt
nichts, ein gelesener Lauf auch nicht.

Daten: ``einsundeins_1und1_nacht_20261121.json`` (die Ergebnisdatei dieser Nacht,
unverändert) und ``einsundeins_1und1-2_nacht_20261121.json`` (zweiter Eintrag,
gelesen); Bestand und Pflichtliste sind von Hand auf vier Modelle verkleinert.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from klickergebnisse import WURZEL

from telco_radar.analyze.buendel_abdeckung import (
    als_markdown,
    lade_pflicht,
    lade_und_pruefe,
)

HEUTE = "2026-11-21"
FIXTURES = WURZEL / "tests" / "fixtures" / "klickcrawler"
NACHT = "einsundeins_1und1_nacht_20261121.json"
ZWEITER = "einsundeins_1und1-2_nacht_20261121.json"
PFLICHT = """\
pflicht_anbieter:
  - 1&1
pflicht_modelle:
  - google-pixel-10a
  - apple-iphone-17
  - samsung-galaxy-s26-ultra
  - apple-iphone-duo
"""
SKRIPT = WURZEL / "scripts" / "klick_tageslauf.py"


def _lade(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _wurzel(tmp_path: Path, **klick: dict) -> Path:
    """Repo-Abbild mit einem 1&1-Bündel (Pixel 10a) am Messtag und den Klick-Dateien."""
    zustand = tmp_path / "data" / "state"
    (zustand / "klick").mkdir(parents=True)
    buendel = {
        "id": "buendel--1-1--google-pixel-10a-128gb-obsidian--1-1-all-net-flat-s--36m",
        "sku_id": "google-pixel-10a-128gb-obsidian",
        "anbieter": "1&1",
        "tarif_name": "1&1 All-Net-Flat S",
        "laufzeit_monate": 36,
        "last_verified": HEUTE,
        "zustand": "neu",
    }
    tco = {"updated": HEUTE, "buendel": [buendel]}
    (zustand / "geraete_tco.json").write_text(json.dumps(tco), encoding="utf-8")
    for schluessel, daten in klick.items():
        datei = zustand / "klick" / f"{schluessel.replace('_', '-')}.json"
        datei.write_text(json.dumps(daten), encoding="utf-8")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "geraete_abdeckung.yaml").write_text(PFLICHT, "utf-8")
    return tmp_path


def _modell_befunde(wurzel: Path) -> list[str]:
    return [b.text for b in lade_und_pruefe(wurzel).befunde if b.art == "modell_fehlt"]


def test_ausfall_des_messtags_belegt_die_geraete_seiner_seiten(tmp_path):
    nacht = _lade(NACHT)
    assert (nacht["anbieter"], nacht["datum"], nacht["laufstatus"]) == (
        "1und1",
        HEUTE,
        "gestoert",
    )
    wurzel = _wurzel(tmp_path, **{"1und1": nacht})

    assert _modell_befunde(wurzel) == [
        "1&1: 1 Pflichtmodelle ohne Bündel und ohne belegte Lücke: apple-iphone-duo"
    ]


def test_der_grund_steht_in_der_matrix(tmp_path):
    wurzel = _wurzel(tmp_path, **{"1und1": _lade(NACHT)})
    ergebnis = lade_und_pruefe(wurzel)
    text = als_markdown(
        ergebnis, lade_pflicht(wurzel / "config" / "geraete_abdeckung.yaml")
    )

    grund = ergebnis.luecken[("1&1", "apple-iphone-17")]
    assert grund.startswith("Klick-Lauf 1und1 ausgefallen: gestoert: ")
    assert grund.endswith("Abruf gestört (HTTP 502)")
    assert ergebnis.luecken[("1&1", "samsung-galaxy-s26-ultra")] == grund
    zeile = next(z for z in text.splitlines() if z.startswith("| apple-iphone-17 |"))
    assert f"belegt: {grund}" in zeile


def test_gegenprobe_ausfall_vom_vortag_belegt_nichts(tmp_path):
    gestern = {**_lade(NACHT), "datum": "2026-11-20"}
    wurzel = _wurzel(tmp_path, **{"1und1": gestern})

    assert _modell_befunde(wurzel) == [
        "1&1: 3 Pflichtmodelle ohne Bündel und ohne belegte Lücke: apple-iphone-17, "
        "samsung-galaxy-s26-ultra, apple-iphone-duo"
    ]


def test_gegenprobe_gelesener_lauf_belegt_nichts(tmp_path):
    from telco_radar.klick_vertrag import ausfall

    gelesen = {**_lade(NACHT), "laufstatus": "gelesen", "grund": None}
    wurzel = _wurzel(tmp_path, **{"1und1": gelesen, "1und1_2": _lade(ZWEITER)})

    assert ausfall(gelesen) is None
    assert _modell_befunde(wurzel) == [
        "1&1: 3 Pflichtmodelle ohne Bündel und ohne belegte Lücke: apple-iphone-17, "
        "samsung-galaxy-s26-ultra, apple-iphone-duo"
    ]


def test_die_meldung_nennt_die_zahl_aller_und_hoechstens_acht_namen(tmp_path):
    """Der Bericht vom 21.11. zählte 14, die Meldung nannte 8: ``BEISPIELE``."""
    viele = PFLICHT + "".join(f"  - modell-{i}\n" for i in range(9))
    wurzel = _wurzel(tmp_path, **{"1und1": _lade(NACHT)})
    (wurzel / "config" / "geraete_abdeckung.yaml").write_text(viele, "utf-8")

    (text,) = _modell_befunde(wurzel)
    assert text.startswith("1&1: 10 Pflichtmodelle ohne Bündel")
    assert len(text.split(": ", 2)[2].split(", ")) == 8


def test_ausfall_nennt_laufstatus_und_grund_der_datei():
    from telco_radar.klick_vertrag import ausfall

    nacht = _lade(NACHT)

    assert ausfall(nacht) == f"gestoert: {nacht['grund']}"
    assert ausfall(_lade(ZWEITER)) is None


AUTO = "einsundeins_1und1-auto_20261120.json"
"""Echte Datei vom 20.11.: eine Seite /iphone-duo, Seitenform, 0 Seiten gelesen."""


def _auto_heute(**felder) -> dict:
    """Die Datei am Messtag; ein Feld ``None`` fehlt danach ganz."""
    daten = {**_lade(AUTO), "datum": HEUTE, **felder}
    return {k: v for k, v in daten.items() if v is not None}


def _duo_befunde(tmp_path: Path, daten: dict) -> list[str]:
    wurzel = _wurzel(tmp_path, **{"1und1_auto": daten})
    pflicht = "pflicht_anbieter:\n  - 1&1\npflicht_modelle:\n  - apple-iphone-duo\n"
    (wurzel / "config" / "geraete_abdeckung.yaml").write_text(pflicht, "utf-8")
    return _modell_befunde(wurzel)


DUO_ROT = ["1&1: 1 Pflichtmodelle ohne Bündel und ohne belegte Lücke: apple-iphone-duo"]


def test_seitenform_am_messtag_ist_kein_ausfall_und_bleibt_befund(tmp_path):
    """Prüfer zu PR 197: ``laufstatus`` ist ``gestoert``, sobald keine Seite gelesen
    wurde, auch an der Seitenform. Das ist ein Erfassungsmangel, kein Ausfall: ein
    Ein-Seiten-Job hieße sonst jeden Tag neu belegt, ohne Verjährung."""
    daten = _auto_heute()
    assert daten["laufstatus"] == "gestoert"
    assert [s["stoerung"] for s in daten["seiten"]] == ["seitenform"]

    assert _duo_befunde(tmp_path, daten) == DUO_ROT


@pytest.mark.parametrize(
    ("laufstatus", "grund"),
    [
        ("leer", "keine Kombination erfasst"),
        ("nicht_gelesen", "verschoben: geraete.yml läuft"),
        (None, None),
        ("gestoert", None),
    ],
    ids=["leer", "verschoben", "ohne-laufstatus", "ohne-grund"],
)
def test_kein_ausfall_belegt_nichts_und_bleibt_gruen(
    tmp_path, skript, capsys, laufstatus, grund
):
    """Prüfer zu PR 197: leer gelesen, geplante Verschiebung und eine Datei ohne
    Laufstatus oder Grund sind kein Ausfall: kein Beleg, keine ``::error``-Zeile, kein
    Exit 3."""
    from telco_radar.klick_vertrag import ausfall

    seite = {**_lade(AUTO)["seiten"][0], "status": "nicht_besucht", "stoerung": None}
    daten = {**_auto_heute(laufstatus=laufstatus, grund=grund), "seiten": [seite]}

    assert ausfall(daten) is None
    assert _duo_befunde(tmp_path, daten) == DUO_ROT
    assert skript.endcode(daten, rot_bei_ausfall=True) == 0
    assert capsys.readouterr().out == ""


def test_im_ausfall_bleibt_eine_seite_anderer_form_befund(tmp_path):
    """Ausfall (502) und eine Seitenform-Seite im selben Lauf: belegt ist nur, was der
    Ausfall nicht lesen ließ."""
    nacht = _lade(NACHT)
    duo = {**_lade(AUTO)["seiten"][0]}
    daten = {**nacht, "seiten": [duo, *nacht["seiten"]]}

    assert _duo_befunde(tmp_path, daten) == DUO_ROT


@pytest.fixture(scope="module")
def skript():
    spec = importlib.util.spec_from_file_location("klick_tageslauf_ausfall", SKRIPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def test_ausfall_macht_den_job_rot_nur_mit_schalter(skript, capsys):
    from telco_radar.klick_vertrag import ausfall

    nacht = _lade(NACHT)

    assert skript.endcode(nacht, rot_bei_ausfall=True) == skript.FEHLER_AUSFALL == 3
    assert skript.endcode(nacht, rot_bei_ausfall=False) == 0
    zeilen = capsys.readouterr().out.splitlines()
    assert zeilen == [f"::error title=Klick-Ausfall 1und1::{ausfall(nacht)}"] * 2


def test_gegenprobe_gelesener_lauf_bleibt_gruen(skript, capsys):
    assert skript.endcode(_lade(ZWEITER), rot_bei_ausfall=True) == 0
    assert capsys.readouterr().out == ""


def test_fixtures_sind_die_dateien_der_nacht():
    """Die Fixture ist die abgelegte Datei, keine nachgebaute (``_herkunft.json``)."""
    herkunft = json.loads((FIXTURES / "_herkunft.json").read_text(encoding="utf-8"))
    eintraege = {e["datei"]: e for e in herkunft["eintraege"]}
    assert "44840854026" in eintraege[NACHT]["quelle"]
    seiten = _lade(NACHT)["seiten"]
    assert len(seiten) == 21 and {s["status"] for s in seiten} == {"nicht_besucht"}
