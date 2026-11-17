"""Der eine Render der Orakel: die Website aus dem Schnappschuss, je Worker einmal."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from telco_radar.config import load_config
from telco_radar.report.html import render_site

WURZEL = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def gw_seite(bestand: Path, tmp_path_factory: pytest.TempPathFactory) -> dict:
    """Geräteseite, Fragmente und Export aus dem Schnappschuss, dazu sein Ordner.

    Die Bündelliste je Modell liegt im Nachladefragment, nicht in ``geraete.html``;
    beide Dokumente bleiben getrennt, sonst fielen die Inline-Bündel des Startmodells
    in den letzten Lager-Block. Die Wurzel ist ein Wegwerfordner, dessen ``data`` auf
    den Schnappschuss zeigt: ``render_site`` liest Teile des Bestands über die Wurzel
    der Konfiguration, nicht über den Berichtsordner.

    UI-1717 Aufgabe 5: ``#gr-radar-inhalt`` steht im First Paint leer - app.js
    holt sein Markup erst beim Sichtbarwerden aus ``data/geraete-radar.html``.
    ``geraete`` traegt hier denselben Inhalt an derselben Stelle, damit Tests,
    die #wr-alarme/#wr-abweichung direkt aus ``geraete`` lesen, unveraendert
    greifen."""
    wurzel = tmp_path_factory.mktemp("orakel")
    (wurzel / "config").symlink_to(WURZEL / "config")
    (wurzel / "data").symlink_to(bestand)
    site = wurzel / "site"
    ausfaelle = render_site(site, wurzel / "data" / "reports", load_config(wurzel))
    assert not ausfaelle, f"Render des Schnappschusses unvollständig: {ausfaelle}"
    tco = json.loads((bestand / "state" / "geraete_tco.json").read_text("utf-8"))
    geraete_html = (site / "geraete.html").read_text(encoding="utf-8")
    radar_pfad = site / "data" / "geraete-radar.html"
    if radar_pfad.exists():
        radar_html = radar_pfad.read_text(encoding="utf-8")
        geraete_html = re.sub(
            r'(<div id="gr-radar-inhalt"[^>]*>)(</div>)',
            lambda m: m.group(1) + radar_html + m.group(2),
            geraete_html,
            count=1,
        )
    return {
        "bestand": bestand,
        "geraete": geraete_html,
        "fragment": "".join(
            p.read_text("utf-8") for p in sorted((site / "data" / "zr").glob("*.html"))
        ),
        "buendel": (site / "data" / "geraete-buendel.html").read_text("utf-8"),
        "csv": site / "exporte" / "geraete-tco.csv",
        "stand": tco["updated"],
    }
