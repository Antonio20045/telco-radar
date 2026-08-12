"""Impressum, Datenschutz und die Schwelle, die daran haengt.

Der teuerste Fehler dieses Pakets waere nicht ein haesslicher Absatz, sondern
ein Anmeldeformular, das Adressen einsammelt, bevor es ein Impressum gibt.
Deshalb prueft dieser Test nicht nur, DASS die Seiten entstehen, sondern dass
die Unvollstaendigkeit einer Seite wirklich etwas AUSSCHALTET - und zwar im
Code, nicht in einem Test (eine Regel, die nur ein Test kennt, schaltet keine
Navigation; siehe Geraeteseite, CLAUDE.md §5).
"""
import re

import pytest
from bs4 import BeautifulSoup

from telco_radar.report import rechtstexte
from telco_radar.report.html import render_site

WURZEL_SEITEN = ("index.html", "meldungen.html", "transparenz.html",
                 "differenzierung.html", "wettbewerb.html", "suche.html")


@pytest.fixture()
def wurzel(tmp_path):
    """Eine Projektwurzel mit vollstaendigen Rechtstexten."""
    legal = tmp_path / "content" / "legal"
    legal.mkdir(parents=True)
    (legal / "impressum.md").write_text(
        "# Impressum\n\nMusterfirma\nMusterweg 1, 12345 Musterstadt\n",
        encoding="utf-8")
    (legal / "datenschutz.md").write_text(
        "# Datenschutzerklärung\n\n## 1. Verantwortlicher\n\nMusterfirma\n",
        encoding="utf-8")
    consent = tmp_path / "content" / "consent_texts"
    consent.mkdir(parents=True)
    (consent / "2026-08-11.md").write_text("Ich möchte den Radar.\n",
                                           encoding="utf-8")
    return tmp_path


def _luecke_einbauen(wurzel):
    datei = wurzel / "content" / "legal" / "impressum.md"
    datei.write_text(datei.read_text(encoding="utf-8").replace(
        "Musterweg 1, 12345 Musterstadt", "{{ANSCHRIFT}}"), encoding="utf-8")


# ------------------------------------------------------------ das Modul ----

def test_vollstaendige_texte_erreichen_die_schwelle(wurzel):
    assert rechtstexte.vollstaendig(wurzel) is True
    assert rechtstexte.offene_stellen(wurzel) == []


def test_ein_platzhalter_reisst_die_schwelle(wurzel):
    _luecke_einbauen(wurzel)
    assert rechtstexte.vollstaendig(wurzel) is False
    assert ("impressum", "ANSCHRIFT") in rechtstexte.offene_stellen(wurzel)


def test_eine_fehlende_pflichtseite_reisst_die_schwelle_ebenso(wurzel):
    """Ein vollstaendiges Impressum ohne Datenschutzerklaerung nuetzt nichts -
    Art. 13 DSGVO verlangt die Information ZUM ZEITPUNKT der Erhebung."""
    (wurzel / "content" / "legal" / "datenschutz.md").unlink()
    assert rechtstexte.vollstaendig(wurzel) is False
    assert rechtstexte.lade(wurzel, "datenschutz") is None
    offen = dict(rechtstexte.offene_stellen(wurzel))
    assert "datenschutz.md" in offen["datenschutz"]


def test_der_platzhalter_steht_sichtbar_im_text(wurzel):
    """Nicht leer und nicht stillschweigend weggelassen: der Leser soll die
    offene Stelle sehen. Ein Impressum mit einer leeren Zeile sieht aus wie
    ein vollstaendiges mit knappem Satz."""
    _luecke_einbauen(wurzel)
    text = rechtstexte.lade(wurzel, "impressum")
    assert "{{" not in text.markdown
    assert "noch nicht eingetragen" in text.markdown
    assert text.luecken == ["ANSCHRIFT"]


def test_die_eigene_ueberschrift_faellt_weg(wurzel):
    """`# Impressum` wuerde als nackter Text im Fliesstext stehen -
    `_md_to_html` kennt kein h1. Den Titel setzt die Vorlage."""
    text = rechtstexte.lade(wurzel, "impressum")
    assert not text.markdown.startswith("#")
    assert text.titel == "Impressum"


# ------------------------------------------------- Einwilligungsfassungen --

def test_einwilligung_ist_versioniert_und_nachrechenbar(wurzel):
    aktuell = rechtstexte.aktuelle_einwilligung(wurzel)
    assert aktuell.version == "2026-08-11"
    assert aktuell.hash.startswith("sha256:")
    # Der Nachweis besteht darin, dass JEDER ihn nachrechnen kann, der den
    # Text hat - also ohne Pepper und ohne Projektwissen.
    import hashlib
    erwartet = hashlib.sha256(
        aktuell.text.strip().encode("utf-8")).hexdigest()
    assert aktuell.hash == f"sha256:{erwartet}"


def test_eine_alte_fassung_bleibt_abrufbar(wurzel):
    """Die Aufsichtsbehoerde fragt nach dem Wortlaut von DAMALS."""
    (wurzel / "content" / "consent_texts" / "2026-09-01.md").write_text(
        "Neuer Wortlaut.\n", encoding="utf-8")
    assert rechtstexte.aktuelle_einwilligung(wurzel).version == "2026-09-01"
    alt = rechtstexte.einwilligung(wurzel, "2026-08-11")
    assert alt is not None and "Ich möchte" in alt.text
    assert alt.hash != rechtstexte.aktuelle_einwilligung(wurzel).hash


def test_eine_geaenderte_fassung_faellt_am_hash_auf(wurzel):
    vorher = rechtstexte.aktuelle_einwilligung(wurzel).hash
    datei = wurzel / "content" / "consent_texts" / "2026-08-11.md"
    datei.write_text("Ich möchte den Radar. Und noch etwas.\n",
                     encoding="utf-8")
    assert rechtstexte.aktuelle_einwilligung(wurzel).hash != vorher


# ---------------------------------------------------------- die Seiten -----

def _render(wurzel):
    reports_dir = wurzel / "data" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    site_dir = wurzel / "site"
    render_site(site_dir, reports_dir, cfg=None)
    return site_dir


def test_beide_seiten_entstehen_und_stehen_in_jeder_fusszeile(wurzel):
    site = _render(wurzel)
    assert (site / "impressum.html").exists()
    assert (site / "datenschutz.html").exists()
    ohne = []
    for name in WURZEL_SEITEN:
        datei = site / name
        if not datei.exists():
            continue
        fuss = BeautifulSoup(datei.read_text(encoding="utf-8"),
                             "html.parser").select_one(".foot .foot-recht")
        ziele = {a["href"] for a in fuss.select("a")} if fuss else set()
        if {"impressum.html", "datenschutz.html"} - ziele:
            ohne.append((name, sorted(ziele)))
    assert not ohne, f"Fusszeile ohne Pflichtlinks: {ohne}"


def test_eine_unterseite_zeigt_eine_ebene_hoeher(wurzel):
    """`reports/` und `promo/` liegen tiefer. Ein fester Pfad
    `impressum.html` waere dort eine 404 - genau der Fehler, den `prefix`
    verhindert, und der auf der Startseite nie auffaellt.

    Gemessen an der Archivwoche: sie entsteht aus derselben Vorlage wie die
    Startseite, nur mit `prefix="../"`. Ohne einen Bericht gibt es sie nicht,
    also legt der Test einen an."""
    import json
    (wurzel / "data" / "reports").mkdir(parents=True, exist_ok=True)
    (wurzel / "data" / "reports" / "2026-08-05.json").write_text(json.dumps({
        "date": "2026-08-05", "stats": {"new": 1}, "briefing_md": "Text.",
        "regions": {"Europa": {"highlights": []}},
    }), encoding="utf-8")
    site = _render(wurzel)
    datei = site / "reports" / "2026-08-05.html"
    assert datei.exists()
    fuss = BeautifulSoup(datei.read_text(encoding="utf-8"),
                         "html.parser").select_one(".foot-recht")
    assert {a["href"] for a in fuss.select("a")} == {
        "../impressum.html", "../datenschutz.html"}


def test_die_seite_nennt_die_drei_auftragsverarbeiter(wurzel):
    """GitHub, Render und Brevo verarbeiten in dieser Architektur
    personenbezogene Daten. Fehlt einer, ist die Erklaerung unvollstaendig -
    und zwar an der Stelle, an der eine Behoerde zuerst nachsieht."""
    site = _render(wurzel)
    # Der echte Text des Repos, nicht die Fixture.
    from pathlib import Path
    echt = Path(__file__).resolve().parents[1]
    text = rechtstexte.lade(echt, "datenschutz").markdown
    for name in ("Render", "GitHub", "Brevo"):
        assert name in text, name
    for pflicht in ("Art. 6 Abs. 1 lit. a", "Art. 77", "Widerruf",
                    "Double-Opt-in", "Speicherdauer"):
        assert pflicht in text, pflicht
    assert (site / "datenschutz.html").exists()


def test_die_luecke_steht_oben_auf_der_seite(wurzel):
    _luecke_einbauen(wurzel)
    site = _render(wurzel)
    soup = BeautifulSoup((site / "impressum.html").read_text(encoding="utf-8"),
                         "html.parser")
    kasten = soup.select_one(".rechtstext-luecke")
    assert kasten is not None
    assert "ANSCHRIFT" in kasten.get_text()
    # ... und zwar VOR dem Fliesstext.
    koerper = soup.select_one(".rechtstext-body")
    assert kasten.sourceline < koerper.sourceline


def test_rohes_html_im_rechtstext_wird_entschaerft(wurzel):
    """Dieselbe Sanitisierung wie beim Bericht. Diese Dateien sind zwar aus
    dem Repo, aber sie laufen durch denselben Renderer - eine Ausnahme hier
    waere ein zweiter Pfad mit anderen Regeln."""
    (wurzel / "content" / "legal" / "impressum.md").write_text(
        "# Impressum\n\nText <script>alert(1)</script> Ende\n",
        encoding="utf-8")
    site = _render(wurzel)
    html = (site / "impressum.html").read_text(encoding="utf-8")
    assert "<script>alert" not in html
    assert "alert(1)" not in html


def test_ohne_content_verzeichnis_kippt_keine_seite(tmp_path):
    """Ein Projekt ohne `content/` muss weiter rendern - sonst haengt die
    ganze Website an einer Textdatei."""
    site = _render(tmp_path)
    assert (site / "index.html").exists()
    assert not (site / "impressum.html").exists()
    fuss = BeautifulSoup((site / "index.html").read_text(encoding="utf-8"),
                         "html.parser").select_one(".foot-inner")
    # Kein Link auf eine Seite, die es nicht gibt.
    assert fuss.select_one(".foot-recht") is None


def test_das_echte_repo_hat_beide_pflichtseiten():
    from pathlib import Path
    echt = Path(__file__).resolve().parents[1]
    for schluessel in ("impressum", "datenschutz"):
        assert rechtstexte.lade(echt, schluessel) is not None, schluessel
    assert rechtstexte.aktuelle_einwilligung(echt) is not None


def test_der_api_key_steht_in_keiner_datei_des_repos():
    """Der Brevo-Key gehoert ausschliesslich in ein GitHub-Secret. Ein Key im
    Repo ist oeffentlich, sobald das Repo es ist - und dieses ist es."""
    from pathlib import Path
    wurzel = Path(__file__).resolve().parents[1]
    # Brevo-Keys beginnen mit "xkeysib-" (API v3) bzw. "xsmtpsib-" (SMTP).
    muster = re.compile(r"xkeysib-[A-Za-z0-9]|xsmtpsib-[A-Za-z0-9]")
    treffer = []
    for pfad in wurzel.rglob("*"):
        if not pfad.is_file() or ".git/" in str(pfad):
            continue
        if pfad.suffix not in {".py", ".yml", ".yaml", ".md", ".json", ".j2",
                               ".js", ".css", ".txt", ".sh"}:
            continue
        try:
            inhalt = pfad.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if muster.search(inhalt):
            treffer.append(str(pfad.relative_to(wurzel)))
    assert not treffer, f"Brevo-Key im Repo: {treffer}"
