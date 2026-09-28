"""P4: der wöchentliche Bewegungsblock (`report/geraete_bewegung.py`).

Die Fixtures sind Messungen in der Form von `geraete_zeitreihe._messungen`
mit eigenem Datum (Regel 11). Der wichtigste Fall ist der Angebotswechsel:
am echten Bestand vom 27.09.2026 waren alle sechs Treffer einer naiven
Rechnung Vodafone-Sprünge zwischen Mobil S und Mobil M, keine Preisänderung.
"""
import json
from datetime import date

import pytest

from telco_radar.report import geraete_bewegung as gb
from telco_radar.report import geraete_zeitreihe as zr

MODELL, BAND = "apple-iphone-17-pro-256", "mittel"
BIS, VON = "2026-09-27", "2026-09-20"


def _m(bid, wert, monate=24, url=""):
    return {"satz": {"id": bid, "quelle_url": url or f"https://x.test/{bid}"},
            "wert": wert, "monate": monate}


def _reihe(bid, werte: dict, monate=24):
    return {d: _m(bid, w, monate) for d, w in werte.items()}


def _block(anbieter: dict, erlaubt=None, **kw):
    messungen = {(MODELL, BAND): anbieter}
    return gb.bewegungen(
        messungen, erlaubt if erlaubt is not None else {MODELL: [BAND]},
        {MODELL: "Apple iPhone 17 Pro 256 GB"}, {BAND: {"label": "Mittel"}},
        lambda satz: satz["id"], **kw)


def _vf(werte=None, bid="vf-s"):
    return _reihe(bid, werte or {VON: 2000.0, BIS: 2000.0})


def test_ein_wettbewerber_senkt_seinen_preis():
    b = _block({"Vodafone": _vf(),
                "o2": _reihe("o2-m", {VON: 1500.0, BIS: 1400.0})})
    assert b["error"] is None and b["stichtag"] == BIS
    assert b["vergleichstag"] == VON
    [z] = b["zeilen"]
    assert (z["anbieter"], z["delta"], z["fremd_delta"], z["eigen_delta"]) \
        == ("o2", -100.0, -100.0, 0.0)
    assert (z["abstand_vorher"], z["abstand_jetzt"]) == (-500.0, -600.0)
    assert z["link"] == f"geraete.html?modell={MODELL}&band={BAND}"
    assert z["quelle_url"] == "https://x.test/o2-m"
    assert z["eigen_quelle_url"] == "https://x.test/vf-s"
    assert z["band_label"] == "Mittel"


def test_vodafone_bewegt_sich_und_der_abstand_mit():
    b = _block({"Vodafone": _vf({VON: 2000.0, BIS: 2120.0}),
                "o2": _reihe("o2-m", {VON: 1500.0, BIS: 1500.0})})
    [z] = b["zeilen"]
    assert (z["delta"], z["eigen_delta"], z["fremd_delta"]) == (-120.0, 120.0,
                                                                 0.0)


def test_gleiche_bewegung_auf_beiden_seiten_ist_keine():
    b = _block({"Vodafone": _vf({VON: 2000.0, BIS: 1900.0}),
                "o2": _reihe("o2-m", {VON: 1500.0, BIS: 1400.0})})
    assert b["zeilen"] == [] and b["geprueft"] == 1


@pytest.mark.parametrize("neu, gemeldet", [(1450.0, False), (1449.99, True)])
def test_die_euroschwelle_ist_echt_groesser(neu, gemeldet):
    # 50,00 EUR bei 2.000 EUR sind 2,5 % - nur die Euroschwelle zaehlt.
    b = _block({"Vodafone": _vf(),
                "o2": _reihe("o2-m", {VON: 1500.0, BIS: neu})})
    assert bool(b["zeilen"]) is gemeldet


def test_die_prozentschwelle_greift_unter_fuenfzig_euro():
    # 45 EUR gegen eine Vodafone-Leitzahl von 800 EUR sind 5,6 %.
    b = _block({"Vodafone": _vf({VON: 800.0, BIS: 800.0}),
                "o2": _reihe("o2-m", {VON: 700.0, BIS: 655.0})})
    assert [z["delta"] for z in b["zeilen"]] == [-45.0]
    # 39 EUR sind 4,9 % - keine Meldung.
    b = _block({"Vodafone": _vf({VON: 800.0, BIS: 800.0}),
                "o2": _reihe("o2-m", {VON: 700.0, BIS: 661.0})})
    assert b["zeilen"] == []


def test_ohne_pruefbaren_vergleich_ein_ausfall_statt_ruhe():
    """Liest der Vodafone-Adapter nichts, sind alle Paare ohne Aussage -
    das ist ein Ausfall, kein „keine Bewegung"."""
    b = _block({"o2": _reihe("o2-m", {VON: 1500.0, BIS: 1400.0})})
    assert b["error"] == gb.AUSFALL_NICHT_PRUEFBAR
    assert b["ohne_aussage"] == {gb.GRUND_MESSUNG: 1}
    # Gegenprobe: ein pruefbarer Vergleich ohne Bewegung ist kein Ausfall.
    b = _block({"Vodafone": _vf(),
                "o2": _reihe("o2-m", {VON: 1500.0, BIS: 1500.0})})
    assert b["error"] is None and b["geprueft"] == 1
    assert b["eigen_stichtag"] == BIS


def test_ein_angebotswechsel_ist_keine_preisaenderung():
    """Der Fall vom 27.09.2026: Vodafones guenstigstes Buendel springt von
    Mobil M (2.436 EUR) auf Mobil S (2.196 EUR), weil Mobil S am
    Vergleichstag nicht gelesen wurde. Kein Preis hat sich geaendert."""
    vf = {VON: _m("vf-m", 2436.0), BIS: _m("vf-s", 2196.0)}
    b = _block({"Vodafone": vf,
                "congstar": _reihe("cs-s", {VON: 1507.0, BIS: 1507.0})})
    assert b["zeilen"] == []
    assert b["ohne_aussage"] == {gb.GRUND_WECHSEL: 1}
    assert b["geprueft"] == 0 and b["error"] == gb.AUSFALL_NICHT_PRUEFBAR


def test_auch_der_wettbewerber_muss_dasselbe_angebot_sein():
    cs = {VON: _m("cs-36", 1800.0), BIS: _m("cs-24", 1507.0)}
    b = _block({"Vodafone": _vf(), "congstar": cs})
    assert b["zeilen"] == [] and b["ohne_aussage"] == {gb.GRUND_WECHSEL: 1}


def test_die_messung_darf_drei_tage_vor_dem_vergleichstag_liegen():
    b = _block({"Vodafone": _vf({"2026-09-17": 2000.0, BIS: 2000.0}),
                "o2": _reihe("o2-m", {"2026-09-17": 1500.0, BIS: 1400.0})})
    assert len(b["zeilen"]) == 1
    b = _block({"Vodafone": _vf({"2026-09-16": 2000.0, BIS: 2000.0}),
                "o2": _reihe("o2-m", {"2026-09-16": 1500.0, BIS: 1400.0})})
    assert b["zeilen"] == []
    assert b["ohne_aussage"] == {gb.GRUND_MESSUNG: 1}


def test_ohne_vodafone_am_vergleichstag_keine_aussage():
    b = _block({"Vodafone": _vf({BIS: 2000.0}),
                "o2": _reihe("o2-m", {VON: 1500.0, BIS: 1400.0})})
    assert b["zeilen"] == [] and b["ohne_aussage"] == {gb.GRUND_MESSUNG: 1}


def test_eine_leitzahl_ueber_36_monate_ist_nicht_vergleichbar():
    b = _block({"Vodafone": _vf(),
                "1&1": _reihe("11-m", {VON: 1500.0, BIS: 1300.0}, monate=36)})
    assert b["zeilen"] == []
    assert b["ohne_aussage"] == {gb.GRUND_ZEITRAUM: 1}


def test_ein_paar_ausserhalb_der_wahl_menge_faellt_heraus():
    b = _block({"Vodafone": _vf(),
                "o2": _reihe("o2-m", {VON: 1500.0, BIS: 1400.0})},
               erlaubt={MODELL: ["klein"]})
    assert b["zeilen"] == [] and b["geprueft"] == 0


def test_hoechstens_fuenf_zeilen_der_groesste_ausschlag_zuerst():
    anbieter = {"Vodafone": _vf()}
    for i, delta in enumerate((-60, 300, -90, 120, -75, 200, 55)):
        anbieter[f"W{i}"] = _reihe(f"w{i}", {VON: 1500.0, BIS: 1500.0 + delta})
    b = _block(anbieter)
    assert [z["delta"] for z in b["zeilen"]] == [300, 200, 120, -90, -75]
    assert b["weitere"] == 2


def test_der_stichtag_ist_der_juengste_messtag():
    b = _block({"Vodafone": _vf({"2026-09-18": 2000.0,
                                 "2026-09-25": 2000.0}),
                "o2": _reihe("o2-m", {"2026-09-18": 1500.0,
                                      "2026-09-25": 1400.0})})
    assert b["stichtag"] == "2026-09-25"
    assert b["vergleichstag"] == "2026-09-18"


def test_ohne_messung_ein_benannter_ausfall():
    b = gb.bewegungen({}, {}, {}, {}, lambda s: s["id"])
    assert b["error"] and b["zeilen"] == []


def test_die_gescheiterte_zeitreihe_traegt_einen_ausfall():
    assert zr.leer()["bewegung_woche"]["error"]


# ------------------------------------------------- Woche und Berichts-JSON

def test_nur_die_erste_ausgabe_der_woche_zeigt_den_block(tmp_path):
    (tmp_path / "2026-09-30.json").write_text("{}")   # Mi, KW 40
    (tmp_path / "2026-09-25.json").write_text("{}")   # Fr, KW 39
    assert gb.erste_ausgabe_der_woche(tmp_path, date(2026, 9, 30))
    assert not gb.erste_ausgabe_der_woche(tmp_path, date(2026, 10, 2))
    (tmp_path / "differenzierung.json").write_text("{}")
    assert gb.erste_ausgabe_der_woche(tmp_path, date(2026, 9, 30))


def _patch(monkeypatch, aufbereiten):
    from telco_radar.report import geraete_view
    monkeypatch.setattr(geraete_view, "aufbereiten", aufbereiten)
    monkeypatch.setattr("telco_radar.geraete_config.lade_quellen",
                        lambda root: None)
    monkeypatch.setattr("telco_radar.geraete_config.lade_katalog",
                        lambda root: None)


def _aufbereitet(block):
    return lambda *a, **k: {"zeitreihe": {"bewegung_woche": block}}


def _frisch(eigen):
    return {"error": None, "stichtag": "2026-09-27", "vergleichstag":
            "2026-09-20", "eigen_stichtag": eigen, "zeilen": [],
            "weitere": 0, "geprueft": 3, "ohne_aussage": {}}


def test_fuer_bericht_prueft_die_frische_der_vodafone_messung(
        monkeypatch, tmp_path):
    """Die Wettbewerber sind frisch (27.09.), Vodafone steht seit dem 20.09.
    - der Block darf keine Ruhe melden."""
    _patch(monkeypatch, _aufbereitet(_frisch("2026-09-20")))
    b = gb.fuer_bericht(tmp_path, date(2026, 9, 30), tmp_path)
    assert b["error"] == ("die letzte Vodafone-Messung vom 20.09.2026 ist "
                          "veraltet")
    assert b["im_newsletter"] is True
    # Gegenprobe: drei Tage alt ist noch frisch.
    _patch(monkeypatch, _aufbereitet(_frisch("2026-09-27")))
    assert gb.fuer_bericht(tmp_path, date(2026, 9, 30), tmp_path)["error"] \
        is None


def test_fuer_bericht_wirft_nie_und_nennt_den_grund(monkeypatch, tmp_path,
                                                     caplog):
    def kaputt(*a, **k):
        raise KeyError("sku_id")
    _patch(monkeypatch, kaputt)
    b = gb.fuer_bericht(tmp_path, date(2026, 9, 30), tmp_path)
    assert b["error"] == gb.AUSFALL_AUFBEREITUNG and b["zeilen"] == []
    # Der Ausfall steht in der Mail (Regel 9) - und das Genaue im Protokoll.
    assert b["im_newsletter"] is True
    assert "KeyError" in caplog.text
    json.dumps(b)   # steht so im Berichts-JSON


# ------------------------------------------- Verdrahtung mit echter Zeitreihe

def test_die_zeitreihe_liefert_den_block_aus_ihrer_historie(tmp_path):
    """Ohne Attrappen: `geraete_view` -> `geraete_zeitreihe` -> Block. Die
    Fixture der Zeitreihen-Tests bekommt einen Vergleichstag dazu: o2 war
    am 08.09. um 3 EUR Rate teurer (24 x 3 = 72 EUR), Vodafone und congstar
    unveraendert."""
    from test_geraete_zeitreihe_ansicht import _baue
    from telco_radar.geraete_config import lade_katalog, lade_quellen
    from telco_radar.report import geraete_view

    root, state = _baue(tmp_path)
    historie = state / "geraete_tco_historie.jsonl"
    zeilen = [json.loads(z) for z in historie.read_text().splitlines()]
    neue = []
    for vorlage_tag, rate_neu, bid_teil in (("2026-09-14", 21.0, "--o2--"),
                                            ("2026-09-14", 25.75,
                                             "--vodafone--"),
                                            ("2026-09-15", 22.0,
                                             "--congstar--")):
        z = next(z for z in zeilen if z["datum"] == vorlage_tag
                 and bid_teil in z["id"])
        neue.append(dict(z, datum="2026-09-08", abgerufen_am="2026-09-08",
                         geraet_monatsrate=rate_neu,
                         gesamt=round(1.0 + 24 * 20.0 + 24 * rate_neu, 2)))
    historie.write_text(historie.read_text() + "\n".join(
        json.dumps(z) for z in neue) + "\n")
    g = geraete_view.aufbereiten(state, lade_quellen(root),
                                 lade_katalog(root), heute="2026-09-16")
    b = g["zeitreihe"]["bewegung_woche"]
    assert (b["error"], b["stichtag"], b["vergleichstag"]) == \
        (None, "2026-09-15", "2026-09-08")
    assert b["geprueft"] == 2      # o2 und congstar gegen Vodafone, klein
    [z] = b["zeilen"]
    assert (z["anbieter"], z["delta"], z["fremd_delta"], z["eigen_delta"]) \
        == ("o2", -72.0, -72.0, 0.0)
    assert z["link"] == ("geraete.html?modell=" + z["modell"]
                         + "&band=" + z["band"])
    assert z["band"] in g["zeitreihe"]["daten"]["erlaubt"][z["modell"]]


def test_die_pipeline_schreibt_den_block_ins_berichts_json():
    """Die Verdrahtung in `pipeline.run` - am Quelltext, weil der Lauf selbst
    sammelt. Der Block muss VOR dem ersten Schreiben des JSON stehen."""
    from pathlib import Path
    quelle = (Path(__file__).resolve().parents[1]
              / "src/telco_radar/pipeline.py").read_text(encoding="utf-8")
    setzen = quelle.index('report_json["geraete_bewegung"] = '
                          'geraete_bewegung.fuer_bericht(')
    schreiben = quelle.index("json_path.write_text(")
    assert setzen < schreiben
