"""Beleg je Preiszeile (Ziel 1d): Link je Zeile, „ohne Beleg“ mit Grund, Quote.

Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7). Gerendert wird das echte Makro
`buendelzeile`; Bilder und Quote kommen aus `geraete_belege` (dieselbe Funktion für
Zeile und Satz, Clean Code 1).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, Undefined, select_autoescape

from telco_radar.beleg_manifest import MANIFEST_NAME, baue_manifest, schreibe
from telco_radar.beleg_regeln import ANZEIGE_TAGE, dateiname
from telco_radar.report import geraete_belege
from telco_radar.report.geraete_preisstand import anzeige
from telco_radar.report.geraete_tco_grafik import euro as _euro

HEUTE = date(2026, 11, 10)
BERICHTE = [{"date": "2026-11-10"}]
MODELL = "iphone-17-256"


def euro(betrag) -> str:
    """Der echte Filter; Felder, die die Testkarte nicht trägt, bleiben leer."""
    return "" if isinstance(betrag, Undefined) else _euro(betrag)


HINWEIS = "Der Messlauf lichtet je Gerät und Anbieter"


def umgebung(tmp_path: Path, anhaenge: dict[str, list[str]]) -> Environment:
    schreibe(tmp_path / MANIFEST_NAME, baue_manifest(anhaenge, HEUTE))
    env = Environment(
        loader=FileSystemLoader(Path(geraete_belege.__file__).parent / "templates"),
        autoescape=select_autoescape(["html", "htm", "xml", "j2"]),
    )
    env.filters["euro"] = euro
    env.filters["date_de"] = lambda iso: date.fromisoformat(iso[:10]).strftime("%d.%m.")
    env.globals["preis_anzeige"] = anzeige
    geraete_belege.installiere(env, tmp_path, BERICHTE)
    return env


def karte(
    anbieter: str, tarif: str, *, crawler: bool = True, preis: bool = True
) -> dict:
    return {
        "anbieter": anbieter,
        "tarif": tarif,
        "belastbar": preis,
        "vom_crawler": crawler,
        "gesamt": 900.0 if preis else None,
        "sku_id": "",
        "anb_farbe": "#000",
        "zustand": "neu",
    }


def zeile(env: Environment, k: dict) -> BeautifulSoup:
    quelle = '{% from "_geraete_buendel.html.j2" import buendelzeile %}'
    html = env.from_string(quelle + "{{ buendelzeile(k, m) }}").render(k=k, m=MODELL)
    return BeautifulSoup(html, "html.parser")


def bild(anbieter: str, tag: str = "2026-11-10") -> str:
    return dateiname(MODELL, anbieter, date.fromisoformat(tag))


def test_jede_zeile_des_paares_verlinkt_das_bild_nicht_nur_die_guenstigste(tmp_path):
    env = umgebung(tmp_path, {"belege-2026-11-10": [bild("vodafone")]})
    for tarif in ("Smart M", "Smart L", "Smart XL"):
        marke = zeile(env, karte("Vodafone", tarif)).select_one("a.gr-kk-marke--beleg")
        assert marke is not None, tarif
        assert marke["href"].endswith(f"/belege-2026-11-10/{bild('vodafone')}")
        assert "10.11." in marke.get_text()
        assert HINWEIS in marke["title"]


def test_zeile_ohne_bild_traegt_ohne_beleg_mit_grund_je_messweg(tmp_path):
    env = umgebung(tmp_path, {"belege-2026-11-10": [bild("vodafone")]})
    klick = zeile(env, karte("o2", "M", crawler=True)).select_one(
        ".gr-kk-marke--ohnebeleg"
    )
    liste = zeile(env, karte("o2", "M", crawler=False)).select_one(
        ".gr-kk-marke--ohnebeleg"
    )
    assert klick.get_text(strip=True) == "ohne Beleg"
    assert "Klick-Lauf gelesen" in klick["title"]
    assert str(ANZEIGE_TAGE) in klick["title"]
    assert "Anbieterliste" in liste["title"]
    assert klick["title"] != liste["title"]
    assert zeile(env, karte("o2", "M")).select_one("a.gr-kk-marke--beleg") is None


def test_andere_geraet_oder_anbieter_erbt_kein_bild_gegenprobe(tmp_path):
    env = umgebung(tmp_path, {"belege-2026-11-10": [bild("vodafone")]})
    fremd = env.from_string(
        '{% from "_geraete_buendel.html.j2" import buendelzeile %}'
        "{{ buendelzeile(k, 'anderes-geraet-128') }}"
    ).render(k=karte("Vodafone", "M"))
    assert "gr-kk-marke--ohnebeleg" in fremd
    assert "gr-kk-marke--beleg" not in fremd


def test_zeile_ohne_preis_traegt_keine_belegmarke(tmp_path):
    env = umgebung(tmp_path, {"belege-2026-11-10": [bild("vodafone")]})
    seite = zeile(env, karte("Vodafone", "M", preis=False))
    assert seite.select_one(".gr-kk-marke--beleg, .gr-kk-marke--ohnebeleg") is None


def test_kaputtes_manifest_nennt_den_grund_an_der_zeile(tmp_path):
    (tmp_path / MANIFEST_NAME).write_text("{kaputt", encoding="utf-8")
    env = Environment(
        loader=FileSystemLoader(Path(geraete_belege.__file__).parent / "templates"),
        autoescape=select_autoescape(["html", "htm", "xml", "j2"]),
    )
    env.filters["euro"] = euro
    env.filters["date_de"] = lambda iso: iso
    env.globals["preis_anzeige"] = anzeige
    assert geraete_belege.installiere(env, tmp_path, BERICHTE)
    marke = zeile(env, karte("Vodafone", "M")).select_one(".gr-kk-marke--ohnebeleg")
    assert "Liste der Belegbilder" in marke["title"]


def modelle() -> list[dict]:
    return [
        {
            "id": MODELL,
            "zeilen_band": [
                karte("Vodafone", "M"),
                karte("Vodafone", "L"),
                karte("o2", "M"),
            ],
            "zeilen_ohne_band": [
                karte("Vodafone", "Flat"),
                karte("Telekom", "S", preis=False),
            ],
        },
        {"id": "pixel-10-128", "zeilen_band": [karte("Vodafone", "M")]},
    ]


def test_quote_zaehlt_dieselben_zeilen_wie_die_marken(tmp_path):
    env = umgebung(tmp_path, {"belege-2026-11-10": [bild("vodafone")]})
    q = geraete_belege.quote(env.globals["zeilenbeleg"], modelle())
    assert (q["mit"], q["gesamt"]) == (3, 5)
    assert q["satz"].startswith("3 von 5 Preisen mit Screenshot vom Original")
    markiert = sum(
        1
        for m in modelle()
        for k in [*m.get("zeilen_band", []), *m.get("zeilen_ohne_band", [])]
        if k["belastbar"]
        and zeile(env, k).select_one("a.gr-kk-marke--beleg") is not None
        and m["id"] == MODELL
    )
    assert markiert == q["mit"]


def test_quote_ohne_bilder_ist_null_und_ohne_preise_stumm(tmp_path):
    env = umgebung(tmp_path, {})
    q = geraete_belege.quote(env.globals["zeilenbeleg"], modelle())
    assert (q["mit"], q["gesamt"]) == (0, 5)
    assert q["satz"].startswith("0 von 5 Preisen")
    leer = geraete_belege.quote(env.globals["zeilenbeleg"], [])
    assert leer == {"mit": 0, "gesamt": 0, "satz": ""}
