"""Belege neben dem Preis: die Vorlage liest nur das Manifest, ohne Netz.

Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7). Geprüft wird, was
`geraete_belege.installiere` je (Gerät, Anbieter) aus dem Manifest bereitstellt
(`belege_fuer`); die Seite zeigt ein Bild nur noch an der Preiszeile, die es bestätigt
(`tests/test_beleg_kombi.py`, `tests/test_beleg_position.py`).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from telco_radar.beleg_manifest import (
    MANIFEST_NAME,
    Beleg,
    baue_manifest,
    markiere_ausfall,
    schreibe,
)
from telco_radar.beleg_regeln import (
    ANZEIGE_GROSS_ANZAHL,
    ANZEIGE_TAGE,
    AUFBEWAHRUNG_TAGE,
    dateiname,
)
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


def zeige(env: Environment, zeile=ZEILE) -> list[dict]:
    """Die Bilder von `installiere` für (Gerät, Anbieter), neueste zuerst."""
    return env.globals["belege_fuer"](zeile[0], zeile[1])


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
    bilder = zeige(env)
    assert len(bilder) == 1
    assert bilder[0]["url"].endswith(f"/belege-2026-11-10/{name}")
    assert bilder[0]["datum"] == "2026-11-10" and bilder[0]["gross"] is False


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
    bilder = zeige(env)
    assert [(b["datum"], b["gross"]) for b in bilder] == [
        ("2026-11-10", False),
        ("2026-11-05", True),
    ]


def test_ohne_beleg_erscheint_nichts(tmp_path):
    env = umgebung()
    geraete_belege.installiere(env, tmp_path, BERICHTE)
    assert zeige(env) == []


def test_anderes_geraet_oder_anbieter_zeigt_nichts(tmp_path):
    ordner = manifest(
        tmp_path,
        {"belege-2026-11-10": [datei("iphone-17-256", "o2", "2026-11-10")]},
    )
    env = umgebung()
    geraete_belege.installiere(env, ordner, BERICHTE)
    assert zeige(env) == []
    assert zeige(env, ("iphone-17-256", "o2")) != []


def test_bericht_von_morgen_blendet_abgelaufenes_aus(tmp_path):
    name = datei("iphone-17-256", "vodafone", "2026-11-03")
    ordner = manifest(tmp_path, {"belege-2026-11-03": [name]})
    for tag, erwartet in (("2026-11-10", True), ("2026-11-11", False)):
        env = umgebung()
        geraete_belege.installiere(env, ordner, [{"date": tag}])
        assert bool(zeige(env)) is erwartet


def test_kaputtes_manifest_ist_ein_benannter_ausfall(tmp_path):
    (tmp_path / MANIFEST_NAME).write_text("{kaputt", encoding="utf-8")
    env = umgebung()
    ausfaelle = geraete_belege.installiere(env, tmp_path, BERICHTE)
    assert [a.teil for a in ausfaelle] == [geraete_belege.TEIL]
    assert "BelegManifestFehler" in ausfaelle[0].grund
    assert zeige(env) == []


def test_vorlage_ohne_anbindung_bricht_nicht():
    assert "belege_fuer" not in umgebung().globals


def test_anbietername_mit_sonderzeichen_trifft_den_dateinamen(tmp_path):
    name = datei("iphone-17-256", "1-1", "2026-11-10")
    ordner = manifest(tmp_path, {"belege-2026-11-10": [name]})
    env = umgebung()
    geraete_belege.installiere(env, ordner, BERICHTE)
    assert zeige(env, ("iphone-17-256", "1&1")) != []


def test_anzeige_sieben_tage_und_hoechstens_drei_aeltere_grosse(tmp_path):
    """Heute 10.11.: Bild vom 5.11. und die drei jüngsten älteren großen."""
    tage = ("2026-10-01", "2026-10-08", "2026-10-15", "2026-10-22")
    ordner = manifest(
        tmp_path,
        {
            "belege-gross-2026-10": [
                datei("iphone-17-256", "vodafone", t) for t in tage
            ],
            "belege-2026-11-05": [datei("iphone-17-256", "vodafone", "2026-11-05")],
        },
    )
    env = umgebung()
    geraete_belege.installiere(env, ordner, BERICHTE)
    gezeigt = [b["datum"] for b in zeige(env)]
    assert gezeigt == ["2026-11-05", "2026-10-22", "2026-10-15", "2026-10-08"]


def test_anzeige_grenzen_sind_benannte_konstanten():
    assert (ANZEIGE_TAGE, ANZEIGE_GROSS_ANZAHL) == (7, 3)
    assert ANZEIGE_TAGE == AUFBEWAHRUNG_TAGE


def test_anzeige_aeltere_kleine_aenderung_bleibt_weg_gegenprobe():
    """Ohne Manifest-Filter: älter als sieben Tage und nicht groß, nicht angezeigt."""
    heute = date(2026, 11, 10)
    url = "https://example.invalid/b.webp"
    klein = Beleg("g", "a", date(2026, 11, 2), False, url)
    gross = Beleg("g", "a", date(2026, 11, 2), True, url)
    grenze = Beleg("g", "a", date(2026, 11, 3), False, url)
    assert geraete_belege.sortiert_je_preis([klein], heute) == {}
    assert len(geraete_belege.sortiert_je_preis([gross], heute)[("g", "a")]) == 1
    assert len(geraete_belege.sortiert_je_preis([grenze], heute)[("g", "a")]) == 1


def test_stoerungsvermerk_im_manifest_wird_ein_benannter_ausfall(tmp_path):
    name = datei("iphone-17-256", "vodafone", "2026-11-10")
    ordner = manifest(tmp_path, {"belege-2026-11-10": [name]})
    gut = geraete_belege.installiere(umgebung(), ordner, BERICHTE)
    assert gut == []
    markiere_ausfall(ordner / MANIFEST_NAME, "Lauf endete mit Exit 124", HEUTE)
    env = umgebung()
    ausfaelle = geraete_belege.installiere(env, ordner, BERICHTE)
    assert [a.teil for a in ausfaelle] == [geraete_belege.TEIL]
    assert "Exit 124" in ausfaelle[0].grund
    assert zeige(env) != []
