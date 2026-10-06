"""Der Ausfallhinweis bricht lange Pfade um, statt die Seite seitwärts zu schieben."""

from telco_radar.report.html import render_site

TIEFE = "OrdnernameOhneJedeStelleZumUmbrechen" * 2


def test_ein_langer_pfad_im_ausfallhinweis_schiebt_die_seite_nicht(tmp_path, chromium):
    wurzel = tmp_path / TIEFE
    reports = wurzel / "data" / "reports"
    reports.mkdir(parents=True)
    site = wurzel / "site"
    render_site(site, reports, cfg=None)
    seite = chromium.new_page(viewport={"width": 390, "height": 844})
    try:
        seite.goto((site / "index.html").as_uri())
        gemessen = seite.evaluate(
            """() => ({
                 hinweis: document.querySelector('#ausfaelle').textContent,
                 doc: document.documentElement.scrollWidth,
                 fenster: window.innerWidth,
               })"""
        )
    finally:
        seite.close()
    assert "ZumUmbrechen" in gemessen["hinweis"]
    assert gemessen["doc"] <= gemessen["fenster"], gemessen
