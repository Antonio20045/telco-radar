"""Der Ausfallhinweis bricht lange Wörter um, statt die Seite seitwärts zu schieben."""

from telco_radar.report.html import render_site

LANGES_WORT = "/OrdnernameOhneJedeStelleZumUmbrechen" * 12


def test_ein_langes_wort_im_ausfallhinweis_schiebt_die_seite_nicht(tmp_path, chromium):
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    site = tmp_path / "site"
    render_site(site, reports, cfg=None)
    seite = chromium.new_page(viewport={"width": 390, "height": 844})
    try:
        seite.goto((site / "index.html").as_uri())
        gemessen = seite.evaluate(
            """(wort) => {
                 const hinweis = document.querySelector('#ausfaelle');
                 hinweis.textContent = 'Nicht neu gebaut: Konfiguration (' + wort + ')';
                 return {
                   doc: document.documentElement.scrollWidth,
                   fenster: window.innerWidth,
                 };
               }""",
            LANGES_WORT,
        )
    finally:
        seite.close()
    assert gemessen["doc"] <= gemessen["fenster"], gemessen
