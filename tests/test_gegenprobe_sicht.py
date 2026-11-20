"""Leser der Gegenprobe gegen aufgenommene Preisbereiche (``gegenprobe_sicht``).

Die Fixtures unter ``tests/fixtures/gegenprobe/`` sind die sichtbaren Preisbereiche
der Anbieterseiten vom 20.11.2026, aufgenommen mit ``scripts/gegenprobe.py
--aufnehmen`` (nur sichtbare Knoten, ohne Attribute). Gelesen wird wie im Lauf: der
Browser rendert sie und liefert ``innerText``; kein Netz.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from telco_radar import gegenprobe as gp
from telco_radar.collect.geraete import gegenprobe_sicht as sicht

FIXTURES = Path(__file__).parent / "fixtures" / "gegenprobe"

ERWARTET = {
    "telekom": (
        {
            "tarif_monatlich": 49.95,
            "geraet_monatsrate": 9.5,
            "laufzeit_monate": 24,
            "geraet_zuzahlung": 1.0,
            "anschlusspreis": 39.95,
        },
        "MagentaMobil M",
    ),
    "o2": (
        {
            "tarif_monatlich": 19.99,
            "geraet_monatsrate": 18.5,
            "laufzeit_monate": 24,
            "geraet_zuzahlung": 1.0,
            "anschlusspreis": 0.0,
        },
        None,
    ),
    "congstar": (
        {
            "tarif_monatlich": 15.0,
            "geraet_monatsrate": 42.0,
            "laufzeit_monate": 36,
            "geraet_zuzahlung": 49.0,
            "anschlusspreis": 0.0,
        },
        None,
    ),
    "vodafone": (
        {
            "tarif_monatlich": 19.95,
            "geraet_monatsrate": 57.0,
            "laufzeit_monate": 24,
            "geraet_zuzahlung": 1.0,
            "anschlusspreis": 0.0,
        },
        "Mobil XS",
    ),
    "1-1": ({"buendel_monatlich": 57.99, "laufzeit_monate": 24}, "1&1 All-Net-Flat S"),
    "saturn-mediamarkt-telekom-netz": (
        {"tarif_monatlich": 94.95, "geraet_zuzahlung": 1.0, "anschlusspreis": 39.99},
        None,
    ),
}
"""Was die Seite am 20.11.2026 zeigte (abgelesen im Bild des Laufs)."""

GESPEICHERT = {
    "telekom": {
        "tarif_monatlich": 49.95,
        "geraet_monatsrate": 5.0,
        "laufzeit_monate": 24,
        "geraet_zuzahlung": 1.0,
        "anschlusspreis": 39.95,
    },
    "o2": {
        "tarif_monatlich": 19.99,
        "geraet_monatsrate": 18.5,
        "laufzeit_monate": 24,
        "geraet_zuzahlung": 1.0,
        "anschlusspreis": 39.99,
    },
}
"""Bestand vom 20.11.2026 zu den zwei Seiten, die abwichen (echte Befunde)."""

STATUS = {
    "telekom": gp.ABWEICHEND,
    "o2": gp.ABWEICHEND,
    "congstar": gp.BESTAETIGT,
    "vodafone": gp.BESTAETIGT,
    "1-1": gp.BESTAETIGT,
    "saturn-mediamarkt-telekom-netz": gp.BESTAETIGT,
}


@pytest.fixture(scope="module")
def texte(chromium):
    seite = chromium.new_page()
    try:
        out = {}
        for name in ERWARTET:
            seite.set_content((FIXTURES / f"{name}.html").read_text(encoding="utf-8"))
            out[name] = seite.inner_text("body")
        return out
    finally:
        seite.close()


FAELLE = [(n, f) for n, (w, _) in ERWARTET.items() for f in gp.FELDER]


@pytest.mark.parametrize(("anbieter", "feld"), FAELLE)
def test_jeder_posten_der_aufnahme(texte, anbieter, feld):
    werte = sicht.LESER[anbieter](texte[anbieter]).werte()
    assert werte.get(feld) == ERWARTET[anbieter][0].get(feld)


@pytest.mark.parametrize("anbieter", list(ERWARTET))
def test_tarifname_der_aufnahme(texte, anbieter):
    assert sicht.LESER[anbieter](texte[anbieter]).tarif_name == (ERWARTET[anbieter][1])


@pytest.mark.parametrize("anbieter", list(ERWARTET))
def test_status_gegen_den_bestand_des_tages(texte, anbieter):
    gelesen = sicht.LESER[anbieter](texte[anbieter]).werte()
    gespeichert = GESPEICHERT.get(anbieter, ERWARTET[anbieter][0])
    status, *_ = gp.vergleiche(gespeichert, gelesen)
    assert status == STATUS[anbieter]


@pytest.mark.parametrize("anbieter", list(ERWARTET))
def test_jeder_gelesene_betrag_steht_im_text(texte, anbieter):
    s = sicht.LESER[anbieter](texte[anbieter])
    for wert in (w for w in s.roh.values() if w.endswith(" €")):
        zahl = wert.removesuffix(" €").replace(".", "")
        kurz = zahl.removesuffix(",00")
        assert zahl in texte[anbieter].replace(".", "") or kurz in texte[anbieter]


@pytest.mark.parametrize(
    ("text", "wert"),
    [
        ("1.199", 1199.0),
        ("29,50", 29.5),
        ("26,–", 26.0),
        ("0,-", 0.0),
        ("849,90", 849.9),
        ("1.056,–", 1056.0),
        ("9,5", 9.5),
        ("7", 7.0),
    ],
)
def test_betrag(text, wert):
    assert sicht.betrag(text) == wert


def test_o2_liest_nicht_den_buendelpreis_als_tarif():
    text = (
        "Gerät & Tarif monatlich\n51,49 €\nDein Angebot\nGerät monatlich:\n54,50 €\n"
        "Ratenzahlung: 24 Monate\nTarif monatlich:\n14,99 €\n"
    )
    s = sicht.o2(text)
    assert (s.tarif_monatlich, s.geraet_monatsrate) == (14.99, 54.5)


def test_o2_nimmt_den_ersten_anschlusspreis_nicht_den_durchgestrichenen():
    s = sicht.o2("einmaliger Anschlusspreis\n0,00 €\n39,99 €\n")
    assert s.anschlusspreis == 0.0


def test_telekom_ohne_passende_rate_liest_keine_raten():
    text = (
        "6 € mtl. x 36\n+1 € Anzahlung\nMagentaMobil M\n49,95 €\n"
        "zzgl. 39,95 € ⌀ pro Karte einmalig\nEinmalige Zahlung\n40,95 €\n"
        "inkl. Bereitstellung 39,95 €\nGesamtpreis monatlich\n70,00 €\n"
    )
    s = sicht.telekom(text)
    assert s.tarif_monatlich == 49.95
    assert s.geraet_monatsrate is None and s.laufzeit_monate is None


def test_telekom_liest_grossgeschriebene_beschriftung():
    text = (
        "9,50 € mtl. x 24\n+1 € Anzahlung\nMagentaMobil M\n49,95 €\n"
        "zzgl. 39,95 € ⌀ pro Karte einmalig\nEINMALIGE ZAHLUNG\n40,95 €\n"
        "inkl. Bereitstellung 39,95 €\nGESAMTPREIS MONATLICH\n59,45 €\n"
    )
    s = sicht.telekom(text)
    assert (s.geraet_monatsrate, s.laufzeit_monate, s.geraet_zuzahlung) == (
        9.5,
        24,
        1.0,
    )


def test_vodafone_ohne_angebotspreis_hat_keinen_tarif():
    text = "Gewählt: 24 Raten\nPro Monat\n57 €" + sicht.VODAFONE_TRENNER + "Einmal\n1 €"
    s = sicht.vodafone(text)
    assert s.geraet_monatsrate == 57.0 and s.tarif_monatlich is None


def test_vodafone_nennt_anschlusspreis_wenn_er_anfaellt():
    text = (
        "Gewählt: 24 Raten\nPro Monat\n57 €"
        + sicht.VODAFONE_TRENNER
        + "Mobil M mit 50 GB\nAngebotspreis 90,00 €\n  Anschlusspreis 39,99 €\n"
    )
    assert sicht.vodafone(text).anschlusspreis == 39.99


def test_congstar_ohne_passende_zahlweise_bleibt_anzahlung_offen():
    text = (
        "24 mtl. Zahlungen\nMonatliche Kosten\n58,50 €\nAnzahlung\n49,00 €\n"
        "Summe 1. bis 36. Monat\n57,00 €\nTarif\n15,00 €\nGerät\n42,00 €\n"
        "in den ersten 36 Monaten\nSumme einmalig\n49,00 €\n"
    )
    s = sicht.congstar(text)
    assert s.laufzeit_monate == 36
    assert s.geraet_zuzahlung is None and s.anschlusspreis is None


def test_einsundeins_geraet_und_tarif_ergeben_den_monatsbetrag(texte):
    roh = sicht.einsundeins(texte["1-1"]).roh
    geraet = sicht.betrag(roh["Gerät monatlich"].removesuffix(" €"))
    tarif = sicht.betrag(roh["Tarif monatlich (Kachel)"].removesuffix(" €"))
    gesamt = sicht.betrag(roh["Monatliche Gesamtkosten"].removesuffix(" €"))
    assert round(geraet + tarif, 2) == gesamt == 57.99


def test_einsundeins_liest_sichtbaren_anschlusspreis():
    text = (
        "1&1 All-Net-Flat S\n14,99 €\nAnschlusspreis 39,90 €\n"
        "Monatliche Gesamtkosten\n57,99 €"
    )
    assert sicht.einsundeins(text).anschlusspreis == 39.9


def test_jeder_anbieter_mit_weg_hat_einen_leser():
    from telco_radar.collect.geraete.gegenprobe_wege import WEGE

    assert set(WEGE) == set(sicht.LESER)
