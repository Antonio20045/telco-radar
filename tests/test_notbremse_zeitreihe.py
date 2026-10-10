"""Notbremse in der Zeitreihe der Geräteseite (Datenkonzept Geräteradar, Schritt 1).

Sieger, Antwortsatz und Alternativ-Beträge der Zeitreihe nehmen nur Karten, die
zählen: eine Schätzung oder ein Satz mit abgelaufener Aktion stellt nie den
günstigsten Preis. Ein Band, in dem nur solche Karten stehen, bleibt wählbar und
nennt den Grund. Das Rechenweg-Panel nennt den Zeitraum seiner Zahl mit demselben
Etikett wie die Karten (1&1: „Kosten über 36 Monate“) und schreibt Monatsnamen
deutsch, auch unter englischem Locale. Gerendert aus dem Bestand vom 2026-10-03;
der Bezugstag kommt aus dem Bestand, nie vom heutigen Datum.
"""

from __future__ import annotations

import locale
import re
import shutil

import pytest
from bestand_pfad import ZUSTAND, abbild, lese_wurzel
from bs4 import BeautifulSoup

from telco_radar.config import load_config
from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view
from telco_radar.report.html import render_site

HEUTE = "2026-10-03"
DEUTSCHE_MONATE = {
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
}
DATUM = re.compile(r"\b\d{1,2}\. ([A-Za-zä]+) \d{4}\b")
BETRAG = re.compile(r"([\d.]+,\d{2}) €")


@pytest.fixture(scope="module")
def gerendert(tmp_path_factory):
    """Seite und Fragment, gerendert unter dem C-Locale (englische Monatsnamen)."""
    wurzel = tmp_path_factory.mktemp("notbremse-zr")
    vorher = locale.setlocale(locale.LC_TIME)
    locale.setlocale(locale.LC_TIME, "C")
    try:
        render_site(wurzel / "site", abbild(wurzel), load_config(wurzel))
    finally:
        locale.setlocale(locale.LC_TIME, vorher)
    seite = (wurzel / "site" / "geraete.html").read_text(encoding="utf-8")
    fragment = (wurzel / "site" / "data" / "geraete-zeitreihe.html").read_text(
        encoding="utf-8"
    )
    return seite, BeautifulSoup(fragment, "html.parser")


@pytest.fixture(scope="module")
def karten(tmp_path_factory):
    """Die Karten je (Modell, Band, Ratenlaufzeit) mit ``zaehlt`` aus dem
    öffentlichen Eingang; die Näherung steht in der 24er-Ansicht."""
    zustand = tmp_path_factory.mktemp("notbremse-zr-karten") / "state"
    shutil.copytree(ZUSTAND, zustand)
    wurzel = lese_wurzel()
    geraete = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=HEUTE
    )
    je_band: dict[tuple, list] = {}
    for modell in geraete["tco"]["modelle"]:
        for karte in modell["karten"]:
            if karte.get("band"):
                lz = 24 if karte.get("naeherung") else karte.get("raten_laufzeit")
                paar = (modell["id"], karte["band"], lz)
                je_band.setdefault(paar, []).append(karte)
    return je_band


def _euro(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def _brauchbar(karte: dict) -> bool:
    return bool(
        karte.get("vergleichbar")
        and karte.get("belastbar")
        and karte.get("gesamt") is not None
    )


def _bloecke(fragment: BeautifulSoup) -> list[tuple[tuple, str]]:
    return [
        (
            (b["data-modell"], b["data-band"], int(b["data-laufzeit"])),
            b.select_one(".gr-zr-antwort").decode(),
        )
        for b in fragment.select(".gr-zr-lager")
    ]


def _sieger(antwort: str, karten: list) -> list[dict]:
    """Die Karten, deren Betrag der Antwortsatz als erste Zahl nennt."""
    zahl = re.search(r"<b class=\"gr-zr-zahl\">([^<]+)</b>", antwort)
    betrag = BETRAG.search(zahl.group(1)) if zahl else None
    if betrag is None:
        return []
    return [k for k in karten if k.get("gesamt") == _euro(betrag.group(1))]


def test_sieger_der_zeitreihe_zaehlt(gerendert, karten):
    _, fragment = gerendert
    gesperrt = []
    for paar, antwort in _bloecke(fragment):
        traeger = _sieger(antwort, karten.get(paar, []))
        if traeger and all(not k.get("zaehlt", True) for k in traeger):
            k = traeger[0]
            gesperrt.append(f"{paar}: {k['anbieter']} {k['tarif']} {k['gesamt']}")
    assert not gesperrt, (
        f"Sieger zählt nicht: {len(gesperrt)} Antwortsätze nennen eine Schätzung "
        f"oder abgelaufene Aktion (z. B. {gesperrt[:3]})"
    )


def test_gemessene_sieger_bleiben(gerendert, karten):
    """Gegenprobe: ein gemessener Sieger war schon vorher der günstigste, der
    zählt, und bleibt stehen."""
    _, fragment = gerendert
    gemessen = {
        k["anbieter"]
        for paar, antwort in _bloecke(fragment)
        for k in _sieger(antwort, karten.get(paar, []))
        if k.get("zaehlt", True)
    }
    assert {"Vodafone", "o2", "congstar"} <= gemessen, gemessen


def test_band_nur_mit_schaetzungen_bleibt_und_nennt_den_grund(gerendert, karten):
    """Eine Datenqualitätsheuristik schaltet nie die Navigation: das Band bleibt
    wählbar, der Satz nennt den Grund statt eines Preises."""
    _, fragment = gerendert
    nur_gesperrt = []
    for paar, antwort in _bloecke(fragment):
        brauchbar = [k for k in karten.get(paar, []) if _brauchbar(k)]
        if brauchbar and not any(k.get("zaehlt", True) for k in brauchbar):
            nur_gesperrt.append((paar, antwort))
    assert nur_gesperrt, "Bänder nur mit Schätzungen fehlen in der Zeitreihe"
    ohne_grund = [
        paar
        for paar, antwort in nur_gesperrt
        if "steht kein Bündel im Vergleich: " not in antwort
        or (
            "(nicht direkt genannt)" not in antwort
            and "(Aktion abgelaufen)" not in antwort
        )
    ]
    mit_preis = [paar for paar, antwort in nur_gesperrt if "gr-zr-zahl" in antwort]
    assert not ohne_grund and not mit_preis, (
        f"Band nur mit Schätzungen: {len(ohne_grund)} ohne Grund "
        f"(z. B. {ohne_grund[:3]}), {len(mit_preis)} mit Preis ({mit_preis[:3]})"
    )


@pytest.fixture(scope="module")
def fehlen(tmp_path_factory):
    """Die Zeilen fehlender Anbieter je (Modell, Band, Ratenlaufzeit)."""
    zustand = tmp_path_factory.mktemp("notbremse-zr-fehlen") / "state"
    shutil.copytree(ZUSTAND, zustand)
    wurzel = lese_wurzel()
    geraete = geraete_view.aufbereiten(
        zustand, lade_quellen(wurzel), lade_katalog(wurzel), heute=HEUTE
    )
    return {
        (p["modell"], p["band"], p["laufzeit"]): p["fehlen"]
        for p in geraete["zeitreihe"]["paare"]
    }


def test_luecke_nennt_schaetzung_nicht_als_fehlendes_buendel(fehlen, karten):
    falsch, benannt = [], 0
    for paar, zeilen in fehlen.items():
        gesperrt = {
            k["anbieter"]
            for k in karten.get(paar, [])
            if _brauchbar(k) and not k.get("zaehlt", True)
        }
        for f in zeilen:
            benannt += f["kurz"] == "Nicht im Vergleich"
            if f["anbieter"] in gesperrt and f["kurz"].startswith("Nur in anderen"):
                falsch.append(f"{paar}: {f}")
    assert not falsch, (
        f"Lücke: {len(falsch)} Zeilen nennen eine Schätzung „kein Bündel“ "
        f"(z. B. {falsch[:2]})"
    )
    assert benannt, "Lücke: erwartet „Nicht im Vergleich“ im Bestand"


def test_alternativen_der_fehlzeilen_zaehlen(fehlen, karten):
    """Die Alternativ-Beträge anderer Bänder („o2: Nur in anderen Bändern:
    M 958,75 €“) stammen nur aus Karten, die zählen; gemessene bleiben."""
    gesperrt, gemessen = [], 0
    for (modell, _, laufzeit), zeilen in fehlen.items():
        for f in zeilen:
            anbieter = f["anbieter"]
            for stufe, betrag in re.findall(r"([A-Z]+) ([\d.]+,\d{2}) €", f["kurz"]):
                traeger = [
                    k
                    for k in karten.get((modell, stufe.lower(), laufzeit), [])
                    if k["anbieter"] == anbieter and k.get("gesamt") == _euro(betrag)
                ]
                if traeger and not any(k.get("zaehlt", True) for k in traeger):
                    gesperrt.append(f"{modell} {anbieter} {stufe}")
                gemessen += bool(traeger) and anbieter == "congstar"
    assert not gesperrt, (
        f"Alternative zählt nicht: {len(gesperrt)} Beträge aus Schätzungen "
        f"(z. B. {gesperrt[:3]})"
    )
    assert gemessen, "keine gemessene Alternative in den Fehlzeilen - Fall fehlt"


def _panels(fragment: BeautifulSoup) -> list[tuple[str, BeautifulSoup]]:
    """(Anbieter, Inhalt) je Rechenweg-Vorlage des Fragments."""
    return [
        (v["data-anb"], BeautifulSoup(v.decode_contents(), "html.parser"))
        for v in fragment.select("template[data-anb]")
    ]


def test_panel_von_eins_und_eins_nennt_36_monate(gerendert):
    _, fragment = gerendert
    etiketten: dict[str, set] = {"1&1": set(), "o2": set()}
    for anbieter, inhalt in _panels(fragment):
        etikett = inhalt.select_one(".gr-zr-plabel")
        if anbieter in etiketten and etikett is not None:
            etiketten[anbieter].add(etikett.get_text(strip=True))
    assert etiketten["1&1"], "keine Rechenweg-Panels von 1&1 im Bestand"
    falsch = sorted(etiketten["1&1"] - {"Kosten über 36 Monate"})
    assert not falsch, (
        f"Kosten über 36 Monate: erwartet im Panel von 1&1, steht {falsch}"
    )


def test_panel_von_o2_bleibt_bei_24_monaten(gerendert):
    """Gegenprobe: die aufgeteilte Preisform trägt weiter 24 Monate."""
    _, fragment = gerendert
    etiketten = {
        etikett.get_text(strip=True)
        for anbieter, inhalt in _panels(fragment)
        if anbieter == "o2" and (etikett := inhalt.select_one(".gr-zr-plabel"))
    }
    assert etiketten == {"Kosten über 24 Monate"}, etiketten


def test_monatsnamen_sind_deutsch_auch_unter_englischem_locale(gerendert):
    seite, fragment = gerendert
    panel = {
        m
        for _, inhalt in _panels(fragment)
        for m in DATUM.findall(inhalt.get_text(" "))
    }
    assert "Oktober" in panel, f"Monatsname: erwartet „Oktober“ im Panel, steht {panel}"
    monate = panel | set(DATUM.findall(fragment.get_text(" ")))
    monate |= set(DATUM.findall(BeautifulSoup(seite, "html.parser").get_text(" ")))
    assert monate <= DEUTSCHE_MONATE, f"Monatsname nicht deutsch: {monate}"
