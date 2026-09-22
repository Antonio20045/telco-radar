"""P0-B-z2: Spaltenkopf und Sortierung der Buendeltafel ueber ZWEI Zeitraeumen.

Die Buendeltafel ist die einzige Tafel der Seite, in der beide Zeitraeume
der Leitzahl wirklich untereinander stehen: getrennt gezahlte Angebote
tragen 24 Monate, ein zusammengelegter Buendelmonatspreis (1&1) traegt
seine eigene Ratenlaufzeit - heute 36. Genau dort standen zwei Aussagen,
die niemand gemessen hat:

  1. Der Spaltenkopf behauptete fest "Kosten über 24 Monate" - auch ueber
     einer Zeile, deren Etikett "Kosten über 36 Monate" sagt.
  2. Derselbe Kopf IST der Sortierknopf: `app.js` sortierte nach
     `data-gesamt` allein und stellte die 36-Monats-Summe damit in EINEN
     Rang mit den 24-Monats-Summen.

Beides wird hier an einer Fixture mit GEMISCHTEN Zeitraeumen gemessen -
am echten Makro und im echten Chromium, weil die Sortierung im Browser
laeuft (CLAUDE.md: eine Rechnung, die im Browser laeuft, wird im Browser
getestet).

Die GEGENPROBEN stehen je Test: eine Fixture ohne 36-Monats-Zeile waere
mit jeder Sortierung gruen, und ein Kopf ohne Monatszahl ist nur dann eine
Aussage, wenn die Zeilen darunter ihren Zeitraum selbst nennen.
"""
from __future__ import annotations

import contextlib
import json
import pathlib

import pytest
import yaml
from bs4 import BeautifulSoup

from telco_radar.report.html import _env, render_site

from test_geraete_browser_fixture import (
    HEUTE, _KATALOG, _FARBEN, _QUELLEN, _chromium, _listung, _server, _sku)

WURZEL = pathlib.Path(__file__).resolve().parents[1]
DEVICE = "apple-iphone-17-pro"
MODELL = "apple-iphone-17-pro-256"

# VIER Anbieter in EINEM Band (Klein, alle Tarife unter 20 GB) - drei mit
# getrennter Rate (24 Monate) und 1&1 mit EINEM Monatsbetrag fuer Tarif und
# Geraet ueber 36 Monate. Die Betraege sind so gewaehlt, dass die
# 36-Monats-Summe MITTEN in die 24-Monats-Reihe faellt:
#
#   congstar  1 + 24 x 10,00 + 24 x 24,99 =   840,76 EUR   (24 Mon.)
#   o2        1 + 24 x 18,00 + 24 x 24,99 = 1.032,76 EUR   (24 Mon.)
#   1&1       100 + 36 x 30,00            = 1.180,00 EUR   (36 Mon.)
#   Vodafone  1 + 24 x 26,00 + 24 x 24,99 = 1.224,76 EUR   (24 Mon.)
#
# Eine Sortierung nach dem Betrag allein schiebt 1&1 also zwischen o2 und
# Vodafone - das ist der Befund, und daran wird gemessen.
_RATEN = [("o2", "o2:klein", "O2 Mobile Klein", 10, 18.0),
          ("congstar", "cs:klein", "Allnet Flat XS", 15, 10.0),
          ("Vodafone", "vf:klein", "Vodafone Mobil XS", 18, 26.0)]
_ZUSAMMEN = ("1&1", "11:klein", "All-Net-Flat S", 12, 30.0, 100.0, 36)

_SOLL = {"congstar": 840.76, "o2": 1032.76, "1&1": 1180.00,
         "Vodafone": 1224.76}


def _baue(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "site_baum"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {n: {"laeufe": 4, "funde_gesamt": 1}
                     for n in ("Vodafone", "o2", "1&1", "congstar")},
        "listungen": [_listung("Vodafone", DEVICE, 256, 1199.90),
                      _listung("o2", DEVICE, 256, 1099.00)]}),
        encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = []
    for anbieter, tarif_id, tarif, _gb, rate in _RATEN:
        buendel.append({
            "id": f"buendel--{anbieter.lower()}--{_sku(DEVICE, 256)}"
                  f"--{tarif_id}--24",
            "sku_id": _sku(DEVICE, 256), "anbieter": anbieter,
            "tarif_name": tarif, "tarif_id": tarif_id,
            "tarif_id_guete": "hoch", "tarif_monatlich": 24.99,
            "tarif_bindung_monate": 24,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": rate,
            "laufzeit_monate": 24, "anschlusspreis": 0.0,
            "zustand": "neu", "rabatte": [],
            "quelle_url": f"https://example.de/{anbieter.lower()}/{DEVICE}",
            "abgerufen_am": HEUTE, "first_seen": HEUTE,
            "last_verified": HEUTE})
    anbieter, tarif_id, tarif, _gb, monatlich, zuzahlung, laufzeit = _ZUSAMMEN
    buendel.append({
        "id": f"buendel--1und1--{_sku(DEVICE, 256)}--{tarif_id}--{laufzeit}",
        "sku_id": _sku(DEVICE, 256), "anbieter": anbieter,
        "tarif_name": tarif, "tarif_id": tarif_id, "tarif_id_guete": "hoch",
        # EIN Betrag fuer Tarif UND Geraet (§ 13.2) - kein `tarif_monatlich`,
        # keine `geraet_monatsrate`.
        "buendel_monatlich": monatlich, "tarif_bindung_monate": 24,
        "geraet_zuzahlung": zuzahlung, "laufzeit_monate": laufzeit,
        "anschlusspreis": 0.0, "zustand": "neu", "rabatte": [],
        "quelle_url": "https://example.de/1und1/anf-s",
        "abgerufen_am": HEUTE, "first_seen": HEUTE, "last_verified": HEUTE})
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")
    tarife = [
        {"anbieter": a, "name": t, "tarif_id": tid, "art": "mobilfunk",
         "grundgebuehr": 24.99, "laufzeit_monate": 24, "datenvolumen_gb": gb,
         "preisphasen": [{"von_monat": 1, "bis_monat": None,
                          "betrag": 24.99}],
         "dokument_url": f"https://example.de/pib/{tid}",
         "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}
        for a, tid, t, gb in
        [(a, tid, t, gb) for a, tid, t, gb, _r in _RATEN]
        + [(_ZUSAMMEN[0], _ZUSAMMEN[1], _ZUSAMMEN[2], _ZUSAMMEN[3])]]
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return _baue(tmp_path_factory.mktemp("z2kopf"))


@pytest.fixture(scope="module")
def suppe(site):
    return BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")


def _zeilen(suppe):
    return suppe.select("#gr-buendel #gr-bndliste .gr-bnd")


def _etikett_monate(zeile) -> int | None:
    etikett = zeile.select_one(".gr-bnd-tco .gr-bnd-label")
    if not etikett:
        return None
    text = etikett.get_text(strip=True)
    assert text.startswith("Kosten über "), text
    return int(text.split()[2])


# --------------------------------------------------------------------------
# Die Fixture selbst - ohne diese Gegenprobe prueft der Rest nichts
# --------------------------------------------------------------------------

def test_die_fixture_mischt_wirklich_zwei_zeitraeume(suppe):
    """GEGENPROBE zu allem, was folgt: vier Zeilen in EINEM Band, drei mit
    24 und eine mit 36 Monaten - und die 36er faellt nach Betrag MITTEN in
    die Reihe. Traegt die Fixture das nicht, sind die Tests darunter mit
    jedem Kopf und jeder Sortierung gruen."""
    zeilen = _zeilen(suppe)
    assert len(zeilen) == 4, [z.get("data-anbieter") for z in zeilen]
    betraege = {z["data-anbieter"]: float(z["data-gesamt"]) for z in zeilen}
    assert betraege == pytest.approx(_SOLL), betraege
    monate = {z["data-anbieter"]: _etikett_monate(z) for z in zeilen}
    assert monate == {"congstar": 24, "o2": 24, "Vodafone": 24, "1&1": 36}, \
        monate
    # Nach Betrag allein stuende 1&1 an Platz 3 von 4 - nicht am Rand, wo
    # eine Gruppierung ohnehin landet.
    rang = sorted(betraege, key=lambda a: betraege[a])
    assert rang == ["congstar", "o2", "1&1", "Vodafone"], rang


# --------------------------------------------------------------------------
# 1. Der Spaltenkopf behauptet keinen Zeitraum, den er nicht halten kann
# --------------------------------------------------------------------------

def test_der_spaltenkopf_der_buendeltafel_nennt_keine_monatszahl(suppe):
    """Gegen den alten Stand rot: dort stand fest "Kosten über 24 Monate"
    im Kopf UND in seinem `aria-label`, ueber einer Zeile mit dem Etikett
    "Kosten über 36 Monate" in derselben Spalte."""
    kopf = suppe.select_one("#gr-buendel .gr-bnd-kopf")
    assert kopf, "Kopf der Buendeltafel nicht gefunden - Lookup leer"
    knopf = kopf.select_one("button[data-bsort='tco']")
    assert knopf, "der Sortierknopf der Kostenspalte fehlt"
    text = knopf.get_text(" ", strip=True)
    beschriftung = f"{text} {knopf.get('aria-label', '')}"
    assert "Monate" not in beschriftung, beschriftung
    assert "24" not in beschriftung and "36" not in beschriftung, beschriftung
    # Die Spalte ist trotzdem benannt - und mit demselben Wort, mit dem der
    # Rechenweg jeder Zeile die Zahl erklaert ("mit Tarif").
    assert text == "Kosten mit Tarif", text
    assert knopf.get("aria-label"), "der Knopf braucht seine Vorlesehilfe"

    # GEGENPROBE: der Zeitraum ist nicht verschwunden, er steht an JEDER
    # Zahl - und zwar der gemessene.
    monate = sorted({_etikett_monate(z) for z in _zeilen(suppe)})
    assert monate == [24, 36], monate


def test_auch_die_gruppe_ohne_tarifband_nennt_die_spalte_ohne_zeitraum(site):
    """Dieselbe Spalte, zweiter Kopf: die Gruppe "Ohne Tarifband" trug die
    24 als eigene Textkopie. Zwei Koepfe mit zwei Texten waeren die
    naechste Stelle, an der Tafel und Gruppe auseinanderlaufen."""
    texte = []
    for pfad in ("geraete.html", "data/geraete-buendel.html"):
        datei = site / pfad
        if not datei.exists():
            continue
        suppe = BeautifulSoup(datei.read_text(encoding="utf-8"),
                              "html.parser")
        texte += [k.get_text(" ", strip=True)
                  for k in suppe.select(".gr-bnd-kopf")]
    assert texte, "kein einziger Spaltenkopf gefunden - Lookup leer"
    assert all("Monate" not in t for t in texte), texte
    assert all("Kosten mit Tarif" in t for t in texte), texte


# --------------------------------------------------------------------------
# 2. Der Zeitraum steht als Attribut an der Zeile - gelesen, nicht gebaut
# --------------------------------------------------------------------------

def test_jede_zeile_traegt_ihren_zeitraum_als_sortiergruppe(suppe):
    """`data-leitzahl-monate` ist das Feld, das app.js liest - es MUSS
    dieselbe Zahl sein, die das Etikett derselben Zeile nennt (eine
    Beschriftungsregel, eine Gruppierung).

    Gegen den alten Stand rot: das Attribut gab es nicht, und `data-
    laufzeit` daneben ist fuer JEDE Zeile 24 - auch fuer die 36er.
    """
    zeilen = _zeilen(suppe)
    paare = [(z.get("data-leitzahl-monate"), _etikett_monate(z))
             for z in zeilen]
    assert all(a for a, _e in paare), paare
    assert all(int(a) == e for a, e in paare), paare
    # GEGENPROBE: `data-laufzeit` taugt nicht als Gruppe - es ist die
    # Tariflaufzeit der Rechnung und ueberall 24.
    assert {z.get("data-laufzeit") for z in zeilen} == {"24"}, \
        [z.get("data-laufzeit") for z in zeilen]


def test_ohne_gemessenen_zeitraum_bleibt_die_sortiergruppe_leer():
    """Eine Zeile ohne belastbare Zahl hat keinen Zeitraum - das Attribut
    steht LEER da, nicht auf 0 und nicht auf 24 (Clean Code 3: 0 nur, wo 0
    eine Aussage ist)."""
    leer = {"anbieter": "Telekom", "tarif": "", "zustand": "",
            "zustand_etikett": "", "belastbar": False, "label": "",
            "gesamt": None, "schnitt_monat": None, "laufzeit": None,
            "leitzahl_monate": None, "raten_laufzeit": None,
            "tarif_bindung": None, "geraetepreis": None,
            "geraetepreis_art": None, "zuzahlung": None, "monatlich": None,
            "buendel_monatlich": None, "naeherung": False, "eigen": False,
            "delta": None, "delta_kurz": "", "delta_zustand": None,
            "sku_id": "", "quelle_url": "", "abgerufen_am": "",
            "leer_grund": "Kein Bündel erhoben", "alt_marke": "",
            "frisch": True, "band": "klein", "band_gb_text": ""}
    zeile = BeautifulSoup(_env().from_string(
        '{% from "_geraete_buendel.html.j2" import buendelzeile %}'
        "{{ buendelzeile(k) }}").render(k=leer),
        "html.parser").select_one(".gr-bnd")
    assert zeile.get("data-leitzahl-monate") == "", zeile.attrs
    assert zeile.get("data-gesamt") == "", zeile.attrs
    # GEGENPROBE: die Zeile steht da, mit ihrem Grund - sie wird nicht
    # weggelassen, nur weil sie keinen Zeitraum hat.
    assert "Kein Bündel erhoben" in "".join(zeile.find_all(string=True))


# --------------------------------------------------------------------------
# 3. Die Sortierung im echten Chromium
# --------------------------------------------------------------------------

@contextlib.contextmanager
def _browser_ctx(site):
    sync_playwright = pytest.importorskip(
        "playwright.sync_api", reason="playwright fehlt").sync_playwright
    exe = _chromium()
    with _server(site) as wurzel, sync_playwright() as p:
        try:
            browser = (p.chromium.launch(executable_path=exe) if exe
                       else p.chromium.launch())
        except Exception:                    # noqa: BLE001
            pytest.skip("kein Chromium gefunden")
        try:
            yield wurzel, browser
        finally:
            browser.close()


@pytest.fixture(scope="module")
def ctx(site):
    with _browser_ctx(site) as c:
        yield c


@pytest.fixture()
def seite(ctx):
    wurzel, browser = ctx
    s = browser.new_page(viewport={"width": 1440, "height": 900})
    try:
        s.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
        yield s
    finally:
        s.close()


def _reihe(s):
    """(Anbieter, Zeitraum, Betrag) je sichtbarer Zeile, in DOM-Reihenfolge."""
    return s.eval_on_selector_all(
        "#gr-bndliste .gr-bnd:not([hidden])",
        "e => e.map(z => [z.dataset.anbieter, "
        "z.getAttribute('data-leitzahl-monate'), "
        "parseFloat(z.dataset.gesamt)])")


def test_die_sortierung_stellt_zwei_zeitraeume_nicht_in_einen_rang(seite):
    """Der Befund im Browser: ein Klick auf den Kopf stellte die
    36-Monats-Summe (1.180,00 EUR) zwischen o2 (1.032,76) und Vodafone
    (1.224,76) - als waere sie teurer als die eine und guenstiger als die
    andere. Beides ist nicht gemessen.

    Gegen den alten Stand rot: dort lautete die Reihe nach dem Klick
    [congstar, o2, 1&1, Vodafone].
    """
    seite.click("#gr-buendel .gr-bnd-kopf button[data-bsort='tco']")
    seite.wait_for_timeout(120)
    reihe = _reihe(seite)
    assert [z[0] for z in reihe] == ["congstar", "o2", "Vodafone", "1&1"], \
        reihe
    # Erst der Zeitraum, dann der Betrag INNERHALB des Zeitraums.
    assert [z[1] for z in reihe] == ["24", "24", "24", "36"], reihe
    je_zeitraum = {}
    for _a, mon, betrag in reihe:
        je_zeitraum.setdefault(mon, []).append(betrag)
    for mon, betraege in je_zeitraum.items():
        assert betraege == sorted(betraege), (mon, betraege)
    # NICHTS WIRD GEKAPPT: die Zeile mit dem anderen Zeitraum steht weiter
    # da, mit ihrer Zahl und ihrem Etikett.
    assert len(reihe) == 4, reihe
    etikett = seite.eval_on_selector_all(
        "#gr-bndliste .gr-bnd:not([hidden]) .gr-bnd-label",
        "e => e.map(x => x.textContent.trim())")
    assert etikett[-1] == "Kosten über 36 Monate", etikett


def test_die_umgekehrte_richtung_dreht_nur_innerhalb_des_zeitraums(seite):
    """Der Zeitraum ist kein Wert, der rangiert, sondern der Rahmen, in dem
    rangiert wird: der zweite Klick dreht die Betraege INNERHALB der
    24-Monats-Gruppe - die 36er bleibt fuer sich und wandert nicht als
    "guenstigstes Angebot" nach vorn."""
    knopf = "#gr-buendel .gr-bnd-kopf button[data-bsort='tco']"
    seite.click(knopf)
    seite.wait_for_timeout(120)
    seite.click(knopf)
    seite.wait_for_timeout(120)
    reihe = _reihe(seite)
    assert [z[0] for z in reihe] == ["Vodafone", "o2", "congstar", "1&1"], \
        reihe
    assert [z[1] for z in reihe] == ["24", "24", "24", "36"], reihe


def test_eine_zeile_ohne_gemessenen_zeitraum_rangiert_hinten_und_bleibt(seite):
    """Der dritte Zustand: kein gemessener Zeitraum (leeres Attribut). Er
    wird nicht als 24 angenommen (Clean Code 4) - die Zeile steht hinter
    allen Zeitraeumen und bleibt in der Liste. Gemessen an einer Zeile,
    deren Attribut im DOM geleert wird: der Bestand kennt diesen Fall
    heute nicht (ohne gemessene Laufzeit ist die Kennzahl unbelastbar),
    die Sortierung muss ihn trotzdem tragen."""
    seite.eval_on_selector(
        "#gr-bndliste .gr-bnd[data-anbieter='congstar']",
        "z => z.setAttribute('data-leitzahl-monate', '')")
    seite.click("#gr-buendel .gr-bnd-kopf button[data-bsort='tco']")
    seite.wait_for_timeout(120)
    reihe = _reihe(seite)
    assert len(reihe) == 4, reihe
    assert [z[1] for z in reihe] == ["24", "24", "36", ""], reihe
    assert reihe[-1][0] == "congstar", reihe


def test_die_anbieter_sortierung_bleibt_eine_reine_namensfolge(seite):
    """GEGENPROBE zur Gruppierung: sie gilt NUR fuer den Kostenrang. Nach
    Anbieter sortiert steht 1&1 vorn, wo der Name hingehoert - der
    Zeitraum mischt sich dort nicht ein."""
    seite.click("#gr-buendel .gr-bnd-kopf button[data-bsort='anbieter']")
    seite.wait_for_timeout(120)
    namen = [z[0] for z in _reihe(seite)]
    assert namen == sorted(namen, key=str.lower), namen
    assert namen[0] == "1&1", namen


# --------------------------------------------------------------------------
# 4. MITNEHMEN: kein Rueckfall auf die Konstante 24 im Markup
# --------------------------------------------------------------------------

def _zeile_text(karte: dict) -> str:
    """Der Text EINER Buendelzeile am ECHTEN Makro - auch der im
    `<template>`, wo der Rechenweg seit dem P4-Fix liegt (dieselbe Lesart
    wie `tests/test_geraete_laufzeit_auf_der_seite.vorlage_text`)."""
    zeile = BeautifulSoup(_env().from_string(
        '{% from "_geraete_buendel.html.j2" import buendelzeile %}'
        "{{ buendelzeile(k) }}").render(k=karte), "html.parser")
    return " ".join("".join(zeile.find_all(string=True)).split())


def _finanzierungskarte(raten_laufzeit) -> dict:
    """Eine Zeile mit Finanzierungssumme - wie die Referenzrechnung, die
    ihre `geraetepreis_art` aus dem Quellbuendel uebernimmt
    (`geraete_tco_karten._referenzkarte`) und dabei KEINE Ratenlaufzeit
    mitbringt."""
    return {"anbieter": "Vodafone", "tarif": "Vodafone Mobil XS",
            "zustand": "neu", "zustand_etikett": "", "belastbar": True,
            "label": "Kosten über 24 Monate", "gesamt": 1500.0,
            "schnitt_monat": 62.5, "laufzeit": 24, "leitzahl_monate": 24,
            "raten_laufzeit": raten_laufzeit, "tarif_bindung": 24,
            "geraetepreis": 900.0, "geraetepreis_art": "finanzierung",
            "zuzahlung": 1.0, "monatlich": 24.99, "rate": 37.46,
            "raten_summe": 899.0, "buendel_monatlich": None,
            "anschlusspreis": None, "nach_bindung": 29.99,
            "gezahlt_nach_24": 1500.0, "offen_nach_24": None,
            "offene_raten": 0, "eff_ohne_geraet": None, "eff_basis": None,
            "bestandteile": [], "luecken": [], "boni": [], "delta": None,
            "delta_kurz": "", "delta_zustand": None, "naeherung": False,
            "eigen": True, "frisch": True, "alt_marke": "", "sku_id": "x",
            "quelle_url": "", "abgerufen_am": "", "tarif_quelle_url": "",
            "band": "klein", "band_gb_text": "", "ab_preis": False,
            "leer_grund": ""}


def test_ohne_gemessene_ratenzahl_steht_keine_24_im_paradox_satz():
    """Gegen den alten Stand rot: `{{ k.raten_laufzeit or k.laufzeit }}`
    fiel auf `k.laufzeit` (die Konstante 24) zurueck und behauptete "alle
    24 Geräteraten", wo keine Ratenzahl gemessen ist."""
    text = _zeile_text(_finanzierungskarte(None))
    assert "alle 24 Geräteraten" not in text, text
    assert "Anzahl nicht gemessen" in text, text

    # GEGENPROBE: die GEMESSENE Ratenzahl steht da, und zwar sie selbst -
    # 36 Raten bleiben 36, nicht 24.
    text36 = _zeile_text(_finanzierungskarte(36))
    assert "alle 36 Geräteraten" in text36, text36
    assert "Anzahl nicht gemessen" not in text36, text36


def test_ohne_gemessene_ratenzahl_steht_keine_24_am_buendelmonatspreis():
    """Derselbe Rueckfall am zusammengelegten Monatsbetrag (1&1): ohne
    gemessene Laufzeit stand dort "24 Monate" - eine Zahl, die dieser
    Betrag nie getragen hat."""
    karte = _finanzierungskarte(None)
    karte.update({"buendel_monatlich": 30.0, "geraetepreis": None,
                  "geraetepreis_art": None, "rate": None,
                  "raten_summe": None})
    text = _zeile_text(karte)
    assert "zusammen · 24 Monate" not in text, text
    assert "None" not in text, text
    assert "Laufzeit nicht gemessen" in text, text

    karte["raten_laufzeit"] = 36
    text36 = _zeile_text(karte)
    assert "zusammen · 36 Monate" in text36, text36
    assert "Laufzeit nicht gemessen" not in text36, text36
