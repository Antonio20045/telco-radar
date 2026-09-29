"""Die Ruhe-Mechanik der Geräteseite (Kosten-Rangliste in section#kosten).

Zwei Regeln, die `scripts/pruefe_portal.py` an der echten Seite misst:

  1. FLIESSTEXT-DECKEL (Kriterium 13, `fliesstext_zeichen` gegen
     `_FLIESSTEXT_DECKEL`): Text in #kosten außerhalb von Zahlen und Chips.
     Antonio: "Ich will keinen Text sehen."
  2. KLICKBARKEIT ZEIGT SICH (Kriterium 15, `SUMMARY_JS`): jedes summary
     trägt cursor:pointer und ein gezeichnetes Aufklappzeichen.

Diese Tests halten dieselben Funktionen gegen Mini-HTML fest - eine
Rechnung, keine zweite. Die Klickbarkeit wird im echten Browser gegen die
WIRKLICHE style.css gemessen: eine Regel, die niemanden trifft, wäre im
Quelltext vorhanden und prüfte nichts.
"""
from __future__ import annotations

import glob
import importlib.util
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

REPO = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "pruefe_portal", REPO / "scripts" / "pruefe_portal.py")
pp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pp)


def _mini(html: str):
    return BeautifulSoup(html, "html.parser").select_one("#kosten")


# ---- 1. Fließtext-Deckel: die Zählweise -------------------------------

def test_deckel_zaehlt_text_ausserhalb_von_zahlen_und_chips():
    kosten = _mini(
        '<section id="kosten"><h1>iPhone 17 <span>256 GB</span></h1>'
        '<div id="kv-wahl"><button class="kv-chip">Apple</button>'
        '<span class="kv-reihe-name">Marke</span></div>'
        '<ol><li class="kv-zeile"><span class="kv-anb">congstar</span>'
        '<span class="kv-summe">1.783,00 €</span></li></ol>'
        '<p class="kv-ohne">Telekom · o2</p>'
        '<script id="kv-daten">{"a": "sehr langer Datenknoten"}</script>'
        '</section>')
    assert pp.fliesstext_zeichen(kosten) == \
        len("iPhone 17 256 GB Telekom · o2")


def test_deckel_zaehlt_neue_prosa_in_jedem_element():
    """Gegenprobe: ein Erklärabsatz wird gezählt, egal in welchem Tag er
    steht - ein Deckel nur über <p> ließe ein <div> voller Text durch."""
    ohne = _mini('<section id="kosten"><h2>Kosten</h2></section>')
    mit = _mini('<section id="kosten"><h2>Kosten</h2>'
                '<div>So lesen Sie diese Liste.</div></section>')
    assert pp.fliesstext_zeichen(mit) - pp.fliesstext_zeichen(ohne) == \
        len(" So lesen Sie diese Liste.")


def test_deckel_zaehlt_knoepfe_templates_und_kommentare_nicht():
    kosten = _mini('<section id="kosten"><p>x<button>o2 · 36 Raten →'
                   '</button></p><template><p>unsichtbar</p></template>'
                   '<!-- Kommentar --></section>')
    assert pp.fliesstext_zeichen(kosten) == 1


def test_deckel_normalisiert_leerraum():
    kosten = _mini('<section id="kosten"><p>  viel   Leer\ntraum\t  hier  '
                   '</p></section>')
    assert pp.fliesstext_zeichen(kosten) == len("viel Leer traum hier")


def test_deckel_haelt_einen_erklaerabsatz_draussen():
    """Der Deckel lässt Titel, Kopfzeilen und eine Fehlermeldung zu, aber
    keinen Absatz Erklärprosa (Gegenprobe knapp über der Grenze)."""
    assert 0 < pp._FLIESSTEXT_DECKEL <= 600
    genau = _mini(f'<section id="kosten"><p>{"a" * pp._FLIESSTEXT_DECKEL}'
                  '</p></section>')
    drueber = _mini(f'<section id="kosten"><p>'
                    f'{"a" * (pp._FLIESSTEXT_DECKEL + 1)}</p></section>')
    assert pp.fliesstext_zeichen(genau) <= pp._FLIESSTEXT_DECKEL
    assert pp.fliesstext_zeichen(drueber) > pp._FLIESSTEXT_DECKEL


# ---- 2. Klickbarkeit zeigt sich (echter Browser, echte style.css) -----

def _chromium() -> str | None:
    for muster in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                   str(Path.home() / "Library/Caches/ms-playwright"
                       / "chromium*/chrome-mac*/Google Chrome for Testing.app"
                       / "Contents/MacOS/Google Chrome for Testing"),
                   str(Path.home() / ".cache/ms-playwright"
                       / "chromium*/chrome-linux*/chrome")):
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    # None heisst "nimm den Browser, den Playwright selbst verwaltet" -
    # dieselbe Rueckfalloption wie pruefe_portal.
    return None


def _style() -> str:
    return (REPO / "src" / "telco_radar" / "report" / "templates"
            / "style.css").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def seite():
    playwright = pytest.importorskip("playwright.sync_api")
    try:
        ctx = playwright.sync_playwright()
        pw = ctx.start()
        browser = pw.chromium.launch(executable_path=_chromium())
    except Exception as exc:  # noqa: BLE001 - kein Browser, kein Messwert
        pytest.skip(f"Chromium startet nicht ({type(exc).__name__})")
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    yield page
    browser.close()
    pw.stop()


def test_je_summary_der_kostenliste_zeiger_und_pfeil(seite):
    """Gegenprobe inklusive: ein summary ohne .kv-pfeil hat kein
    Aufklappzeichen, und ein nacktes summary außerhalb der Kostenliste
    bekommt von den kv-Regeln keinen Zeiger - die Messung unterscheidet,
    statt alles grün zu melden."""
    html = f"""<!doctype html><html><head><style>{_style()}</style></head>
    <body>
    <section id="kosten">
      <ol class="kv-liste"><li class="kv-zeile"><details class="kv-auf">
        <summary class="kv-kern"><span class="kv-anb">congstar</span>
          <span class="kv-summe">1.783 €</span>
          <span class="kv-pfeil" aria-hidden="true"></span></summary>
        <div class="kv-weg">x</div></details></li></ol>
      <details class="kv-gruppe kv-gruppe--neben">
        <summary class="kv-neben-kopf"><h2 class="kv-kopfzeile">36</h2>
          <span class="kv-pfeil" aria-hidden="true"></span></summary>
      </details>
    </section>
    <div id="woanders"><details><summary>nackt</summary></details></div>
    </body></html>"""
    seite.set_content(html)
    kosten = seite.evaluate(pp.SUMMARY_JS, "#kosten")
    assert len(kosten) == 2
    assert [d["kern"] for d in kosten] == [True, False]
    for d in kosten:
        assert d["pointer"] is True, kosten
        assert d["caret"] is True, kosten
    nackt = seite.evaluate(pp.SUMMARY_JS, "#woanders")
    assert nackt == [{"text": "nackt", "kern": False,
                      "pointer": False, "caret": False}]
