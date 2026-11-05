"""Datenkonzept Geräte 5.4, Nachzug: Bandgraph, Graph-Knoten und Export je Laufzeit.

„Grafik: eine Linie je Anbieter in der gewählten Laufzeit, Achse H“ und „der
Umschalter steuert … Grafik … und Export“. Bis zu diesem Nachzug zog
`baender_fuer_modell` je Anbieter die günstigste Karte über ALLE Laufzeiten
(congstar mit 12 Raten in der Grafik, die 24 Monate hieß), beschriftete die
Achse fest „Kosten über 24 Monate“ und rechnete das Δ der Balken gegen die
günstigste Vodafone-Karte über alle Laufzeiten; der Bündel-Export war eine
einzige Datei. Jeder Test hier ist gegen diesen Stand rot.

Bestand und Erwartungen sind die von `test_laufzeit_vergleich` (iPhone 17 Pro
256 GB, Band XS; die Beträge stehen dort als Rechnung aus den Rohwerten). Dazu
Kriterium 11 der Portal-Abnahme: die große Zahl nennt ihren Zeitraum.
"""

from __future__ import annotations

import csv
import importlib.util
import io
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from test_laufzeit_vergleich import MODELL, SOLL, ansicht

from telco_radar.report import geraete_export, geraete_laufzeit

_SKRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pruefe_portal.py"
_spec = importlib.util.spec_from_file_location("pruefe_portal", _SKRIPT)
portal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portal)


@pytest.fixture(scope="module")
def g(tmp_path_factory):
    return ansicht(tmp_path_factory.mktemp("lzgrafik"))


def _modell(g) -> dict:
    return next(m for m in g["tco"]["modelle"] if m["id"] == MODELL)


def _band(g, laufzeit: int) -> dict:
    return next(
        b for b in _modell(g)["baender_je_laufzeit"][laufzeit] if b["key"] == "xs"
    )


def _komma(betrag: float) -> str:
    return f"{betrag:.2f}".replace(".", ",")


@pytest.mark.parametrize("laufzeit", sorted(SOLL))
def test_der_bandgraph_zeigt_je_anbieter_die_karte_seiner_laufzeit(g, laufzeit):
    band = _band(g, laufzeit)
    soll = SOLL[laufzeit]
    assert band["laufzeit"] == laufzeit
    assert {w["anbieter"]: w["gesamt"] for w in band["werte"]} == soll
    assert {z["anbieter"]: z["gesamt"] for z in band["balken"]["zeilen"]} == soll
    assert {li["anbieter"] for li in band["grafik"]["linien"]} == set(soll)
    svg = band["grafik"]["svg"]
    zeitraum, fremd = (36, 24) if laufzeit == 36 else (24, 36)
    assert f"Kosten über {zeitraum} Monate" in svg
    assert f"{fremd} Monate" not in svg


def test_die_standardansicht_des_bandgraphen_hat_24_raten(g):
    """Gegenprobe zum alten Stand: dort stand congstar mit der 12er-Karte
    (1.201,00 €) im Standardgraphen, nicht mit der 24er (1.279,00 €)."""
    modell = _modell(g)
    assert modell["baender"] is modell["baender_je_laufzeit"][24]
    xs = next(b for b in modell["baender"] if b["key"] == "xs")
    werte = {w["anbieter"]: w["gesamt"] for w in xs["werte"]}
    assert werte["congstar"] == SOLL[24]["congstar"] != SOLL[12]["congstar"]
    assert "Telekom" not in werte and werte["1&1"] == SOLL[24]["1&1"]


def test_das_delta_des_bandgraphen_gilt_nur_gegen_vodafone_derselben_laufzeit(g):
    for laufzeit, soll in SOLL.items():
        zeilen = {z["anbieter"]: z for z in _band(g, laufzeit)["balken"]["zeilen"]}
        assert zeilen["Vodafone"]["referenz"], laufzeit
        for anbieter, betrag in soll.items():
            if anbieter == "Vodafone":
                continue
            assert zeilen[anbieter]["delta_euro"] == round(
                betrag - soll["Vodafone"], 2
            ), (laufzeit, anbieter)
    assert _band(g, 36)["balken"]["zeilen"][0]["anbieter"] == "congstar"
    assert "1&1" not in {z["anbieter"] for z in _band(g, 36)["balken"]["zeilen"]}


def test_ein_anbieter_ohne_buendel_dieser_laufzeit_heisst_nicht_erfasst(g):
    fehlend = {f["anbieter"]: f["grund"] for f in _band(g, 24)["fehlend"]}
    assert fehlend == {
        "Telekom": "Telekom ist mit 24 Raten nicht erfasst.",
    }
    zwoelf = {f["anbieter"]: f["grund"] for f in _band(g, 12)["fehlend"]}
    assert zwoelf == {
        a: f"{a} ist mit 12 Raten nicht erfasst." for a in ("Telekom", "1&1", "o2")
    }
    sechsunddreissig = {f["anbieter"]: f["grund"] for f in _band(g, 36)["fehlend"]}
    assert sechsunddreissig == {
        "o2": "o2 ist mit 36 Raten nicht erfasst.",
        "1&1": "1&1 wird nur über 24 Monate verglichen.",
    }


def test_der_graph_knoten_traegt_jede_laufzeit_getrennt(g):
    knoten = next(m for m in g["tco"]["graph_daten"]["modelle"] if m["id"] == MODELL)
    assert set(knoten["baender"]) == set(SOLL)
    for laufzeit, soll in SOLL.items():
        zeilen = knoten["baender"][laufzeit]["xs"]["zeilen"]
        assert {z["anbieter"]: z["gesamt"] for z in zeilen} == soll, laufzeit


def _buendelzeilen(pfad: Path) -> list[dict]:
    text = pfad.read_text(encoding="utf-8-sig")
    return [
        z
        for z in csv.DictReader(io.StringIO(text), delimiter=";")
        if z["Art"] == "Bündel"
    ]


def test_der_export_je_laufzeit_traegt_genau_ihre_buendel(g, tmp_path):
    tco = g["tco"]["export"]
    info = geraete_export.schreibe_exporte(tmp_path, [], [], None, tco=tco)
    alle = _buendelzeilen(tmp_path / info["tco"]["datei"])
    assert len(alle) == sum(len(s) for s in SOLL.values())
    assert set(info["tco_je_laufzeit"]) == set(SOLL)
    for laufzeit, soll in SOLL.items():
        eintrag = info["tco_je_laufzeit"][laufzeit]
        assert eintrag["datei"] == f"exporte/geraete-tco-{laufzeit}.csv"
        zeilen = _buendelzeilen(tmp_path / eintrag["datei"])
        assert eintrag["zeilen"] == len(zeilen)
        assert {z["Laufzeit Monate"] for z in zeilen if z["Anbieter"] != "1&1"} == {
            str(laufzeit)
        }
        assert {
            z["Anbieter"]: geraete_export.leitzahl_aus_zeile(z) for z in zeilen
        } == {anbieter: _komma(betrag) for anbieter, betrag in soll.items()}


def test_sim_only_steht_wie_die_naeherung_unter_der_standardansicht():
    teile = geraete_laufzeit.export_je_laufzeit(
        {
            "buendel": [{"raten_laufzeit": 36}, {"raten_laufzeit": 48}],
            "sim_only": [{"anbieter": "Vodafone"}],
        }
    )
    assert {lz: len(t["sim_only"]) for lz, t in teile.items()} == {12: 0, 24: 1, 36: 0}
    assert {lz: len(t["buendel"]) for lz, t in teile.items()} == {12: 0, 24: 0, 36: 1}


def _zeile(label: str | None, leitzahl: str = "36", gesamt: str = "1927.54") -> str:
    etikett = f'<em class="gr-bnd-label">{label}</em>' if label is not None else ""
    return (
        f'<details class="gr-bnd" data-gesamt="{gesamt}" '
        f'data-leitzahl-monate="{leitzahl}"><summary><span class="gr-bnd-tco">'
        f"1.927,54 € {etikett}</span></summary></details>"
    )


def _tafel(*zeilen: str):
    return BeautifulSoup(f'<div id="tafel-tco">{"".join(zeilen)}</div>', "html.parser")


def test_kriterium_11_verlangt_den_zeitraum_an_der_grossen_zahl():
    """Datenkonzept 5.3: „über H Monate“ an der Zahl, H wie die Zeile ihn
    trägt. Gegenproben: ohne Etikett und mit falschem H wird das Kriterium rot;
    eine Zeile ohne Zahl braucht kein Etikett."""
    gut = _zeile("Kosten über 36 Monate")
    assert portal.zeitraum_maengel(_tafel(gut)) == []
    assert portal.zeitraum_maengel(_tafel(gut, _zeile(None, gesamt=""))) == []
    assert portal.zeitraum_maengel(_tafel(gut, _zeile(None))) == [
        "1 Bündelzeilen ohne 'über H Monate'"
    ]
    assert portal.zeitraum_maengel(_tafel(_zeile("Kosten über 24 Monate"))) == [
        "1 Bündelzeilen ohne 'über H Monate'"
    ]
