"""Kennzahlen der Prüfstelle je Anbieter und Erfassungslücken (Regel 12).

Datenkonzept Geräteradar, Schritt 7: Abdeckung je Laufzeit, Frische,
Quarantänequote, Konfliktquote und Belegquote stehen als Daten neben „nicht
prüfbar“. Orakel ist eine Handrechnung an einem kleinen Bestand mit fest
eingetragenem vollem Feld je Bündel; die Gegenprobe ändert einen Status und erwartet
die nachgerechnete Änderung. Die Quellen-Seite liest den Lauf-Eintrag ``pruefung`` aus
``geraete_tco.json``. Fester Bezugstag, nie das heutige Datum.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup
from orakel.test_seiten_inhalt import lies_seite, render

from telco_radar.analyze import geraete_pruefkennzahlen
from telco_radar.analyze.geraete_pruefkennzahlen import kennzahlen
from telco_radar.analyze.geraete_pruefstatus import vermerk
from telco_radar.analyze.geraete_regeln import erfassungsluecken

HEUTE = "2026-10-03"


def _satz(anbieter: str, nr: int, laufzeit: int, pruefung=None, **feld) -> dict:
    satz = {
        "id": f"{anbieter}-{nr}",
        "sku_id": f"phone-{nr}",
        "anbieter": anbieter,
        "tarif_name": f"Tarif {nr}",
        "geraet_zuzahlung": float(nr),
        "geraet_monatsrate": 10.0 + nr,
        "tarif_monatlich": 20.0 + nr,
        "tarif_bindung_monate": nr,
        "anschlusspreis": 39.99,
        "laufzeit_monate": laufzeit,
        "abgerufen_am": HEUTE,
        **feld,
    }
    if pruefung is not None:
        satz["pruefung"] = pruefung
    return satz


def _p(status: str, verletzt=(), luecken=(), nicht=()) -> dict:
    return {
        "status": status,
        "gruende": [{"regel": r, "satz": f"Regel {r}"} for r in verletzt],
        "luecken": list(luecken),
        "nicht_pruefbar": list(nicht),
    }


def _bestand(a2: str = "quarantaene") -> list[dict]:
    """o2: vier geprüfte Bündel; congstar: eines nie geprüft, eines gescheitert."""
    return [
        _satz("o2", 1, 24, _p("gueltig", luecken=[7], nicht=[9, 11, 13])),
        _satz(
            "o2",
            2,
            24,
            _p(a2, verletzt=[3] if a2 == "quarantaene" else [], nicht=[9, 11, 13]),
        ),
        _satz("o2", 3, 36, _p("veraltet", verletzt=[16], nicht=[9, 11])),
        _satz("o2", 4, 36, _p("quarantaene", verletzt=[9, 13], nicht=[11])),
        _satz("congstar", 5, 24),
        _satz(
            "congstar",
            6,
            24,
            {"status": "unbekannt", "fehler": "RuntimeError: kaputt"},
        ),
    ]


def _kennzahlen(bestand: list[dict]) -> dict:
    """Die Kennzahlen mit dem vollen Feld je Bündel, wie die Prüfstelle sie rechnet."""
    felder = {s["id"]: s["pruefung"] for s in bestand if "pruefung" in s}
    return kennzahlen(bestand, felder)


def _zeile(daten: dict, name: str) -> dict:
    return next(z for z in daten["anbieter"] if z["name"] == name)


def _prozent(zeile: dict) -> dict:
    namen = ("frische", "quarantaenequote", "konfliktquote", "belegquote")
    return {n: zeile[n]["prozent"] for n in namen}


def test_kennzahlen_je_anbieter_gegen_handrechnung():
    o2 = _zeile(_kennzahlen(_bestand()), "o2")
    assert (o2["buendel"], o2["geprueft"]) == (4, 4)
    assert (o2["gueltig"], o2["quarantaene"], o2["veraltet"]) == (1, 2, 1)
    assert o2["abdeckung"] == [
        {"monate": 6, "gueltig": 0, "erfasst": False},
        {"monate": 12, "gueltig": 0, "erfasst": False},
        {"monate": 24, "gueltig": 1, "erfasst": True},
        {"monate": 36, "gueltig": 0, "erfasst": True},
    ]
    assert o2["frische"] == {"zahl": 3, "von": 4, "prozent": 75, "nicht_pruefbar": 0}
    assert o2["quarantaenequote"]["prozent"] == 50
    assert o2["konfliktquote"] == {
        "zahl": 1,
        "von": 1,
        "prozent": 100,
        "nicht_pruefbar": 3,
    }
    assert o2["belegquote"] == {"zahl": 1, "von": 2, "prozent": 50, "nicht_pruefbar": 2}
    assert o2["ohne_daten"] == [11], "Regel 11 an keinem o2-Bündel prüfbar"


def test_gegenprobe_ein_status_weniger_in_quarantaene():
    o2 = _zeile(_kennzahlen(_bestand(a2="gueltig")), "o2")
    assert (o2["gueltig"], o2["quarantaene"]) == (2, 1)
    assert o2["quarantaenequote"]["prozent"] == 25
    assert o2["abdeckung"][2] == {"monate": 24, "gueltig": 2, "erfasst": True}
    assert _prozent(o2) == {
        "frische": 75,
        "quarantaenequote": 25,
        "konfliktquote": 100,
        "belegquote": 50,
    }


def test_ohne_gepruefte_buendel_ist_jede_quote_nicht_pruefbar_nie_null():
    congstar = _zeile(_kennzahlen(_bestand()), "congstar")
    assert (congstar["nie_geprueft"], congstar["gescheitert"]) == (1, 1)
    assert congstar["fehler"] == "RuntimeError: kaputt"
    assert congstar["geprueft"] == 0
    assert set(_prozent(congstar).values()) == {None}
    assert congstar["ohne_daten"] == []


def test_summe_zaehlt_alle_anbieter():
    summe = _kennzahlen(_bestand())["summe"]
    assert (summe["buendel"], summe["geprueft"]) == (6, 4)
    assert (summe["nie_geprueft"], summe["gescheitert"]) == (1, 1)
    assert (summe["gueltig"], summe["quarantaene"], summe["veraltet"]) == (1, 2, 1)


def test_je_regel_zaehlt_nicht_pruefbar_und_luecken():
    regeln = {r["nr"]: r for r in _kennzahlen(_bestand())["regeln"]}
    assert len(regeln) == 16
    assert regeln[11]["nicht_pruefbar"] == 4, "nicht prüfbar wird je Regel gezählt"
    assert (regeln[9]["verletzt"], regeln[9]["nicht_pruefbar"]) == (1, 3)
    assert (regeln[13]["verletzt"], regeln[13]["nicht_pruefbar"]) == (1, 2)
    assert regeln[7]["luecke"] == 1
    assert regeln[12]["luecke"] == 3, "o2: 2 Erfassungslücken, congstar: 1"
    assert regeln[1] == {
        "nr": 1,
        "name": "Rechenprobe",
        "verletzt": 0,
        "luecke": 0,
        "nicht_pruefbar": 0,
    }


def test_gleicher_wert_bei_allen_buendeln_ist_erfassungsluecke():
    luecken = erfassungsluecken(_bestand())
    assert luecken == {
        "congstar": ["6, 12 und 36 Monate nicht erfasst"],
        "o2": [
            "6 und 12 Monate nicht erfasst",
            "Anschluss bei allen 4 Bündeln 39,99 €",
        ],
    }


def test_gegenprobe_erfassungsluecke():
    bestand = _bestand()
    bestand[0]["anschlusspreis"] = 0.0
    bestand += [_satz("o2", 7, 6), _satz("o2", 8, 12)]
    assert "o2" not in erfassungsluecken(bestand)
    laufzeiten = ((1, 6), (2, 12), (3, 24), (4, 36))
    vodafone = [_satz("Vodafone", n, m, anschlusspreis=float(n)) for n, m in laufzeiten]
    assert erfassungsluecken(vodafone) == {}
    gleich = [{**s, "anschlusspreis": 0.0} for s in vodafone]
    assert erfassungsluecken(gleich) == {
        "Vodafone": ["Anschluss bei allen 4 Bündeln 0,00 €"]
    }, "0,00 € ist gemessen und bei allen gleich: Erfassungslücke"
    assert erfassungsluecken(gleich[:2]) == {
        "Vodafone": ["24 und 36 Monate nicht erfasst"]
    }, "zwei gleiche Werte sind zu wenig für eine Aussage"


def test_tarifbindung_ist_keine_erfassungsluecke_der_messung():
    """Die Seite zeigt die Tarifbindung aus dem Tarifblatt (Regel 7 nicht prüfbar);
    eine überall fehlende gemessene Bindung ist deshalb keine Aussage der Seite."""
    bestand = [
        _satz("o2", n, m, tarif_bindung_monate=None, anschlusspreis=float(n))
        for n, m in enumerate((6, 12, 24, 36))
    ]
    assert erfassungsluecken(bestand) == {}
    gleich = [{**s, "anschlusspreis": 39.99} for s in bestand]
    assert erfassungsluecken(gleich) == {
        "o2": ["Anschluss bei allen 4 Bündeln 39,99 €"]
    }, "Gegenprobe: ein gemessenes Pflichtfeld bleibt Erfassungslücke"


def _datei(bestand: list[dict], lauf: dict | None) -> str:
    """``geraete_tco.json`` wie nach einem Gerätelauf: Vermerk je Satz, Lauf-Eintrag."""
    saetze = [
        {**s, "pruefung": vermerk(s["pruefung"]).als_text()} if "pruefung" in s else s
        for s in bestand
    ]
    daten = {"updated": HEUTE, "buendel": saetze, "sim_only": []}
    return json.dumps(daten if lauf is None else {**daten, "pruefung": lauf})


def test_ansicht_liest_den_lauf_eintrag(tmp_path):
    leer = {"vorhanden": False, "fehler": "", "lauf": ""}
    assert geraete_pruefkennzahlen.aufbereiten(tmp_path) == leer
    datei = tmp_path / geraete_pruefkennzahlen.DATEI
    datei.write_text("{kaputt", encoding="utf-8")
    kaputt = geraete_pruefkennzahlen.aufbereiten(tmp_path)
    assert kaputt["fehler"].startswith("geraete_tco.json unlesbar"), kaputt
    datei.write_text(_datei(_bestand(), None), encoding="utf-8")
    assert geraete_pruefkennzahlen.aufbereiten(tmp_path) == leer, "noch kein Lauf"
    lauf = {"lauf": HEUTE, **_kennzahlen(_bestand())}
    datei.write_text(_datei(_bestand(), lauf), encoding="utf-8")
    daten = geraete_pruefkennzahlen.aufbereiten(tmp_path)
    assert (daten["vorhanden"], daten["lauf"]) == (True, HEUTE)
    assert daten["summe"] == _kennzahlen(_bestand())["summe"]
    fehler = {"lauf": HEUTE, "fehler": "RuntimeError: kaputt"}
    datei.write_text(_datei(_bestand(), fehler), encoding="utf-8")
    daten = geraete_pruefkennzahlen.aufbereiten(tmp_path)
    assert (daten["vorhanden"], daten["fehler"]) == (False, "RuntimeError: kaputt")


def _quellenseite(tmp_path, inhalt: str | None) -> BeautifulSoup:
    """Rendert die Quellen-Seite mit ``inhalt`` als ``geraete_tco.json``."""
    if inhalt is not None:
        zustand = tmp_path / "data" / "state"
        zustand.mkdir(parents=True)
        (zustand / geraete_pruefkennzahlen.DATEI).write_text(inhalt, encoding="utf-8")
    html = lies_seite(render(tmp_path), "transparenz.html")
    return BeautifulSoup(html, "html.parser")


def _karten(karte) -> dict[str, dict[str, str]]:
    return {
        a["data-anbieter"]: {
            z.select_one(".fwb-name").get_text(): z.select_one(
                ".fwb-zustand"
            ).get_text()
            for z in a.select(".fwb-ind")
        }
        for a in karte.select("article.fwb-frage")
    }


def test_quellenseite_zeigt_die_kennzahlen_aus_den_daten(tmp_path):
    inhalt = _datei(_bestand(), {"lauf": HEUTE, **_kennzahlen(_bestand())})
    karte = _quellenseite(tmp_path, inhalt).select_one("#geraete-pruefung")
    assert karte is not None, "Karte der Prüfstelle fehlt auf der Quellen-Seite"
    kacheln = {
        k.find("span").get_text(): k.find("b").get_text()
        for k in karte.select(".t-kennzahl")
    }
    assert kacheln == {
        "gültig": "1",
        "Quarantäne": "2",
        "veraltet": "1",
        "nicht geprüft": "1",
        "Prüfung gescheitert": "1",
    }
    karten = _karten(karte)
    assert karten["o2"] == {
        "Bündel": "4",
        "gültig 24 Monate": "1",
        "gültig 36 Monate": "0",
        "frisch": "75 %",
        "Quarantäne": "50 %",
        "Konflikte": "100 % von 1, 3 nicht prüfbar",
        "Belege": "50 % von 2, 2 nicht prüfbar",
        "nicht prüfbar": "Regel 11",
    }
    assert "gültig 6 Monate" not in karten["o2"], "nicht erfasst steht als Lücke"
    quoten = [karten["congstar"][n] for n in ("frisch", "Quarantäne", "Belege")]
    assert quoten == ["nicht prüfbar"] * 3, "nie 0 % ohne Nenner"
    o2 = karte.select_one('article[data-anbieter="o2"]').get_text(" ", strip=True)
    assert "6 und 12 Monate nicht erfasst · Anschluss bei allen 4 Bündeln 39,99 €" in o2
    assert "Prüfung gescheitert: RuntimeError: kaputt" in karte.get_text(
        " ", strip=True
    )


def test_ohne_geraetelauf_entfaellt_die_karte(tmp_path):
    assert (
        _quellenseite(tmp_path / "ohne", None).select_one("#geraete-pruefung") is None
    )
    ohne_lauf = _quellenseite(tmp_path / "alt", _datei(_bestand(), None))
    assert ohne_lauf.select_one("#geraete-pruefung") is None, "noch nie geprüft"
    ausfall = _quellenseite(tmp_path / "kaputt", "{kaputt").select_one(
        "#geraete-pruefung"
    )
    assert ausfall is not None, "eine unlesbare Datei ist ein Ausfall, kein Nichts"
    assert "Prüfung nicht lesbar: geraete_tco.json unlesbar" in ausfall.get_text()


def test_quote_nennt_nicht_pruefbare_buendel(tmp_path):
    """1 von 10 o2-Bündeln hat einen Beleg: nie „Belege 100 %“ ohne die 9 daneben."""
    bestand = [_satz("o2", 1, 24, _p("gueltig"))] + [
        _satz("o2", n, 24, _p("gueltig", nicht=[13])) for n in range(2, 11)
    ]
    lauf = {"lauf": HEUTE, **_kennzahlen(bestand)}
    o2 = _zeile(lauf, "o2")
    assert o2["belegquote"] == {
        "zahl": 1,
        "von": 1,
        "prozent": 100,
        "nicht_pruefbar": 9,
    }
    karte = _quellenseite(tmp_path, _datei(bestand, lauf)).select_one(
        "#geraete-pruefung"
    )
    zeilen = _karten(karte)["o2"]
    assert zeilen["Belege"] == "100 % von 1, 9 nicht prüfbar", zeilen
    assert zeilen["frisch"] == "100 %", "Gegenprobe: ohne nicht prüfbare nur die Quote"
