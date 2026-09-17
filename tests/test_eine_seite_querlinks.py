"""Die EINE Geräteseite: Kein Link mehr auf die Alt-URL (E3, Querlinks).

Antonio (AUFTRAG_GERAETE_EINE_SEITE_V2 §9a): „Also erstens, wieso gibt es
jetzt zwei Unterseiten: Geräte und Wettbewerbsradar? […] Geräte,
Wettbewerbsradar, eine Unterseite." Seit E3 Schritt 3 (17.09.2026) ist
wettbewerbsradar.html eine Meta-Refresh-Weiterleitung auf
geraete.html#tafel-radar; die 88 modellbezogenen Querlinks der
Abweichungstafel springen als `geraete.html?modell=…&band=…` in den
Graphen der EINEN Seite.

Ein Link, der die Alt-URL neu setzen würde, zeigte still auf eine
noindex-Seite ohne Inhalt - dieselbe Fehlerklasse wie der
Navigationseintrag vom 11.08. (gebaut und nicht da). Diese Datei hält
die Zahl dauerhaft fest, die der Querlink-Umbau gemessen hat: GENAU EINE
Datei wettbewerbsradar.html im ganzen Site-Baum (die Weiterleitung selbst)
und NULL href/src/action auf sie von irgendeiner anderen Datei.
"""
import re
from pathlib import Path

from test_geraete_seite import _baue

# Ein Verweis auf die Alt-URL - egal ob href, src oder action, doppelte oder
# einfache Anfuehrungszeichen, mit Prefix (../ aus Archivwochen, / absolut)
# oder Suffix (#anker, ?query). Die Weiterleitungsdatei selbst ist die
# einzige erlaubte Ausnahme: SIE darf (und muss) auf geraete.html zeigen.
_ALT_URL = re.compile(
    r"""(?:href|src|action)=["'][^"']*wettbewerbsradar\.html[^"']*["']""")


def _dateien(site: Path):
    """Alle ausgelieferten HTML- und JS-Dateien, rekursiv - auch Fragmente
    unter data/, Archivwochen unter reports/ und app.js."""
    for pfad in sorted(site.rglob("*")):
        if pfad.is_file() and pfad.suffix in (".html", ".js"):
            yield pfad


def test_die_alt_url_liegt_genau_einmal_als_weiterleitung(tmp_path):
    """Es gibt genau EINE Datei dieses Namens im ganzen Site-Baum - eine
    zweite (etwa unter reports/ oder data/) waere eine Seite ohne Inhalt,
    die Suchmaschinen und Lesezeichen statt der Weiterleitung fänden."""
    site = _baue(tmp_path)
    treffer = [p for p in site.rglob("wettbewerbsradar.html")]
    assert len(treffer) == 1, [str(t.relative_to(site)) for t in treffer]
    inhalt = treffer[0].read_text(encoding="utf-8")
    assert "url=geraete.html#tafel-radar" in inhalt
    assert "noindex" in inhalt


def test_keine_datei_verweist_auf_die_alt_url(tmp_path):
    """Die Gegenprobe des Querlink-Umbaus als Zahl: 0. Geprueft wird die
    Flaeche - jede HTML- und JS-Datei des Renderns, nicht nur die Navigation;
    app.js gehoert dazu, weil der Explorer der Archivwochen Links im Browser
    baut und ein dort gesetzter Verweis in keinem statischen Test auffaelle."""
    site = _baue(tmp_path)
    fremde = []
    for pfad in _dateien(site):
        if pfad.name == "wettbewerbsradar.html":
            continue
        if _ALT_URL.search(pfad.read_text(encoding="utf-8")):
            fremde.append(str(pfad.relative_to(site)))
    assert fremde == [], fremde


def test_die_weiterleitung_landet_auf_einem_anker_der_seite(tmp_path):
    """Ein Meta-Refresh auf einen Anker, den es nicht gibt, laedt die Seite
    und springt nirgendwo hin - der Lookup muss getroffen sein, sonst prueft
    die Kette ins Leere (CLAUDE.md §6). Der Anker wird aus der Weiterleitung
    GELESEN, nicht fest vorgegeben: aendert das Redirect-Ziel, prueft dieser
    Test den neuen Anker statt blind den alten."""
    site = _baue(tmp_path)
    weiter = (site / "wettbewerbsradar.html").read_text(encoding="utf-8")
    ziel = re.search(r'url=([a-z0-9_.-]+\.html)(#[a-z0-9_-]+)?', weiter)
    assert ziel is not None, "Weiterleitung nennt kein Ziel"
    datei, anker = ziel.group(1), (ziel.group(2) or "").lstrip("#")
    roh = (site / datei).read_text(encoding="utf-8")
    if anker:
        assert f'id="{anker}"' in roh, anker


def test_app_js_behaelt_den_modell_deep_link(tmp_path):
    """Die 88 Sprung-Links der Abweichungstafel tragen
    `geraete.html?modell=…&band=…`. Sie landen nur dann im Graphen, wenn
    app.js die Parameter auch liest - ein Umbau, der den Leser fallen laesst,
    macht jeden dieser Links zu einem blossen Seitenaufruf."""
    site = _baue(tmp_path)
    js = (site / "app.js").read_text(encoding="utf-8")
    assert "URLSearchParams(location.search)" in js
    assert "params.get('modell')" in js
