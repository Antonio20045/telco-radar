"""Fällt das Graph-Fragment aus, nennt die Seite den Ausfall (Regel 6).

Der Abruf `data/zr/<modell>.html` wird im echten Chromium abgelehnt; nach dem
Bandwechsel steht ein benannter Satz statt des alten Graphen. Gegenprobe:
läuft der Abruf, steht der neue Graph und kein Ausfallsatz.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import pathlib
import socket
import threading

import pytest
from browser_konsole import konsole_sammeln
from test_geraete_zeitreihe_ansicht import HEUTE, baue

from telco_radar.report.html import render_site

AUSFALL = "konnte nicht geladen werden"


def _baue_site(tmp_path: pathlib.Path) -> pathlib.Path:
    root, _ = baue(tmp_path)
    reports = root / "data" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / f"{HEUTE}.json").write_text(
        json.dumps(
            {
                "date": HEUTE,
                "language": "de",
                "briefing_md": "## Auf einen Blick\n\n- Nichts.\n",
                "stats": {},
                "regions": [],
            }
        ),
        encoding="utf-8",
    )
    (reports / f"{HEUTE}.md").write_text("# B\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return site


@contextlib.contextmanager
def _server(site: pathlib.Path):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


@pytest.fixture(scope="module")
def _seite(tmp_path_factory, chromium):
    site = _baue_site(tmp_path_factory.mktemp("zrausfall"))
    with _server(site) as basis:
        yield chromium, basis


def _wechsle_band(_seite, abrufe_sperren: bool):
    browser, basis = _seite
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    s = context.new_page()
    konsole_sammeln(s)
    if abrufe_sperren:
        context.route("**/data/zr/*", lambda route: route.abort())
    s.goto(f"{basis}/geraete.html", wait_until="load")
    s.wait_for_timeout(250)
    s.click("#gr-zr-baender button[data-band='m']")
    s.wait_for_timeout(400)
    text = s.eval_on_selector("#gr-zr-gruppe", "e => e.textContent")
    graphen = s.locator("#gr-zr-gruppe svg.gr-zr").count()
    context.close()
    return text, graphen


def test_ausfall_des_fragments_steht_als_satz_auf_der_seite(_seite):
    text, graphen = _wechsle_band(_seite, abrufe_sperren=True)
    assert AUSFALL in text
    assert graphen == 0, "der alte Graph gehört nicht zum gewählten Band"


def test_ohne_ausfall_steht_der_graph_und_kein_ausfallsatz(_seite):
    text, graphen = _wechsle_band(_seite, abrufe_sperren=False)
    assert AUSFALL not in text
    assert graphen == 1
