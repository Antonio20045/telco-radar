"""Soll/Ist-Vollständigkeit je Anbieter, Stufe 1 (Abnahmekriterium 1, 21.11.2026).

Bis zu diesem Stand warf ``geraete_pipeline.main`` die Bilanz des Gerätelaufs weg, und
nichts zählte, was der Anbieter selbst anbietet. Hier: Ist-Zählung gegen einen Auszug
des echten Bestands vom 21.11.2026 (mit Gegenprobe), Lücken mit hergeleitetem Grund,
der Wächter rot/grün, die Lauf-Datei aus dem Nachtlauf und die Zeile auf der Seite.

Alle Daten setzen ihr Datum selbst (harte Regel 7); der Nachtlauf-Test übernimmt das
Datum, das ``main`` der Stufe übergibt, statt selbst auf die Uhr zu sehen.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_geraete_buendel_kopf_zeitraum as basis
from bs4 import BeautifulSoup
from test_geraete_browser_fixture import HEUTE as SEITE_HEUTE

from telco_radar import geraete_lauf
from telco_radar import geraete_soll_waechter as waechter
from telco_radar.geraete_vollstaendigkeit import (
    ERWARTET,
    GRUND_NICHT_IM_KATALOG,
    GRUND_PAKET,
    GRUND_STUFE2,
    GRUND_TW_LISTE,
    GRUND_TW_NETZ,
    GRUND_TW_ZEIT,
    UNBENANNT,
    SichtbareAuswahl,
    Signale,
    baue,
    haenge_kombinationen_ein,
    ist_zaehlung,
)
from telco_radar.report import geraete_vollstaendigkeit as seite
from telco_radar.report.html import render_site

WURZEL = Path(__file__).resolve().parents[1]
FIXTURES = WURZEL / "tests" / "fixtures" / "geraete_soll"
TAG = "2026-11-21"
T_NETZ = "Saturn/MediaMarkt · Telekom-Netz"
O2_NETZ = "Saturn/MediaMarkt · o2-Netz"
VF_NETZ = "Saturn/MediaMarkt · Vodafone-Netz"
STOERUNG = "1&1 nicht erfasst: Lesen gestört (HTTP 502, 21.11.2026)"


def _auszug() -> list[dict]:
    daten = json.loads((FIXTURES / "ist_auszug_20261121.json").read_text("utf-8"))
    return daten["buendel"]


def _soll(*modelle, art="sitemap", grund=None, gleich=False) -> dict:
    return {
        "art": art,
        "quelle": "https://beispiel.invalid/liste",
        "gleiche_quelle_wie_sammler": gleich,
        "gezaehlt_um": f"{TAG}T03:00:00+00:00",
        "grund": grund,
        "speicher_grund": "Die Liste des Anbieters nennt keine Speichergrößen",
        "funde": len(modelle),
        "modelle": None if grund else [_m(*m) for m in modelle],
    }


def _m(schluessel, im_katalog=True, nur_paket=False) -> dict:
    return {
        "schluessel": schluessel,
        "name": schluessel,
        "url": f"https://beispiel.invalid/{schluessel}",
        "im_katalog": im_katalog,
        "nur_paket": nur_paket,
    }


def _zeilen(voll: dict) -> dict:
    return {z["name"]: z for z in voll["anbieter"]}


def test_ist_zaehlung_des_messtags_gegen_den_auszug():
    ist = ist_zaehlung(_auszug(), TAG)
    telekom = ist["Telekom"].zahlen()
    von_hand = [
        b for b in _auszug() if b["anbieter"] == "Telekom" and b["abgerufen_am"] == TAG
    ]
    assert telekom["buendel"] == len(von_hand) == 42
    assert telekom["modelle"] == 3
    assert telekom["modell_speicher"] == 5
    assert telekom["tarife"] == 5
    assert telekom["laufzeiten"] == 3
    assert ist["1&1"].zahlen()["modell_speicher"] == 3
    assert ist[O2_NETZ].zahlen()["buendel"] == 7
    assert VF_NETZ not in ist


def test_ist_gegenprobe_eine_zeile_weniger_aendert_die_zahl():
    ohne = [
        b
        for b in _auszug()
        if not (
            b["anbieter"] == "Telekom" and b["sku_id"].startswith("google-pixel-11")
        )
    ]
    voll = ist_zaehlung(_auszug(), TAG)["Telekom"].zahlen()
    weniger = ist_zaehlung(ohne, TAG)["Telekom"].zahlen()
    assert weniger["modelle"] == voll["modelle"] - 1
    assert weniger["modell_speicher"] == voll["modell_speicher"] - 1
    assert weniger["buendel"] < voll["buendel"]


def test_ein_anderer_messtag_zaehlt_nicht_mit():
    ist = ist_zaehlung(_auszug(), "2026-11-20")
    assert ist["Telekom"].zahlen()["buendel"] == 5
    assert "congstar" not in ist


def _signale(**k) -> Signale:
    return Signale(erfassung=k.pop("erfassung", {}), **k)


def _voll(soll: dict, signale: Signale | None = None) -> dict:
    return baue(TAG, f"{TAG}T04:00:00+00:00", _auszug(), soll, signale or _signale())


def test_jeder_erwartete_anbieter_hat_eine_zeile_mit_drei_ebenen():
    zeilen = _zeilen(_voll({}))
    assert list(zeilen) == list(ERWARTET)
    for zeile in zeilen.values():
        assert set(zeile["ebenen"]) == {"modelle", "modell_speicher", "kombinationen"}
        assert zeile["ebenen"]["modelle"]["soll"] is None
        assert zeile["ebenen"]["modelle"]["soll_grund"]
        assert zeile["ebenen"]["kombinationen"]["soll_grund"] == GRUND_STUFE2


def test_luecken_tragen_hergeleitete_gruende_und_den_umgekehrten_fall():
    soll = {
        "Telekom": _soll(
            ("apple-iphone-17",),
            ("google-pixel-10",),
            ("https://telekom.de/shop/geraet/hmd/x1", False),
        ),
        "1&1": _soll(("apple-iphone-16",), ("apple-iphone-17",)),
        "o2": _soll(("google-pixel-11", True, True)),
    }
    erfassung = {
        "1&1": STOERUNG,
        "Telekom|google-pixel-10": "Bei Telekom nicht im Angebot (ganz gelesen)",
    }
    z = _zeilen(_voll(soll, _signale(erfassung=erfassung)))
    telekom = z["Telekom"]["ebenen"]["modelle"]
    gruende = {lu["schluessel"]: lu["grund"] for lu in telekom["luecken"]}
    assert telekom["soll"] == 3 and telekom["ist"] == 3 and telekom["erfasst"] == 1
    assert gruende["google-pixel-10"].startswith("Bei Telekom nicht im Angebot")
    assert gruende["https://telekom.de/shop/geraet/hmd/x1"] == GRUND_NICHT_IM_KATALOG
    assert telekom["nicht_im_soll_zahl"] == 2
    assert {e["schluessel"] for e in telekom["nicht_im_soll"]} == {
        "google-pixel-11",
        "samsung-galaxy-a57",
    }
    einsundeins = z["1&1"]["ebenen"]["modelle"]
    assert [lu["grund"] for lu in einsundeins["luecken"]] == [STOERUNG]
    assert z["o2"]["ebenen"]["modelle"]["luecken"][0]["grund"] == GRUND_PAKET
    assert all(zeile["unbenannt"] == 0 for zeile in z.values())


def test_ohne_signal_heisst_die_luecke_unbenannt():
    z = _zeilen(_voll({"congstar": _soll(("apple-iphone-17",), ("xiaomi-17t",))}))
    luecke = z["congstar"]["ebenen"]["modelle"]["luecken"][0]
    assert luecke["schluessel"] == "xiaomi-17t"
    assert luecke["grund"] == UNBENANNT and not luecke["benannt"]
    assert z["congstar"]["unbenannt"] == 1


def test_tarifwelt_gruende_je_netz():
    sitemap = _soll(("apple-iphone-17",), ("xiaomi-18-pro",), ("google-pixel-11",))
    signale = _signale(
        tarifwelt={"status": "frist", "ungelesen": ["google-pixel-11"]},
        tarifwelt_modelle=("apple-iphone-17", "google-pixel-11"),
    )
    soll = {T_NETZ: sitemap, VF_NETZ: sitemap, O2_NETZ: sitemap}
    z = _zeilen(_voll(soll, signale))
    vf = {
        lu["schluessel"]: lu["grund"]
        for lu in z[VF_NETZ]["ebenen"]["modelle"]["luecken"]
    }
    assert vf == {
        "apple-iphone-17": GRUND_TW_NETZ,
        "xiaomi-18-pro": GRUND_TW_LISTE,
        "google-pixel-11": GRUND_TW_ZEIT,
    }
    assert z[O2_NETZ]["ebenen"]["modelle"]["erfasst"] == 1


def test_bestand_nicht_gespeichert_benennt_jede_luecke():
    z = _zeilen(
        baue(
            TAG,
            "",
            [],
            {"Vodafone": _soll(("apple-iphone-17",))},
            _signale(ausfall="weg"),
        )
    )
    assert z["Vodafone"]["ebenen"]["modelle"]["luecken"][0]["grund"] == "weg"


def _schreibe(tmp_path: Path, voll: dict | None) -> Path:
    state = tmp_path / "data" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "geraete_tco.json").write_text(json.dumps({"updated": TAG}), "utf-8")
    if voll is not None:
        geraete_lauf.schreibe(state, TAG, {"bilanz": {}, "vollstaendigkeit": voll})
    return tmp_path


def test_waechter_gruen_bei_benannten_luecken_und_nicht_zaehlbarem_soll(
    tmp_path, capsys
):
    soll = {
        "1&1": _soll(("apple-iphone-17",), gleich=True),
        "Telekom": _soll(
            grund="Schutzantwort des Anbieters (HTTP 403), nicht umgangen"
        ),
    }
    voll = _voll(soll, _signale(erfassung={"1&1": STOERUNG}))
    assert waechter.main(["--root", str(_schreibe(tmp_path, voll))]) == 0
    ausgabe = capsys.readouterr().out
    assert "Telekom: Soll nicht zählbar (Schutzantwort" in ausgabe
    assert "::error::" not in ausgabe


def test_waechter_rot_bei_unbenannter_luecke(tmp_path, capsys):
    voll = _voll({"congstar": _soll(("xiaomi-17t",))})
    assert waechter.main(["--root", str(_schreibe(tmp_path, voll))]) == 1
    assert "congstar: 1 Lücken ohne Grund: xiaomi-17t" in capsys.readouterr().out


def test_waechter_rot_wenn_ein_anbieter_fehlt_oder_die_datei(tmp_path):
    voll = _voll({})
    voll["anbieter"] = [z for z in voll["anbieter"] if z["name"] != "o2"]
    lauf = {"datum": TAG, "vollstaendigkeit": voll}
    assert waechter.pruefe(lauf, TAG) == ["o2: keine Zählung"]
    assert waechter.main(["--root", str(_schreibe(tmp_path, None))]) == 1
    kaputt = {
        "datum": TAG,
        "vollstaendigkeit": {"fehler": "Zählung gescheitert: OSError: voll"},
    }
    assert waechter.pruefe(kaputt, TAG) == ["Zählung gescheitert: OSError: voll"]


def test_waechter_liest_genau_den_messtag_eine_vortagsdatei_ist_rot(tmp_path, capsys):
    """Prüfung PR 201: fehlt die Datei des Messtags, darf eine ältere nicht grün
    machen; trägt die Datei ein anderes Datum, ebenso nicht."""
    voll = _voll({"1&1": _soll(("apple-iphone-16",), gleich=True)})
    wurzel = _schreibe(tmp_path, voll)
    assert waechter.main(["--root", str(wurzel), "--datum", TAG]) == 0
    assert waechter.main(["--root", str(wurzel), "--datum", "2026-11-22"]) == 1
    assert "keine Lauf-Datei für den Messtag 2026-11-22" in capsys.readouterr().out
    lauf = {"datum": "2026-11-20", "vollstaendigkeit": voll}
    assert waechter.pruefe(lauf, TAG) == [
        f"Lauf-Datei trägt den 2026-11-20, Messtag ist {TAG}"
    ]


def test_waechter_meldet_erfasste_modelle_ausserhalb_eines_unabhaengigen_solls():
    unabhaengig = _voll({"Telekom": _soll(("apple-iphone-17",))})
    lauf = {"datum": TAG, "vollstaendigkeit": unabhaengig}
    assert waechter.pruefe(lauf, TAG) == [
        "Telekom: 2 erfasste Modelle fehlen im unabhängigen Soll"
    ]
    gleich = _voll({"Telekom": _soll(("apple-iphone-17",), gleich=True)})
    assert waechter.pruefe({"datum": TAG, "vollstaendigkeit": gleich}, TAG) == []


def test_gleichnamige_luecken_sind_unterscheidbar():
    soll = _soll(
        ("https://a.invalid/leica/leitzphone", False),
        ("https://a.invalid/xiaomi/leitzphone", False),
    )
    for m in soll["modelle"]:
        m["name"] = "Leica Leitzphone"
    luecken = _zeilen(_voll({"congstar": soll}))["congstar"]["ebenen"]["modelle"]
    namen = sorted(lu["name"] for lu in luecken["luecken"])
    assert namen == [
        "Leica Leitzphone (leica/leitzphone)",
        "Leica Leitzphone (xiaomi/leitzphone)",
    ]


def test_waechter_rot_wenn_ein_soll_ohne_grund_fehlt():
    voll = _voll({})
    voll["anbieter"][0]["ebenen"]["modell_speicher"]["soll_grund"] = None
    assert waechter.pruefe({"datum": TAG, "vollstaendigkeit": voll}, TAG) == [
        "Telekom: Soll modell_speicher fehlt ohne benannten Grund"
    ]


def test_stufe2_haengt_kombinationen_ein():
    voll = _voll({})
    auswahl = SichtbareAuswahl(
        anbieter="congstar",
        modell="apple-iphone-17",
        seite="https://www.congstar.de/geraete/apple/apple-iphone-17/",
        speicher=("256gb", "512gb", "1024gb"),
        tarife=("allnet-flat-m",),
        laufzeiten=(24, 36),
        gezaehlt_um=f"{TAG}T05:00:00+00:00",
    )
    ist = ist_zaehlung(_auszug(), TAG)["congstar"].kombinationen
    assert "apple-iphone-17-256gb--allnet-flat-m--24m" in ist
    haenge_kombinationen_ein(voll, "congstar", [auswahl], _auszug(), _signale())
    ebene = _zeilen(voll)["congstar"]["ebenen"]["kombinationen"]
    assert ebene["soll"] == 6
    assert ebene["erfasst"] == 4
    assert {lu["schluessel"] for lu in ebene["luecken"]} == {
        "apple-iphone-17-1024gb--allnet-flat-m--24m",
        "apple-iphone-17-1024gb--allnet-flat-m--36m",
    }
    assert _zeilen(voll)["congstar"]["unbenannt"] == 2


def _buendel(anbieter: str, tag: str) -> dict:
    sku = "apple-iphone-17-pro-256gb-silber"
    return {
        "id": f"buendel--{anbieter.lower()}--{sku}--tarif-m--24m",
        "sku_id": sku,
        "anbieter": anbieter,
        "tarif_id": "tarif-m",
        "laufzeit_monate": 24,
        "abgerufen_am": tag,
    }


CONGSTAR_AUSFALL = "congstar nicht erfasst: Lesen gestört (21.11.2026)"


def _lauf_fuer_seite(tag: str) -> dict:
    """Telekom: unabhängiges Soll mit einer Lücke; o2: unabhängig und ganz erfasst;
    1&1: Liste, die auch die Messung liest; congstar: ganz erfasst, aber mit
    Ausfallvermerk; Vodafone: kein Soll."""
    soll = {
        "Telekom": _soll(("apple-iphone-17-pro",), ("google-pixel-10",)),
        "Vodafone": _soll(grund="Abruf gescheitert (HTTP 502)"),
        "o2": _soll(("apple-iphone-17-pro",)),
        "1&1": _soll(("apple-iphone-17-pro",), gleich=True),
        "congstar": _soll(("apple-iphone-17-pro",)),
    }
    buendel = [_buendel(n, tag) for n in ("Telekom", "o2", "1&1", "congstar")]
    signale = _signale(erfassung={"congstar": CONGSTAR_AUSFALL})
    voll = baue(tag, f"{tag}T04:00:00+00:00", buendel, soll, signale)
    return {"bilanz": {}, "vollstaendigkeit": voll}


@pytest.fixture(scope="module")
def seite_mit_lauf(tmp_path_factory):
    site = basis._baue(tmp_path_factory.mktemp("vs"))
    state = site.parent / "data" / "state"
    geraete_lauf.schreibe(state, SEITE_HEUTE, _lauf_fuer_seite(SEITE_HEUTE))
    shutil.rmtree(site)
    render_site(site, site.parent / "data" / "reports")
    return site


def _vs(site: Path) -> BeautifulSoup:
    html = (site / "geraete.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "html.parser").select_one("#vollstaendigkeit")


def _summary(li) -> str:
    return li.summary.get_text(" ", strip=True)


def test_die_seite_zeigt_je_anbieter_die_zahl_aus_der_lauf_datei(seite_mit_lauf):
    block = _vs(seite_mit_lauf)
    lauf = _lauf_fuer_seite(SEITE_HEUTE)["vollstaendigkeit"]
    zeilen = {li["data-anbieter"]: li for li in block.select("li.gr-vs-z")}
    assert list(zeilen) == [z["name"] for z in lauf["anbieter"]]
    for z in lauf["anbieter"]:
        m = z["ebenen"]["modelle"]
        li = zeilen[z["name"]]
        assert li["data-ist"] == str(m["ist"])
        if m["soll"] is None:
            assert _summary(li).startswith(f"{z['name']}: {m['ist']} Modelle erfasst")
            assert "data-soll" not in li.attrs
        else:
            assert li["data-soll"] == str(m["soll"])
            assert li["data-erfasst"] == str(m["erfasst"])
            assert _summary(li).startswith(
                f"{z['name']}: {m['erfasst']} von {m['soll']} Modellen"
            )
    assert _summary(zeilen["Telekom"]) == "Telekom: 1 von 2 Modellen erfasst · 1 Lücke"
    assert _summary(zeilen["o2"]) == "o2: 1 von 1 Modellen erfasst · vollständig"
    assert _summary(zeilen["1&1"]) == (
        "1&1: 1 von 1 Modellen der Anbieterliste erfasst · Liste nicht unabhängig"
    )
    assert _summary(zeilen["Vodafone"]) == (
        "Vodafone: 0 Modelle erfasst · Angebot noch nicht gezählt"
    )
    assert "Abruf gescheitert (HTTP 502)" in zeilen["Vodafone"].get_text(
        " ", strip=True
    )
    assert "Stand vom" not in block.get_text()


def test_die_seite_nennt_den_ausfallvermerk_und_sagt_dann_nicht_vollstaendig(
    seite_mit_lauf,
):
    """Prüfung PR 201 (``test_seite_sagt_vollstaendig_trotz_ausfallvermerk``)."""
    li = _vs(seite_mit_lauf).select_one('li.gr-vs-z[data-anbieter="congstar"]')
    assert "vollständig" not in _summary(li)
    ausfall = li.select_one(".gr-vs-ausfall")
    assert ausfall is not None and ausfall.get_text(strip=True) == CONGSTAR_AUSFALL
    assert li.select_one("details").find(class_="gr-vs-ausfall") is None


def test_vollstaendig_nur_bei_unabhaengigem_soll_ohne_luecke_und_ohne_ausfall():
    lauf = _lauf_fuer_seite(SEITE_HEUTE)
    je = {z["name"]: z for z in seite.zeilen(lauf, SEITE_HEUTE)["zeilen"]}
    assert je["o2"]["marke"] == "vollständig"
    assert je["1&1"]["marke"] == "Liste nicht unabhängig"
    assert je["congstar"]["marke"] == ""
    assert je["congstar"]["ausfall"] == CONGSTAR_AUSFALL
    assert je["Vodafone"]["marke"] == "Angebot noch nicht gezählt"


def test_die_seitenzeile_folgt_der_datei_gegenprobe():
    lauf = _lauf_fuer_seite(SEITE_HEUTE)
    anders = copy.deepcopy(lauf)
    for z in anders["vollstaendigkeit"]["anbieter"]:
        if z["name"] == "Telekom":
            z["ebenen"]["modelle"].update(erfasst=0, soll=7)
    vorher = seite.zeilen(lauf, SEITE_HEUTE)["zeilen"][0]["satz"]
    nachher = seite.zeilen(anders, SEITE_HEUTE)["zeilen"][0]["satz"]
    assert vorher == "Telekom: 1 von 2 Modellen erfasst"
    assert nachher == "Telekom: 0 von 7 Modellen erfasst"
    alt = seite.zeilen(lauf, "2026-12-01")
    assert alt["stand"].startswith("Stand vom ")


def test_ohne_lauf_datei_nennt_die_seite_den_ausfall(tmp_path):
    site = basis._baue(tmp_path)
    block = _vs(site)
    assert block is not None
    assert block.get_text(" ", strip=True) == seite.FEHLT
    assert not block.select("li.gr-vs-z")


def test_eine_unlesbare_lauf_datei_ist_ein_ausfall(tmp_path):
    state = tmp_path / "data" / "state" / geraete_lauf.ORDNER
    state.mkdir(parents=True)
    (state / f"{TAG}.json").write_text("{kaputt", encoding="utf-8")
    umgebung = SimpleNamespace(globals={})

    ausfaelle = seite.installiere(umgebung, tmp_path / "data" / "state")
    assert [a.teil for a in ausfaelle] == [seite.TEIL]
    assert umgebung.globals["vollstaendigkeit"](TAG)["fehlt"] == seite.UNLESBAR
