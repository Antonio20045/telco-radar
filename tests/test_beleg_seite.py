"""Belege neben dem Preis: die Vorlage liest nur das Manifest, ohne Netz.

Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7). Gerendert wird mit der Umgebung
von `render_site` das echte Makro `belegeintrag`, angebunden über
`geraete_belege.installiere`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape

from telco_radar.beleg_manifest import MANIFEST_NAME, baue_manifest, schreibe
from telco_radar.beleg_regeln import dateiname
from telco_radar.report import geraete_belege
from telco_radar.report.geraete_tco_grafik import euro

HEUTE = date(2026, 11, 10)
BERICHTE = [{"date": "2026-11-10"}]
ZEILE = ("iphone-17-256", "Vodafone")


MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August")
MONATE += ("September", "Oktober", "November", "Dezember")


def datum_de(iso: str) -> str:
    """Deutsches Datum wie die Seite, aus dem ISO-Datum."""
    tag = date.fromisoformat(iso[:10])
    return f"{tag.day}. {MONATE[tag.month - 1]} {tag.year}"


def umgebung() -> Environment:
    """Die Vorlagen von `render_site` mit den Filtern, die das Makro braucht."""
    env = Environment(
        loader=FileSystemLoader(Path(geraete_belege.__file__).parent / "templates"),
        autoescape=select_autoescape(["html", "htm", "xml", "j2"]),
    )
    env.filters["euro"] = euro
    env.filters["date_de"] = datum_de
    return env


def zeige(env: Environment, zeile=ZEILE) -> BeautifulSoup:
    quelle = '{% from "_geraete_buendel.html.j2" import belegeintrag %}'
    vorlage = env.from_string(quelle + "{{ belegeintrag(g, a) }}")
    return BeautifulSoup(vorlage.render(g=zeile[0], a=zeile[1]), "html.parser")


def manifest(tmp_path: Path, anhaenge: dict[str, list[str]]) -> Path:
    schreibe(tmp_path / MANIFEST_NAME, baue_manifest(anhaenge, HEUTE))
    return tmp_path


def datei(geraet: str, anbieter: str, tag: str) -> str:
    return dateiname(geraet, anbieter, date.fromisoformat(tag))


def test_beleg_erscheint_mit_zahl_datum_und_adresse(tmp_path):
    name = datei("iphone-17-256", "vodafone", "2026-11-10")
    ordner = manifest(tmp_path, {"belege-2026-11-10": [name]})
    env = umgebung()
    assert geraete_belege.installiere(env, ordner, BERICHTE) == []
    seite = zeige(env)
    assert seite.select_one("summary").get_text(strip=True) == "Belege (1)"
    bild = seite.select_one("details.gr-belege img")
    assert bild["data-src"].endswith(f"/belege-2026-11-10/{name}")
    assert bild.get("src") is None
    assert "10. November 2026" in seite.select_one(".gr-belege-tag").get_text()


def test_mehrere_tage_neueste_zuerst_und_grosse_aenderung_benannt(tmp_path):
    alt = datei("iphone-17-256", "vodafone", "2026-11-05")
    neu = datei("iphone-17-256", "vodafone", "2026-11-10")
    ordner = manifest(
        tmp_path,
        {
            "belege-2026-11-05": [alt],
            "belege-gross-2026-11": [alt],
            "belege-2026-11-10": [neu],
        },
    )
    env = umgebung()
    geraete_belege.installiere(env, ordner, BERICHTE)
    seite = zeige(env)
    assert seite.select_one("summary").get_text(strip=True) == "Belege (2)"
    tage = [t.get_text() for t in seite.select(".gr-belege-tag")]
    assert tage[0].startswith("10. November 2026") and "große Änderung" not in tage[0]
    assert tage[1].startswith("5. November 2026") and "große Änderung" in tage[1]


def test_ohne_beleg_erscheint_nichts(tmp_path):
    env = umgebung()
    geraete_belege.installiere(env, tmp_path, BERICHTE)
    assert zeige(env).select_one("details") is None


def test_anderes_geraet_oder_anbieter_zeigt_nichts(tmp_path):
    ordner = manifest(
        tmp_path,
        {"belege-2026-11-10": [datei("iphone-17-256", "o2", "2026-11-10")]},
    )
    env = umgebung()
    geraete_belege.installiere(env, ordner, BERICHTE)
    assert zeige(env).select_one("details") is None
    assert zeige(env, ("iphone-17-256", "o2")).select_one("details") is not None


def test_bericht_von_morgen_blendet_abgelaufenes_aus(tmp_path):
    name = datei("iphone-17-256", "vodafone", "2026-11-03")
    ordner = manifest(tmp_path, {"belege-2026-11-03": [name]})
    for tag, erwartet in (("2026-11-10", True), ("2026-11-11", False)):
        env = umgebung()
        geraete_belege.installiere(env, ordner, [{"date": tag}])
        assert (zeige(env).select_one("details") is not None) is erwartet


def test_kaputtes_manifest_ist_ein_benannter_ausfall(tmp_path):
    (tmp_path / MANIFEST_NAME).write_text("{kaputt", encoding="utf-8")
    env = umgebung()
    ausfaelle = geraete_belege.installiere(env, tmp_path, BERICHTE)
    assert [a.teil for a in ausfaelle] == [geraete_belege.TEIL]
    assert "BelegManifestFehler" in ausfaelle[0].grund
    assert zeige(env).select_one("details") is None


def test_vorlage_ohne_anbindung_bricht_nicht():
    assert zeige(umgebung()).select_one("details") is None


def test_anbietername_mit_sonderzeichen_trifft_den_dateinamen(tmp_path):
    name = datei("iphone-17-256", "1-1", "2026-11-10")
    ordner = manifest(tmp_path, {"belege-2026-11-10": [name]})
    env = umgebung()
    geraete_belege.installiere(env, ordner, BERICHTE)
    assert zeige(env, ("iphone-17-256", "1&1")).select_one("details") is not None
