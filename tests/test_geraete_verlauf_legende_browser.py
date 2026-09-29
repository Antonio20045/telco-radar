"""QA-Fix 24.09.2026, Punkt 4 (Entscheidung): am Preisverlauf-Reiter
traegt nur die VERDECKTE Linie ein Endlabel (Disambiguierung zweier
Linien auf fast derselben Hoehe, siehe `tests/test_geraete_reiter_browser
.py`) - nicht jeder Anbieter. Diese Entscheidung ist keine Luecke, WENN
die Legende wirklich JEDEN gezeichneten Anbieter mit seiner Hausfarbe
nennt (`report/anbieter_farben.py`, EINE Quelle) - dieser Test haelt das
fest, am selben Sechs-Anbieter-Gerät wie
`test_geraete_verlauf_chart_mobil_browser.py`."""
from __future__ import annotations

import pytest

from telco_radar.report import anbieter_farben

from test_geraete_verlauf_chart_mobil_browser import _REIHEN, _browser_ctx


@pytest.fixture(scope="module")
def seite(tmp_path_factory):
    with _browser_ctx(tmp_path_factory) as (wurzel, browser):
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        s = ctx.new_page()
        s.goto(f"{wurzel}/geraete.html", wait_until="networkidle")
        s.click('.gr-reiter [data-tafel="tafel-verlauf"]')
        s.wait_for_timeout(120)
        s.fill("#gr-vsuche", "iPhone 17 256")
        s.wait_for_timeout(150)
        s.click("#gr-vtreffer li:first-child")
        s.wait_for_timeout(300)
        yield s


def test_die_legende_nennt_jeden_gezeichneten_anbieter(seite):
    namen = seite.eval_on_selector_all(
        ".gr-vlegende-teil", "es => es.map(e => e.textContent.trim())")
    erwartet = {a for a, _p in _REIHEN}
    assert erwartet <= set(namen), (
        f"die Legende nennt nicht alle Anbieter: {namen}, erwartet "
        f"mindestens {erwartet}")


def test_telekom_ist_magenta_in_der_legende(seite):
    """Telekom muss in JEDEM Fall magenta und beschriftet sein - die
    Legendenfarbe kommt aus der EINEN Quelle (`anbieter_farben.py`), nicht
    aus einer zweiten Palette in app.js."""
    farbe = seite.eval_on_selector(
        ".gr-vlegende-teil:has-text('Telekom') .gr-vlegende-punkt",
        "e => getComputedStyle(e).backgroundColor")
    assert farbe, "kein Telekom-Legendenpunkt gefunden"
    erwartet = anbieter_farben.farbe_fuer("Telekom")
    assert erwartet.lower() == "#e20074", (
        f"anbieter_farben.py hat sich geaendert: {erwartet!r}")
    # rgb(226, 0, 116) == #e20074
    assert farbe.replace(" ", "") in ("rgb(226,0,116)", "rgba(226,0,116,1)"), (
        f"die Legendenfarbe ist nicht Telekom-Magenta: {farbe!r}")
