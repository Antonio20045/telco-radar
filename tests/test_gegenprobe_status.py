"""Gegenprobe: geschärfte Statuswerte und eine Tagesdatei, die ergänzt wird.

Lauf 21.11.2026 (``data/state/gegenprobe/2026-11-21.jsonl``): 65 o2-Zeilen hießen
„abweichend“, obwohl der Bestand den Anschlusspreis nur als Lücke führte (gespeichert
None, Seite 39,99 € oder 0,00 €); 420 Zeilen hießen „nicht prüfbar“, obwohl die Seite
nur aus Zeitmangel nie geöffnet wurde. „abweichend“ zählt seitdem nur echte
Wertwidersprüche, eine gefüllte Lücke heißt ``erfassungsluecke``, ein nie geöffnetes
Bündel ``nicht_gegengeprueft``. Die Statuswerte stehen hier als Text, damit die Tests
gegen den alten Stand fachlich rot sind und nicht an einem fehlenden Namen scheitern.
"""

from __future__ import annotations

import json

import pytest

from telco_radar import gegenprobe as gp
from telco_radar import versandkosten
from telco_radar.report import geraete_preisbeleg as pb

ID = "buendel--o2--apple-iphone-14-128gb-schwarz--o2-mobile-s-mit-15-gb-24-mon--24m"
GESPEICHERT = {
    "tarif_monatlich": 29.99,
    "geraet_monatsrate": 25.0,
    "laufzeit_monate": 24,
    "geraet_zuzahlung": 1.0,
    "anschlusspreis": None,
}
GELESEN = {**{k: v for k, v in GESPEICHERT.items() if v is not None}}


def _zeile(**anders) -> dict:
    werte = {
        "datum": "2026-11-21",
        "buendel_id": ID,
        "anbieter": "o2",
        "status": "bestaetigt",
        "anlass": "preisaenderung",
        "gesamt_gespeichert": 1247.74,
    }
    werte.update(anders)
    return werte


def test_luecke_im_bestand_ist_eine_erfassungsluecke_keine_abweichung():
    status, abw, _, _ = gp.vergleiche(GESPEICHERT, {**GELESEN, "anschlusspreis": 39.99})
    assert status == "erfassungsluecke"
    assert abw == []
    assert gp.luecken_von(GESPEICHERT, {**GELESEN, "anschlusspreis": 39.99}) == [
        {"feld": "anschlusspreis", "gespeichert": None, "gelesen": 39.99}
    ]


def test_echter_widerspruch_bleibt_abweichend_auch_neben_einer_luecke():
    gelesen = {**GELESEN, "anschlusspreis": 0.0, "geraet_monatsrate": 27.0}
    status, abw, _, _ = gp.vergleiche(GESPEICHERT, gelesen)
    assert status == "abweichend"
    assert [a["feld"] for a in abw] == ["geraet_monatsrate"]
    assert [a["feld"] for a in gp.luecken_von(GESPEICHERT, gelesen)] == [
        "anschlusspreis"
    ]


def test_gleiche_werte_ohne_luecke_bleiben_bestaetigt():
    gespeichert = {**GESPEICHERT, "anschlusspreis": 39.99}
    gelesen = {**GELESEN, "anschlusspreis": 39.99}
    assert gp.vergleiche(gespeichert, gelesen)[0] == gp.BESTAETIGT
    assert gp.luecken_von(gespeichert, gelesen) == []


def test_erfassungsluecke_braucht_den_gelesenen_posten():
    with pytest.raises(ValueError, match="Lücke"):
        gp.Ergebnis(**_zeile(status=gp.ERFASSUNGSLUECKE))
    e = gp.Ergebnis(
        **_zeile(
            status=gp.ERFASSUNGSLUECKE,
            luecken=[{"feld": "anschlusspreis", "gespeichert": None, "gelesen": 0.0}],
        )
    )
    assert e.status == "erfassungsluecke"


def test_nicht_gegengeprueft_braucht_einen_grund():
    with pytest.raises(ValueError, match="Grund"):
        gp.Ergebnis(**_zeile(status=gp.NICHT_GEGENGEPRUEFT))


def test_versand_wird_verglichen_wenn_die_seite_ihn_zeigt():
    gespeichert = {**GESPEICHERT, "anschlusspreis": 0.0, "versand": 6.99}
    gleich = {**GELESEN, "versand": 6.99}
    anders = {**GELESEN, "versand": 9.99}
    assert gp.vergleiche(gespeichert, gleich)[0] == gp.BESTAETIGT
    status, abw, _, _ = gp.vergleiche(gespeichert, anders)
    assert status == gp.ABWEICHEND
    assert abw == [{"feld": "versand", "gespeichert": 6.99, "gelesen": 9.99}]
    assert gp.vergleiche(gespeichert, GELESEN)[0] == gp.BESTAETIGT


def test_gespeicherter_versand_kommt_aus_der_versandtabelle(monkeypatch):
    tabelle = {"o2": versandkosten.Versandangabe("o2", 6.99)}
    monkeypatch.setattr(versandkosten, "_TABELLE", tabelle)
    werte = gp.gespeicherte_werte({"anbieter": "o2", **GESPEICHERT})
    assert werte["versand"] == 6.99
    assert gp.gespeicherte_werte({"anbieter": "Unbekannt"})["versand"] is None


def test_alte_zeile_zeitbudget_heisst_nicht_gegengeprueft(tmp_path):
    pfad = tmp_path / "2026-11-21.jsonl"
    alt = _zeile(status="nicht_pruefbar", grund=gp.GRUND_ZEITBUDGET)
    pfad.write_text(json.dumps(alt) + "\n", encoding="utf-8")
    (e,) = gp.lies_tag(pfad)
    assert (e.status, e.grund) == ("nicht_gegengeprueft", gp.GRUND_ZEITBUDGET)


def test_alte_zeile_luecke_heisst_erfassungsluecke(tmp_path):
    pfad = tmp_path / "2026-11-21.jsonl"
    luecke = {"feld": "anschlusspreis", "gespeichert": None, "gelesen": 39.99}
    echt = {"feld": "geraet_monatsrate", "gespeichert": 25.0, "gelesen": 27.0}
    zeilen = [
        _zeile(status="abweichend", abweichungen=[luecke]),
        _zeile(buendel_id=ID + "x", status="abweichend", abweichungen=[luecke, echt]),
    ]
    pfad.write_text("".join(json.dumps(z) + "\n" for z in zeilen), encoding="utf-8")
    nur_luecke, beides = gp.lies_tag(pfad)
    assert nur_luecke.status == "erfassungsluecke"
    assert (nur_luecke.abweichungen, nur_luecke.luecken) == ([], [luecke])
    assert beides.status == "abweichend"
    assert (beides.abweichungen, beides.luecken) == ([echt], [luecke])


def test_nie_geoeffnet_verdeckt_keine_aeltere_gegenprobe_desselben_preises(tmp_path):
    tage = {
        "2026-11-19": _zeile(datum="2026-11-19"),
        "2026-11-21": _zeile(status="nicht_pruefbar", grund=gp.GRUND_ZEITBUDGET),
    }
    for datum, zeile in tage.items():
        (tmp_path / f"{datum}.jsonl").write_text(json.dumps(zeile) + "\n", "utf-8")
    probe = pb.Gegenproben(gp.lies_alle(tmp_path).values()).zum_preis(ID, 1247.74)
    assert probe is not None
    assert (probe.datum, probe.status) == ("2026-11-19", "bestaetigt")


def test_luecke_ohne_gesamtkosten_findet_ihre_gegenprobe():
    luecke = gp.Ergebnis(
        **_zeile(
            status=gp.ERFASSUNGSLUECKE,
            gesamt_gespeichert=None,
            luecken=[{"feld": "anschlusspreis", "gespeichert": None, "gelesen": 0.0}],
        )
    )
    anderes = gp.Ergebnis(**_zeile(buendel_id=ID + "x", gesamt_gespeichert=None))
    proben = pb.Gegenproben([luecke, anderes])
    assert proben.zum_preis(ID, None) is luecke
    assert proben.zum_preis(ID + "y", None) is None


def test_seite_nennt_die_gefuellte_luecke():
    e = gp.Ergebnis(
        **_zeile(
            status=gp.ERFASSUNGSLUECKE,
            luecken=[{"feld": "anschlusspreis", "gespeichert": None, "gelesen": 39.99}],
        )
    )
    anzeige = pb.gegenprobe_anzeige(e)
    assert anzeige["wort"] == "Erfassungslücke"
    assert anzeige["luecken"] == ["Anschlusspreis: gespeichert fehlt, Seite 39,99 €"]
    assert anzeige["abweichungen"] == []


def test_zweiter_lauf_ergaenzt_und_ueberschreibt_keine_pruefung(tmp_path):
    pfad = tmp_path / "2026-11-21.jsonl"
    geprueft = gp.Ergebnis(**_zeile())
    offen = gp.Ergebnis(
        **_zeile(buendel_id=ID + "b", status="nicht_gegengeprueft", grund="Zeitbudget")
    )
    gp.ergaenze_tag(pfad, [geprueft, offen])
    spaeter = [
        gp.Ergebnis(**_zeile(status="nicht_gegengeprueft", grund="Zeitbudget")),
        gp.Ergebnis(**_zeile(buendel_id=ID + "b", geprueft_um="2026-11-21T09:00")),
        gp.Ergebnis(**_zeile(buendel_id=ID + "c")),
    ]
    gp.ergaenze_tag(pfad, spaeter)
    status = {e.buendel_id: e.status for e in gp.lies_tag(pfad)}
    assert status == {ID: "bestaetigt", ID + "b": "bestaetigt", ID + "c": "bestaetigt"}
