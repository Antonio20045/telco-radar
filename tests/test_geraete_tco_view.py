"""Der Reiter "Was kostet es": `report/geraete_tco_view.py`.

WAS DIESE TESTS FESTHALTEN
---------------------------
Diese Tafel rechnet selbst nichts - sie ruft `tco_model.tco_24()` und
`tco_model.geraeteanteil()` auf und FORMT das Ergebnis. Der ganze Sinn des
Reiters ist eine einzige Unterscheidung: `Tco.gesamt` ist auch dann eine
Zahl, wenn kein Tarifpreis bekannt ist (dann ist es der Geraetebetrag) -
die Tafel zeigt `gesamt`/`monatlich` aber NUR bei `Tco.belastbar`. Jeder
Test hier prueft genau EINE Zusicherung des Moduls.

Die Zahlen stammen, wie in `test_tco_model.py`, aus dem o2-Rechenbeispiel
vom 03.09.2026 (1 EUR Anzahlung, 24 x 30 EUR Rate = 721 EUR).

KEIN NETZ, KEINE UHR, KEIN gemeinsamer Zustand zwischen den Tests.
"""

from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report.geraete_tco_view import (
    ANBIETER_UNBEKANNT,
    aufbereiten,
    leer,
    ohne_zuordnung_satz,
)
from telco_radar.tco_model import (
    Buendel,
    tco_24,
)

_ANZAHLUNG, _RATE = 1.0, 30.0
_SKU = "apple-iphone-14-128gb-mitternacht"


def _buendel(**kw) -> Buendel:
    """Ein vollstaendiges Buendel; jeder Test aendert nur, was er misst."""
    felder = dict(
        sku_id=_SKU,
        anbieter="o2",
        tarif_name="o2 Mobile M",
        tarif_monatlich=29.99,
        geraet_zuzahlung=_ANZAHLUNG,
        geraet_monatsrate=_RATE,
        laufzeit_monate=24,
        anschlusspreis=39.99,
        quelle_url="https://www.o2online.de/tarife/mobile-m",
        abgerufen_am="2026-09-03",
    )
    felder.update(kw)
    return Buendel(**felder)


def test_ohne_tarifpreis_zeigt_die_zeile_keine_zahl_obwohl_tco_24_eine_liefert():
    """`tco_24` liefert fuer ein Buendel ohne Tarifgrundpreis sehr wohl ein
    `gesamt` (den Geraetebetrag) - Regel 2 des Modulkopfs verlangt, dass die
    Tafel es trotzdem NICHT zeigt. Ohne die erste Zusicherung wuerde dieser
    Test nichts pruefen, deshalb steht sie hier explizit."""
    b = _buendel(tarif_monatlich=None)
    roh = tco_24(b)
    assert roh.gesamt is not None, "sonst beweist der Test nur, dass es keine Zahl gab"
    assert roh.belastbar is False

    zeile = aufbereiten([b], [], [], katalog=None)["export"]["buendel"][0]
    assert zeile["tco24"] is None
    assert zeile["tarif_monatlich"] is None
    assert zeile["luecke"] == "Tarifgrundpreis"


def test_ein_vollstaendiges_buendel_ergibt_leitzahl_und_monatsbetrag():
    b = _buendel()
    roh = tco_24(b)
    assert roh.belastbar is True, "sonst prueft der Test den falschen Fall"

    zeile = aufbereiten([b], [], [], katalog=None)["export"]["buendel"][0]
    assert zeile["tco24"] == roh.gesamt == 1480.75
    assert zeile["luecke"] == ""


def test_ein_store_woerterbuch_mit_betriebsfeldern_wird_gelesen():
    """Genau die Form, die `TcoDB.buendel()` liefert: ein dict MIT `id`,
    `first_seen`, `last_verified` - Felder, die keine Felder der
    Datenklasse sind. Dieser Test bricht, wenn jemand auf `Typ(**eintrag)`
    umstellt."""
    satz = {
        "id": "buendel--o2--apple-iphone-14-128gb-mitternacht--o2-mobile-m",
        "sku_id": _SKU,
        "anbieter": "o2",
        "tarif_name": "o2 Mobile M",
        "first_seen": "2026-09-01",
        "last_verified": "2026-09-03",
        "tarif_monatlich": 29.99,
        "geraet_zuzahlung": _ANZAHLUNG,
        "geraet_monatsrate": _RATE,
        "laufzeit_monate": 24,
        "anschlusspreis": 39.99,
        "quelle_url": "https://www.o2online.de/x",
        "abgerufen_am": "2026-09-03",
    }
    ergebnis = aufbereiten([satz], [], [], katalog=None)
    assert len(ergebnis["export"]["buendel"]) == 1
    assert ergebnis["export"]["buendel"][0]["tco24"] == tco_24(_buendel()).gesamt


def test_ein_kaputter_satz_kostet_keine_tafel():
    """Zwei Saetze rein, einer verletzt `Buendel.__post_init__` (kein
    Anbieter) - eine Zeile raus, der gueltige Nachbar bleibt stehen."""
    kaputt = {"sku_id": _SKU, "tarif_name": "o2 Mobile M", "tarif_monatlich": 29.99}
    gueltig = {
        "sku_id": "apple-iphone-16-128gb-schwarz",
        "anbieter": "o2",
        "tarif_name": "o2 Mobile M",
        "tarif_monatlich": 29.99,
    }

    ergebnis = aufbereiten([kaputt, gueltig], [], [], katalog=None)
    assert len(ergebnis["export"]["buendel"]) == 1
    assert ergebnis["export"]["buendel"][0]["sku_id"] == "apple-iphone-16-128gb-schwarz"


def test_leer_traegt_jedes_feld_das_aufbereiten_traegt():
    voll = aufbereiten([], [], [], katalog=None)
    assert set(leer().keys()) == set(voll.keys())


def test_eine_listung_mit_raten_ohne_barpreis_kostet_nicht_die_seite():
    """B1. `preis_ohne_vertrag` ist ein EIGENES Optional-Feld.

    Eine Listung mit Ratenform ohne Barpreis ist moeglich - `geraete_store`
    schreibt jedes Preisfeld einzeln - und kommt mit Phase 4 (Zuzahlung mit
    Tarifreferenz statt Kassenpreis). `float(None)` haette hier geworfen,
    `render_site` waere auf `geraete_view.leer()` gefallen, und damit waeren
    ALLE fuenf Reiter leer und der Navigationseintrag "Geraete" von jeder
    Seite verschwunden.
    """
    ohne_barpreis = {
        "anbieter": "otelo",
        "zustand": "neu",
        "sku_id": "a-b-128gb",
        "device_id": "a-b",
        "preis_ohne_vertrag": None,
        "anzahlung": 1.0,
        "monatsrate": 30.0,
        "laufzeit_monate": 24,
    }
    d = aufbereiten([], [], [ohne_barpreis], katalog=None)

    assert d["lesbar"] is True
    assert d["modelle"] == [] and d["export"]["buendel"] == []


def test_eine_unlesbare_datei_ist_nicht_leer():
    """B6. `TcoDB` unterscheidet die zwei ausdruecklich - dieses Modul
    reichte den Zustand aber nicht durch, und die Tafel meldete bei kaputter
    Datei "es fehlen die Tarifpreise"."""
    assert aufbereiten([], [], [], katalog=None)["lesbar"] is True
    assert aufbereiten([], [], [], katalog=None, lesbar=False)["lesbar"] is False


def test_eine_sim_only_referenz_aus_dem_speicher_wird_gelesen():
    """Der Weg Store-dict -> `SimOnlyReferenz`, mit den Betriebsfeldern.

    Fuer `Buendel` gibt es diesen Test schon. Ohne ihn hier liesse ein
    Feldnamen-Tippfehler in `_REFERENZ_FELDER` JEDE Referenz stumm wegfallen:
    `geraeteanteil` waere dauerhaft `None`, und kein Test schluege an.
    """
    b = _buendel(anbieter="o2", tarif_name="o2 M")
    referenz = {
        "id": "simonly--o2--o2-m",
        "anbieter": "o2",
        "tarif_name": "o2 M",
        "tarif_sim_only_monatlich": 19.99,
        "anschlusspreis": 39.99,
        "quelle_url": "https://o2.example/s",
        "abgerufen_am": "2026-09-03",
        "first_seen": "2026-09-01",
        "last_verified": "2026-09-03",
    }
    d = aufbereiten([b], [referenz], [], katalog=None)
    assert [z["tarif"] for z in d["export"]["sim_only"]] == ["o2 M"], (
        "die Referenz ist angekommen"
    )
    assert d["export"]["sim_only"][0]["tarif_monatlich"] == 19.99


_PIB_MOBIL_XS = {
    "anbieter": "Vodafone",
    "name": "Vodafone Mobil XS",
    "tarif_id": "vodafone:vodafone-mobil-xs",
    "grundgebuehr": 29.95,
    "laufzeit_monate": 24,
    "datenvolumen_gb": 18.0,
    "preisphasen": [
        {"von_monat": 1, "bis_monat": 24, "betrag": 29.95},
        {"von_monat": 25, "bis_monat": None, "betrag": 29.95},
    ],
    "dokument_url": "https://example.de/pib/mobil-xs",
    "abgerufen_am": "2026-09-16",
    "confidence": {},
    "fundstellen": {},
}


def _fold8_xs() -> dict:
    """Die Bündel-Messung des Befunds: Samsung Galaxy Z Fold8 256 an
    Vodafone Mobil XS - 31,95 EUR Tarif im Shop (das Blatt nennt 29,95 EUR
    ohne Smartphone-Zuschlag), 36 Raten à 42,50 EUR, 0,99 EUR Anzahlung."""
    return {
        "id": "buendel--vodafone--samsung-galaxy-z-fold8-256gb-cream--mobil-xs",
        "sku_id": "samsung-galaxy-z-fold8-256gb-cream",
        "anbieter": "Vodafone",
        "tarif_name": "Mobil XS",
        "tarif_id": "vodafone:vodafone-mobil-xs",
        "tarif_id_guete": "hoch",
        "tarif_monatlich": 31.95,
        "geraet_zuzahlung": 0.99,
        "geraet_monatsrate": 42.5,
        "laufzeit_monate": 36,
        "anschlusspreis": 0.0,
        "zustand": "neu",
        "rabatte": [],
        "quelle_url": "https://www.vodafone.de/privat/handys/"
        "samsung-galaxy-z-fold8.html",
        "abgerufen_am": "2026-09-16",
        "first_seen": "2026-09-12",
        "last_verified": "2026-09-16",
    }


def test_widerspruch_zwischen_blatt_und_messung_entscheidet_die_messung():
    """0,99 + 24 x 31,95 + 36 x 42,50 + 0 = 2.297,79 EUR - nicht 2.249,79.

    Das Blatt beschreibt den Tarif OHNE den geräteabhängigen Zuschlag,
    die Messung am Bündel den Preis, den der Kunde zahlt. Bis zum Fix
    reicherte die Tafel die Phasen des Blatts an und liess sie der Messung
    vorgehen: die Karte sagte 'monatlich 31,95 EUR', die Postenliste
    rechnete 24 x 29,95 = 718,80 EUR - die Leitzahl war mit der eigenen
    Karte nicht nachrechenbar (473 Vodafone-Bündel, um je 48,00 EUR zu
    niedrig, samt Delta zur Vodafone-Referenz)."""
    zeile = aufbereiten(
        [_fold8_xs()],
        [],
        [],
        katalog=None,
        tarife={"vodafone:vodafone-mobil-xs": _PIB_MOBIL_XS},
    )["export"]["buendel"][0]
    assert zeile["tco24"] == 2297.79
    assert zeile["tco24"] != 2249.79


def test_phasen_innerhalb_der_preisspanne_bleiben_phasengewichtet():
    """Ein echter Rabatt bleibt: '12 Monate 21,95 EUR, danach 31,95 EUR'
    bei einer Messung von 31,95 EUR - die Messung liegt IN der Preisspanne
    des Blatts, also beschreibt das Blatt dieses Angebot:
    12 x 21,95 + 12 x 31,95 = 646,80 EUR statt flach 766,80 EUR. Der
    Widerspruchs-Fix darf die Phasen nicht pauschal mitnehmen."""
    satz = dict(
        _PIB_MOBIL_XS,
        preisphasen=[
            {"von_monat": 1, "bis_monat": 12, "betrag": 21.95},
            {"von_monat": 13, "bis_monat": None, "betrag": 31.95},
        ],
    )
    zeile = aufbereiten(
        [_fold8_xs()], [], [], katalog=None, tarife={"vodafone:vodafone-mobil-xs": satz}
    )["export"]["buendel"][0]
    assert zeile["tco24"] == round(0.99 + 646.8 + 36 * 42.5, 2)


def test_phasen_ohne_messung_gelten_weiterhin():
    """Keine Messung, kein Widerspruch: das Blatt allein traegt die Phasen
    (24 x 29,95 = 718,80 EUR) - derselbe Zustand wie vor dem Fix."""
    b = _fold8_xs()
    b["tarif_monatlich"] = None
    zeile = aufbereiten(
        [b], [], [], katalog=None, tarife={"vodafone:vodafone-mobil-xs": _PIB_MOBIL_XS}
    )["export"]["buendel"][0]
    assert zeile["tco24"] == round(0.99 + 718.8 + 36 * 42.5, 2)


def test_phasen_fuer_buendel_entscheidet_nur_bei_widerspruch():
    """Die EINE Stelle der Rangfolge Blatt/Messung: liegt die Messung
    ausserhalb der Preisspanne des Blatts, gibt es keine Phasen (flach);
    liegt sie innerhalb, gelten sie; ohne Messung gibt es keinen
    Widerspruch; ohne Blatt keine Phasen."""
    phasen = karten.phasen_aus_tarifsatz(_PIB_MOBIL_XS)
    assert phasen, "Gegenprobe: das Blatt hat Phasen"
    assert karten.phasen_fuer_buendel(_PIB_MOBIL_XS, 31.95) == []
    assert karten.phasen_fuer_buendel(_PIB_MOBIL_XS, 29.95) == phasen
    assert karten.phasen_fuer_buendel(_PIB_MOBIL_XS, None) == phasen
    assert karten.phasen_fuer_buendel({}, 31.95) == []


def _offen(*anbieter: str) -> list[dict]:
    return [
        {"sku_id": f"sku-{i}", "anbieter": a, "grund": "x"}
        for i, a in enumerate(anbieter)
    ]


def test_der_satz_zu_buendeln_ohne_geraet_nennt_anzeigename_und_zahl():
    satz = ohne_zuordnung_satz(
        _offen("o2", "o2", "telekom"), {"o2": "O2", "telekom": "Telekom"}
    )
    assert satz == (
        "Nicht auf der Tafel, weil kein Gerät zuzuordnen ist: "
        "2 Bündel von O2, 1 Bündel von Telekom."
    )


def test_der_satz_zeigt_nie_den_rohen_schluessel():
    """Gegenprobe: ohne Anzeigenamen erscheint der Schluessel, mit ihnen nicht."""
    roh = ohne_zuordnung_satz(_offen("vodafone-de"), {})
    assert "vodafone-de" in roh
    satz = ohne_zuordnung_satz(_offen("vodafone-de"), {"vodafone-de": "Vodafone"})
    assert "vodafone-de" not in satz and "1 Bündel von Vodafone" in satz


def test_der_satz_ordnet_viele_zuerst_dann_nach_name():
    satz = ohne_zuordnung_satz(_offen("b", "a", "c", "c"), {})
    assert satz.endswith("2 Bündel von c, 1 Bündel von a, 1 Bündel von b.")


def test_der_satz_fehlt_wenn_nichts_offen_ist():
    assert ohne_zuordnung_satz([], {"o2": "O2"}) == ""
    assert leer()["ohne_zuordnung_satz"] == ""


def test_ein_leerer_anbietername_heisst_unbekannt_nicht_fragezeichen():
    satz = ohne_zuordnung_satz(_offen(""), {})
    assert ANBIETER_UNBEKANNT in satz and "?" not in satz


def test_aufbereiten_reicht_den_satz_mit_anzeigenamen_durch():
    d = aufbereiten(
        [_buendel(anbieter="o2")], [], [], katalog=None, anbieter_anzeige={"o2": "O2"}
    )
    assert d["ohne_zuordnung_satz"].endswith("1 Bündel von O2.")
