"""Gegenprobe: Vergleich, Auswahl und Tagesdatei (``telco_radar.gegenprobe``)."""

from __future__ import annotations

import json

import pytest

from telco_radar import gegenprobe as gp

GETRENNT = (
    "tarif_monatlich",
    "geraet_monatsrate",
    "laufzeit_monate",
    "geraet_zuzahlung",
    "anschlusspreis",
)
GESPEICHERT = {
    "tarif_monatlich": 49.95,
    "geraet_monatsrate": 5.0,
    "laufzeit_monate": 24,
    "geraet_zuzahlung": 1.0,
    "anschlusspreis": 39.95,
    "buendel_monatlich": None,
}


def _gelesen(**anders):
    werte = {k: v for k, v in GESPEICHERT.items() if v is not None}
    werte.update(anders)
    return {k: v for k, v in werte.items() if v is not None}


def test_alles_gleich_ist_bestaetigt():
    status, abw, fehlt, grund = gp.vergleiche(GESPEICHERT, _gelesen(), GETRENNT)
    assert (status, abw, fehlt, grund) == (gp.BESTAETIGT, [], [], None)


@pytest.mark.parametrize(
    ("feld", "gelesen"),
    [
        ("geraet_monatsrate", 9.5),
        ("tarif_monatlich", 44.95),
        ("anschlusspreis", 0.0),
        ("geraet_zuzahlung", 99.0),
        ("laufzeit_monate", 36),
    ],
)
def test_abweichung_nennt_beide_werte(feld, gelesen):
    status, abw, _, _ = gp.vergleiche(
        GESPEICHERT, _gelesen(**{feld: gelesen}), GETRENNT
    )
    assert status == gp.ABWEICHEND
    assert abw == [{"feld": feld, "gespeichert": GESPEICHERT[feld], "gelesen": gelesen}]


def test_ein_cent_unterschied_ist_eine_abweichung():
    status, _, _, _ = gp.vergleiche(
        GESPEICHERT, _gelesen(tarif_monatlich=49.96), GETRENNT
    )
    assert status == gp.ABWEICHEND


def test_rundungsrauschen_unter_einem_cent_ist_gleich():
    status, _, _, _ = gp.vergleiche(
        GESPEICHERT, _gelesen(tarif_monatlich=49.95000001), GETRENNT
    )
    assert status == gp.BESTAETIGT


def test_fehlender_pflichtposten_ist_nicht_pruefbar_mit_namen():
    status, abw, fehlt, grund = gp.vergleiche(
        GESPEICHERT, _gelesen(anschlusspreis=None), GETRENNT
    )
    assert status == gp.NICHT_PRUEFBAR
    assert fehlt == ["anschlusspreis"]
    assert grund == "Auf der Seite nicht ablesbar: Anschlusspreis"


def test_abweichung_geht_vor_fehlendem_posten():
    gelesen = _gelesen(anschlusspreis=None, geraet_monatsrate=9.5)
    status, abw, fehlt, _ = gp.vergleiche(GESPEICHERT, gelesen, GETRENNT)
    assert status == gp.ABWEICHEND
    assert fehlt == ["anschlusspreis"]
    assert [a["feld"] for a in abw] == ["geraet_monatsrate"]


def test_gespeicherte_luecke_wird_nicht_verglichen_und_fehlt_nicht():
    gespeichert = {**GESPEICHERT, "anschlusspreis": None}
    status, _, fehlt, _ = gp.vergleiche(
        gespeichert, _gelesen(anschlusspreis=None), GETRENNT
    )
    assert status == gp.BESTAETIGT
    assert fehlt == []


def test_nichts_gelesen_ist_nicht_bestaetigt():
    leer = dict.fromkeys(GESPEICHERT)
    status, _, _, grund = gp.vergleiche(leer, {}, GETRENNT)
    assert status == gp.NICHT_PRUEFBAR
    assert grund == "Kein Preis auf der Seite gelesen"


def test_nicht_pflichtiger_posten_wird_trotzdem_verglichen():
    status, abw, _, _ = gp.vergleiche(
        GESPEICHERT, _gelesen(anschlusspreis=0.0), ("tarif_monatlich",)
    )
    assert status == gp.ABWEICHEND
    assert abw[0]["feld"] == "anschlusspreis"


def _zeile(bid, datum, gesamt, **werte):
    return {
        "id": bid,
        "datum": datum,
        "abgerufen_am": werte.pop("abgerufen_am", datum),
        "gesamt": gesamt,
        "tarif_monatlich": 10.0,
        **werte,
    }


def _id(anbieter, n):
    return f"buendel--{anbieter}--geraet-{n}--tarif--24m"


def test_auswahl_nimmt_jede_aenderung_groesste_zuerst():
    heute = [
        _zeile(_id("o2", 1), "2026-11-20", 110.0),
        _zeile(_id("o2", 2), "2026-11-20", 300.0),
        _zeile(_id("o2", 3), "2026-11-20", 100.0),
    ]
    vortag = [
        _zeile(_id("o2", 1), "2026-11-19", 100.0),
        _zeile(_id("o2", 2), "2026-11-19", 200.0),
        _zeile(_id("o2", 3), "2026-11-19", 100.0),
    ]
    wahl = gp.auswahl("2026-11-20", heute, vortag, je_anbieter=0)
    assert wahl == [
        (_id("o2", 2), gp.ANLASS_AENDERUNG),
        (_id("o2", 1), gp.ANLASS_AENDERUNG),
    ]


def test_auswahl_erkennt_postenaenderung_bei_gleicher_summe():
    heute = [_zeile(_id("o2", 1), "2026-11-20", 100.0, anschlusspreis=0.0)]
    vortag = [_zeile(_id("o2", 1), "2026-11-19", 100.0, anschlusspreis=39.99)]
    assert gp.auswahl("2026-11-20", heute, vortag, 0) == [
        (_id("o2", 1), gp.ANLASS_AENDERUNG)
    ]


def test_nicht_gemessene_zeile_zaehlt_nicht():
    heute = [_zeile(_id("o2", 1), "2026-11-20", 120.0, abgerufen_am="2026-11-18")]
    vortag = [_zeile(_id("o2", 1), "2026-11-19", 100.0)]
    assert gp.auswahl("2026-11-20", heute, vortag, 5) == []


def test_neues_buendel_ist_keine_aenderung_aber_kandidat():
    heute = [_zeile(_id("o2", 1), "2026-11-20", 120.0)]
    assert gp.auswahl("2026-11-20", heute, [], 5) == [
        (_id("o2", 1), gp.ANLASS_STICHPROBE)
    ]


def _viele(anbieter, n, datum):
    return [_zeile(_id(anbieter, i), datum, 100.0) for i in range(n)]


def test_stichprobe_je_anbieter_fest_je_datum():
    heute = _viele("o2", 30, "2026-11-20") + _viele("telekom", 30, "2026-11-20")
    a = gp.auswahl("2026-11-20", heute, [], 5)
    b = gp.auswahl("2026-11-20", list(reversed(heute)), [], 5)
    assert a == b
    assert sum(gp.anbieter_aus_id(bid) == "o2" for bid, _ in a) == 5
    assert sum(gp.anbieter_aus_id(bid) == "telekom" for bid, _ in a) == 5


def test_stichprobe_wechselt_mit_dem_datum():
    tag1 = gp.auswahl("2026-11-20", _viele("o2", 40, "2026-11-20"), [], 5)
    tag2 = gp.auswahl("2026-11-21", _viele("o2", 40, "2026-11-21"), [], 5)
    assert {b for b, _ in tag1} != {b for b, _ in tag2}


def test_kleiner_anbieter_kommt_ganz():
    wahl = gp.auswahl("2026-11-20", _viele("1-1", 3, "2026-11-20"), [], 5)
    assert len(wahl) == 3


def test_vorgabe_der_stichprobe_ist_fuenf():
    assert gp.STICHPROBE_JE_ANBIETER == 5


@pytest.mark.parametrize(
    ("bid", "anbieter"),
    [
        ("buendel--o2--x--t--24m", "o2"),
        ("buendel--saturn-mediamarkt-o2-netz--x--t--24m", "saturn-mediamarkt-o2-netz"),
        ("unfug", ""),
    ],
)
def test_anbieter_aus_id(bid, anbieter):
    assert gp.anbieter_aus_id(bid) == anbieter


def _ergebnis(**anders):
    werte = {
        "datum": "2026-11-20",
        "buendel_id": _id("o2", 1),
        "anbieter": "o2",
        "status": gp.BESTAETIGT,
        "anlass": gp.ANLASS_STICHPROBE,
    }
    werte.update(anders)
    return gp.Ergebnis(**werte)


def test_tagesdatei_hin_und_zurueck(tmp_path):
    pfad = gp.tagesdatei(tmp_path, "2026-11-20")
    e = [
        _ergebnis(),
        _ergebnis(
            buendel_id=_id("o2", 2),
            status=gp.ABWEICHEND,
            abweichungen=[
                {"feld": "anschlusspreis", "gespeichert": 39.99, "gelesen": 0}
            ],
        ),
    ]
    gp.schreibe_tag(pfad, e)
    assert pfad == tmp_path / "data/state/gegenprobe/2026-11-20.jsonl"
    assert gp.lies_tag(pfad) == e
    assert gp.lies_alle(pfad.parent)[(_id("o2", 2), "2026-11-20")].status == (
        gp.ABWEICHEND
    )


def test_ohne_tagesdatei_ist_die_liste_leer(tmp_path):
    assert gp.lies_tag(tmp_path / "fehlt.jsonl") == []
    assert gp.lies_alle(tmp_path / "fehlt") == {}


def test_kaputte_zeile_nennt_ihre_nummer(tmp_path):
    pfad = tmp_path / "2026-11-20.jsonl"
    pfad.write_text(gp.als_zeile(_ergebnis()) + "\n{kaputt\n", encoding="utf-8")
    with pytest.raises(gp.GegenprobeFehler, match="Zeile 2"):
        gp.lies_tag(pfad)


def test_unbekannter_status_wird_abgelehnt(tmp_path):
    pfad = tmp_path / "2026-11-20.jsonl"
    zeile = json.loads(gp.als_zeile(_ergebnis()))
    zeile["status"] = "ok"
    pfad.write_text(json.dumps(zeile) + "\n", encoding="utf-8")
    with pytest.raises(gp.GegenprobeFehler, match="unbekannter Status"):
        gp.lies_tag(pfad)


def test_nicht_pruefbar_braucht_einen_grund():
    with pytest.raises(ValueError, match="ohne Grund"):
        _ergebnis(status=gp.NICHT_PRUEFBAR)


def test_abweichend_braucht_einen_posten():
    with pytest.raises(ValueError, match="abweichend"):
        _ergebnis(status=gp.ABWEICHEND)


def test_bildname_ist_stabil_und_haengt_am_tag():
    a = gp.kennung(_id("o2", 1), "2026-11-20")
    assert a == gp.kennung(_id("o2", 1), "2026-11-20")
    assert a != gp.kennung(_id("o2", 1), "2026-11-21")
    assert len(a) == 16


def test_bild_liegt_im_release_des_tages():
    assert gp.bild_url("2026-11-20", "abc.webp") == (
        "https://github.com/Antonio20045/telco-radar/releases/download/"
        "gegenprobe-2026-11-20/abc.webp"
    )
