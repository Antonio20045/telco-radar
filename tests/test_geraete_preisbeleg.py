"""Beleg je Preis (``report.geraete_preisbeleg``): Rechenweg, Gegenprobe, Lücken.

Der Rechenweg sind die Summanden aus ``kosten_ueber``; ein Leser, der die Terme
nachrechnet, kommt auf die Zahl der Zeile. Das gilt für jedes Bündel des
Schnappschusses vom 03.10.2026 (Gegenprobe gegen echte Daten).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from telco_radar import gegenprobe as gp
from telco_radar.analyze.geraete_pruefstatus import buendel_aus_satz
from telco_radar.report import geraete_preisbeleg as pb
from telco_radar.report.geraete_rechnung import felder, zum_lesen
from telco_radar.tarif_model import Preisphase
from telco_radar.tco_model import Buendel, kosten_ueber

SCHNAPPSCHUSS = Path(__file__).parent / "fixtures" / "bestand" / "2026-10-03" / "state"
ID = "buendel--vodafone--google-pixel-11-pro-xl-512gb-schwarz--mobil-xs--24m"


def _buendel(**anders) -> Buendel:
    werte = {
        "sku_id": "google-pixel-11-pro-xl-512gb-schwarz",
        "anbieter": "Vodafone",
        "tarif_name": "Mobil XS",
        "tarif_monatlich": 19.95,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 57.0,
        "laufzeit_monate": 24,
        "anschlusspreis": 0.0,
    }
    werte.update(anders)
    return Buendel(**werte)


FORMEN = {
    "24 Raten": _buendel(),
    "36 Raten": _buendel(laufzeit_monate=36, geraet_monatsrate=38.0),
    "12 Raten": _buendel(laufzeit_monate=12, geraet_monatsrate=114.0),
    "Phasen": _buendel(
        tarif_phasen=[Preisphase(1, 12, 21.95), Preisphase(13, 24, 24.95)],
        tarif_monatlich=21.95,
    ),
    "1&1": _buendel(
        anbieter="1&1",
        tarif_name="1&1 All-Net-Flat S",
        tarif_monatlich=None,
        geraet_monatsrate=None,
        geraet_zuzahlung=0.0,
        buendel_monatlich=57.99,
        anschlusspreis=39.9,
    ),
    "Tarifwelt": _buendel(
        anbieter="Saturn/MediaMarkt · o2-Netz",
        geraet_monatsrate=0.0,
        geraet_zuzahlung=129.99,
        anschlusspreis=39.99,
    ),
}


@pytest.mark.parametrize("form", list(FORMEN))
def test_terme_ergeben_die_zahl_der_zeile(form):
    kosten = kosten_ueber(FORMEN[form])
    schritte = felder(kosten)["rechnung_einzeln"]
    weg = pb.rechenweg(schritte, kosten.gesamt)
    assert kosten.gesamt is not None
    assert pb.summe(schritte) == kosten.gesamt
    assert weg["text"].endswith(f"= {pb.euro(kosten.gesamt)}")
    assert weg["text"].count(" + ") == len(schritte) - 1


def test_rechenweg_wie_ihn_ein_kunde_liest():
    kosten = kosten_ueber(FORMEN["24 Raten"])
    weg = pb.rechenweg(felder(kosten)["rechnung_einzeln"], kosten.gesamt)
    assert weg["text"].startswith(
        "24 × 57,00 € Gerät + 24 × 19,95 € Tarif + 1,00 € Anzahlung"
    )
    assert weg["text"].endswith(f" = {pb.euro(kosten.gesamt)}")


def test_jedes_buendel_des_schnappschusses_rechnet_auf():
    bestand = json.loads((SCHNAPPSCHUSS / "geraete_tco.json").read_text("utf-8"))
    geprueft = 0
    for satz in bestand["buendel"]:
        try:
            kosten = kosten_ueber(buendel_aus_satz(satz))
        except (TypeError, ValueError):
            continue
        if kosten.gesamt is None:
            continue
        assert pb.summe(zum_lesen(kosten.rechnung)) == kosten.gesamt, satz["id"]
        geprueft += 1
    assert geprueft > 1000


def test_ohne_zahl_kein_rechenweg():
    assert pb.rechenweg([{"anzahl": 24, "betrag": 1.0, "wort": "Tarif"}], None) is None
    assert pb.rechenweg([], 10.0) is None


def _ergebnis(**anders) -> gp.Ergebnis:
    werte = {
        "datum": "2026-11-20",
        "buendel_id": ID,
        "anbieter": "Vodafone",
        "status": gp.BESTAETIGT,
        "anlass": gp.ANLASS_STICHPROBE,
        "geprueft_um": "2026-11-20T17:34:46+00:00",
        "gesamt_gespeichert": 1846.78,
        "gespeichert": {"geraet_monatsrate": 57.0, "anschlusspreis": 0.0},
    }
    werte.update(anders)
    return gp.Ergebnis(**werte)


def test_gegenprobe_gehoert_nur_zum_gleichen_preis():
    proben = pb.Gegenproben([_ergebnis()])
    assert proben.zum_preis(ID, 1846.78).status == gp.BESTAETIGT
    assert proben.zum_preis(ID, 1900.0) is None
    assert proben.zum_preis(ID, None) is None


def test_juengste_gegenprobe_des_preises_zaehlt():
    alt = _ergebnis(datum="2026-11-19", status=gp.NICHT_PRUEFBAR, grund="x")
    proben = pb.Gegenproben([_ergebnis(), alt])
    assert proben.zum_preis(ID, 1846.78).datum == "2026-11-20"
    assert proben.am(ID, "2026-11-19").status == gp.NICHT_PRUEFBAR


def test_andere_farbe_gleicher_preis_ist_dasselbe_angebot():
    proben = pb.Gegenproben([_ergebnis()])
    weiss = ID.replace("-schwarz--", "-weiss--")
    assert proben.zum_preis(weiss, 1846.78) is not None
    assert proben.zum_preis(weiss, 1800.0) is None


@pytest.mark.parametrize(
    ("bid", "angebot"),
    [
        (ID, "buendel--vodafone--google-pixel-11-pro-xl-512gb--mobil-xs--24m"),
        (
            "buendel--o2--apple-iphone-14-128gb-schwarz-refurbished--t--24m",
            "buendel--o2--apple-iphone-14-128gb-refurbished--t--24m",
        ),
        ("buendel--o2--ohne-speicher--t--24m", "buendel--o2--ohne-speicher--t--24m"),
        ("kaputt", "kaputt"),
    ],
)
def test_angebot_ohne_farbe_mit_zustand(bid, angebot):
    assert pb.angebot(bid) == angebot


def test_erneuert_ist_nicht_dasselbe_angebot_wie_neu():
    neu = "buendel--o2--apple-iphone-14-128gb-schwarz--t--24m"
    erneuert = "buendel--o2--apple-iphone-14-128gb-schwarz-refurbished--t--24m"
    proben = pb.Gegenproben([_ergebnis(buendel_id=erneuert, gesamt_gespeichert=1.0)])
    assert proben.zum_preis(neu, 1.0) is None


def test_andere_farbe_und_anderer_tag_stehen_am_beleg():
    weiss = ID.replace("-schwarz--", "-weiss--")
    e = _ergebnis(datum="2026-11-19")
    anzeige = pb.gegenprobe_anzeige(e, weiss, "2026-11-20")
    assert anzeige["hinweise"] == [
        "andere Farbe (schwarz)",
        "Prüfung vom 19.11.2026, Preis gelesen am 20.11.2026",
    ]
    assert pb.gegenprobe_anzeige(e, ID, "2026-11-19")["hinweise"] == []


def test_teilweise_bestaetigt_heisst_so():
    e = _ergebnis(status=gp.TEILWEISE, grund="Bestätigt: Tarif; nicht gelesen: x")
    anzeige = pb.gegenprobe_anzeige(e)
    assert anzeige["wort"] == "teilweise bestätigt"
    assert anzeige["grund"].startswith("Bestätigt: ")


def test_luecke_im_bestand_steht_als_fehlend():
    """Eine gefüllte Lücke ist seit 21.11.2026 eine Erfassungslücke, keine
    Abweichung; die Seite nennt sie weiter mit beiden Werten."""
    e = _ergebnis(
        status=gp.ABWEICHEND,
        abweichungen=[{"feld": "anschlusspreis", "gespeichert": None, "gelesen": 39.9}],
    )
    anzeige = pb.gegenprobe_anzeige(e)
    assert anzeige["luecken"] == ["Anschlusspreis: gespeichert fehlt, Seite 39,90 €"]
    assert (anzeige["status"], anzeige["abweichungen"]) == (gp.ERFASSUNGSLUECKE, [])


def test_abweichung_nennt_beide_werte_auf_der_seite():
    e = _ergebnis(
        status=gp.ABWEICHEND,
        abweichungen=[
            {"feld": "geraet_monatsrate", "gespeichert": 5.0, "gelesen": 9.5}
        ],
    )
    anzeige = pb.gegenprobe_anzeige(e)
    assert anzeige["wort"] == "abweichend"
    assert anzeige["abweichungen"] == ["Geräterate: gespeichert 5,00 €, Seite 9,50 €"]


def test_uhrzeit_steht_in_berliner_zeit():
    assert pb.gegenprobe_anzeige(_ergebnis())["uhrzeit"] == "18:34 Uhr"
    assert pb.uhrzeit("2026-11-20T17:34:46") == ""
    assert pb.uhrzeit(None) == ""


def test_nicht_gelesene_null_posten_werden_nicht_genannt():
    e = _ergebnis(
        nicht_gelesen=["geraet_monatsrate", "laufzeit_monate", "anschlusspreis"],
        gespeichert={"geraet_monatsrate": 0.0, "anschlusspreis": 39.9},
    )
    assert pb.gegenprobe_anzeige(e)["nicht_gelesen"] == ["Anschlusspreis"]


def test_beleg_ohne_bild_und_gegenprobe_nennt_die_luecken():
    b = pb.beleg(
        quelle_url="https://www.vodafone.de/privat/handys/x.html",
        abgerufen_am="2026-11-20",
        schritte=None,
        gesamt=None,
        bild=None,
        gegenprobe=None,
    )
    assert b["quelle"] == "vodafone.de" and b["gelesen_am"] == "20.11.2026"
    assert b["rechenweg"] is None and b["rechenweg_fehlt"] == pb.SATZ_OHNE_RECHENWEG
    assert b["bild"] is None and b["bild_fehlt"] == pb.SATZ_OHNE_BILD
    assert b["gegenprobe"] is None
    assert b["gegenprobe_fehlt"] == pb.SATZ_OHNE_GEGENPROBE


def test_ohne_eigenes_bild_zeigt_der_beleg_das_bild_der_gegenprobe():
    e = _ergebnis(
        bild="https://github.com/x/releases/download/gegenprobe-2026-11-20/a.webp"
    )
    b = pb.beleg(
        quelle_url="",
        abgerufen_am="",
        schritte=None,
        gesamt=None,
        bild=None,
        gegenprobe=e,
    )
    assert b["bild"]["url"].endswith("/a.webp")
    assert (b["bild"]["art"], b["bild"]["datum"]) == ("Gegenprobe", "20.11.2026")


def test_bild_der_messung_geht_vor():
    e = _ergebnis(bild="https://x/gegenprobe.webp")
    messung = {"url": "https://x/messung.webp", "datum": "2026-11-20", "art": "Messung"}
    b = pb.beleg(
        quelle_url="",
        abgerufen_am="",
        schritte=None,
        gesamt=None,
        bild=messung,
        gegenprobe=e,
    )
    assert b["bild"]["url"] == "https://x/messung.webp"


def test_kaputte_tagesdatei_ist_ein_ausfall(tmp_path):
    (tmp_path / "gegenprobe").mkdir()
    (tmp_path / "gegenprobe" / "2026-11-20.jsonl").write_text("{kaputt\n", "utf-8")

    class Umgebung:
        """Mimt die Jinja-Umgebung, die `installiere` mit `env.globals` füllt."""

        def __init__(self) -> None:
            self.globals: dict = {}

    env = Umgebung()
    ausfaelle = pb.installiere(env, tmp_path, {"fuer": lambda k: None})
    assert [a.teil for a in ausfaelle] == [pb.TEIL]
    assert env.globals["preisbeleg"]({"gesamt": 1.0})["gegenprobe"] is None


def _abweichend(**anders):
    return _ergebnis(
        status=gp.ABWEICHEND,
        abweichungen=[
            {"feld": "geraet_monatsrate", "gespeichert": 5.0, "gelesen": 9.5}
        ],
        **anders,
    )


def test_messung_und_gegenprobe_stehen_mit_zeit_nebeneinander():
    e = _abweichend(gemessen_um="2026-11-20T02:48+00:00")
    anzeige = pb.gegenprobe_anzeige(e)
    assert anzeige["messung"] == "20.11.2026, 03:48 Uhr"
    assert anzeige["uhrzeit"] == "18:34 Uhr"


def test_grosser_zeitabstand_wird_an_der_abweichung_genannt():
    weit = pb.gegenprobe_anzeige(_abweichend(gemessen_um="2026-11-20T02:48+00:00"))
    assert pb.SATZ_ZEIT_ABSTAND in weit["hinweise"]
    nah = pb.gegenprobe_anzeige(_abweichend(gemessen_um="2026-11-20T16:00+00:00"))
    assert pb.SATZ_ZEIT_ABSTAND not in nah["hinweise"]
    assert nah["wort"] == "abweichend"


def test_unbekannte_messzeit_wird_an_der_abweichung_genannt():
    anzeige = pb.gegenprobe_anzeige(_abweichend())
    assert pb.SATZ_ZEIT_UNBEKANNT in anzeige["hinweise"]
    assert pb.gegenprobe_anzeige(_ergebnis())["hinweise"] == []
