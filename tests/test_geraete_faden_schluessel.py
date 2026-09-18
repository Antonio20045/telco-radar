"""P4 SCHRITT 2c (STRATEGIE_GERAETE_V3, 18.09.2026): EINE Modell-Menge
statt drei - der rote Faden zwischen den Reitern.

Befund katalog.md §4: vier Modell-Zugaenge auf EINER Seite mit drei
Modell-Mengen (88/97 · 111 · 321) und zwei Schluesseln - der objektive
Kern von Antonios „kein roter Faden, Mischmasch". Seit P3 tragen Katalog
und Radar/Zeitreihe denselben WERT-Schluessel (`modell_schluessel`), aber
der Katalog hielt ihn nicht im Markup, kein Sprung fuehrte zwischen den
Reitern, und die Differenz der Mengen war nirgends benannt.

Diese Datei nagelt die Vereinheitlichung fest:

1. Jede Katalog-Modellzeile traegt ihren `modell_schluessel` als
   `data-modell` (derselbe Schluessel wie Radar-Liste und Zeitreihen-
   Wahl) - mit Vollstaendigkeits-Gegenprobe (CLAUDE.md §6: ein Lookup,
   der nichts trifft, ist gruen und prueft nichts).
2. Der Radar->Katalog-Sprung (gr-ksprung) trifft eine Katalog-Zeile mit
   DEMSELBEN Schluessel; jede Radar-Modellzeile hat Link ODER die
   benannte Luecke „nicht im Katalog" (reines Buendel ohne Listung).
3. Der Katalog->Zeitreihe-Sprung (gr-sprung am Modellnamen) steht NUR,
   wo die Zeitreihe das Modell kennt (`daten.erlaubt`, nicht-leer) -
   dieselbe EINE Quelle, aus der app.js waehlt; sonst kein Link.

Die Browser-Haelfte der Kette (Klick, Reiterwechsel, Filter, ?ansicht=)
steht in `tests/test_geraete_radar_sprung_browser.py`.
"""
from __future__ import annotations

import json
import pathlib

import pytest
from bs4 import BeautifulSoup

from telco_radar.report.html import render_site

from test_geraete_zeitreihe_ansicht import HEUTE, _baue as _baue_zeitreihe
from test_geraete_zeitreihe_ansicht import _baue_mit_auto
from test_geraete_tco_zustand import _baue as _baue_zustand

WURZEL = pathlib.Path(__file__).resolve().parents[1]


def _rendern(root: pathlib.Path) -> BeautifulSoup:
    """Site in tmp_path bauen und geraete.html als Suppe zurückgeben."""
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")


def _seite(tmp_path: pathlib.Path) -> BeautifulSoup:
    """Die Zeitreihen-Fixture als gerenderte Seite: drei Modelle, drei
    Lagen - iPhone 17 Pro (Bänder klein+mittel), Galaxy S26 (Band klein),
    Pixel 11 (Listung OHNE Bündel -> Katalog ohne Graph-Sprung)."""
    root, _state = _baue_zeitreihe(tmp_path)
    return _rendern(root)


def _erlaubt(suppe: BeautifulSoup) -> set[str]:
    """Die WAHL-Menge der Zeitreihe (nicht-leere Bänder-Listen) - dieselbe
    Menge, gegen die app.js einen Deep-Link prueft."""
    knoten = suppe.select_one("#gr-zeitreihe-daten")
    assert knoten is not None, "Zeitreihen-Knoten fehlt - Test prueft nichts"
    return {k for k, v in json.loads(knoten.get_text())["erlaubt"].items()
            if v}


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


# --------------------------------------------------------------------------
# 1. Der EINE Schluessel steht im Markup aller Reiter
# --------------------------------------------------------------------------

def test_jede_katalogzeile_traegt_ihren_modell_schluessel(tmp_path):
    """`data-modell` an der Katalog-Modellzeile ist der `schluessel` aus
    `katalog_modellzeilen()` - bis P4 stand er nur im Python-Dict, kein
    Sprung konnte die Zeile finden. Die Gegenprobe zaehlt mit: ein
    Match-Check ohne Vollstaendigkeit verschwieg den naechsten Umbau."""
    import yaml

    s = _seite(tmp_path)
    zeilen = s.select("#gr-katalogtabelle tr.gr-k-zeile")
    assert zeilen, "keine Katalog-Modellzeile - der Test prueft nichts"
    ids = [z.get("data-modell") for z in zeilen]
    assert all(ids), "Katalogzeile ohne data-modell"

    # Der Schluessel des Markups ist der gerechnete `modell_schluessel`:
    # nachgebaut aus derselben Fixture (device_id + Speicherstufe).
    root, _ = _baue_zeitreihe(tmp_path / "gegenprobe")
    roh = json.loads((root / "data" / "state" / "geraete_db.json")
                     .read_text(encoding="utf-8"))
    erwartet = {f"{e['device_id']}-{int(e['speicher_gb'])}"
                for e in roh["listungen"]}
    getroffen = {i for i in ids if i in erwartet}
    assert len(getroffen) == len(set(ids)) == len(erwartet), \
        f"Schluessel-Mengen weichen ab: nur {len(getroffen)} von " \
        f"{len(set(ids))} Zeilen treffen die {len(erwartet)} gerechneten"


def test_radar_und_katalog_nutzen_denselben_schluesselraum(tmp_path):
    """Die Modell-Zeilen des Radars und die des Katalogs tragen
    `modell_schluessel`-Ids im selben Namensraum - die Schnittmenge ist
    kein Zufallstreffer ueber Titel. Gemessen an der gemeinsamen Menge:
    jede Radar-Zeile mit Katalog-Zeile hat den Link, jede ohne die
    benannte Luecke."""
    s = _seite(tmp_path)
    radar_ids = {a.get("data-modell") for a in
                 s.select("#wr-abweichung a.gr-sprung[data-modell]")}
    sprung_ids = {a.get("data-modell") for a in
                  s.select("#wr-abweichung a.gr-ksprung[data-modell]")}
    katalog_ids = {z.get("data-modell") for z in
                   s.select("#gr-katalogtabelle tr.gr-k-zeile")}
    assert radar_ids and katalog_ids, "Fixture zu duenn"
    # Derselbe Schluesselraum: die Sprungziele sind KEINE eigene Menge.
    assert sprung_ids <= radar_ids & katalog_ids, \
        "Katalog-Sprung zeigt auf einen Schluessel ausserhalb der Menge"
    # Beide Richtungen der Menge sind besetzt (Schnitt nicht leer UND
    # nicht deckungsgleich - sonst prueft die Fixture die Luecke nicht).
    assert radar_ids & katalog_ids, "kein gemeinsames Modell in der Fixture"
    assert radar_ids - katalog_ids or katalog_ids - radar_ids, \
        "Fixture deckt keinen Differenzfall"


# --------------------------------------------------------------------------
# 2. Radar -> Katalog: jeder Sprung trifft, jede Luecke ist benannt
# --------------------------------------------------------------------------

def test_jeder_radar_katalog_sprung_trifft_seine_zeile(tmp_path):
    s = _seite(tmp_path)
    katalog_ids = {z.get("data-modell") for z in
                   s.select("#gr-katalogtabelle tr.gr-k-zeile")}
    links = s.select("#wr-abweichung a.gr-ksprung[data-modell]")
    assert links, "kein Katalog-Sprung im Radar - der Test prueft nichts"
    fehlende = [a.get("data-modell") for a in links
                if a.get("data-modell") not in katalog_ids]
    assert not fehlende, f"Sprung ohne Zielzeile: {fehlende}"


def test_jede_radarzeile_hat_link_oder_benannte_luecke(tmp_path):
    """Link ODER „nicht im Katalog" - keine Zeile endet stumm. Die Zahl
    beider zusammen ist die Zahl der Modell-Zeilen (kein dritter Zustand)."""
    s = _seite(tmp_path)
    zeilen = s.select("#wr-abweichung tr.gr-a-zeile[data-auf]")
    assert zeilen, "keine Radar-Modellzeile"
    mit_link = [z for z in zeilen if z.select_one("a.gr-ksprung")]
    mit_luecke = [z for z in zeilen
                  if z.select_one("td span.gr-a-klein")
                  and z.select_one("td span.gr-a-klein").get_text(strip=True)
                  == "nicht im Katalog"]
    assert len(mit_link) + len(mit_luecke) == len(zeilen), \
        f"{len(zeilen)} Zeilen, aber nur {len(mit_link)} Link + " \
        f"{len(mit_luecke)} Luecke - es gibt einen stummen dritten Zustand"


def test_reines_buendel_ohne_listung_heisst_nicht_im_katalog(tmp_path):
    """Der Differenzfall aus dem Auftrag: ein Modell MIT Bündel (Radar-
    Zeile), OHNE Listung (keine Katalog-Zeile) - der Katalog-Sprung darf
    nicht als toter Link stehen, die Luecke heisst beim Namen. Fixture:
    `graphloses_modell` haengt ein iPhone-16-Pro-Max-Buendel ohne Listung
    an (BRIEF_RAHMEN2_R3, derselbe Fall wie im Bestand).

    P4-Fix (Sicht-Pruefung 18.09.): der Graph-Sprung derselben Zeile ist
    mitgefallen - das Bündel loest auf KEIN Band auf (`erlaubt` leer,
    nachgemessen an der Fixture), der Deep-Link waere auf das Startgeraet
    gefallen. Der Test findet die Zeile deshalb ueber die MODELLZELLE
    (ueber den Link ginge sie seit dem Fix nicht mehr) und haelt BEIDE
    Luecken fest: 'nicht im Katalog' und 'noch keine Zeitreihe'."""
    s = _baue_zustand(tmp_path, graphloses_modell=True)
    katalog_ids = {z.get("data-modell") for z in
                   s.select("#gr-katalogtabelle tr.gr-k-zeile")}
    ziel = "apple-iphone-16-pro-max-256"
    assert ziel not in katalog_ids, \
        "Fixture-Voraussetzung: das Modell hat keine Katalog-Zeile"
    erlaubt = _erlaubt(s)
    assert ziel not in erlaubt, \
        "Fixture-Voraussetzung: das Modell ist nicht waehlbar " \
        f"(erlaubt enthaelt {ziel})"
    zeile = next(z for z in s.select("#wr-abweichung tr.gr-a-zeile")
                 if "iPhone 16 Pro Max" in _text(z.select_one("td")))
    assert zeile is not None, "Radar-Zeile des Modells fehlt"
    assert zeile.select_one("a.gr-ksprung") is None, \
        "Katalog-Sprung auf ein Modell ohne Katalog-Zeile"
    assert zeile.select_one("a.gr-sprung") is None, \
        "Graph-Sprung auf ein nicht waehlbares Modell (toter Deep-Link)"
    kleins = [" ".join(sp.get_text(" ", strip=True).split())
              for sp in zeile.select("span.gr-a-klein")]
    assert "nicht im Katalog" in kleins
    assert "noch keine Zeitreihe" in kleins


# --------------------------------------------------------------------------
# 3. Katalog -> Zeitreihe: der Link steht nur, wo der Sprung trifft
# --------------------------------------------------------------------------

def test_katalog_graph_sprung_trifft_die_wahlmenge(tmp_path):
    """Der Graph-Link am Katalog-Modellnamen zeigt auf `daten.erlaubt`
    (nicht-leer) - dieselbe Menge, gegen die app.js einen Deep-Link
    prueft. Ein toter Deep-Link fiele laut app.js still aufs Startgeraet
    zurueck und zeigte ein ANDERES Geraet, als der Link verspricht."""
    s = _seite(tmp_path)
    erlaubt = _erlaubt(s)
    links = s.select("#gr-katalogtabelle a.gr-sprung[data-modell]")
    assert links, "kein Graph-Sprung im Katalog - der Test prueft nichts"
    fehlende = [a.get("data-modell") for a in links
                if a.get("data-modell") not in erlaubt]
    assert not fehlende, \
        f"Graph-Sprung ausserhalb der Wahlmenge: {fehlende}"


def test_modell_ohne_buendel_hat_keinen_graph_sprung(tmp_path):
    """Pixel 11 der Fixture: Listung (Katalog-Zeile MIT Preis), aber kein
    Bündel - keine Zeitreihe, kein Graph-Link. Fail-closed: die TCO-Spalte
    nennt den Grund („kein Bündel gemessen"), der Link schweigt."""
    s = _seite(tmp_path)
    zeile = s.select_one(
        '#gr-katalogtabelle tr.gr-k-zeile[data-modell="google-pixel-11-128"]')
    assert zeile is not None, "Fixture-Voraussetzung: Pixel-11-Zeile fehlt"
    assert zeile.select_one("a.gr-sprung") is None, \
        "Graph-Sprung auf ein Modell ohne Zeitreihe"


def test_zr_feld_ohne_erlaubnis_bleibt_false(tmp_path):
    """Unit auf `katalog_modellzeilen`: ohne `zr_erlaubt` (None oder
    leer) ist `zr` ueberall False - fail-closed. Mit erlaubt nur True,
    wo das Modell wirklich drinsteht (gelesen, nie nachgerechnet)."""
    from telco_radar.geraete_config import lade_katalog
    from telco_radar.report.geraete_view import katalog_modellzeilen

    root, _ = _baue_zeitreihe(tmp_path)
    roh = json.loads((root / "data" / "state" / "geraete_db.json")
                     .read_text(encoding="utf-8"))
    eintraege = roh["listungen"]
    katalog = lade_katalog(root)

    ohne = katalog_modellzeilen(eintraege, katalog)
    assert ohne and not any(m["zr"] for m in ohne), \
        "zr=True ohne zr_erlaubt - der Link stünde blind"

    schluessel = {m["schluessel"] for m in ohne}
    teil = schluessel - {"google-pixel-11-128"}
    mit = katalog_modellzeilen(eintraege, katalog, zr_erlaubt=
                               {k: ["klein"] for k in teil})
    wahr = {m["schluessel"] for m in mit if m["zr"]}
    assert wahr == teil, \
        f"zr trifft nicht die uebergebene Menge: {wahr} != {teil}"


# --------------------------------------------------------------------------
# 3b. Radar -> Zeitreihe: P4-Fix (Sicht-Pruefung 18.09.) - fail closed
# --------------------------------------------------------------------------

def test_radar_graph_sprung_ohne_zeitreihe_nennt_die_luecke(tmp_path):
    """Der Live-Befund der P4-Sichtpruefung: die Radar-Tabelle verlinkte
    "im Graph ansehen" auf JEDE Modell-Zeile - kennt die Zeitreihe das
    Modell nicht (10 iPhone-18-Pro/Pro-Max-Zeilen am 18.09., Auto-Modell
    unter der Messtag-Schwelle), fiel der Deep-Link still auf das
    STARTGERAET zurueck: der Klick zeigte die Zahlen eines ANDEREN
    Geraets, ohne Meldung. Die schlimmste Art eines toten Sprungs.

    Seit dem Fix steht der Link nur auf der WAHL-Menge (`daten.erlaubt`,
    nicht-leer - dieselbe Quelle wie der Katalog-Sprung), und jede Zeile
    ausserhalb nennt die Luecke "noch keine Zeitreihe". Fixture:
    `_baue_mit_auto(..., ["2026-09-15"])` haengt genau den Live-Fall an -
    ein AUTO-iPhone-18-Pro mit EINEM Messtag (nicht waehlbar) neben dem
    waehlbaren iPhone 17 Pro (Gegenprobe: der Link steht dort)."""
    root, _state = _baue_mit_auto(tmp_path, ["2026-09-15"])
    s = _rendern(root)
    erlaubt = _erlaubt(s)
    zeilen = s.select("#wr-abweichung tr.gr-a-zeile[data-auf]")
    assert zeilen, "keine Radar-Modellzeile - der Test prueft nichts"

    def _graph_zelle(z):
        """Die LETZTE Zelle ist die Graph-Spalte (Spaltenkopf 'Graph')."""
        zellen = z.select("td")
        return zellen[-1] if zellen else None

    luecken, links = [], []
    for z in zeilen:
        # Der Schluessel steht am gr-sprung (data-modell); die Luecken-
        # Zeile hat keinen Link mehr - ihr Schluessel laesst sich ueber
        # die Modellzelle nicht sicher lesen, deshalb zaehlt der Test
        # Zeilen MIT Link gegen erlaubt und Luecken gegen den Bestand.
        a = z.select_one("a.gr-sprung[data-modell]")
        if a is not None:
            links.append(a.get("data-modell"))
        elif "noch keine Zeitreihe" in _text(_graph_zelle(z) or z):
            luecken.append(z)
    # 1) JEDER Link trifft die Wahlmenge (kein toter Deep-Link mehr).
    tote = [m for m in links if m not in erlaubt]
    assert not tote, f"Graph-Sprung ausserhalb der Wahlmenge: {tote}"
    # 2) Das nicht waehlbare iPhone 18 steht als BENANNTE Luecke da.
    assert luecken, "keine Zeile mit 'noch keine Zeitreihe' - " \
                    "die Fixture deckt den Fall nicht"
    achtzehn = [z for z in luecken
                if "iPhone 18" in _text(z.select_one("td"))]
    assert achtzehn, "das Auto-iPhone-18 der Fixture hat keine Luecken-Zeile"
    assert not any(z.select_one("a.gr-sprung") for z in luecken), \
        "Luecken-Zeile mit Link - der dritte Zustand ist zurueck"
    # 3) Gegenprobe am SELBEN Bestand: das waehlbare iPhone 17 Pro
    # traegt den Link (die Luecke ist eine Aussage ueber das Modell,
    # nicht ein Rueckbau der ganzen Spalte).
    assert any(m and "iphone-17-pro" in m for m in links), \
        "waehlbares Modell ohne Graph-Sprung"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
