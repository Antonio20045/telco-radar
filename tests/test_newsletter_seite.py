"""Die Anmeldeseite, ihre Schwelle und die Stichwort-Vorschau.

Der wichtigste Test hier ist der letzte: die Vorschau zaehlt im BROWSER gegen
`data/keyword-index.json`, `filters.vorschau()` zaehlt in Python gegen die
Berichte. Laufen die zwei auseinander, sagt die Seite eine Zahl voraus, die
der Versand nie einloest - und beide sind fuer sich gruen. Dieselbe Falle wie
beim Archiv-Dialog in app.js, wo zwei Tests Konstanten und Stoppwoerter
zusammenhalten.
"""
import json
import os
import re
import shutil
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from telco_radar.config import load_config
from telco_radar.newsletter.config import lade_katalog
from telco_radar.report import newsletter_seite as ns
from telco_radar.report.html import render_site

WURZEL = Path(__file__).resolve().parents[1]


def _projekt(tmp_path, *, vollstaendig: bool, dienst: str = ""):
    """Eine Projektwurzel mit echten Configs und echten Berichten."""
    for name in ("content", "config", "data"):
        shutil.copytree(WURZEL / name, tmp_path / name)
    if vollstaendig:
        for datei in ("impressum.md", "datenschutz.md"):
            pfad = tmp_path / "content" / "legal" / datei
            pfad.write_text(pfad.read_text(encoding="utf-8").replace(
                "{{ANSCHRIFT}}", "Musterweg 1, 12345 Musterstadt"),
                encoding="utf-8")
    cfg = load_config(tmp_path)
    cfg.settings["newsletter_dienst_url"] = dienst
    site = tmp_path / "site"
    render_site(site, tmp_path / "data" / "reports", cfg=cfg)
    return site


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(WURZEL)


# =====================================  Veroeffentlichungsschwelle  ========

def test_ohne_vollstaendiges_impressum_kein_nav_eintrag(tmp_path):
    """Art. 13 DSGVO verlangt die Information ZUM ZEITPUNKT der Erhebung.
    Ohne sie darf diese Seite keine Adresse entgegennehmen - und die Regel
    steht im CODE, nicht in einem Test: eine Regel, die nur ein Test kennt,
    schaltet keine Navigation."""
    site = _projekt(tmp_path, vollstaendig=False)
    nav = BeautifulSoup((site / "index.html").read_text(encoding="utf-8"),
                        "html.parser").select(".subnav a")
    assert "newsletter.html" not in {a["href"] for a in nav}


def test_mit_vollstaendigem_impressum_steht_der_eintrag_da(tmp_path):
    """Die Gegenprobe - ohne sie belegt der Test oben nur, dass der Eintrag
    NIE erscheint."""
    site = _projekt(tmp_path, vollstaendig=True)
    for seite in ("index.html", "meldungen.html", "transparenz.html"):
        nav = BeautifulSoup((site / seite).read_text(encoding="utf-8"),
                            "html.parser").select(".subnav a")
        assert "newsletter.html" in {a["href"] for a in nav}, seite


def test_die_seite_wird_auch_unterhalb_der_schwelle_gebaut(tmp_path):
    """Gebaut, getestet, ueber ihren direkten Link erreichbar - nur nicht
    verlinkt. Dieselbe Regel wie bei Tarif- und Lieferzeitseite."""
    site = _projekt(tmp_path, vollstaendig=False)
    assert (site / "newsletter.html").exists()
    html = (site / "newsletter.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one(".nl-gesperrt") is not None
    assert soup.select_one("#nl-submit").has_attr("disabled")


def test_oberhalb_der_schwelle_nimmt_die_seite_entgegen(tmp_path):
    site = _projekt(tmp_path, vollstaendig=True, dienst="https://x.invalid")
    soup = BeautifulSoup((site / "newsletter.html").read_text(encoding="utf-8"),
                         "html.parser")
    assert not soup.select_one("#nl-submit").has_attr("disabled")
    assert soup.select_one("form#nl-form").get("data-gesperrt") is None
    # Der Sperrkasten im <noscript> bleibt - er beschreibt einen anderen Fall.
    assert soup.select_one("form .nl-gesperrt") is None


def test_ohne_dienst_url_kann_die_seite_nichts_absenden(tmp_path):
    """Zwei unabhaengige Bedingungen: die Rechtstexte UND ein erreichbarer
    Dienst. Fehlt die Adresse, sagt das Formular es - statt ins Leere zu
    posten."""
    site = _projekt(tmp_path, vollstaendig=True, dienst="")
    html = (site / "newsletter.html").read_text(encoding="utf-8")
    konfig = json.loads(BeautifulSoup(html, "html.parser")
                        .select_one("#nl-config").text)
    assert konfig["dienst"] == ""
    assert konfig["frei"] is True


# ================================================  Inhalt des Formulars  ===

def test_alle_vier_dimensionen_stehen_auf_der_seite(tmp_path, katalog):
    site = _projekt(tmp_path, vollstaendig=True)
    soup = BeautifulSoup((site / "newsletter.html").read_text(encoding="utf-8"),
                         "html.parser")
    from telco_radar.newsletter.config import FELD_JE_DIMENSION
    for dimension, feld in FELD_JE_DIMENSION.items():
        gezeigt = {i["value"] for i in
                   soup.select(f'input[name="{feld}"]')}
        assert gezeigt == katalog.schluessel(dimension), dimension


def test_neben_jeder_dimension_steht_dass_leer_alles_heisst(tmp_path):
    """Die Erwartung fast aller Nutzer - und es ist NICHT die Erwartung der
    anderen. Deshalb steht es da: das ist keine Bedienhilfe, sondern die
    Regel selbst."""
    site = _projekt(tmp_path, vollstaendig=True)
    soup = BeautifulSoup((site / "newsletter.html").read_text(encoding="utf-8"),
                         "html.parser")
    # Nur die vier Dimensionsbloecke - der Stichwortblock traegt denselben
    # Hinweistext-Stil, sagt aber etwas anderes (Stichwoerter sind ADDITIV,
    # dort waere "leer heisst alles" schlicht falsch).
    hinweise = [h.get_text(" ", strip=True)
                for h in soup.select('.nl-block:has(input[type="checkbox"]) .nl-hinweis')]
    assert len(hinweise) == 4, [h[:40] for h in hinweise]
    for text in hinweise:
        assert "alles" in text.lower(), text


def test_die_einwilligung_ist_nicht_vorausgewaehlt(tmp_path):
    """Eine vorangekreuzte Einwilligung ist keine."""
    site = _projekt(tmp_path, vollstaendig=True)
    soup = BeautifulSoup((site / "newsletter.html").read_text(encoding="utf-8"),
                         "html.parser")
    assert not soup.select_one("#nl-consent").has_attr("checked")


def test_der_einwilligungstext_steht_im_wortlaut_daneben(tmp_path):
    """Nicht eine gekuerzte Fassung: eine Zustimmung zu einem Text, den der
    Nutzer nie gesehen hat, ist keine."""
    from telco_radar.report import rechtstexte
    site = _projekt(tmp_path, vollstaendig=True)
    soup = BeautifulSoup((site / "newsletter.html").read_text(encoding="utf-8"),
                         "html.parser")
    auf_der_seite = soup.select_one(".nl-consent-text").get_text(" ", strip=True)
    fassung = rechtstexte.aktuelle_einwilligung(WURZEL)
    for absatz in ns.einwilligung_absaetze(fassung.text):
        assert absatz in auf_der_seite, absatz[:60]
    assert fassung.version in soup.get_text()


def test_der_einwilligungstext_traegt_nicht_die_umbrueche_der_datei():
    """Die Quelldatei ist auf 78 Zeichen umbrochen - so schreibt man
    Textdateien. In einer Spalte von 64 Zeichen stehen diese Umbrueche quer
    dazu, und im Screenshot vom 11.08.2026 sah jede zweite Zeile aus wie ein
    Satzfehler."""
    roh = "Ein Satz, der über\nzwei Zeilen läuft.\n\nEin zweiter Absatz.\n"
    assert ns.einwilligung_absaetze(roh) == [
        "Ein Satz, der über zwei Zeilen läuft.", "Ein zweiter Absatz."]


def test_das_honeypot_feld_ist_kein_hidden_feld(tmp_path):
    """Skripte fuellen `type=hidden` gezielt NICHT aus. Ein sichtbares Feld,
    das aus dem Bild geschoben ist, fuellen sie - und Menschen sehen es nie."""
    site = _projekt(tmp_path, vollstaendig=True)
    soup = BeautifulSoup((site / "newsletter.html").read_text(encoding="utf-8"),
                         "html.parser")
    feld = soup.select_one('input[name="website"]')
    assert feld is not None and feld["type"] == "text"
    assert soup.select_one(".nl-hp")["aria-hidden"] == "true"
    css = (site / "style.css").read_text(encoding="utf-8")
    assert re.search(r"\.nl-hp\{[^}]*left:-9999px", css)


def test_impressum_und_datenschutz_stehen_auf_der_anmeldeseite(tmp_path):
    """Art. 13 DSGVO verlangt die Information dort, wo erhoben wird."""
    site = _projekt(tmp_path, vollstaendig=True)
    ziele = {a["href"] for a in BeautifulSoup(
        (site / "newsletter.html").read_text(encoding="utf-8"),
        "html.parser").find_all("a")}
    assert "impressum.html" in ziele and "datenschutz.html" in ziele


def test_ohne_javascript_ist_wenigstens_sichtbar_dass_es_ihn_gibt(tmp_path):
    site = _projekt(tmp_path, vollstaendig=True)
    html = (site / "newsletter.html").read_text(encoding="utf-8")
    assert "<noscript>" in html
    assert "JavaScript" in html.split("<noscript>")[1].split("</noscript>")[0]


# ===============================================  Die Abschlussseiten  =====

def test_die_abschlussseiten_sind_statisch_und_ohne_dienst(tmp_path):
    """DER Punkt: wer auf den Abmeldelink klickt, waehrend Render die
    Instanz schlafen laesst, wartet sonst eine Minute vor einem Spinner - und
    haelt sich trotzdem fuer abgemeldet. Der Abmeldelink ist der EINZIGE
    Abmeldeweg."""
    site = _projekt(tmp_path, vollstaendig=False)      # sogar unterhalb der Schwelle
    for name in ("newsletter-bestaetigt.html", "newsletter-abgemeldet.html"):
        datei = site / name
        assert datei.exists(), name
        html = datei.read_text(encoding="utf-8")
        # Kein fetch, kein Verweis auf den Dienst - die Seite steht sofort.
        assert "fetch(" not in html
        assert "onrender.com/subscribe" not in html
    abgemeldet = (site / "newsletter-abgemeldet.html").read_text(encoding="utf-8")
    assert "gelöscht" in abgemeldet


# =====================================  Vorschau: Browser gegen Python  ====

def _browser():
    for kandidat in ("/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                     os.environ.get("CHROMIUM_PFAD", "")):
        if kandidat and Path(kandidat).exists():
            return kandidat
    return None


def test_der_index_liegt_neben_der_seite(tmp_path):
    site = _projekt(tmp_path, vollstaendig=True)
    index = json.loads(
        (site / "data" / "keyword-index.json").read_text(encoding="utf-8"))
    assert index["woerter"] and index["meldungen"] > 0
    # Das Formular zeigt auf genau diesen relativen Pfad.
    assert "data/keyword-index.json" in (site / "app.js").read_text(encoding="utf-8")


@pytest.mark.parametrize("begriff", ["telekom", "netz", "starlink", "tarif"])
def test_die_browser_vorschau_sagt_dasselbe_wie_python(tmp_path, begriff):
    """Der Test, um den es geht.

    Die Seite kann `vorschau()` nicht aufrufen - sie zaehlt im Browser gegen
    den Index. Zwei Rechnungen fuer dieselbe Zahl sind zwei Zahlen, und die
    falsche steht auf der Seite. Gemessen wird deshalb im ECHTEN Browser
    gegen die ECHTE Indexdatei, nicht gegen eine nachgebaute Rechnung.
    """
    pfad = _browser()
    if not pfad:
        pytest.skip("kein Chromium")
    from playwright.sync_api import sync_playwright
    from telco_radar.newsletter.filters import vorschau

    site = _projekt(tmp_path, vollstaendig=True, dienst="https://x.invalid")
    reports = tmp_path / "data" / "reports"
    index = json.loads(
        (site / "data" / "keyword-index.json").read_text(encoding="utf-8"))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=pfad)
        seite = browser.new_page()
        seite.goto("file://" + str((site / "newsletter.html").resolve()))
        # Die Rechnung des Browsers, mit dem Index aus der Datei gefuettert.
        im_browser = seite.evaluate(
            """([idx, term, minLaenge]) => {
                 const teile = term.toLowerCase().split(/\\s+/)
                   .filter(w => w.length >= minLaenge);
                 if (!teile.length) return null;
                 return Math.min(...teile.map(w => idx.woerter[w] || 0));
               }""", [index, begriff, 4])
        browser.close()

    from datetime import date
    stand = date.fromisoformat(index["stand"])
    in_python = vorschau(begriff, reports, tage=index["tage"], heute=stand)
    assert im_browser == in_python, (
        f"{begriff}: Browser {im_browser}, Python {in_python}")


def test_wenigstens_ein_begriff_trifft_ueberhaupt(tmp_path):
    """Ohne diese Gegenprobe bestuende der Test oben auch dann, wenn beide
    Seiten konsequent null zaehlen."""
    from datetime import date
    from telco_radar.newsletter.filters import vorschau
    site = _projekt(tmp_path, vollstaendig=True)
    index = json.loads(
        (site / "data" / "keyword-index.json").read_text(encoding="utf-8"))
    treffer = vorschau("telekom", tmp_path / "data" / "reports",
                       tage=index["tage"], heute=date.fromisoformat(index["stand"]))
    assert treffer > 0, "der Vergleichstest prueft sonst nur Nullen"
