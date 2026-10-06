"""Prüfstelle der Geräte-Bündel: je Regel aus Abschnitt 9 ein Fall und eine Gegenprobe.

Datenkonzept Geräteradar, Schritt 7. Der Grundsatz ``_satz()`` steht so in
``geraete_tco.json`` und besteht jede Regel; ``_kontext`` liefert alle Daten, damit
jede Regel an ihm prüfbar ist. Ein Fall ändert genau einen Wert und erwartet Regel,
Status und Satz; seine Gegenprobe ändert denselben Wert so, dass die Regel besteht.
Fester Bezugstag, nie das heutige Datum.
"""

from __future__ import annotations

import pytest

from telco_radar.analyze.geraete_pruefstatus import (
    GUELTIG,
    NICHT_PRUEFBAR,
    QUARANTAENE,
    VERALTET,
    Kontext,
    buendel_aus_satz,
)
from telco_radar.analyze.geraete_regeln import pruefe_bestand, sim_only_tabelle
from telco_radar.collect.geraete.klicktext import volumen_aus_zeile
from telco_radar.tco_model import buendel_id

HEUTE = "2026-10-03"
VORTAG = "2026-10-02"
INF = float("inf")
TARIF = "O2 Mobile M 50 GB"
TARIF_ID = "o2-mobile-m"
SKU = {128: "pruefer-phone-128-schwarz", 256: "pruefer-phone-256-schwarz"}
ABGELAUFEN = {
    "art": "anschluss_erlassen",
    "bedingung": "Online-Aktion",
    "quelle_url": "https://example.org/o2/aktion",
    "eingerechnet": True,
    "gueltig_bis": "2026-09-29",
}


def _satz(speicher: int = 128, **aenderung) -> dict:
    """Ein getrennt bepreistes o2-Bündel: 1 € + 24 × 30 € Gerät, 30 € Tarif."""
    satz = {
        "sku_id": SKU[speicher],
        "anbieter": "o2",
        "tarif_name": TARIF,
        "tarif_id": TARIF_ID,
        "tarif_monatlich": 30.0,
        "tarif_bindung_monate": 24,
        "geraet_zuzahlung": 1.0,
        "geraet_monatsrate": 30.0,
        "laufzeit_monate": 24,
        "anschlusspreis": 39.99,
        "quelle_url": "https://example.org/o2",
        "abgerufen_am": HEUTE,
        **aenderung,
    }
    zuzahlung, rate = satz["geraet_zuzahlung"], satz["geraet_monatsrate"]
    laufzeit = satz["laufzeit_monate"]
    if None not in (zuzahlung, rate, laufzeit):
        satz.setdefault("geraet_summe", round(zuzahlung + rate * laufzeit, 2))
    satz.setdefault("echo", {"werte": {"ratenzahl": laufzeit}, "befunde": []})
    satz.setdefault(
        "beleg_variante", {"laufzeit": laufzeit, "tarif": TARIF, "speicher": speicher}
    )
    satz["id"] = buendel_id(
        satz["sku_id"], satz["anbieter"], satz["tarif_name"], laufzeit
    )
    return satz


def _speicher(sku: str) -> tuple[str, int | None]:
    return ("pruefer-phone", int(sku.split("-")[2]))


def _kontext(saetze: tuple[dict, ...], **aenderung) -> Kontext:
    """Alle Daten, die die Regeln brauchen; der Vortag mit denselben Preisen."""
    referenz = {
        "anbieter": "o2",
        "tarif_name": TARIF,
        "tarif_id": TARIF_ID,
        "tarif_sim_only_monatlich": 30.0,
    }
    werte = {
        "heute": HEUTE,
        "frisch": lambda abgerufen, heute: abgerufen == heute,
        "geraet_von": _speicher,
        "volumen_im_namen": volumen_aus_zeile,
        "sim_only": sim_only_tabelle([referenz]),
        "uvp": {s["sku_id"]: s["geraet_summe"] for s in saetze if "geraet_summe" in s},
        "volumen": {TARIF_ID: 50.0},
        "vortag": {s["id"]: {"id": s["id"], "datum": VORTAG} for s in saetze},
    }
    return Kontext(**{**werte, **aenderung})


def _pruefe(*saetze: dict, **kontext) -> dict[str, dict]:
    ergebnis = pruefe_bestand(saetze, _kontext(saetze, **kontext))
    return {bid: e.als_feld() for bid, e in ergebnis.items()}


def _feld(satz: dict | None = None, **kontext) -> dict:
    satz = satz or _satz()
    return _pruefe(satz, **kontext)[satz["id"]]


def _gruende(feld: dict) -> dict[int, str]:
    return {g["regel"]: g["satz"] for g in feld["gruende"]}


def _erwaehnt(feld: dict, regel: int) -> bool:
    listen = (_gruende(feld), feld["luecken"], feld["nicht_pruefbar"])
    return any(regel in liste for liste in listen)


def test_grundsatz_besteht_jede_regel_und_jede_ausser_7_und_8_ist_pruefbar():
    leer = {"status": GUELTIG, "gruende": [], "luecken": [], "nicht_pruefbar": [7, 8]}
    assert _feld() == leer


FAELLE = [
    (1, {"geraet_summe": 800.0}, {}, QUARANTAENE, "die Seite nennt 800,00 €"),
    (2, {}, {"uvp": {SKU[128]: 1000.0}}, QUARANTAENE, "ist 72% der UVP"),
    (2, {}, {"uvp": {SKU[128]: 500.0}}, QUARANTAENE, "ist 144% der UVP"),
    (
        3,
        {},
        {"sim_only": {f"o2|{TARIF_ID}": 35.01}},
        QUARANTAENE,
        "unter SIM-only 35,01 € abzüglich 5,00 € Bündelnachlass",
    ),
    (
        4,
        {},
        {"volumen": {TARIF_ID: 100.0}},
        QUARANTAENE,
        "Tarifname nennt 50 GB, gemessen 100 GB",
    ),
    (
        6,
        {"laufzeit_monate": 18},
        {},
        QUARANTAENE,
        "18 Raten, erlaubt sind 6, 12, 24 und 36",
    ),
    (
        6,
        {"echo": {"werte": {"ratenzahl": 36}, "befunde": []}},
        {},
        QUARANTAENE,
        "24 Raten, Seite: 36",
    ),
    (
        9,
        {"echo": {"werte": {"ratenzahl": 24}, "befunde": [{"feld": "rate"}]}},
        {},
        QUARANTAENE,
        "Text und Antwort widersprechen sich: rate",
    ),
    (
        10,
        {"aktionen": [ABGELAUFEN]},
        {},
        VERALTET,
        "eingerechnete Aktion bis 29.09.2026 abgelaufen",
    ),
    (13, {"beleg_variante": {"laufzeit": 36}}, {}, QUARANTAENE, "andere Ratenlaufzeit"),
    (16, {"abgerufen_am": "2026-09-01"}, {}, VERALTET, "abgerufen am 01.09.2026"),
]


@pytest.mark.parametrize(
    "regel,satz,kontext,status,text", FAELLE, ids=[f"r{f[0]}" for f in FAELLE]
)
def test_verletzte_regel_setzt_status_mit_benanntem_grund(
    regel, satz, kontext, status, text
):
    feld = _feld(_satz(**satz), **kontext)
    assert feld["status"] == status, feld
    assert text in _gruende(feld).get(regel, ""), feld


GEGENPROBEN = [
    (1, {"geraet_summe": 721.99}, {}),
    (2, {}, {"uvp": {SKU[128]: 840.0}}),
    (2, {}, {"uvp": {SKU[128]: 560.0}}),
    (3, {"tarif_monatlich": 31.0}, {}),
    (4, {"tarif_name": "O2 Mobile Unlimited Max"}, {"volumen": {TARIF_ID: INF}}),
    (6, {"laufzeit_monate": 6}, {}),
    (6, {"laufzeit_monate": 12}, {}),
    (6, {"laufzeit_monate": 36}, {}),
    (9, {"echo": {"werte": {"ratenzahl": 24}, "befunde": []}}, {}),
    (10, {"aktionen": [{**ABGELAUFEN, "gueltig_bis": "2026-10-31"}]}, {}),
    (10, {"aktionen": [{**ABGELAUFEN, "eingerechnet": False}]}, {}),
    (13, {"beleg_variante": {"laufzeit": 24, "tarif": TARIF.upper()}}, {}),
    (16, {"abgerufen_am": HEUTE}, {}),
]


@pytest.mark.parametrize(
    "regel,satz,kontext", GEGENPROBEN, ids=[f"r{g[0]}" for g in GEGENPROBEN]
)
def test_gegenprobe_dieselbe_regel_besteht(regel, satz, kontext):
    feld = _feld(_satz(**satz), **kontext)
    assert not _erwaehnt(feld, regel), feld


def test_sprung_zum_vortag_ist_quarantaene_bis_zum_zweiten_abruf():
    satz = _satz()
    alt = {"id": satz["id"], "datum": VORTAG, "tarif_monatlich": 20.0}
    feld = _feld(satz, vortag={satz["id"]: alt})
    assert feld["status"] == QUARANTAENE
    assert _gruende(feld)[11] == (
        "1.480,99 € statt 1.240,99 € am 02.10.2026 (19%), "
        "Quarantäne bis zum zweiten Abruf"
    )
    gegen = {**alt, "tarif_monatlich": 28.0}
    assert not _erwaehnt(_feld(satz, vortag={satz["id"]: gegen}), 11), (
        "3 % ist kein Sprung"
    )


def test_ohne_vortag_ist_der_sprung_nicht_pruefbar_und_kein_grund():
    feld = _feld(vortag={})
    assert feld["nicht_pruefbar"] == [7, 8, 11]
    assert feld["status"] == GUELTIG


def test_speicher_monotonie_setzt_beide_buendel_in_quarantaene():
    klein = _satz(128)
    gross = _satz(256, geraet_monatsrate=25.0)
    felder = _pruefe(klein, gross)
    satz = "256 GB für 601,00 €, 128 GB für 721,00 €"
    for bid in (klein["id"], gross["id"]):
        assert felder[bid]["status"] == QUARANTAENE, felder[bid]
        assert _gruende(felder[bid]) == {5: satz}, felder[bid]


@pytest.mark.parametrize(
    "gross",
    [
        _satz(256, geraet_monatsrate=35.0),
        _satz(256, geraet_monatsrate=30.0),
        _satz(256, geraet_monatsrate=25.0, tarif_id="o2-mobile-l"),
    ],
    ids=["teurer", "gleich", "anderer-tarif"],
)
def test_gegenprobe_speicher_monotonie(gross):
    klein = _satz(128)
    felder = _pruefe(klein, gross)
    assert not any(_erwaehnt(f, 5) for f in felder.values()), felder


def test_speicher_ohne_katalog_ist_nicht_pruefbar():
    feld = _feld(geraet_von=lambda sku: ("", None))
    assert 5 in feld["nicht_pruefbar"]
    assert feld["status"] == GUELTIG


@pytest.mark.parametrize(
    "regel,o2_unter_sim_only,status",
    [
        (3, 5.00, GUELTIG),
        (3, 5.01, QUARANTAENE),
        (3, 4.00, GUELTIG),
    ],
    ids=["o2-genau-5", "o2-5,01", "o2-4"],
)
def test_o2_bundelnachlass_von_5_euro_ist_belegt(regel, o2_unter_sim_only, status):
    sim = {f"o2|{TARIF_ID}": round(30.0 + o2_unter_sim_only, 2)}
    feld = _feld(_satz(), sim_only=sim)
    assert feld["status"] == status, feld
    assert (regel in _gruende(feld)) is (status == QUARANTAENE)


@pytest.mark.parametrize(
    "sim_only,status", [(30.01, QUARANTAENE), (30.00, GUELTIG)], ids=["0,01", "gleich"]
)
def test_ohne_belegten_nachlass_zaehlt_jeder_cent(sim_only, status):
    congstar = _satz(anbieter="congstar")
    feld = _feld(congstar, sim_only={f"congstar|{TARIF_ID}": sim_only})
    assert feld["status"] == status, feld
    if status == QUARANTAENE:
        assert _gruende(feld)[3] == "Tarif mit Gerät 30,00 € unter SIM-only 30,01 €"


@pytest.mark.parametrize("bindung", [None, 0, 24])
@pytest.mark.parametrize("laufzeit", [24, 36])
def test_tarifbindung_und_preisphasen_zeigt_die_seite_aus_dem_tarifblatt(
    bindung, laufzeit
):
    """Die Ansicht ergänzt beides nur in report/: nicht prüfbar mit Grund, nie
    bestanden, und eine fehlende Bindung bleibt None statt 0."""
    satz = _satz(tarif_bindung_monate=bindung, laufzeit_monate=laufzeit)
    ergebnis = pruefe_bestand([satz], _kontext((satz,)))[satz["id"]]
    nicht = {b.regel: b.satz for b in ergebnis.je(NICHT_PRUEFBAR)}
    assert {7, 8} <= set(nicht), nicht
    assert all("Tarifblatt" in nicht[r] for r in (7, 8)), nicht
    feld = ergebnis.als_feld()
    assert not {7, 8} & set(feld["luecken"]) and not {7, 8} & set(_gruende(feld))
    assert 14 not in feld["luecken"], "die Tarifbindung prüft Regel 7, nicht 14"
    assert buendel_aus_satz(satz).tarif_bindung_monate == bindung


def test_fehlendes_pflichtfeld_ist_luecke_mit_namen():
    feld = _feld(_satz(geraet_zuzahlung=None))
    assert feld["luecken"] == [14], feld
    assert feld["status"] == GUELTIG
    vertrag = _satz(
        tarif_monatlich=None,
        geraet_monatsrate=None,
        buendel_monatlich=60.0,
        tarif_bindung_monate=None,
    )
    assert _feld(vertrag)["luecken"] == [], "Vertrag mit allen gemessenen Feldern"
    ohne_anschluss = {**vertrag, "anschlusspreis": None}
    assert _feld(ohne_anschluss)["luecken"] == [14]
    assert not _erwaehnt(_feld(_satz()), 14)


def test_ohne_ratenlaufzeit_fehlt_der_zeitraum():
    feld = _feld(_satz(laufzeit_monate=None))
    assert {6, 14, 15} <= set(feld["luecken"]), feld
    assert not _erwaehnt(_feld(), 15)


def test_unlesbarer_satz_ist_quarantaene_nach_regel_14():
    kaputt = {**_satz(), "anbieter": ""}
    feld = _pruefe(kaputt)[kaputt["id"]]
    assert feld["status"] == QUARANTAENE
    assert _gruende(feld)[14].startswith("Satz unlesbar")


def test_quarantaene_geht_vor_veraltet():
    satz = _satz(abgerufen_am="2026-09-01", geraet_summe=800.0)
    feld = _feld(satz)
    assert feld["status"] == QUARANTAENE
    assert sorted(_gruende(feld)) == [1, 16]
    assert _feld(_satz(abgerufen_am="2026-09-01"))["status"] == VERALTET


def test_regel_ohne_daten_ist_nicht_pruefbar_statt_bestanden():
    """Wie der Bestand heute: ohne Gerätesumme der Seite, Echo, Beleg, UVP, SIM-only
    und Vortag. Keine dieser Regeln gilt als bestanden, keine setzt Quarantäne."""
    satz = _satz(geraet_summe=None, echo=None, beleg_variante=None)
    feld = _feld(satz, uvp={}, sim_only={}, vortag={})
    assert feld["nicht_pruefbar"] == [1, 2, 3, 6, 7, 8, 9, 11, 13], feld
    assert feld["status"] == GUELTIG
    assert feld["gruende"] == []
