"""``scripts/gegenprobe.py``: eine Prüfung ohne Browser, Historie, Zeitbudget."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_beleg_skripte import lade_skript

from telco_radar import gegenprobe as gp
from telco_radar.collect.geraete.gegenprobe_browser import (
    Gesperrt,
    Lesung,
    NichtPruefbar,
)
from telco_radar.collect.geraete.gegenprobe_sicht import VODAFONE_TRENNER

WURZEL = Path(__file__).resolve().parent.parent
SKRIPT = lade_skript("gegenprobe")

SATZ = {
    "id": "buendel--vodafone--google-pixel-11-pro-xl-512gb-schwarz--mobil-xs--24m",
    "sku_id": "google-pixel-11-pro-xl-512gb-schwarz",
    "anbieter": "Vodafone",
    "tarif_name": "Mobil XS",
    "tarif_monatlich": 19.95,
    "geraet_zuzahlung": 1.0,
    "geraet_monatsrate": 57.0,
    "laufzeit_monate": 24,
    "anschlusspreis": 0.0,
    "quelle_url": "https://www.vodafone.de/privat/handys/google-pixel-11-pro-xl.html",
    "abgerufen_am": "2026-11-20",
}


def _text(rate="57", angebot="76,95", tarif="Mobil XS"):
    return (
        f"Gewählt: 24 Raten\nPreisübersicht\nEinmal\n1 €\nPro Monat\n{rate} €\n"
        f"{VODAFONE_TRENNER}{tarif} mit 23 GB\nPreisübersicht\nEinmal\n1 €\n"
        f"Pro Monat\nStandardpreis 90,00 € – Angebotspreis {angebot} €\n"
        "Standard-Versand 9,98 €\nKein Anschlusspreis.\n"
    )


def _lesen(text=None, fehler=None):
    def lesen(schluessel, satz):
        if fehler is not None:
            raise fehler
        return Lesung(text=text or _text(), seite=satz["quelle_url"], bild=b"RIFF")

    return lesen


def _pruefe(lesen, satz=SATZ):
    return SKRIPT.pruefe(lesen, dict(satz), gp.ANLASS_STICHPROBE, "2026-11-20")


def test_gleiche_seite_ist_bestaetigt_mit_derselben_summe():
    ergebnis, lesung = _pruefe(_lesen())
    assert ergebnis.status == gp.BESTAETIGT
    assert ergebnis.gesamt_gelesen == ergebnis.gesamt_gespeichert
    assert ergebnis.gesamt_gespeichert == pytest.approx(1 + 24 * 19.95 + 24 * 57)
    assert lesung.bild == b"RIFF"
    assert ergebnis.gelesen["roh"]["Angebotspreis (Rate + Tarif)"] == "76,95 €"


def test_abweichende_rate_nennt_beide_werte_und_summen():
    ergebnis, _ = _pruefe(_lesen(_text(rate="60", angebot="79,95")))
    assert ergebnis.status == gp.ABWEICHEND
    assert {a["feld"] for a in ergebnis.abweichungen} == {"geraet_monatsrate"}
    assert ergebnis.gesamt_gelesen == pytest.approx(1 + 24 * 19.95 + 24 * 60)
    assert ergebnis.gesamt_gelesen != ergebnis.gesamt_gespeichert


def test_anderer_tarif_auf_der_seite_ist_keine_abweichung():
    ergebnis, _ = _pruefe(_lesen(_text(tarif="Mobil XL", angebot="99,00")))
    assert ergebnis.status == gp.NICHT_PRUEFBAR
    assert ergebnis.grund == "Die Seite zeigt einen anderen Tarif: Mobil XL"


def test_sperre_ist_nicht_pruefbar_und_wird_genannt():
    ergebnis, lesung = _pruefe(_lesen(fehler=Gesperrt("HTTP 403")))
    assert ergebnis.status == gp.NICHT_PRUEFBAR
    assert ergebnis.grund == f"{gp.GRUND_GESPERRT} (HTTP 403)"
    assert lesung is None


def test_abgebrochener_kundenweg_nennt_seinen_grund():
    ergebnis, _ = _pruefe(_lesen(fehler=NichtPruefbar("Auswahl gesperrt: 1 TB")))
    assert (ergebnis.status, ergebnis.grund) == (
        gp.NICHT_PRUEFBAR,
        "Auswahl gesperrt: 1 TB",
    )


def test_anbieter_ohne_leser():
    satz = {**SATZ, "id": "buendel--fraenk--x--t--24m", "anbieter": "fraenk"}
    ergebnis, _ = _pruefe(_lesen(), satz)
    assert ergebnis.grund == gp.GRUND_KEIN_LESER


def test_ergebnis_steht_als_zeile_in_der_tagesdatei(tmp_path):
    ergebnis, _ = _pruefe(_lesen())
    pfad = gp.tagesdatei(tmp_path, "2026-11-20")
    gp.schreibe_tag(pfad, [ergebnis])
    assert gp.lies_tag(pfad) == [ergebnis]


@pytest.mark.parametrize(
    ("gespeichert", "gelesen", "anders"),
    [
        ("MagentaMobil M", "MagentaMobil M", False),
        ("O2 Mobile S mit 15 GB+ (24 Mon.)", "O2 Mobile S", False),
        ("1&1 All-Net-Flat S", "1&1 All-Net-Flat L", True),
        ("Mobil XS", None, False),
        ("MagentaMobil M", "MagentaMobil L", True),
    ],
)
def test_anderer_tarif(gespeichert, gelesen, anders):
    assert SKRIPT.anderer_tarif(gespeichert, gelesen) is anders


def _tagesdatei(ordner, tag, *zeilen):
    ordner.mkdir(exist_ok=True)
    (ordner / f"{tag}.jsonl").write_text(
        "".join(json.dumps(z) + "\n" for z in zeilen), encoding="utf-8"
    )


def _messung(bid, tag, rate):
    return {"id": bid, "datum": tag, "abgerufen_am": tag, "geraet_monatsrate": rate}


def test_historie_nimmt_je_buendel_die_letzte_messung_davor(tmp_path):
    ordner = tmp_path / "geraete_tco_historie"
    _tagesdatei(ordner, "2026-11-17", _messung("a", "2026-11-17", 1.0))
    _tagesdatei(ordner, "2026-11-19", _messung("b", "2026-11-19", 2.0))
    _tagesdatei(ordner, "2026-11-20", _messung("a", "2026-11-20", 3.0))
    heute, vorher, datum = SKRIPT.lies_historie(ordner, "2026-11-20")
    assert [z["id"] for z in heute] == ["a"]
    assert {z["id"]: z["datum"] for z in vorher} == {
        "a": "2026-11-17",
        "b": "2026-11-19",
    }
    assert datum == "2026-11-19"
    assert gp.auswahl("2026-11-20", heute, vorher, 0) == [("a", gp.ANLASS_AENDERUNG)]


def test_historie_ohne_vortag(tmp_path):
    ordner = tmp_path / "geraete_tco_historie"
    _tagesdatei(ordner, "2026-11-20", _messung("a", "2026-11-20", 1.0))
    assert SKRIPT.lies_historie(ordner, "2026-11-20")[1:] == ([], None)


def test_ohne_lauf_steht_der_grund_in_der_zeile():
    e = SKRIPT._ohne_lauf(SATZ, gp.ANLASS_AENDERUNG, "2026-11-20", gp.GRUND_ZEITBUDGET)
    assert (e.status, e.grund, e.anlass) == (
        gp.NICHT_PRUEFBAR,
        gp.GRUND_ZEITBUDGET,
        gp.ANLASS_AENDERUNG,
    )
    assert e.gespeichert["geraet_monatsrate"] == 57.0


def test_kennungen_aus_den_quellen():
    ua = SKRIPT.kennungen(WURZEL)
    assert ua["Telekom"].startswith("TelcoRadar/")
    assert "Vodafone" not in ua


def test_messzeit_steht_in_der_zeile():
    lauf = "2026-11-20T02:48+00:00"
    ergebnis, _ = SKRIPT.pruefe(
        _lesen(), dict(SATZ), gp.ANLASS_STICHPROBE, "2026-11-20", lauf
    )
    assert ergebnis.gemessen_um == lauf
