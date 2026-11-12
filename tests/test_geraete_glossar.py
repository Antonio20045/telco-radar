"""SQ67 (15.09.2026): drei Stellen der Geraeteseite, die fuer die Zielgruppe
(Vodafone-Device-Einkaeufer, keine Endkunden) klarer werden.

  1. Das Klapplabel nennt die HANDLUNG und die Zahl - "(25 Tarife)" war
     ein Etikett ueber einem Bedienelement, dessen Wirkung niemand
     beschrieb.
  2. Die Paradox-Zeile: "Gerät 999 € / mit Tarif 941 €" ohne Erklaerung
     ist ein Widerspruch der Zeile gegen sich selbst (die mit-Tarif-Zahl
     kann hoeher wie niedriger liegen). Ein kurzer Satz, mit dem Zeitraum,
     der die Zahl traegt.
  3. Das Glossar: vier wiederkehrende Fachbegriffe, je ein Satz, sichtbar
     am Ende der Vergleichsansicht und ueber einen Link erreichbar.

PORTIERT IN DIE O3-STRUKTUR (Merge 16.09.2026): SQ67 wurde auf der
Vor-O1-Seitenstruktur gebaut - Anbieterkarten hinter einer Sammelklappe,
Link unter der Modell-Auswahl. O1-O3 haben die Karten zu Tabellenzeilen
gemacht (`_geraete_buendel.html.j2`), die Sammelklappe ist gefallen, und
zwischen Modell-Auswahl und Graph steht seit A1 nichts mehr (die erste
Balkenzeile liegt an der Telefon-Falz schon knapp, `pruefe_portal.py`
11c - deshalb wurde der Glossar-Link in die Graph-Fussnote verlegt, nicht
unter die Auswahl). Die INTENTION der drei Kriterien traegt; die Orte
sind die der neuen Struktur:

  K1 -> entfallen: der Tarifmassstab samt "N weitere Tarife"-Klappe steht
        seit 02.11.2026 nicht mehr auf der Seite.
  K2 -> der Rechenweg-Aufklapper jeder Buendel-ZEILE (die fuenf
        Kernangaben stehen offen, ALLES weitere im EINEN Rechenweg, A6);
        die Begriffe selber erklaert die Antwortzeile ueber dem Graph
        schon ohne Klick ("Gerätepreis: einmalig ohne Vertrag · mit
        Tarif: Gesamtpreis über 24 Monate").
  K3 -> der Glossar-Abschnitt am Tafelende (unchanged, er kam durch den
        Merge); sein Link in der Graph-Fussnote.

Alle Tests dieser Datei sind NEU - rot-vor gilt nicht, der alte Stand
kannte keines der Merkmale. Dieselbe Fixture wie `test_geraete_rahmen`
(o2 neu und erneuert, Vodafone als Referenzrechnung, optional 1&1 ohne
Geraetepreis): Sie traegt beide Zeilenarten MIT zwei Preisen (Barpreis-
und Finanzierungszweig) plus eine Zeile ohne Geraetepreis als
Gegenprobe.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import re
import socket
import threading

from test_geraete_tco_zustand import _baue, lager, vorlage_text

BEGRIFFE = {"TCO-24", "Tarifband", "Bündel", "Abweichungs-Vorzeichen (+/−) zu Vodafone"}


@contextlib.contextmanager
def _server(site):
    """Ein lokaler Server statt file://, damit ``fetch()`` die Fragmente lädt."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


def baue_mit_referenzen(tmp_path, weitere: int):
    """`_baue` mit mehr SIM-only-Referenzen: erst ab fuenf (SICHTBAR ist
    vier) entsteht die innere "N weitere Tarife"-Klappe - ohne diesen
    Schritt pruefte der K1-Test sie an einer Fixture, die den Fall nie
    ausloest (Lookup-Falle: gruen und prueft nichts)."""
    from telco_radar.report.html import render_site

    _baue(tmp_path)
    pfad = tmp_path / "mit" / "data" / "state" / "geraete_tco.json"
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    vorlage = daten["sim_only"][0]
    for i in range(weitere):
        eintrag = dict(vorlage)
        eintrag.update(
            {
                "id": f"simonly--extra-{i}",
                "anbieter": "congstar",
                "tarif_name": f"Congstar Home {i}",
                "tarif_id": f"cs:{i}",
                "tarif_sim_only_monatlich": 10.0 + i,
                "quelle_url": f"https://example.de/pib/cs-{i}",
            }
        )
        daten["sim_only"].append(eintrag)
    pfad.write_text(json.dumps(daten), encoding="utf-8")
    root = tmp_path / "mit"
    render_site(root / "site", root / "data" / "reports")
    from bs4 import BeautifulSoup

    return BeautifulSoup(
        (root / "site" / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )


def _zeilen_mit_zwei_preisen(soup):
    """Belastbare Zeilen, die einen GERAETEPREIS tragen (Barpreis oder
    Finanzierungssumme) - nur sie zeigen das Paradox zweier Zahlen. Die
    1&1-Zeile der Fixture (ein Monatspreis fuer Tarif und Geraet
    zusammen, kein Geraetepreis) bleibt bewusst aussen vor.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; der
    Aufrufer reicht die Zeilen des Fragments (`lager`)."""
    ergebnis = []
    for zeile in soup.select(".gr-bnd"):
        bar = zeile.select_one(".gr-bnd-bar")
        if bar is None:
            continue
        text = re.sub(r"\s+", " ", bar.get_text(" ", strip=True))
        if text and text != "–":
            ergebnis.append(zeile)
    return ergebnis


def test_jede_zeile_mit_zwei_preisen_traegt_die_paradox_zeile(tmp_path):
    """Eine Zeile, die Geraetepreis UND mit-Tarif-Zahl zeigt, erklaert in
    einem Satz, was die zweite Zahl enthaelt - mit dem Zeitraum, der sie
    traegt. Seit O2 stehen die fuenf Kernangaben offen und ALLES weitere
    im EINEN Rechenweg-Aufklapper der Zeile (A6); die Erklaerung der
    BEGRIFFE ohne Klick leistet die Antwortzeile ueber dem Graph.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    seite = _baue(tmp_path, eins_und_eins=True)
    assert not seite.select("#tafel-tco .gr-bnd"), "Bündelzeilen stehen auf der Seite"
    s = lager(tmp_path)
    zeilen = _zeilen_mit_zwei_preisen(s)
    assert zeilen, "die Fixture traegt keine Zeile mit zwei Preisen"
    for zeile in zeilen:
        paradox = zeile.select_one(".gr-kk-paradox")
        assert paradox is not None, (
            f"Zeile {zeile.get('data-anbieter')}: zwei Preise ohne Erklaerzeile"
        )
        text = re.sub(r"\s+", " ", vorlage_text(paradox))
        assert "Gerät" in text and "Tarif" in text, text
        html = str(zeile)
        assert (
            html.index("gr-bnd-rw-z")
            < html.index("gr-kk-paradox")
            < html.index("gr-kk-bau")
        ), (
            f"Zeile {zeile.get('data-anbieter')}: Paradox-Zeile steht "
            "nicht zwischen Leitzahl und Bau-Zeile"
        )
        for ahne in paradox.parents:
            if ahne.name == "details":
                assert "gr-bnd" in (ahne.get("class") or []), (
                    "die Paradox-Zeile steckt in einer weiteren Aufklappung"
                )
    eins_und_eins = [z for z in s.select(".gr-bnd") if z.get("data-anbieter") == "1&1"]
    assert eins_und_eins, "die Fixture traegt keine 1&1-Zeile"
    for zeile in eins_und_eins:
        assert zeile.select_one(".gr-kk-paradox") is None, (
            "1&1-Zeile ohne Geraetepreis traegt eine Paradox-Zeile"
        )


def test_die_paradox_zeile_nennt_den_zeitraum_ihrer_raten(tmp_path):
    """Der Zeitraum in der Erklaerzeile nennt die Raten DERSELBEN Zeile,
    keine feste Zahl. Bis A1 log das Label "TCO-36" einer Zeile die
    Erklearzeile in die eigene Zukunft und die Kappungstropee "24
    Monatsraten"; seit A1 ist die Pruefung zweigeteilt wie die Erklearzeile
    selbst: der Finanzierungszweig nennt "alle N Raten plus M Monate Tarif"
    (N = Ratenzahl des Bau-Satzes), der Barpreis-Zweig nennt "Gerät + M
    Monate Tarif". M ist der Horizont des Labels, aber höchstens 24: der Tarif
    zählt nur seine Bindung, Monat 25-36 nur die Rate (Antonio 10.10.2026); ein
    Betrag für Tarif und Gerät zusammen (1&1) läuft über den ganzen Horizont.

    Seit 10.10.2026 steht die Bündelliste nicht mehr auf der Seite; geprüft
    wird das Fragment."""
    _baue(tmp_path)
    s = lager(tmp_path)
    geprueft = 0
    for zeile in _zeilen_mit_zwei_preisen(s):
        label = zeile.select_one(".gr-bnd-label")
        paradox = zeile.select_one(".gr-kk-paradox")
        bau = zeile.select_one(".gr-kk-bau")
        if label is None or paradox is None or bau is None:
            continue
        fluss = re.sub(r"\s+", " ", vorlage_text(paradox))
        bau_fluss = re.sub(r"\s+", " ", vorlage_text(bau))
        raten = re.search(r"in (\d+) Raten", bau_fluss)
        label_monate = re.search(r"über (\d+) Monate", label.get_text(" ", strip=True))
        assert label_monate, label.get_text(" ", strip=True)
        monate = label_monate.group(1)
        if "für Tarif und Gerät zusammen" not in bau_fluss and int(monate) > 24:
            monate = "24"
            basis = zeile.select_one(".gr-kk-basis")
            assert basis is not None and "Monat 25–" in vorlage_text(basis), fluss
        if "Geräteraten plus" in fluss:
            geprueft += 1
            assert raten, f"Bau-Satz ohne Ratenzahl: {bau_fluss!r}"
            assert (
                f"alle {raten.group(1)} Geräteraten" in fluss
                and f"{monate} Monate Tarif" in fluss
            ), (
                f"Zeile {zeile.get('data-anbieter')}: Bau sagt "
                f"{raten.group(1)} Raten, Label {monate} Monate, "
                f"Erklaerzeile {fluss!r}"
            )
        else:
            geprueft += 1
            assert f"Gerät + {monate} Monate Tarif" in fluss, (
                f"Zeile {zeile.get('data-anbieter')}: Label "
                f"{label_monate.group(0)}, aber Erklaerzeile {fluss!r}"
            )
    assert geprueft, "keine Zeile mit Erklearzeile - der Test prueft nichts"


def test_das_glossar_ist_endgueltig_weg(tmp_path):
    """Antonio (16.09.2026, §3.1 AUFTRAG_GERAETE_EINE_SEITE_V2): „Ich will
    den Abschnitt Begriffe erklärt: weg." - das Glossar ist ENDE, ebenso
    der 'Wie gerechnet?'-Block; seit Auflage 1 (Pruefung PR #100,
    12.11.2026) bleiben genau ZWEI Rest-Aufklapper (Rechenweg je
    Anbieterzeile, Fuss 'Massstab & Datenlage') - der Rechenschaftssatz
    ("So gerechnet") ist mit dem Antwort-Satz selbst von der Seite. Die
    vier Begriffe leben dort, wo sie gelesen werden: TCO-24 loest seither
    das aria-label des Graph-Abschnitts auf (§4.9), das Band nennt die
    Wahl-Leiste mit ihrer GB-Spanne."""
    s = _baue(tmp_path)
    assert s.select_one("section#gr-glossar") is None, "das Glossar ist zurueckgekehrt"
    text = s.select_one("#tafel-tco").get_text(" ", strip=True)
    assert "Begriffe erklärt" not in text
    assert "Wie gerechnet?" not in text


def test_der_graphkopf_und_die_wahl_leiste_erklaeren_die_begriffe(tmp_path):
    """Was das Glossar trug, steht jetzt am ORT seiner Zahl - seit A1 "Kosten
    über 24 Monate" statt TCO-24, der Name ist seine eigene Aufloesung -,
    das Tarifband mit GB-Spanne an der Wahl - keine zweite Definition
    derselben Worte auf der Seite. Pruefung PR #100, Auflage 1
    (12.11.2026): der Antwort-Satz, der diese Aufloesung bis dahin trug,
    ist von der Seite genommen; sie steht seither im aria-label des
    Graph-Abschnitts (dem Namen der Leitzahl, zugaenglich fuer Screenreader
    auch ohne sichtbaren Satz)."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select_one(".gr-zr-antwort") is None
    graph = tafel.select_one(".gr-zr-graph")
    assert "Kosten über 24 Monate" in (graph.get("aria-label") or "")
    knoepfe = {
        k.get_text(" ", strip=True): k for k in tafel.select("#gr-zr-baender button")
    }
    assert any("5 GB" in text for text in knoepfe), (
        "die Band-Knöpfe nennen kein Datenvolumen"
    )
    assert any("36 GB" in text for text in knoepfe), knoepfe.keys()
