"""P0-B-z2: Spaltenkopf und Sortierung der Buendeltafel ueber ZWEI Zeitraeumen.

Die Buendeltafel ist die einzige Tafel der Seite, in der beide Zeitraeume
der Leitzahl wirklich untereinander stehen: getrennt gezahlte Angebote
tragen 24 Monate, ein Angebot mit 36 Raten 36 Monate (seit 10.10.2026 wird
1&1 nur ueber 24 Monate verglichen; die Fixture mischt darum mit Telekom).
Genau dort standen zwei Aussagen, die niemand gemessen hat:

  1. Der Spaltenkopf behauptete fest "Kosten über 24 Monate" - auch ueber
     einer Zeile, deren Etikett "Kosten über 36 Monate" sagt.
  2. Derselbe Kopf IST der Sortierknopf: `app.js` sortierte nach
     `data-gesamt` allein und stellte die 36-Monats-Summe damit in EINEN
     Rang mit den 24-Monats-Summen.

Beides wird hier an einer Fixture mit GEMISCHTEN Zeitraeumen gemessen -
am echten Makro. Seit 10.10.2026 steht die Bündelliste nicht mehr auf der
Seite; geprüft wird das Fragment `data/geraete-buendel.html` (Zeilen,
Daten-Attribute, Laufzeit-Gruppen) und die Server-Vorsortierung.

Die GEGENPROBEN stehen je Test: eine Fixture ohne 36-Monats-Zeile waere
mit jeder Sortierung gruen, und ein Kopf ohne Monatszahl ist nur dann eine
Aussage, wenn die Zeilen darunter ihren Zeitraum selbst nennen.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml
from bs4 import BeautifulSoup
from tarifleiter_testbestand import mit_leiter
from test_geraete_browser_fixture import (
    _FARBEN,
    _KATALOG,
    _QUELLEN,
    HEUTE,
    _listung,
    _sku,
)

from telco_radar.report.geraete_tco_view import _zeilen_rang
from telco_radar.report.html import _env, render_site

WURZEL = pathlib.Path(__file__).resolve().parents[1]
DEVICE = "apple-iphone-17-pro"
MODELL = "apple-iphone-17-pro-256"

_RATEN = [
    ("o2", "o2:klein", "O2 Mobile Klein", 10, 18.0),
    ("congstar", "cs:klein", "Allnet Flat XS", 15, 10.0),
    ("Vodafone", "vf:klein", "Vodafone Mobil XS", 18, 26.0),
]
_ZUSAMMEN = ("Telekom", "tk:klein", "MagentaMobil S", 12, 16.0, 1.0, 36)

_SOLL = {"congstar": 840.76, "o2": 1032.76, "Telekom": 1176.76, "Vodafone": 1224.76}


def _baue(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "site_baum"
    (root / "config").mkdir(parents=True)
    for name, daten in (
        ("geraete_katalog.yaml", _KATALOG),
        ("farben.yaml", _FARBEN),
        ("geraete_quellen.yaml", _QUELLEN),
    ):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(
        json.dumps(
            {
                "updated": HEUTE,
                "anbieter": {
                    n: {"laeufe": 4, "funde_gesamt": 1}
                    for n in ("Vodafone", "o2", "Telekom", "congstar")
                },
                "listungen": [
                    _listung("Vodafone", DEVICE, 256, 1199.90),
                    _listung("o2", DEVICE, 256, 1099.00),
                ],
            }
        ),
        encoding="utf-8",
    )
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = []
    for anbieter, tarif_id, tarif, _gb, rate in _RATEN:
        buendel.append(
            {
                "id": f"buendel--{anbieter.lower()}--{_sku(DEVICE, 256)}"
                f"--{tarif_id}--24",
                "sku_id": _sku(DEVICE, 256),
                "anbieter": anbieter,
                "tarif_name": tarif,
                "tarif_id": tarif_id,
                "tarif_id_guete": "hoch",
                "tarif_monatlich": 24.99,
                "tarif_bindung_monate": 24,
                "geraet_zuzahlung": 1.0,
                "geraet_monatsrate": rate,
                "laufzeit_monate": 24,
                "anschlusspreis": 0.0,
                "zustand": "neu",
                "rabatte": [],
                "quelle_url": f"https://example.de/{anbieter.lower()}/{DEVICE}",
                "abgerufen_am": HEUTE,
                "first_seen": HEUTE,
                "last_verified": HEUTE,
            }
        )
    anbieter, tarif_id, tarif, _gb, rate, zuzahlung, laufzeit = _ZUSAMMEN
    buendel.append(
        {
            "id": f"buendel--telekom--{_sku(DEVICE, 256)}--{tarif_id}--{laufzeit}",
            "sku_id": _sku(DEVICE, 256),
            "anbieter": anbieter,
            "tarif_name": tarif,
            "tarif_id": tarif_id,
            "tarif_id_guete": "hoch",
            "tarif_monatlich": 24.99,
            "geraet_monatsrate": rate,
            "tarif_bindung_monate": 24,
            "geraet_zuzahlung": zuzahlung,
            "laufzeit_monate": laufzeit,
            "anschlusspreis": 0.0,
            "zustand": "neu",
            "rabatte": [],
            "quelle_url": "https://example.de/telekom/s",
            "abgerufen_am": HEUTE,
            "first_seen": HEUTE,
            "last_verified": HEUTE,
        }
    )
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8",
    )
    tarife = [
        {
            "anbieter": a,
            "name": t,
            "tarif_id": tid,
            "art": "mobilfunk",
            "grundgebuehr": 24.99,
            "laufzeit_monate": 24,
            "datenvolumen_gb": gb,
            "preisphasen": [{"von_monat": 1, "bis_monat": None, "betrag": 24.99}],
            "dokument_url": f"https://example.de/pib/{tid}",
            "abgerufen_am": HEUTE,
            "confidence": {},
            "fundstellen": {},
        }
        for a, tid, t, gb in [(a, tid, t, gb) for a, tid, t, gb, _r in _RATEN]
        + [(_ZUSAMMEN[0], _ZUSAMMEN[1], _ZUSAMMEN[2], _ZUSAMMEN[3])]
    ]
    tarife = mit_leiter(tarife)
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8"
    )
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(
        json.dumps(
            {
                "date": HEUTE,
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _baue(tmp_path_factory.mktemp("z2kopf"))


@pytest.fixture(scope="module")
def suppe(site):
    return BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )


@pytest.fixture(scope="module")
def lager(site):
    return BeautifulSoup(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        "html.parser",
    )


def _zeilen(lager):
    return lager.select("#gr-bnd-vorgabe #gr-bndliste .gr-bnd")


def _gruppen(lager) -> dict[str, list]:
    """Die Zeilen je Laufzeit-Gruppe (`data-lz`), in Fragment-Reihenfolge."""
    gruppen: dict[str, list] = {}
    for z in _zeilen(lager):
        gruppen.setdefault(z.get("data-lz", ""), []).append(z)
    return gruppen


def _etikett_monate(zeile) -> int | None:
    etikett = zeile.select_one(".gr-bnd-tco .gr-bnd-label")
    if not etikett:
        return None
    text = etikett.get_text(strip=True)
    assert text.startswith("Kosten über "), text
    return int(text.split()[2])


def test_die_fixture_mischt_wirklich_zwei_zeitraeume(lager):
    """GEGENPROBE zu allem, was folgt: vier Zeilen in EINEM Band, drei mit
    24 und eine mit 36 Monaten - und die 36er faellt nach Betrag MITTEN in
    die Reihe. Traegt die Fixture das nicht, sind die Tests darunter mit
    jedem Kopf und jeder Sortierung gruen. Seit 10.10.2026 steht die
    Bündelliste nicht mehr auf der Seite; geprüft wird das Fragment."""
    zeilen = _zeilen(lager)
    assert len(zeilen) == 4, [z.get("data-anbieter") for z in zeilen]
    betraege = {z["data-anbieter"]: float(z["data-gesamt"]) for z in zeilen}
    assert betraege == pytest.approx(_SOLL), betraege
    monate = {z["data-anbieter"]: _etikett_monate(z) for z in zeilen}
    assert monate == {"congstar": 24, "o2": 24, "Vodafone": 24, "Telekom": 36}, monate
    rang = sorted(betraege, key=lambda a: betraege[a])
    assert rang == ["congstar", "o2", "Telekom", "Vodafone"], rang


def test_der_spaltenkopf_der_buendeltafel_nennt_keine_monatszahl(suppe, lager):
    """Gegen den alten Stand rot: dort stand fest "Kosten über 24 Monate"
    im Kopf UND in seinem `aria-label`, ueber einer Zeile mit dem Etikett
    "Kosten über 36 Monate" in derselben Spalte. Seit 10.10.2026 steht die
    Bündelliste nicht mehr auf der Seite; geprüft wird, dass der Teil unter
    dem Graphen keinen Kopf und keinen Zeitraum mehr behauptet und der
    Zeitraum im Fragment an jeder Zeile steht."""
    teil = suppe.select_one("#gr-buendel")
    assert teil is not None, "#gr-buendel fehlt - Lookup leer"
    assert teil.select_one(".gr-bnd-kopf") is None, "der Spaltenkopf ist zurück"
    assert teil.select_one("button[data-bsort]") is None, "ein Sortierknopf ist zurück"
    text = " ".join(teil.get_text(" ", strip=True).split())
    assert "Kosten über" not in text and "Monate" not in text, text

    monate = sorted({_etikett_monate(z) for z in _zeilen(lager)})
    assert monate == [24, 36], monate


def _ohneband_kopf() -> str:
    """Der Kopf der Gruppe „Ohne Tarifband“ am ECHTEN Makro - die Fixture
    trägt keine Zeile ohne Band, die Gruppe wird darum direkt gebaut."""
    karte = _finanzierungskarte(36)
    karte["band"] = None
    modell = {
        "alt_hinweis": "",
        "zeilen_band": [],
        "fehlzeilen": [],
        "zeilen_ohne_band": [karte],
        "haendler_ohne_buendel": {},
    }
    gruppe = BeautifulSoup(
        _env()
        .from_string(
            '{% from "_geraete_buendel.html.j2" import buendelgruppe %}'
            "{{ buendelgruppe(m) }}"
        )
        .render(m=modell),
        "html.parser",
    )
    kopf = gruppe.select_one(".gr-ohneband .gr-bnd-kopf")
    assert kopf is not None, "die Gruppe ohne Tarifband trägt keinen Kopf"
    return " ".join(kopf.get_text(" ", strip=True).split())


def test_auch_die_gruppe_ohne_tarifband_nennt_die_spalte_ohne_zeitraum(site):
    """Dieselbe Spalte, zweiter Kopf: die Gruppe "Ohne Tarifband" trug die
    24 als eigene Textkopie. Zwei Koepfe mit zwei Texten waeren die
    naechste Stelle, an der Tafel und Gruppe auseinanderlaufen. Seit
    10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    werden Seite, Fragment und der Kopf am echten Makro."""
    texte = []
    for pfad in ("geraete.html", "data/geraete-buendel.html"):
        datei = site / pfad
        if not datei.exists():
            continue
        suppe = BeautifulSoup(datei.read_text(encoding="utf-8"), "html.parser")
        texte += [k.get_text(" ", strip=True) for k in suppe.select(".gr-bnd-kopf")]
    texte.append(_ohneband_kopf())
    assert all("Monate" not in t for t in texte), texte
    assert all("Kosten mit Tarif" in t for t in texte), texte


def test_jede_zeile_traegt_ihren_zeitraum_als_sortiergruppe(lager):
    """`data-leitzahl-monate` ist das Feld, das app.js liest - es MUSS
    dieselbe Zahl sein, die das Etikett derselben Zeile nennt (eine
    Beschriftungsregel, eine Gruppierung).

    Gegen den alten Stand rot: das Attribut gab es nicht, und `data-
    laufzeit` daneben war fuer JEDE Zeile 24 - auch fuer die 36er. Seit
    Datenkonzept Geräte Schritt 2 ist `karte["laufzeit"]` der Zeitraum H der
    Kernzahl und damit dieselbe Zahl wie das Etikett. Seit 10.10.2026 steht
    die Bündelliste nicht mehr auf der Seite; geprüft wird das Fragment.
    """
    zeilen = _zeilen(lager)
    paare = [(z.get("data-leitzahl-monate"), _etikett_monate(z)) for z in zeilen]
    assert all(a for a, _e in paare), paare
    assert all(int(a) == e for a, e in paare), paare
    assert all(z.get("data-laufzeit") == z.get("data-leitzahl-monate") for z in zeilen)
    assert {z.get("data-laufzeit") for z in zeilen} == {"24", "36"}


def test_ohne_gemessenen_zeitraum_bleibt_die_sortiergruppe_leer():
    """Eine Zeile ohne belastbare Zahl hat keinen Zeitraum - das Attribut
    steht LEER da, nicht auf 0 und nicht auf 24 (Clean Code 3: 0 nur, wo 0
    eine Aussage ist)."""
    leer = {
        "anbieter": "Telekom",
        "tarif": "",
        "zustand": "",
        "zustand_etikett": "",
        "belastbar": False,
        "label": "",
        "gesamt": None,
        "schnitt_monat": None,
        "laufzeit": None,
        "leitzahl_monate": None,
        "raten_laufzeit": None,
        "tarif_bindung": None,
        "geraetepreis": None,
        "geraetepreis_art": None,
        "zuzahlung": None,
        "monatlich": None,
        "buendel_monatlich": None,
        "naeherung": False,
        "eigen": False,
        "delta": None,
        "delta_kurz": "",
        "delta_zustand": None,
        "sku_id": "",
        "quelle_url": "",
        "abgerufen_am": "",
        "leer_grund": "Kein Bündel erhoben",
        "alt_marke": "",
        "frisch": True,
        "band": "xs",
        "band_gb_text": "",
    }
    zeile = BeautifulSoup(
        _env()
        .from_string(
            '{% from "_geraete_buendel.html.j2" import buendelzeile %}'
            "{{ buendelzeile(k) }}"
        )
        .render(k=leer),
        "html.parser",
    ).select_one(".gr-bnd")
    assert zeile.get("data-leitzahl-monate") == "", zeile.attrs
    assert zeile.get("data-gesamt") == "", zeile.attrs
    assert "Kein Bündel erhoben" in "".join(zeile.find_all(string=True))


def test_die_sortierung_stellt_zwei_zeitraeume_nicht_in_einen_rang(lager):
    """Der Befund im Browser: ein Klick auf den Kopf stellte die
    36-Monats-Summe (1.176,76 EUR) zwischen o2 (1.032,76) und Vodafone
    (1.224,76) - als waere sie teurer als die eine und guenstiger als die
    andere. Beides ist nicht gemessen.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment: jeder Zeitraum ist eine eigene Laufzeit-Gruppe mit
    eigenem Kopf, und innerhalb der Gruppe steht die Vorsortierung nach
    Betrag. Der alte Rang [congstar, o2, Telekom, Vodafone] ist keine
    Gruppenfolge.
    """
    gruppen = _gruppen(lager)
    assert sorted(gruppen) == ["24", "36"], sorted(gruppen)
    for lz, zeilen in gruppen.items():
        assert {z.get("data-leitzahl-monate") for z in zeilen} == {lz}, lz
        betraege = [float(z["data-gesamt"]) for z in zeilen]
        assert betraege == sorted(betraege), (lz, betraege)
    reihe = [z["data-anbieter"] for lz in ("24", "36") for z in gruppen[lz]]
    assert reihe == ["congstar", "o2", "Vodafone", "Telekom"], reihe
    koepfe = [
        h.get("data-lz-kopf")
        for h in lager.select("#gr-bnd-vorgabe #gr-bndliste h4[data-lz-kopf]")
    ]
    assert koepfe == ["24", "36"], koepfe
    etikett = gruppen["36"][-1].select_one(".gr-bnd-label").get_text(strip=True)
    assert etikett == "Kosten über 36 Monate", etikett


def test_die_umgekehrte_richtung_dreht_nur_innerhalb_des_zeitraums(lager):
    """Der Zeitraum ist kein Wert, der rangiert, sondern der Rahmen, in dem
    rangiert wird: die umgekehrte Folge dreht die Betraege INNERHALB der
    24-Monats-Gruppe - die 36er bleibt fuer sich und wandert nicht als
    "guenstigstes Angebot" nach vorn. Seit 10.10.2026 steht die
    Bündelliste nicht mehr auf der Seite; geprüft wird die Gruppe im
    Fragment, die die 36er nicht enthält."""
    gruppen = _gruppen(lager)
    rueckwaerts = sorted(
        gruppen["24"], key=lambda z: float(z["data-gesamt"]), reverse=True
    )
    assert [z["data-anbieter"] for z in rueckwaerts] == ["Vodafone", "o2", "congstar"]
    assert [z["data-anbieter"] for z in gruppen["36"]] == ["Telekom"]
    assert all(z.get("data-leitzahl-monate") == "24" for z in rueckwaerts)


def test_eine_zeile_ohne_gemessenen_zeitraum_rangiert_hinten_und_bleibt():
    """Der dritte Zustand: kein gemessener Zeitraum (leeres Attribut). Er
    wird nicht als 24 angenommen (Clean Code 4) - die Zeile steht hinter
    allen gemessenen Zeilen und bleibt in der Liste. Seit 10.10.2026 steht
    die Bündelliste nicht mehr auf der Seite; geprüft wird die
    Server-Vorsortierung (`_zeilen_rang`) und das Attribut am echten Makro."""

    def karte(anbieter, gesamt):
        k = _finanzierungskarte(24)
        k.update({"anbieter": anbieter, "gesamt": gesamt})
        if gesamt is None:
            k.update(
                {
                    "belastbar": False,
                    "leitzahl_monate": None,
                    "laufzeit": None,
                    "leer_grund": "Kein Bündel erhoben",
                }
            )
        return k

    karten = [
        karte("congstar", None),
        karte("o2", 1032.76),
        karte("Vodafone", 1224.76),
        karte("Telekom", 840.76),
    ]
    reihe = sorted(karten, key=_zeilen_rang)
    assert len(reihe) == 4, reihe
    assert [k["anbieter"] for k in reihe] == ["Telekom", "o2", "Vodafone", "congstar"]
    zeile = BeautifulSoup(
        _env()
        .from_string(
            '{% from "_geraete_buendel.html.j2" import buendelzeile %}'
            "{{ buendelzeile(k) }}"
        )
        .render(k=reihe[-1]),
        "html.parser",
    ).select_one(".gr-bnd")
    assert zeile.get("data-leitzahl-monate") == "", zeile.attrs


def test_die_anbieter_sortierung_bleibt_eine_reine_namensfolge(lager):
    """GEGENPROBE zur Gruppierung nach Zeitraum: sie gilt NUR fuer den
    Kostenrang. Unter „alle“ steht zuerst die Laufzeit-Gruppe (Datenkonzept
    Geräte 5.4: 24 Raten nie in einem Rang mit 36); innerhalb der Gruppe ist
    die Anbieterfolge eine reine Namensfolge. Seit 10.10.2026 steht die
    Bündelliste nicht mehr auf der Seite; geprüft wird das Fragment: der
    Sortierschlüssel `data-anbieter` ist der angezeigte Name selbst."""
    gruppen = _gruppen(lager)
    for zeilen in gruppen.values():
        for z in zeilen:
            assert z["data-anbieter"] == z.select_one(".gr-bnd-name").get_text(
                strip=True
            )
    namen = [z["data-anbieter"] for z in gruppen["24"]]
    assert sorted(namen, key=str.lower) == ["congstar", "o2", "Vodafone"], namen
    assert [z["data-anbieter"] for z in gruppen[max(gruppen)]] == ["Telekom"]


def _zeile_text(karte: dict) -> str:
    """Der Text EINER Buendelzeile am ECHTEN Makro - auch der im
    `<template>`, wo der Rechenweg seit dem P4-Fix liegt (dieselbe Lesart
    wie `tests/test_geraete_laufzeit_auf_der_seite.vorlage_text`)."""
    zeile = BeautifulSoup(
        _env()
        .from_string(
            '{% from "_geraete_buendel.html.j2" import buendelzeile %}'
            "{{ buendelzeile(k) }}"
        )
        .render(k=karte),
        "html.parser",
    )
    return " ".join("".join(zeile.find_all(string=True)).split())


def _finanzierungskarte(raten_laufzeit) -> dict:
    """Eine Zeile mit Finanzierungssumme - wie die Referenzrechnung, die
    ihre `geraetepreis_art` aus dem Quellbuendel uebernimmt
    (`geraete_tco_karten._referenzkarte`) und dabei KEINE Ratenlaufzeit
    mitbringt."""
    return {
        "anbieter": "Vodafone",
        "tarif": "Vodafone Mobil XS",
        "zustand": "neu",
        "zustand_etikett": "",
        "belastbar": True,
        "label": "Kosten über 24 Monate",
        "gesamt": 1500.0,
        "schnitt_monat": 62.5,
        "laufzeit": 24,
        "leitzahl_monate": 24,
        "raten_laufzeit": raten_laufzeit,
        "tarif_bindung": 24,
        "geraetepreis": 900.0,
        "geraetepreis_art": "finanzierung",
        "zuzahlung": 1.0,
        "monatlich": 24.99,
        "rate": 37.46,
        "raten_summe": 899.0,
        "buendel_monatlich": None,
        "anschlusspreis": None,
        "nach_bindung": 29.99,
        "gezahlt_nach_24": 1500.0,
        "offen_nach_24": None,
        "offene_raten": 0,
        "eff_ohne_geraet": None,
        "eff_basis": None,
        "bestandteile": [],
        "luecken": [],
        "boni": [],
        "delta": None,
        "delta_kurz": "",
        "delta_zustand": None,
        "naeherung": False,
        "eigen": True,
        "frisch": True,
        "alt_marke": "",
        "sku_id": "x",
        "quelle_url": "",
        "abgerufen_am": "",
        "tarif_quelle_url": "",
        "band": "xs",
        "band_gb_text": "",
        "ab_preis": False,
        "leer_grund": "",
    }


def test_ohne_gemessene_ratenzahl_steht_keine_24_im_paradox_satz():
    """Gegen den alten Stand rot: `{{ k.raten_laufzeit or k.laufzeit }}`
    fiel auf `k.laufzeit` (die Konstante 24) zurueck und behauptete "alle
    24 Geräteraten", wo keine Ratenzahl gemessen ist."""
    text = _zeile_text(_finanzierungskarte(None))
    assert "alle 24 Geräteraten" not in text, text
    assert "Anzahl nicht gemessen" in text, text

    text36 = _zeile_text(_finanzierungskarte(36))
    assert "alle 36 Geräteraten" in text36, text36
    assert "Anzahl nicht gemessen" not in text36, text36


def test_ohne_gemessene_ratenzahl_steht_keine_24_am_buendelmonatspreis():
    """Derselbe Rueckfall am zusammengelegten Monatsbetrag (1&1): ohne
    gemessene Laufzeit stand dort "24 Monate" - eine Zahl, die dieser
    Betrag nie getragen hat."""
    karte = _finanzierungskarte(None)
    karte.update(
        {
            "buendel_monatlich": 30.0,
            "geraetepreis": None,
            "geraetepreis_art": None,
            "rate": None,
            "raten_summe": None,
        }
    )
    text = _zeile_text(karte)
    assert "zusammen · 24 Monate" not in text, text
    assert "None" not in text, text
    assert "Laufzeit nicht gemessen" in text, text

    karte["raten_laufzeit"] = 36
    text36 = _zeile_text(karte)
    assert "zusammen · 36 Monate" in text36, text36
    assert "Laufzeit nicht gemessen" not in text36, text36
