"""„Keinen Tarif in dieser Stufe“ nur bei null gemessenen Tarifen (Karte 3b58f60a).

Eine leere Zelle der Tafel ist entweder eine Messlücke (der Anbieter hat in der Stufe
Tarife, nur zu diesem Gerät fehlt der Preis) oder gar keine Lücke (der Anbieter hat in
der Stufe keinen Tarif). Der zweite Text darf nie über eine echte Messlücke gelegt
werden: im Zweifel bleibt der alte Text stehen (fail-closed, Clean Code 4).
"""

from __future__ import annotations

import json

import pytest
import test_geraete_buendel_kopf_zeitraum as kopf_zeitraum
from bs4 import BeautifulSoup

from telco_radar.report import geraete_stufen
from telco_radar.report.geraete_luecken import fehlen_im_paar
from telco_radar.report.html import render_site

KEIN_TARIF = "Kein Tarif in dieser Datenstufe"
_SATZ = {"zeilen": [], "fremd": [], "gesperrt": []}


def _karte(anbieter: str, band: str, tarif_id: str, **mehr) -> dict:
    return {
        "anbieter": anbieter,
        "sku_id": f"{anbieter}-{band}-geraet",
        "band": band,
        "tarif_id": tarif_id,
        "raten_laufzeit": 24,
        **mehr,
    }


def _modell(karten: list, stufen: dict | None) -> dict:
    return {"id": "apple-iphone-duo-256", "karten": karten, "stufen": stufen}


def _fehlen(modell: dict, band: str) -> dict[str, dict]:
    zeilen = fehlen_im_paar(modell, _SATZ, band, 24, {}, 24)
    return {z["anbieter"]: z for z in zeilen}


def test_zaehlung_nimmt_tarifliste_und_buendel_ohne_doppelzaehlung():
    tarife = {"o2-m": {"anbieter": "o2"}, "o2-l": {"anbieter": "o2"}}
    band_je_tarif = {"o2-m": "m", "o2-l": "l"}
    modelle = [{"karten": [_karte("o2", "m", "o2-m"), _karte("o2", "xl", "o2-xl")]}]
    stufen = geraete_stufen.tarife_je_stufe(modelle, tarife, band_je_tarif)
    assert stufen == {"o2": {"m": 1, "l": 1, "xl": 1}}


def test_tarif_ohne_stufe_zaehlt_fuer_keine_stufe():
    tarife = {"o2-max": {"anbieter": "o2"}}
    assert geraete_stufen.tarife_je_stufe([], tarife, {}) == {}


def test_anbieter_mit_tarif_ohne_stufe_ist_nicht_bestimmbar():
    """1&1 Unlimited XL hat kein erhobenes Volumen und könnte in jede Stufe fallen:
    für 1&1 darf in keiner Stufe „keinen Tarif“ stehen, andere Anbieter bleiben."""
    tarife = {
        "1u1-m": {"anbieter": "1&1", "art": "mobilfunk"},
        "1u1-xl": {"anbieter": "1&1", "art": "mobilfunk"},
        "o2-m": {"anbieter": "o2", "art": "mobilfunk"},
    }
    stufen = geraete_stufen.tarife_je_stufe([], tarife, {"1u1-m": "m", "o2-m": "m"})
    assert stufen == {"o2": {"m": 1}}
    assert not geraete_stufen.stufe_ohne_tarif(stufen, "1&1", "xl")
    assert geraete_stufen.stufe_ohne_tarif(stufen, "o2", "xl")


def test_festnetztarif_ohne_volumen_macht_den_anbieter_nicht_unbestimmbar():
    tarife = {
        "o2-m": {"anbieter": "o2", "art": "mobilfunk"},
        "o2-home": {"anbieter": "o2", "art": "festnetz"},
    }
    stufen = geraete_stufen.tarife_je_stufe([], tarife, {"o2-m": "m"})
    assert stufen == {"o2": {"m": 1}}


@pytest.mark.parametrize(
    ("stufen", "anbieter", "band", "erwartet"),
    [
        ({"o2": {"m": 6}}, "o2", "s", True),
        ({"o2": {"m": 6, "s": 1}}, "o2", "s", False),
        ({"o2": {"m": 6}}, "Telekom", "s", False),
        ({}, "o2", "s", False),
        (None, "o2", "s", False),
    ],
)
def test_stufe_ohne_tarif_ist_nur_bei_null_wahr(stufen, anbieter, band, erwartet):
    assert geraete_stufen.stufe_ohne_tarif(stufen, anbieter, band) is erwartet


def test_null_tarife_in_der_stufe_tragen_den_eigenen_text():
    """o2 hat Tarife in M und XL, in S keinen: der Anbieter fehlt in S nicht aus
    Messgründen."""
    karten = [_karte("o2", "m", "o2-m"), _karte("o2", "xl", "o2-xl")]
    stufen = {"o2": {"m": 1, "xl": 1}}
    zeile = _fehlen(_modell(karten, stufen), "s")["o2"]
    assert KEIN_TARIF in zeile["kurz"]
    assert "o2 hat in dieser Datenstufe keinen Tarif" in zeile["satz"]


def test_gegenprobe_mit_tarif_in_der_stufe_bleibt_es_eine_messluecke():
    """Telekom hat in M Tarife, nur zu diesem Gerät fehlt der Preis in M: das ist
    die echte Lücke und darf nie den Text „keinen Tarif“ tragen."""
    karten = [_karte("Telekom", "l", "tk-l")]
    stufen = {"Telekom": {"m": 1, "l": 1}}
    zeile = _fehlen(_modell(karten, stufen), "m")["Telekom"]
    assert KEIN_TARIF not in zeile["kurz"]
    assert KEIN_TARIF not in zeile["satz"]
    assert zeile["kurz"].startswith("Nur in anderen Bändern")


def test_gegenprobe_ganz_ohne_bundel_aber_mit_tarif_bleibt_noch_nicht_erfasst():
    stufen = {"congstar": {"m": 4}}
    zeile = _fehlen(_modell([], stufen), "m")["congstar"]
    assert zeile["kurz"] == "Noch nicht erfasst"


def test_ganz_ohne_buendel_und_ohne_tarif_in_der_stufe_sagt_keinen_tarif():
    stufen = {"congstar": {"m": 4}}
    zeile = _fehlen(_modell([], stufen), "s")["congstar"]
    assert KEIN_TARIF in zeile["kurz"]


def test_ohne_bestand_wird_nichts_behauptet():
    """Fehlt der Bestand (Tarifliste nicht gelesen), bleibt jeder alte Text."""
    karten = [_karte("o2", "m", "o2-m")]
    zeile = _fehlen(_modell(karten, None), "s")["o2"]
    assert KEIN_TARIF not in zeile["kurz"]
    zeile = _fehlen({"id": "x", "karten": karten}, "s")["o2"]
    assert KEIN_TARIF not in zeile["kurz"]


def test_anbieter_ohne_einen_gemessenen_tarif_gilt_als_nicht_gemessen():
    zeile = _fehlen(_modell([], {"o2": {"m": 1}}), "s")["Telekom"]
    assert KEIN_TARIF not in zeile["kurz"]
    assert zeile["kurz"] == "Noch nicht erfasst"


def test_alternativen_in_anderen_stufen_bleiben_neben_dem_text_stehen():
    karten = [_karte("o2", "m", "o2-m", tco=2125.75, gesamt=2125.75)]
    zeile = _fehlen(_modell(karten, {"o2": {"m": 1}}), "s")["o2"]
    if "in anderen Stufen" in zeile["kurz"]:
        assert KEIN_TARIF in zeile["kurz"]


def test_erklaersatz_nennt_datenvolumen_und_leere_stufe_trotz_vieler_tarife():
    satz = geraete_stufen.TARIFSTUFEN_REGEL
    assert "Datenvolumen" in satz
    assert "in GB" in satz
    assert "nicht nach dem Namen" in satz
    assert "bleibt sie bei ihm leer" in satz


def _baue_site(pfad, unstufig: bool = False):
    """Bestand der Kopf-Zeitraum-Fixture (Vodafone, o2, congstar, Telekom in XS) plus
    ein Vodafone-Bündel in M und ein o2-Tarif in M ohne Bündel. In M gilt dann:
    Telekom und congstar haben keinen Tarif, o2 hat einen (Messlücke), 1&1 ist gar
    nicht gemessen. Mit `unstufig` hat congstar zusätzlich einen Tarif ohne Volumen."""
    site = kopf_zeitraum._baue(pfad)
    wurzel = site.parent
    state = wurzel / "data" / "state"
    tco = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    vodafone = next(b for b in tco["buendel"] if b["anbieter"] == "Vodafone")
    tid = "vodafone:leiter-m-mit-smartphone"
    tco["buendel"].append(
        {**vodafone, "id": vodafone["id"] + "-m", "tarif_id": tid, "tarif_name": "M"}
    )
    (state / "geraete_tco.json").write_text(json.dumps(tco), encoding="utf-8")
    saetze = [
        json.loads(z)
        for z in (state / "tarife.jsonl").read_text(encoding="utf-8").splitlines()
        if z
    ]
    o2 = next(z for z in saetze if z["anbieter"] == "o2")
    saetze.append(
        {**o2, "name": "O2 Mobile Mittel", "tarif_id": "o2:m", "datenvolumen_gb": 40}
    )
    if unstufig:
        cs = next(z for z in saetze if z["anbieter"] == "congstar")
        saetze.append(
            {**cs, "name": "Unlimited", "tarif_id": "cs:unl", "datenvolumen_gb": None}
        )
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(z) for z in saetze) + "\n", encoding="utf-8"
    )
    render_site(site, wurzel / "data" / "reports")
    return site


def _fragment(site) -> BeautifulSoup:
    fragment = site / "data" / "bnd" / f"{kopf_zeitraum.MODELL}.html"
    return BeautifulSoup(fragment.read_text(encoding="utf-8"), "html.parser")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _baue_site(tmp_path_factory.mktemp("stufen"))


@pytest.fixture(scope="module")
def seite_unstufig(tmp_path_factory) -> BeautifulSoup:
    return _fragment(_baue_site(tmp_path_factory.mktemp("unstufig"), True))


@pytest.fixture(scope="module")
def seite(site) -> BeautifulSoup:
    return _fragment(site)


def _zustand(seite: BeautifulSoup, anbieter: str, band: str) -> str:
    treffer = seite.select(
        f'.gr-anb-fehlt[data-anbieter="{anbieter}"][data-band="{band}"]'
        '[data-fehlt-lz="24"] .gr-anb-fehlt-zustand'
    )
    assert len(treffer) == 1, (anbieter, band, treffer)
    return treffer[0].get_text(strip=True)


def test_seite_ohne_tarif_in_m_heisst_keinen_tarif(seite):
    assert KEIN_TARIF in _zustand(seite, "Telekom", "m")
    assert KEIN_TARIF in _zustand(seite, "congstar", "m")


def test_seite_gegenprobe_o2_hat_in_m_einen_tarif_und_bleibt_messluecke(seite):
    assert KEIN_TARIF not in _zustand(seite, "o2", "m")


def test_seite_tarif_ohne_stufe_sperrt_den_text_fuer_den_ganzen_anbieter(
    seite_unstufig,
):
    """congstar hat einen Tarif ohne Volumen: in M darf für congstar nicht „keinen
    Tarif“ stehen, Telekom (ohne solchen Tarif) behält den Text."""
    assert KEIN_TARIF not in _zustand(seite_unstufig, "congstar", "m")
    assert KEIN_TARIF in _zustand(seite_unstufig, "Telekom", "m")


def test_seite_gegenprobe_nicht_gemessener_anbieter_bleibt_noch_nicht_erfasst(seite):
    assert _zustand(seite, "1&1", "m") == "Noch nicht erfasst"
    assert _zustand(seite, "1&1", "xs") == "Noch nicht erfasst"


def test_seite_gegenprobe_in_xs_hat_jeder_gemessene_anbieter_einen_tarif(seite):
    assert KEIN_TARIF not in _zustand(seite, "Telekom", "xs")
    assert not [
        z for z in seite.select('.gr-anb-fehlt[data-band="xs"]') if KEIN_TARIF in z.text
    ]


def test_seite_traegt_den_erklaersatz_der_regel(site):
    """Antonio, 12.12.2026: der Satz steht nicht mehr unter der Tabelle der
    Geräteseite, sondern auf der Methodikseite - derselbe Wortlaut, EIN Feld."""
    geraete = BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )
    assert geraete.select_one("#gr-tarifstufen-regel") is None
    html = BeautifulSoup(
        (site / "geraete-quellen.html").read_text(encoding="utf-8"), "html.parser"
    )
    absatz = next(
        li
        for li in html.select("#methodik .list-row")
        if li.select_one(".list-row-date").text == "Tarifstufen"
    )
    text = absatz.get_text(" ", strip=True)
    assert "Datenvolumen" in text
    assert "nicht nach dem Namen" in text
