"""P4/D3 (18.09.2026): die Ruhe-Mechanik der Geräteseite ist messbar.

Drei Regeln aus STRATEGIE_GERAETE_V3 §P4 / design.md (17.09.2026):

  1. FLIESSTEXT-DECKEL je Reiter (`pruefe_portal.fliesstext_zeichen`
     gegen `_FLIESSTEXT_DECKEL`) - FM 4: "Text kriecht zurück". Antonio:
     "Ich will keinen Text sehen."
  2. KEIN FLIESSTBLOCK UNTER GRAFIKEN (`max_absatz_nach_svg` gegen
     `_MAX_ABSATZ_NACH_SVG` = 200) - design.md Regel 8. Der gefallene
     1813-Zeichen-Datenblock unter dem G2-Graph war der Fall.
  3. KLICKBARKEIT ZEIGT SICH - jedes <summary> der Geräteseite trägt
     cursor:pointer und ein Aufklappzeichen (design.md Regel 5: 20 von 22
     Aufklappern des Vergleichs-Reiters sahen aus wie Tabellenzeilen).

Diese Tests halten die ZÄHLFUNKTIONEN gegen Mini-HTML fest - dieselben
Funktionen, gegen die `pruefe_portal.py` Kriterium 13/14 die echte Seite
misst (eine Rechnung, keine zweite). Die Klickbarkeit wird an einem
echten Browser gegen die WIRKLICHE style.css gemessen, nicht gegen ihre
Quelltext-Existenz: eine Regel, die niemanden färbt, wäre grün und
prüfte nichts.
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


def _mini(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---- 1. Fließtext-Deckel: die Zählweise -------------------------------

def test_deckel_zaehlt_sichtbare_und_aufklapp_absaetze():
    """FM 4 nennt den Preis-Klick den Härtetest - "gerät er zum
    Textblock, ist FM 4 sofort zurück". Deshalb zählt der Deckel Text
    hinter Klicks MIT: ein Deckel, der nur den ersten Bildschirm misst,
    sähe genau diesen Rückschlag nicht."""
    soup = _mini('<div id="t"><p>Erste Zeile.</p>'
                 '<details><summary>mehr</summary>'
                 '<p>Und der Aufklapp-Text.</p></details></div>')
    tafel = soup.select_one("#t")
    assert pp.fliesstext_zeichen(tafel) == \
        len("Erste Zeile.") + len("Und der Aufklapp-Text.")


def test_deckel_zaehlt_templates_nicht():
    """Templates sind nie sichtbar (der P1-Rechenweg-Pool wird erst per
    Klick zum DOM montiert) - sie belongen zu keiner Tafel-Ruhe."""
    soup = _mini('<div id="t"><p>sichtbar</p>'
                 '<template data-m="x"><p>70,00 € × 24 = 1 680 €</p>'
                 '</template></div>')
    assert pp.fliesstext_zeichen(soup.select_one("#t")) == len("sichtbar")


def test_deckel_normalisiert_leerraum():
    soup = _mini('<div id="t"><p>  viel   Leer\ntraum\t  hier  </p></div>')
    assert pp.fliesstext_zeichen(soup.select_one("#t")) == \
        len("viel Leer traum hier")


def test_deckel_ignoriert_leere_absaetze():
    soup = _mini('<div id="t"><p>   </p><p>x</p></div>')
    assert pp.fliesstext_zeichen(soup.select_one("#t")) == 1


def test_jeder_reiter_hat_einen_deckel():
    """pruefe_portal erwartet vier Tafeln (`erwartet` in Kriterium 11) -
    jeder davon braucht einen Deckel, sonst ist der fünfte Reiter ein
    Textloch. Der Test hält die Abdeckung, nicht die Höhe."""
    erwartet = ["tafel-tco", "tafel-radar", "tafel-verlauf", "tafel-katalog"]
    assert sorted(pp._FLIESSTEXT_DECKEL) == sorted(erwartet)
    assert all(w > 0 for w in pp._FLIESSTEXT_DECKEL.values())


# ---- 2. Kein Fließblock unter Grafiken --------------------------------

def test_absatz_nach_svg_wird_gemessen():
    soup = _mini('<div id="t"><svg></svg><p>Der Datenblock unter dem '
                 'Graph, der die Kurve als Text wiederholt.</p></div>')
    n, _ = pp.max_absatz_nach_svg(soup.select_one("#t"))
    assert n == len("Der Datenblock unter dem Graph, "
                    "der die Kurve als Text wiederholt.")


def test_absatz_im_container_nach_svg_wird_gemessen():
    """Graph-Wrapper-Struktur: svg und der Absatz stehen Geschwister in
    einem div - der Absatz ist erstes Element seines Containers."""
    soup = _mini('<div id="t"><svg></svg><div class="gr-vbild-wrap">'
                 '<p>Bildunterschrift.</p></div></div>')
    n, _ = pp.max_absatz_nach_svg(soup.select_one("#t"))
    assert n == len("Bildunterschrift.")


def test_versteckter_absatz_nach_svg_zaehlt_nicht():
    """Initial hidden (die JS-gefüllten Verlaufs-Sätze) oder hinter
    zugeklapptem details - die Regel misst, was der Leser unter der
    Grafik SIEHT, nicht was im DOM liegt."""
    soup = _mini('<div id="t"><svg></svg>'
                 '<p hidden>versteckt</p>'
                 '<details><summary>z</summary><svg></svg>'
                 '<p>im Aufklapper</p></details></div>')
    n, _ = pp.max_absatz_nach_svg(soup.select_one("#t"))
    assert n == 0


def test_absatz_ohne_svg_davor_zaehlt_nicht():
    soup = _mini('<div id="t"><h3>Titel</h3><p>Ganz normaler Absatz, '
                 'der niemanden stört.</p></div>')
    assert pp.max_absatz_nach_svg(soup.select_one("#t"))[0] == 0


def test_die_200_zeichen_grenze_ist_genau_der_datenblock_fall():
    """design.md maß 1813 Zeichen unter dem G2-Graph. Die Grenze muss
    einen solchen Block verbeugen (Gegenprobe: eine kurze
    Bildunterschrift besteht)."""
    assert pp._MAX_ABSATZ_NACH_SVG == 200
    kurz = "a" * pp._MAX_ABSATZ_NACH_SVG
    lang = "a" * (pp._MAX_ABSATZ_NACH_SVG + 1)
    soup = _mini(f'<div id="t"><svg></svg><p>{kurz}</p></div>')
    assert pp.max_absatz_nach_svg(soup.select_one("#t"))[0] \
        <= pp._MAX_ABSATZ_NACH_SVG
    soup = _mini(f'<div id="t"><svg></svg><p>{lang}</p></div>')
    assert pp.max_absatz_nach_svg(soup.select_one("#t"))[0] \
        > pp._MAX_ABSATZ_NACH_SVG


# ---- 3. Klickbarkeit zeigt sich (echter Browser, echte style.css) -----

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
    # dieselbe Rueckfalloption wie pruefe_portal (Phase 6a: ein
    # uebersprungenes Kriterium sieht in der Bilanz aus wie ein bestandenes).
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


def test_je_summary_der_geraeteseite_zeiger_und_caret(seite):
    """Gegenprobe inklusive: .mressort (Meldungsseite) trägt sein EIGENES
    ▾ aus der Vor-P4-Regel, und ein NACKTES summary außerhalb von
    .gr-tafel bekommt von der neuen Regel nichts - das Scoping ist
    Absicht, keine Nebenwirkung auf andere Seiten."""
    html = f"""<!doctype html><html><head><style>{_style()}</style></head>
    <body>
    <div class="gr-tafel" id="t1">
      <details><summary>Maßstab &amp; Datenlage</summary><p>x</p></details>
      <details class="gr-tdetail" open><summary>congstar · Tarif</summary>
        <p>x</p></details>
      <details class="gr-mehrliste"><summary>41 weitere</summary></details>
    </div>
    <details class="mressort" open><summary><h2>Ressort</h2></summary>
      <p>x</p></details>
    <div class="woanders"><details><summary>plain</summary></details></div>
    </body></html>"""
    seite.set_content(html)
    ergebnis = seite.evaluate(
        """() => {
          const inTafel = [...document.querySelectorAll('.gr-tafel summary')]
            .map(s => ({cursor: getComputedStyle(s).cursor,
                        caret: (getComputedStyle(s, '::after').content
                                || 'none') !== 'none'}));
          const mressort = [...document.querySelectorAll('.mressort>summary')]
            .map(s => (getComputedStyle(s, '::after').content || 'none'));
          const woanders = document.querySelector('.woanders summary');
          return {inTafel, mressort,
                  nackt: {cursor: getComputedStyle(woanders).cursor,
                          caret: (getComputedStyle(woanders, '::after').content
                                  || 'none') !== 'none'}};
        }""")
    assert len(ergebnis["inTafel"]) == 3
    for e in ergebnis["inTafel"]:
        assert e["cursor"] == "pointer", ergebnis
        assert e["caret"] is True, ergebnis
    # .mressort trägt sein EIGENES ▾ (Vor-P4-Regel) - unangetastet.
    assert all(c not in ("none", "") for c in ergebnis["mressort"]), ergebnis
    # Und das nackte summary außerhalb bleibt, wie es war - die Regel
    # greift nur innerhalb der Geräteseiten-Tafeln.
    assert ergebnis["nackt"]["caret"] is False, ergebnis


def test_datenlage_behaelt_ihr_eigenes_aufklappzeichen(seite):
    """Die +/–-Regel von .gr-vdatenlage steht SPAETER im Stylesheet und
    gewinnt bei gleicher Spezifität - der Datenlage-Aufklapper behält
    seine Form, statt ▾ und + gleichzeitig zu tragen. Ein ::after gibt es
    nur einmal: verliert die Regel hier, stünde ▾ statt + da."""
    html = f"""<!doctype html><html><head><style>{_style()}</style></head>
    <body><div class="gr-tafel"><details class="gr-vdatenlage">
      <summary>Datenlage</summary><p>x</p></details></div></body></html>"""
    seite.set_content(html)
    inhalt = seite.evaluate(
        """() => getComputedStyle(
              document.querySelector('.gr-vdatenlage>summary'),
              '::after').content""")
    assert inhalt.strip('"\'') == "+", inhalt
