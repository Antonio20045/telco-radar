"""P2 (03.11.2026) im echten Chromium: Schriftgrößen-Rangfolge, schlichter
Kopf, sichtbarer Abschnitt „teurer“ und ausgedünnte Datumsachse am Handy."""

from __future__ import annotations

import pytest
import test_geraete_zeitreihe_browser as zb


@pytest.fixture(scope="module")
def seite_p2(tmp_path_factory, chromium):
    site = zb._baue_site(tmp_path_factory.mktemp("p2browser"))
    with zb._server(site) as basis:
        yield chromium, basis


@pytest.fixture
def schreibtisch(seite_p2):
    with zb._ansicht(seite_p2) as paar:
        yield paar


@pytest.fixture
def telefon(seite_p2):
    with zb._ansicht(seite_p2, 390, 844, touch=True) as paar:
        yield paar


def test_der_kopf_ist_schlicht_und_die_zahl_ist_die_groesste_schrift(schreibtisch):
    s, _ = schreibtisch
    m = s.evaluate("""() => {
      const k = document.querySelector('.gx-auftakt');
      const zahl = k.querySelector('.gx-held b');
      const h2 = document.querySelector('#teuer h2');
      return {
        bild: getComputedStyle(k).backgroundImage,
        grund: getComputedStyle(k).backgroundColor,
        bilder: k.querySelectorAll('img').length,
        zahl: parseFloat(getComputedStyle(zahl).fontSize),
        h2: parseFloat(getComputedStyle(h2).fontSize),
      };
    }""")
    assert m["bild"] == "none" and m["bilder"] == 0, m
    assert m["grund"] != "rgb(230, 0, 0)", m
    assert m["zahl"] > 2 * m["h2"], m
    assert m["h2"] <= 22, m


def test_der_abschnitt_teurer_ist_ohne_scrollen_sichtbar(schreibtisch):
    s, _ = schreibtisch
    unsichtbar = s.evaluate("""() => [...document.querySelectorAll(
      '#teuer, #teuer *')].filter(e =>
        parseFloat(getComputedStyle(e).opacity) < 1).length""")
    assert unsichtbar == 0


def test_am_handy_ist_die_datumsachse_ausgeduennt(telefon):
    s, _ = telefon
    s.evaluate("() => document.getElementById('tco').scrollIntoView()")
    s.wait_for_timeout(150)
    m = s.evaluate("""() => {
      const t = [...document.querySelectorAll(
        '#tafel-tco svg.gr-zr--schmal text.gr-zr-xtick')]
        .map(e => e.getBoundingClientRect()).filter(r => r.width > 0)
        .sort((a, b) => a.left - b.left);
      let luecke = 1e9;
      for (let i = 1; i < t.length; i++)
        luecke = Math.min(luecke, t[i].left - t[i - 1].right);
      const zw = [...document.querySelectorAll(
        '#tafel-tco svg.gr-zr--schmal circle.gr-zr-punkt:not(.gr-zr-ende)')]
        .filter(c => getComputedStyle(c).opacity !== '0').length;
      return {n: t.length, luecke, sichtbareZwischenpunkte: zw};
    }""")
    assert m["n"] >= 2, m
    assert m["luecke"] >= 0, m
    assert m["sichtbareZwischenpunkte"] == 0, m


_UEBERLAPPUNG = """() => {
  const r = s => document.querySelector(s).getBoundingClientRect();
  const held = r('.gx-held'), zahl = r('.gx-held b'), modus = r('.gx-modus');
  const rand = getComputedStyle(document.querySelector('.gx-modus')).marginTop;
  return {held: [held.top, held.bottom], zahl: [zahl.top, zahl.bottom],
          modus: [modus.top, modus.bottom],
          rand: parseFloat(rand)};
}"""


def _ohne_ueberlappung(s):
    s.evaluate("() => window.scrollTo(0, 0)")
    s.wait_for_timeout(150)
    m = s.evaluate(_UEBERLAPPUNG)
    for teil in ("held", "zahl"):
        assert m["modus"][0] >= m[teil][1], (teil, m)
    assert m["rand"] >= 0, ("ein negativer Rand zieht den Schalter in die Zahl", m)
    return m


def test_am_schreibtisch_deckt_der_schalter_die_leitzahl_nicht_ab(schreibtisch):
    s, _ = schreibtisch
    m = _ohne_ueberlappung(s)
    assert m["modus"][0] >= m["held"][1], m


def test_am_handy_deckt_der_schalter_die_leitzahl_nicht_ab(telefon):
    s, _ = telefon
    m = _ohne_ueberlappung(s)
    assert m["modus"][0] - m["held"][1] >= 8, m
