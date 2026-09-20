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

  K1 -> die Aufklapper, die eine MENGE verbergen: der Massstab
        ("N Tarife anzeigen") und die innere "N weitere Tarife"-Klappe.
        app.js setzt KEIN Klapplabel mehr nach (der Karten-Sortierer ist
        mit der Klappe gefallen) - der Wortlaut lebt nur im Template.
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

import json
import re

from test_geraete_tco_zustand import _baue, vorlage_text

BEGRIFFE = {"TCO-24", "Tarifband", "Bündel",
            "Abweichungs-Vorzeichen (+/−) zu Vodafone"}


def _baue_mit_referenzen(tmp_path, weitere: int):
    """`_baue` mit mehr SIM-only-Referenzen: erst ab fuenf (SICHTBAR ist
    vier) entsteht die innere "N weitere Tarife"-Klappe - ohne diesen
    Schritt pruefte der K1-Test sie an einer Fixture, die den Fall nie
    ausloest (Lookup-Falle: gruen und prueft nichts)."""
    from telco_radar.report.html import render_site
    s = _baue(tmp_path)
    pfad = tmp_path / "mit" / "data" / "state" / "geraete_tco.json"
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    vorlage = daten["sim_only"][0]
    for i in range(weitere):
        eintrag = dict(vorlage)
        eintrag.update({
            "id": f"simonly--extra-{i}", "anbieter": "congstar",
            "tarif_name": f"Congstar Home {i}", "tarif_id": f"cs:{i}",
            "tarif_sim_only_monatlich": 10.0 + i,
            "quelle_url": f"https://example.de/pib/cs-{i}"})
        daten["sim_only"].append(eintrag)
    pfad.write_text(json.dumps(daten), encoding="utf-8")
    root = tmp_path / "mit"
    render_site(root / "site", root / "data" / "reports")
    from bs4 import BeautifulSoup
    return BeautifulSoup((root / "site" / "geraete.html").read_text(
        encoding="utf-8"), "html.parser")


# --------------------------------------------------------------------------
# 1. Das Klapplabel (portiert: Massstabs-Klappen statt Kartenklappe)
# --------------------------------------------------------------------------

def test_das_klapplabel_nennt_handlung_und_zahl(tmp_path):
    """Jede Klappe, die eine MENGE verbergen, traegt "<N> <Ding> anzeigen"
    - die Zahl als nackter Text direkt vor dem Wort (das Abnahmekriterium
    greift die Zeile per grep am Quelltext) und ein Aktionswort. In der
    O3-Struktur sind das der Tarifmassstab und seine innere Klappe; die
    Kartenklappe, fuer die SQ67 die Regel erfand, ist mit O2 gefallen."""
    s = _baue_mit_referenzen(tmp_path, weitere=4)
    # E2 (§3.1c): die zwei Fuss-Aufklapper (Massstab, Datenlage) sind EIN
    # Aufklapper "Massstab & Datenlage" - der NAME ist Antonios Wortlaut
    # und traegt keine Zahl. Die SQ67-Regel (Zahl + Handlung) lebt an der
    # Stelle weiter, an der sie erfunden wurde: die Zahl steht im ersten
    # Satz des Inhalts und zaehlt die Zeilen beider Tabellen.
    klappe = s.select_one("details#gr-massstab-datenlage")
    assert klappe is not None, \
        "die Fixture traegt keine Massstabs-Klappe (keine Referenzen)"
    summary = klappe.select_one("summary")
    text = re.sub(r"\s+", " ", summary.get_text(" ", strip=True))
    assert text == "Maßstab & Datenlage", f"falscher Klapname: {text!r}"
    inhalt = " ".join(klappe.get_text(" ", strip=True).split())
    treffer = re.search(r"(\d+)\s+Tarife\s+aus\s+den", inhalt)
    assert treffer, f"keine Tarifzahl im Inhalt: {inhalt[:120]!r}"
    zeilen = klappe.select("table.gr-ttab--simonly tbody tr")
    assert zeilen, "Klappe ohne Tabellenzeilen - der Test prueft nichts"
    assert int(treffer.group(1)) == len(zeilen), (
        f"der Satz zaehlt {treffer.group(1)}, die Klappe traegt "
        f"{len(zeilen)} Tarifzeilen")


def test_die_innere_klappe_nennt_handlung_und_zahl(tmp_path):
    """Die innere Klappe ("N weitere Tarife") folgt derselben Regel wie
    die aeussere - bis zur Portierung hiess sie "Die uebrigen N Tarife",
    ein Etikett ohne Handlung. Die Zahl muss die Zeilen der EIGENEN
    Tabelle zaehlen, nicht die Gesamtmenge der aeusseren Klappe."""
    s = _baue_mit_referenzen(tmp_path, weitere=4)
    klappe = s.select_one("details#gr-massstab-datenlage")
    innere = klappe.select("details.gr-auf summary")
    texte = [re.sub(r"\s+", " ", t.get_text(" ", strip=True))
             for t in innere]
    treffer = [t for t in texte
               if re.search(r"\d+\s+weitere\s+Tarife\s+anzeigen", t)]
    assert treffer, \
        f"keine innere Klappe mit Handlung und Zahl: {texte!r} - die " \
        "Fixture stellt mehr als vier Referenzen, der Fall MUSS eintreten"
    innere_klappe = klappe.select("details.gr-auf")[0]
    zeilen = innere_klappe.select("table.gr-ttab--simonly tbody tr")
    assert zeilen, "innere Klappe ohne eigene Tabellenzeilen"
    assert re.search(rf"{len(zeilen)}\s+weitere\s+Tarife\s+anzeigen",
                     treffer[0]), (
        f"{treffer[0]!r} zaehlt nicht die {len(zeilen)} Zeilen ihrer "
        "eigenen Tabelle")


def test_app_js_setzt_keine_klapplabels_mehr_nach():
    """Nachfolger des SQ67-Tests 'app.js baut dasselbe Klapplabel nach':
    Der Karten-Sortierer, der das Karten-Klapplabel im gefilterten
    Zustand neu setzte, ist mit der Klappe in O2 gefallen - der Wortlaut
    lebt NUR NOCH im Template, es gibt keine zweite Stelle, die mit ihm
    auseinanderlaufen koennte. Dieser Test haelt genau das fest: setzt
    jemand wieder einen Label-Wortlaut im JS nach, taucht hier die
    Doppelung auf, gegen die der Ursprungstest gebaut war."""
    from pathlib import Path
    app_js = (Path(__file__).resolve().parents[1]
              / "src/telco_radar/report/templates/app.js").read_text(
                  encoding="utf-8")
    assert "Tarife anzeigen" not in app_js, \
        "app.js setzt einen Klapplabel-Wortlaut nach - der lebt seit der " \
        "Portierung nur im Template"
    assert "Anbieterangebote anzeigen" not in app_js, \
        "app.js setzt das alte Karten-Klapplabel nach - die Kartenklappe " \
        "ist seit O2 gefallen"


# --------------------------------------------------------------------------
# 2. Die Paradox-Zeile (portiert: Rechenweg der Buendel-Zeile)
# --------------------------------------------------------------------------

def _zeilen_mit_zwei_preisen(soup):
    """Belastbare Zeilen, die einen GERAETEPREIS tragen (Barpreis oder
    Finanzierungssumme) - nur sie zeigen das Paradox zweier Zahlen. Die
    1&1-Zeile der Fixture (ein Monatspreis fuer Tarif und Geraet
    zusammen, kein Geraetepreis) bleibt bewusst aussen vor."""
    ergebnis = []
    for zeile in soup.select("#tafel-tco .gr-bnd"):
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
    BEGRIFFE ohne Klick leistet die Antwortzeile ueber dem Graph."""
    s = _baue(tmp_path, eins_und_eins=True)
    zeilen = _zeilen_mit_zwei_preisen(s)
    assert zeilen, "die Fixture traegt keine Zeile mit zwei Preisen"
    for zeile in zeilen:
        paradox = zeile.select_one(".gr-kk-paradox")
        assert paradox is not None, (
            f"Zeile {zeile.get('data-anbieter')}: zwei Preise ohne "
            "Erklaerzeile")
        text = re.sub(r"\s+", " ", vorlage_text(paradox))
        assert "Gerät" in text and "Tarif" in text, text
        # Die Zeile steht DIREKT unter den zwei Zahlen des Rechenwegs:
        # nach der Leitzeile (TCO gesamt), vor der Oe-Bindungszeile -
        # nicht erst am Ende hinter Belegen und Luecken.
        html = str(zeile)
        assert html.index("gr-bnd-rw-z") < html.index("gr-kk-paradox") \
            < html.index("gr-kk-bau"), (
            f"Zeile {zeile.get('data-anbieter')}: Paradox-Zeile steht "
            "nicht zwischen Leitzahl und Bau-Zeile")
        # Sichtbar ohne WEITEREN Klick: kein eigener <details>-Block
        # zwischen Zeilengrenze und Satz - die Zeile selbst ist der EINE
        # Aufklapper, der sie sichtbar macht.
        for ahne in paradox.parents:
            if ahne.name == "details":
                assert "gr-bnd" in (ahne.get("class") or []), \
                    "die Paradox-Zeile steckt in einer weiteren Aufklappung"
    # Gegenprobe gegen die Lookup-Falle: die 1&1-Zeile der Fixture hat
    # KEINEN Geraetepreis (nur den kombinierten Monatspreis, 13.2) und
    # damit keine zwei Zahlen - sie darf die Erklaerzeile nicht tragen.
    eins_und_eins = [z for z in s.select("#tafel-tco .gr-bnd")
                     if z.get("data-anbieter") == "1&1"]
    assert eins_und_eins, "die Fixture traegt keine 1&1-Zeile"
    for zeile in eins_und_eins:
        assert zeile.select_one(".gr-kk-paradox") is None, \
            "1&1-Zeile ohne Geraetepreis traegt eine Paradox-Zeile"


def test_die_paradox_zeile_nennt_den_zeitraum_ihrer_raten(tmp_path):
    """Der Zeitraum in der Erklaerzeile nennt die Raten DERSELBEN Zeile,
    keine feste Zahl. Bis A1 log das Label "TCO-36" einer Zeile die
    Erklearzeile in die eigene Zukunft und die Kappungstropee "24
    Monatsraten"; seit A1 ist die Pruefung zweigeteilt wie die Erklearzeile
    selbst: der Finanzierungszweig nennt "alle N Raten plus M Monate Tarif"
    (N = Ratenzahl des Bau-Satzes), der Barpreis-Zweig nennt "Gerät + M
    Monate Tarif" (M = der Horizont des Labels "Kosten über 24 Monate")."""
    s = _baue(tmp_path)
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
        label_monate = re.search(r"über (\d+) Monate",
                                 label.get_text(" ", strip=True))
        assert label_monate, label.get_text(" ", strip=True)
        monate = label_monate.group(1)
        if "Geräteraten plus" in fluss:
            geprueft += 1
            assert raten, f"Bau-Satz ohne Ratenzahl: {bau_fluss!r}"
            assert f"alle {raten.group(1)} Geräteraten" in fluss \
                and f"{monate} Monate Tarif" in fluss, (
                f"Zeile {zeile.get('data-anbieter')}: Bau sagt "
                f"{raten.group(1)} Raten, Label {monate} Monate, "
                f"Erklaerzeile {fluss!r}")
        else:
            geprueft += 1
            assert f"Gerät + {monate} Monate Tarif" in fluss, (
                f"Zeile {zeile.get('data-anbieter')}: Label "
                f"{label_monate.group(0)}, aber Erklaerzeile {fluss!r}")
    assert geprueft, "keine Zeile mit Erklearzeile - der Test prueft nichts"


# --------------------------------------------------------------------------
# 3. Das Glossar
# --------------------------------------------------------------------------

def test_das_glossar_ist_endgueltig_weg(tmp_path):
    """Antonio (16.09.2026, §3.1 AUFTRAG_GERAETE_EINE_SEITE_V2): „Ich will
    den Abschnitt Begriffe erklärt: weg." - das Glossar ist ENDE, ebenso
    der 'Wie gerechnet?'-Block; genau DREI Rest-Aufklapper bleiben
    (Rechenschaftssatz, Rechenweg je Anbieterzeile, Fuss 'Massstab &
    Datenlage'). Die vier Begriffe leben dort, wo sie gelesen werden:
    TCO-24 loest der Antwort-Satz selbst auf (§4.9), das Band nennt die
    Wahl-Leiste mit ihrer GB-Spanne."""
    s = _baue(tmp_path)
    assert s.select_one("section#gr-glossar") is None, \
        "das Glossar ist zurueckgekehrt"
    text = s.select_one("#tafel-tco").get_text(" ", strip=True)
    assert "Begriffe erklärt" not in text
    assert "Wie gerechnet?" not in text


def test_der_antwort_satz_und_die_wahl_leiste_erklaeren_die_begriffe(
        tmp_path):
    """Was das Glossar trug, steht jetzt am ORT seiner Zahl: die Leitzahl
    mit ihrem Namen im Antwort-Satz (seit A1 "Kosten über 24 Monate" -
    der Name ist seine eigene Aufloesung), das Tarifband mit GB-Spanne an
    der Wahl - keine zweite Definition derselben Worte auf der Seite."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    antwort = tafel.select_one(".gr-zr-antwort").get_text(" ", strip=True)
    assert "Kosten über 24 Monate" in antwort
    knoepfe = {k.get_text(" ", strip=True): k
               for k in tafel.select("#gr-zr-baender button")}
    assert any("20 GB" in text for text in knoepfe), \
        "die Band-Knöpfe nennen keine GB-Spanne"
    assert any("60 GB" in text for text in knoepfe), knoepfe.keys()
