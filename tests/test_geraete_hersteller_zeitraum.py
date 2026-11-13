"""Die Herstellergrafik muss zeitlich vollständig sein (Antonio, 13.11.2026).

Zwei Befunde am echten Bestand vom 13.11.2026 stehen hinter diesen Tests:

1. Ein Bündel, das am HEUTIGEN Stand als „veraltet“ gilt (Prüfregel Frische
   oder abgelaufene Aktion), löschte rückwirkend jeden seiner Messtage -
   congstar stand mit 7 statt 45 Messtagen in der Tafel. Ob eine Messung an
   IHREM Tag frisch war, entscheidet ``ist_frisch(abgerufen_am, tag)``; das
   Urteil über den heutigen Stand gehört nicht in die Vergangenheit.
2. Tage ganz ohne Abstand (kein Vodafone-Preis, also keine einzige Zelle)
   standen trotzdem in der Tageliste: sie zählten in „Mittel aus N Messtagen“
   mit und schoben das früheste wählbare Datum des eigenen Zeitraums nach
   vorn, obwohl dort nichts zu sehen ist.

Die Tests hängen an festen Beispieltagen, nie am heutigen Datum.
"""

from __future__ import annotations

import json

import pytest

from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.report import geraete_hersteller as hm
from telco_radar.report import geraete_notbremse as nb

LAUFZEIT = hm.LAUFZEIT
TAGE = ("2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01")
STAND = TAGE[-1]


def _karte(anbieter: str, gesamt: float, tarif: str) -> dict:
    return {
        "anbieter": anbieter,
        "band": "m",
        "gesamt": gesamt,
        "tarif": tarif,
        "vergleichbar": True,
        "belastbar": True,
        "frisch": True,
        "zaehlt": True,
        "naeherung": False,
        "raten_laufzeit": LAUFZEIT,
        "leitzahl_monate": LAUFZEIT,
        "quelle_url": f"https://beispiel.test/{anbieter}?tarif=m",
    }


def _messung(wert: float, tag: str) -> dict:
    return {
        "wert": wert,
        "monate": LAUFZEIT,
        "zaehlt": True,
        "satz": {"abgerufen_am": tag},
    }


def _gebremst(wert: float, tag: str, **flags) -> dict:
    """Eine Messung, die am heutigen Stand nicht zählt - mit benanntem Grund."""
    return {**_messung(wert, tag), "zaehlt": False, **flags}


def _welt(vodafone_tage=TAGE, telekom=None) -> dict:
    """Ein Apple-Modell; Vodafone und Telekom über die fünf Beispieltage.

    ``telekom`` ist {Tag: Messung}; ohne Angabe zählt Telekom an allen Tagen.
    """
    mid = "apple-iphone-18-pro-256"
    katalog = Katalog(
        geraete=[
            Geraet(
                hersteller="Apple",
                modell="iPhone 18 Pro",
                generation=18,
                speicher=[256, 512],
                auto="",
            )
        ]
    )
    karten = [
        _karte("Vodafone", 2200.0, "Vodafone Mobil M"),
        _karte("Telekom", 2000.0, "Telekom Tarif M"),
    ]
    je = {
        "Vodafone": {t: _messung(2200.0, t) for t in vodafone_tage},
        "Telekom": telekom
        if telekom is not None
        else {t: _messung(2000.0, t) for t in TAGE},
    }
    return {
        "katalog": katalog,
        "tco": {
            "baender_katalog": [{"key": "m", "label": "M"}],
            "modelle": [{"id": mid, "karten": karten}],
        },
        "messungen": {(mid, "m", LAUFZEIT): je},
    }


def _rechne(welt: dict) -> dict:
    return hm.berechne(welt["messungen"], welt["tco"], welt["katalog"], STAND)


def test_eine_zaehlende_messung_zaehlt_auch_am_tag():
    assert nb.zaehlt_am_tag(_messung(1.0, TAGE[0])) is True


def test_heute_veraltete_pruefung_loescht_den_messtag_nicht():
    assert nb.zaehlt_am_tag(_gebremst(1.0, TAGE[0], veraltet_pruefung=True)) is True


def test_heute_abgelaufene_aktion_loescht_den_messtag_nicht():
    assert nb.zaehlt_am_tag(_gebremst(1.0, TAGE[0], veraltet_aktion=True)) is True


@pytest.mark.parametrize("flag", nb.IMMER)
def test_ein_nie_vergleichbarer_preis_bleibt_auch_rueckblickend_draussen(flag):
    """Schätzung, Zweitprodukt-Tarif, Quarantäne, gescheiterte Prüfung und
    „nicht im Sortiment“ waren auch am Messtag kein gültiger Vergleich."""
    assert nb.zaehlt_am_tag(_gebremst(1.0, TAGE[0], **{flag: True})) is False


def test_nicht_im_sortiment_schlaegt_das_veraltet_urteil():
    m = _gebremst(1.0, TAGE[0], veraltet_pruefung=True, nicht_im_sortiment=True)
    assert nb.zaehlt_am_tag(m) is False


def test_ohne_jedes_flag_und_ohne_zaehlt_bleibt_die_messung_draussen():
    assert nb.zaehlt_am_tag({"wert": 1.0, "zaehlt": False}) is False


def test_die_listen_der_gruende_ueberschneiden_sich_nicht():
    assert not set(nb.NUR_HEUTE) & set(nb.IMMER)


def test_tageswerte_behalten_den_heute_veralteten_tag():
    je = {"congstar": {t: _gebremst(900.0, t, veraltet_pruefung=True) for t in TAGE}}
    assert sorted(hm.tageswerte(je)["congstar"]) == list(TAGE)


def test_tageswerte_verwerfen_die_quarantaene():
    je = {"congstar": {t: _gebremst(900.0, t, quarantaene=True) for t in TAGE}}
    assert hm.tageswerte(je)["congstar"] == {}


def test_tageswerte_verwerfen_eine_messung_die_an_ihrem_tag_alt_war():
    """Die Frische je Tag bleibt die Grenze - nur eben tagbezogen."""
    alt = _gebremst(900.0, TAGE[-1], veraltet_pruefung=True)
    alt["satz"] = {"abgerufen_am": "2026-01-01"}
    assert hm.tageswerte({"congstar": {TAGE[-1]: alt}})["congstar"] == {}


def test_tageswerte_verwerfen_eine_fremde_ratenlaufzeit():
    fremd = _gebremst(900.0, TAGE[0], veraltet_pruefung=True)
    fremd["monate"] = 36
    assert hm.tageswerte({"congstar": {TAGE[0]: fremd}})["congstar"] == {}


def test_tageswerte_verwerfen_eine_messung_ohne_wert():
    ohne = _messung(900.0, TAGE[0])
    ohne["wert"] = None
    assert hm.tageswerte({"congstar": {TAGE[0]: ohne}})["congstar"] == {}


def test_ein_tag_ohne_vodafone_preis_steht_nicht_in_der_tageliste():
    r = _rechne(_welt(vodafone_tage=TAGE[1:]))
    assert r["tage"] == list(TAGE[1:])
    assert TAGE[0] not in r["pct"]


def test_mit_vodafone_an_allen_tagen_bleiben_alle_tage():
    assert _rechne(_welt())["tage"] == list(TAGE)


def test_jeder_gelistete_tag_traegt_mindestens_einen_abstand():
    r = _rechne(_welt(vodafone_tage=TAGE[2:]))
    for tag in r["tage"]:
        assert any(w is not None for zeile in r["pct"][tag] for w in zeile)


def test_der_heute_veraltete_wettbewerber_faerbt_alle_seine_tage_ein():
    """Der Befund congstar: ohne die Korrektur bliebe kein einziger Tag."""
    gebremst = {t: _gebremst(2000.0, t, veraltet_pruefung=True) for t in TAGE}
    r = _rechne(_welt(telekom=gebremst))
    j = hm.WETTBEWERBER.index("Telekom")
    assert [t for t in r["tage"] if r["pct"][t][0][j] is not None] == list(TAGE)


def test_ein_quarantaene_wettbewerber_bleibt_an_jedem_tag_eine_luecke():
    gebremst = {t: _gebremst(2000.0, t, quarantaene=True) for t in TAGE}
    r = _rechne(_welt(telekom=gebremst))
    j = hm.WETTBEWERBER.index("Telekom")
    assert all(r["pct"][t][0][j] is None for t in r["tage"])


def test_die_grenzen_des_eigenen_zeitraums_sind_echte_messtage():
    welt = _welt(vodafone_tage=TAGE[1:])
    d = hm.aufbereiten(welt["messungen"], welt["tco"], welt["katalog"], STAND)
    assert d["tage_von"] == TAGE[1] and d["tage_bis"] == TAGE[-1]


def test_mittel_ueber_tage_zaehlt_nur_tage_mit_wert():
    r = _rechne(_welt(vodafone_tage=TAGE[2:]))
    _, tage = hm.mittel_ueber_tage(r, TAGE[0], TAGE[-1])
    assert tage == len(TAGE) - 2


def test_mittel_ueber_tage_mittelt_die_tage_des_fensters():
    r = _rechne(_welt())
    zeilen, tage = hm.mittel_ueber_tage(r, TAGE[0], TAGE[-1])
    j = hm.WETTBEWERBER.index("Telekom")
    assert tage == len(TAGE)
    assert zeilen[0][j] == pytest.approx(hm.abstand(2200.0, 2000.0))


def test_ein_fenster_ohne_messtag_gibt_keine_null_sondern_eine_luecke():
    r = _rechne(_welt())
    zeilen, tage = hm.mittel_ueber_tage(r, "2026-01-01", "2026-01-02")
    assert tage == 0 and all(w is None for w in zeilen[0])


def test_zeitraum_rechnet_vom_stand_rueckwaerts():
    _, tage = hm.zeitraum(_rechne(_welt()), 2)
    assert tage == 2


def test_dreissig_tage_umfassen_alle_fuenf_beispieltage():
    _, tage = hm.zeitraum(_rechne(_welt()), 30)
    assert tage == len(TAGE)


def test_das_json_der_seite_nennt_dieselben_tage_wie_die_rechnung():
    welt = _welt(vodafone_tage=TAGE[1:])
    d = hm.aufbereiten(welt["messungen"], welt["tco"], welt["katalog"], STAND)
    daten = json.loads(d["json"].replace("<\\/", "</"))
    assert daten["tage"] == list(TAGE[1:])
    assert len(daten["pct"]) == len(daten["tage"])
