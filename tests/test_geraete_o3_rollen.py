"""O3 (STRATEGIE_GERAETE_OPTIK §3, 15.09.2026): Rollen und Navigation.

Die O2-Abnahme endete mit zwei offenen Befunden an der ARCHITEKTUR der
Geräteseite, die dieser Datei ihre Kriterien geben:

  S3 (Evaluator-Auflage) — der Modell-Umschalter zeigte Bündel-ZEILEN nur
      für das Vorgabegerät (19 von 423 am echten Bestand); die alte
      „Alle Bündel als Tabelle" fiel in O2 ersatzlos weg. Ab O3 zeigt die
      Vergleichsansicht für JEDES wählbare Gerät seine eigenen Zeilen —
      dieselben Garantien wie O2 (Pflichtzeile, Belege, Rechenweg).
  S4 — die toten DIVs: `#tafel-verlauf` ist wieder über einen Reiter
      erreichbar (lebendig), `#tafel-portfolio` ist WEG (seine Abschnitte
      stehen auf dem Wettbewerbs-Radar — Antonios Entscheidung, Strategie
      §5.2).

Dazu die Rollen selbst (Entwurf `docs/entwuerfe/geraete-optik-2026-09-11/
entwurf.html`): Reiterfolge „Vergleich | Wettbewerbs-Radar | Preisverlauf |
Gerätekatalog" mit dem Radar als LINK (Seitenwechsel, kein toter Tab),
ehrlicher Untertitel nach Entwurf-Wortlaut, je Radar-Geräteblock ein
Querlink zurück ins Vergleichsansicht desselben Modells.

Alle statischen Prüfungen hier laufen am ECHTEN Bestand (88 Modelle, 423
Bündelzeilen) — die Fixture der Browser-Tests trägt fünf Zeilen und könnte
Größen- und Zähl-Aussagen nicht tragen.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest
from bs4 import BeautifulSoup

from telco_radar.report.html import render_site

WURZEL = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def site(tmp_path_factory) -> pathlib.Path:
    ziel = tmp_path_factory.mktemp("o3-rollen") / "site"
    render_site(ziel, WURZEL / "data" / "reports")
    return ziel


@pytest.fixture(scope="module")
def geraete(site) -> BeautifulSoup:
    return BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")


@pytest.fixture(scope="module")
def radar(site) -> BeautifulSoup:
    return BeautifulSoup(
        (site / "wettbewerbsradar.html").read_text(encoding="utf-8"),
        "html.parser")


# --------------------------------------------------------------------------
# B1: Reiterleiste und Rollen
# --------------------------------------------------------------------------

def test_die_reiterfolge_ist_vergleich_radar_verlauf_katalog(geraete):
    """Der Entwurf führt vier Einträge; der Radar ist ein LINK auf eine
    andere Seite, kein Tab dieser Seite. Ein `data-tafel` am Radar-Link
    würde ihn zum toten Tab machen: der Umschalter würde nach einem
    Ziel-Element suchen, das es nicht gibt."""
    eintraege = geraete.select(".gr-reiter > *")
    rollen = []
    for e in eintraege:
        if e.name == "button":
            rollen.append((e.get("data-tafel"), e.get_text(strip=True)))
        else:
            rollen.append((e.name, e.get_text(strip=True)))
    assert rollen == [
        ("tafel-tco", "Vergleich"),
        ("a", "Wettbewerbs-Radar"),
        ("tafel-verlauf", "Preisverlauf"),
        ("tafel-katalog", "Gerätekatalog"),
    ], rollen
    radar_link = geraete.select_one(".gr-reiter a[href$='wettbewerbsradar.html']")
    assert radar_link is not None, "der Radar-Quasi-Reiter fehlt"
    # DEUTLICH ALS SEITENWECHSEL erkennbar (Auftrag B1): ein Pfeil im
    # Linktext, nicht nur eine andere Farbe.
    assert radar_link.get_text(strip=True) != "Wettbewerbs-Radar" or \
        radar_link.select_one(".gr-reiter-pfeil"), \
        "der Radar-Reiter trägt keine Seitenwechsel-Kennzeichnung"


def test_der_untertitel_traegt_den_entwurfswortlaut(geraete):
    """B3: Untertitel nach Entwurf — der Satz sagt, was die Seite misst
    (TCO-24 über 24 Monate) und nennt die Schwesterseite beim Namen."""
    satz = geraete.select_one(".gr-untertitel")
    assert satz is not None, "der Untertitel fehlt unter dem Zeitungskopf"
    gesamt = " ".join(satz.get_text(" ", strip=True).split())
    assert "Alle Anbieter eines Modells im gewählten Tarifband" in gesamt
    assert "TCO-24" in gesamt
    assert "Gesamtkosten über 24 Monate" in gesamt
    link = geraete.select_one("a[href$='wettbewerbsradar.html']")
    assert link is not None
    assert "Wettbewerbs-Radar" in link.get_text(strip=True)


def test_der_verlaufs_reiter_fuehrt_auf_eine_lebendige_tafel(geraete):
    """B2: Der Reiter existiert UND die Tafel hinter ihm ist nicht tot —
    sie zeigt entweder die Einzelgerät-Zeitreihe (Suchfeld + JSON-Knoten,
    G2-SVG) oder ihren ehrlichen Leerzustand. Strategie O3: „die zwei toten
    Tafel-DIVs sind danach weg oder lebendig“. Ein leerer Tab-Body wäre die
    nächste tote Tafel."""
    tafel = geraete.select_one("#tafel-verlauf")
    assert tafel is not None, "#tafel-verlauf fehlt"
    assert geraete.select_one(
        ".gr-reiter [data-tafel='tafel-verlauf']") is not None, \
        "kein Reiter-Knopf auf #tafel-verlauf"
    lebendig = (tafel.select_one("#gr-verlaufdaten") is not None
                or tafel.select_one("svg.gr-g2") is not None
                or "liegen noch keine Messreihen vor" in tafel.get_text()
                or "keine Reihe aus Gerät und Anbieter" in tafel.get_text())
    assert lebendig, "die Verlaufs-Tafel ist tot: kein Inhalt, kein Leerzustand"


def test_tafel_portfolio_ist_weg(geraete):
    """B4: Die Portfolio-Tafel verlässt die Geräteseite GANZ — Container,
    Abschnitte und Macros. Ein leer stehender Tab-Body wäre die nächste
    tote Tafel."""
    assert geraete.select_one("#tafel-portfolio") is None
    text = geraete.get_text(" ", strip=True)
    assert "Wie lange ein Gerät im Markt lebt" not in text
    assert "Was diese Woche auffällt" not in text


def test_die_portfolio_abschnitte_stehen_auf_dem_radar(radar):
    """B4: Dieselben Abschnitte, neuer Ort — Verweildauer, Preisverfall,
    Nachfolger-Effekt und Portfolio-Tiefe sind Portfolio-Fragen, und der
    Radar ist die Portfolio-Seite (Antonios Entscheidung, Strategie §5.2)."""
    text = " ".join(radar.get_text(" ", strip=True).split())
    assert "Wie lange ein Gerät im Markt lebt" in text
    assert "Verweildauer im Regal" in text
    assert "Preisverfall gegenüber dem Einführungspreis" in text
    assert "Was der Nachfolger mit dem Preis macht" in text
    assert "Wie viele Generationen ein Anbieter gleichzeitig führt" in text


def test_was_diese_woche_auffaellt_steht_auf_dem_radar(radar):
    """B4: Auch die Wochenkarte der Preisbewegungen gehört zur Markt-
    übersicht, nicht zur Einzelgerät-Seite."""
    text = " ".join(radar.get_text(" ", strip=True).split())
    assert "Was diese Woche auffällt" in text


# --------------------------------------------------------------------------
# B5: Querlink je Radar-Geräteblock
# --------------------------------------------------------------------------

def test_je_radar_gruppe_ein_querlink_mit_deep_link(radar, geraete):
    """B5: Jeder Geräteblock des Radars verlinkt auf DIESELBE Modell-ID,
    die der Selektor der Geräteseite trägt — sonst landet der Deep-Link auf
    dem Vorgabegerät und zeigt ein anderes Gerät, als der Link verspricht.
    Die Gegenprobe ist Teil des Tests (CLAUDE.md §6: ein Lookup, der nichts
    trifft, ist grün und prüft nichts)."""
    ids_selektor = {o.get("value")
                    for o in geraete.select("#gr-modell option")}
    links = radar.select("a[href^='geraete.html?modell=']")
    assert links, "kein Querlink auf dem Radar"
    assert "Dieses Gerät im Vergleich" in links[0].get_text(strip=True)
    fehlende = [a.get("href") for a in links
                if (a.get("href").split("modell=", 1)[-1] not in ids_selektor)]
    assert not fehlende, \
        f"Querlinks auf Modell-IDs außerhalb des Selektors: {fehlende[:5]}"
    # Die Gruppen des Radars kommen aus denselben Modellen — jede sichtbare
    # Gruppe trägt ihren Link (im Aufklapper der Restgruppen darf er fehlen).
    gruppen = radar.select(".wr-gruppe")
    mit_link = radar.select(
        ".wr-gruppe a[href^='geraete.html?modell=']")
    assert len(mit_link) >= min(len(gruppen), 1), \
        f"{len(mit_link)} Querlinks für {len(gruppen)} Gruppen"


# --------------------------------------------------------------------------
# B6: tarife.html erreichbar
# --------------------------------------------------------------------------

def test_tarife_ist_vom_radar_verlinkt(radar):
    """B6: die Tarifübersicht ist die Quelle der Bänder und Tarifbindungen
    — vom Radar (der in Bändern vergleicht) gehört ein Weg dorthin."""
    assert radar.select_one("a[href$='tarife.html']") is not None, \
        "wettbewerbsradar.html verlinkt die Tarifübersicht nicht"


def test_tarife_bleibt_von_der_geraeteseite_verlinkt(geraete):
    """B6: der O1-Fußnoten-Link bleibt — zwei Wege sind erlaubt, null
    waren der Befund („tarife.html ist eine Waise ohne jeden eingehenden
    Link")."""
    assert geraete.select_one("a[href$='tarife.html']") is not None


# --------------------------------------------------------------------------
# A (S3): das Bündel-Fragment — Zeilen für JEDES wählbare Gerät
# --------------------------------------------------------------------------

def test_das_buendel_fragment_existiert_fuer_alle_anderen_modelle(site,
                                                                  geraete):
    """A: Die Zeilen aller Nicht-Vorgabemodelle stehen in einem eigenen
    Fragment unter site/data/ — NICHT in der Seite selbst. O1 hat die
    Seite von 3,9 MB auf ~1,1 MB gebracht; 423 Zeilen à 2,7 KB im HTML
    wären der Weg zurück (gemessen: +1,17 MB). Das Fragment wird beim
    ersten Modellwechsel geladen (lazy), der Netzwerk-Test des
    Rechenweg-Aufklappers bleibt dadurch grün."""
    fragment = site / "data" / "geraete-buendel.html"
    assert fragment.exists(), "site/data/geraete-buendel.html fehlt"
    lager = BeautifulSoup(fragment.read_text(encoding="utf-8"),
                          "html.parser")
    container = lager.select(".gr-bnd-lager[data-modell]")
    assert len(container) >= 80, \
        f"nur {len(container)} Modell-Container im Fragment (88 Modelle)"
    # Das Vorgabemodell steht SCHON auf der Seite - im Fragment würde es
    # doppelt (52 KB am echten Bestand).
    vorgabe = json.loads(
        geraete.select_one("#gr-graph-daten").text)["vorgabe"]
    ids = {c.get("data-modell") for c in container}
    assert vorgabe not in ids, "das Vorgabemodell steht doppelt"
    zeilen = lager.select(".gr-bnd")
    assert len(zeilen) >= 380, \
        f"nur {len(zeilen)} Zeilen im Fragment (423 am Bestand, 19 Vorgabe)"


def test_jede_belastbare_fragment_zeile_traegt_die_pflichtzeile(site):
    """A: dieselben Garantien wie O2 — jede Zeile mit Zahl beantwortet
    „nach 24 Monaten gezahlt" und trägt Sortier-Schlüssel als Daten-
    Attribute (C: TCO-24, Δ, Anbieter)."""
    lager = BeautifulSoup(
        (site / "data" / "geraete-buendel.html").read_text(encoding="utf-8"),
        "html.parser")
    belastbar = [z for z in lager.select(".gr-bnd") if z.get("data-gesamt")]
    assert belastbar, "keine belastbare Zeile im Fragment"
    ohne_pflicht = [z for z in belastbar
                    if z.select_one(".gr-kk-24") is None]
    assert not ohne_pflicht, \
        f"{len(ohne_pflicht)} belastbare Zeilen ohne Pflichtzeile"
    for z in lager.select(".gr-bnd")[:50]:
        assert z.get("data-anbieter"), "Zeile ohne data-anbieter"
        assert z.has_attr("data-delta"), \
            "Zeile ohne data-delta-Sortierschlüssel (auch leer erlaubt)"


def test_die_sortierkoepfe_stehen_ueber_der_bandliste(geraete):
    """C: Die Spaltenköpfe TCO-24, Δ und Anbieter der Bündeltabelle sind
    Knöpfe — sortierbar ohne Reload; die Server-Vorsortierung nach TCO-24
    (O2) bleibt der Ausgangszustand."""
    kopf = geraete.select_one("#gr-buendel .gr-bnd-kopf")
    assert kopf is not None
    beschriftungen = " ".join(kopf.get_text(" ", strip=True).split())
    knoepfe = kopf.select("button[data-bsort]")
    arten = {b.get("data-bsort") for b in knoepfe}
    assert arten == {"tco", "delta", "anbieter"}, arten
    assert "TCO-24" in beschriftungen and "Anbieter" in beschriftungen


# --------------------------------------------------------------------------
# D: O1/O2-Restpunkte
# --------------------------------------------------------------------------

def test_der_karten_hinweis_ist_weg(geraete):
    """S4: Der Hinweis „Die Bündel-Tabelle steht für das Vorgabegerät" war
    die Stimme der S3-Lücke — mit Zeilen für jedes Modell lügt er."""
    assert geraete.select_one("#gr-karten-hinweis") is None
    assert "Vorgabegerät" not in geraete.get_text()


def test_der_wortlaut_nennt_fehlt_nicht_fuehrt(geraete):
    """D1: Entwurf-Wortlaut „Vodafone fehlt in diesem Band – keine
    Δ-Angabe" statt „führt kein Bündel in diesem Band"."""
    knoten = geraete.select_one("#gr-graph-daten")
    daten = json.loads(knoten.text)
    unterzeilen = [b["unterzeile"] for m in daten["modelle"]
                   for b in (m.get("baender") or {}).values()]
    assert unterzeilen, "keine Band-Unterzeile im Datenknoten"
    for z in unterzeilen:
        assert "führt kein Bündel" not in z, z
    assert any("fehlt in diesem Band" in z for z in unterzeilen), \
        "am echten Bestand gibt es Bänder ohne Vodafone-Referenz - " \
        "dort muss der neue Wortlaut stehen"


def test_die_tco_view_liefert_keine_toten_felder_mehr():
    """S4: `tabelle`, `zeilen`, `zeilen_gesamt`, `delta` und `hat_tco`
    hatten nach O2 keinen Leser mehr (Vorlagen, JS, Tests) — Rückbau statt
    Ruhelager. Die Zeilen-Rechnung selbst bleibt: `_offene_posten` braucht
    sie weiter."""
    from telco_radar.report import geraete_tco_view
    ansicht = geraete_tco_view.leer()
    for feld in ("tabelle", "zeilen", "zeilen_gesamt", "delta", "hat_tco"):
        assert feld not in ansicht, feld
    quelle = pathlib.Path(geraete_tco_view.__file__).read_text(
        encoding="utf-8")
    assert '"tabelle":' not in quelle
    assert '"zeilen":' not in quelle
    assert '"delta":' not in quelle
    assert '"hat_tco":' not in quelle
