"""Der eine Render der Orakel: die Website aus dem Schnappschuss, je Worker einmal."""

from __future__ import annotations

import json
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
    der Konfiguration, nicht über den Berichtsordner."""
    wurzel = tmp_path_factory.mktemp("orakel")
    (wurzel / "config").symlink_to(WURZEL / "config")
    (wurzel / "data").symlink_to(bestand)
    site = wurzel / "site"
    ausfaelle = render_site(site, wurzel / "data" / "reports", load_config(wurzel))
    assert not ausfaelle, f"Render des Schnappschusses unvollständig: {ausfaelle}"
    tco = json.loads((bestand / "state" / "geraete_tco.json").read_text("utf-8"))
    return {
        "bestand": bestand,
        "geraete": (site / "geraete.html").read_text(encoding="utf-8"),
        "fragment": (site / "data" / "geraete-zeitreihe.html").read_text("utf-8"),
        "buendel": (site / "data" / "geraete-buendel.html").read_text("utf-8"),
        "csv": site / "exporte" / "geraete-tco.csv",
        "stand": tco["updated"],
    }
