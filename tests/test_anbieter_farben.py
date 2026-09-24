"""P2/D1: die EINE Quelle der Anbieterfarben.

Drei Dinge werden hier festgenagelt, die vorher an drei Stellen ausei-
nanderliefen (Befund: Telekom gruen im Preisverlauf, magenta in der
TCO-Zeitreihe):

  a) jeder bekannte Anbieter hat GENAU eine Farbe, Strichart und
     Markerform, stabil ueber alle Aufrufer,
  b) ein unbekannter Anbieter bekommt NIE eine geratene Farbe, sondern
     immer dieselbe benannte Luecke (Clean Code 3/4),
  c) `style.css` bekommt seinen Anbieterfarben-Block NUR aus dieser
     Tabelle (`css_block`/`in_stylesheet`), nie von Hand.
"""
import logging

import pytest

from telco_radar.report import anbieter_farben as af
from telco_radar.report.geraete_tco_grafik import anbieter_slug


# --------------------------------------------------------------------------
# a) bekannte Anbieter - stabile, unterschiedliche Stile
# --------------------------------------------------------------------------

def test_jeder_bekannte_anbieter_hat_einen_stil():
    for name in af.ANBIETER_FARBE:
        stil = af.stil_fuer(name)
        assert stil.bekannt
        assert stil.farbe.startswith("#") and len(stil.farbe) == 7
        assert stil.strich in af.STRICHMUSTER


def test_stil_fuer_ist_gross_klein_und_leerraum_unabhaengig():
    a = af.stil_fuer("Telekom")
    b = af.stil_fuer("  telekom  ")
    c = af.stil_fuer("TELEKOM")
    assert a == b == c


def test_vodafone_ist_die_einzige_eigene_marke():
    eigene = [n for n, s in af.ANBIETER_FARBE.items() if s.eigen]
    assert eigene == ["vodafone"]
    assert af.ANBIETER_FARBE["vodafone"].farbe == "#e60000"
    assert af.ANBIETER_FARBE["vodafone"].breite == af.BREITE_EIGEN


def test_die_telekom_farbe_ist_die_markenfarbe_nicht_gruen():
    """DER Befund von P2/D1: die alte Hash-Palette traf 'telekom' auf
    `#217a3c` (Gruen, aus `md5('telekom') % 7`)."""
    assert af.stil_fuer("Telekom").farbe == "#e20074"
    assert af.stil_fuer("Telekom").farbe != "#217a3c"


def test_congstar_traegt_linie_und_marker_getrennt():
    """Auftrag: 'congstar Linie #121212 + Marker #FFED00'. Gelb allein
    waere auf hellem Papier unsichtbar - deshalb ist die LINIE schwarz und
    nur der Marker gelb, mit schwarzem Rand."""
    stil = af.stil_fuer("congstar")
    assert stil.farbe == "#121212"
    assert stil.marker_farbe == "#ffed00"
    assert stil.marker_rand == "#121212"


def test_service_provider_sind_grau_und_gepunktet():
    for name in ("mobilcom-debitel", "freenet", "aldi talk"):
        stil = af.stil_fuer(name)
        assert stil.farbe == af.GRAU_SERVICE
        assert stil.strich == "gepunktet"


def test_haendler_sind_grau_durchgezogen_und_nur_an_der_form_verschieden():
    """Saturn (`anbieter_typ: handel` in `geraete_db.json`, wie Medimax)
    stand beim Rendern gegen den echten Bestand als benannte Luecke da,
    bis es hier ergaenzt wurde - derselbe Auftrag wie Medimax und
    ElectronicPartner, keine geratene Farbe."""
    stile = [af.stil_fuer(n) for n in
            ("medimax", "electronicpartner", "saturn")]
    assert all(s.farbe == af.GRAU_HAENDLER for s in stile)
    assert all(s.strich == "voll" for s in stile)
    marker = [s.marker for s in stile]
    assert len(set(marker)) == len(marker), (
        "gleiche Farbe, gleiche Strichart - nur die Form darf sie trennen")


def test_1_und_1_ist_gestrichelt():
    stil = af.stil_fuer("1&1")
    assert stil.strich == "gestrichelt"
    assert stil.muster == "7 4"


def test_slug_stimmt_mit_geraete_tco_grafik_ueberein():
    """Dieselbe CSS-Klasse `gr-anb--<slug>` wird von `geraete_tco_grafik.py`
    UND von dieser Tabelle erzeugt - ein Auseinanderlaufen waere eine
    Farbe, die auf der Vergleichsseite steht und auf der Zeitreihe fehlt."""
    for name in af.ANBIETER_FARBE:
        assert af.slug_fuer(name) == anbieter_slug(name), name


# --------------------------------------------------------------------------
# b) unbekannte Anbieter - benannte Luecke, nie geraten
# --------------------------------------------------------------------------

def test_unbekannter_anbieter_bekommt_die_benannte_luecke():
    stil = af.stil_fuer("Ein ganz neuer Anbieter")
    assert not stil.bekannt
    assert stil == af.LUECKE
    assert stil.farbe == af.LUECKE_FARBE
    assert stil.name_zusatz == "Farbe nicht hinterlegt"


def test_unbekannter_anbieter_wird_protokolliert(caplog):
    with caplog.at_level(logging.WARNING):
        af.stil_fuer("Nirgends Gelistet")
    assert any("Nirgends Gelistet" in m for m in caplog.messages)


def test_ist_bekannt():
    assert af.ist_bekannt("Telekom")
    assert af.ist_bekannt("  O2  ")
    assert not af.ist_bekannt("Nirgends Gelistet")
    assert not af.ist_bekannt(None)
    assert not af.ist_bekannt("")


def test_leerer_anbietername_ist_auch_unbekannt():
    assert af.stil_fuer("") == af.LUECKE
    assert af.stil_fuer(None) == af.LUECKE


def test_legendenname_traegt_den_zusatz_nur_bei_der_luecke():
    assert af.legendenname("Telekom") == "Telekom"
    assert af.legendenname("Nirgends Gelistet") == \
        "Nirgends Gelistet (Farbe nicht hinterlegt)"


def test_farbe_fuer_ist_die_kurzform_von_stil_fuer():
    for name in list(af.ANBIETER_FARBE) + ["Nirgends Gelistet"]:
        assert af.farbe_fuer(name) == af.stil_fuer(name).farbe


# --------------------------------------------------------------------------
# c) das Stylesheet - EIN Platzhalter, EIN erzeugter Block
# --------------------------------------------------------------------------

def test_css_block_traegt_jeden_bekannten_anbieter_und_die_luecke():
    block = af.css_block()
    for stil in list(af.ANBIETER_FARBE.values()) + [af.LUECKE]:
        regel = f".gr-anb--{stil.slug}{{"
        assert regel in block, stil.slug
        assert f"--anb:{stil.farbe};" in block
        assert f"--anb-strich:{stil.muster};" in block


def test_in_stylesheet_ersetzt_genau_den_platzhalter():
    css = "vorher{}\n" + af.MARKE + "\nnachher{}"
    ergebnis = af.in_stylesheet(css)
    assert af.MARKE not in ergebnis
    assert "vorher{}" in ergebnis and "nachher{}" in ergebnis
    assert ".gr-anb--telekom{" in ergebnis


def test_in_stylesheet_ohne_platzhalter_wirft_statt_still_grau_zu_rendern():
    with pytest.raises(af.AnbieterfarbenFehlen):
        af.in_stylesheet("body{color:red}")


def test_render_site_setzt_den_block_ins_echte_style_css(tmp_path):
    """Gegenprobe gegen die echte Vorlage: der Platzhalter steht wirklich
    in `templates/style.css`, und `render_site()` ersetzt ihn - nicht nur
    ein isolierter String im Modultest oben."""
    from telco_radar.report.html import render_site

    reports = tmp_path / "reports"
    reports.mkdir()
    site = tmp_path / "site"
    render_site(site, reports)
    css = (site / "style.css").read_text(encoding="utf-8")
    assert af.MARKE not in css
    assert ".gr-anb--vodafone{--anb:#e60000;" in css
    assert ".gr-anb--telekom{--anb:#e20074;" in css
