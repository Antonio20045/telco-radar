"""o2: ein nicht geprüfter Kaufweg steht auf der Geräteseite, nicht nur im Log.

Prüferbefund zu PR 206 (21.11.2026): Fällt die Tarifübersicht aus oder findet ein Lauf
kein Kachelmuster (`o2_kaufbar.AUSFALL`, `MUSTER_FEHLT`), verschwinden die Zeilen von
O2 Mobile Unlimited L sonst still. Wie bei Vodafone (`vodafone_sicht.UNGEPRUEFT`)
tragen die Rohsätze dann das Merkmal `sichtbarkeit_nicht_geprueft`; der Gerätelauf
schreibt daraus einen Erfassungssatz (`klick_erfassung.mit_kaufweg`, Schlüssel
`o2|kaufweg` in `geraete_tco.json`), und die Messdatum-Zeile von o2 trägt die Marke
„Kaufweg nicht geprüft“ mit dem ganzen Satz im `title`. Synthetisch, fester Tag.
"""

from __future__ import annotations

import json
import shutil

import test_geraete_buendel_kopf_zeitraum as basis
from bs4 import BeautifulSoup

from telco_radar.report.html import render_site

SATZ = "o2: Kaufweg nicht geprüft (Tarifübersicht nicht gelesen, 08.11.2026)"


def _seite(tmp_path, erfassung: dict) -> BeautifulSoup:
    site = basis._baue(tmp_path)
    wurzel = site.parent
    datei = wurzel / "data" / "state" / "geraete_tco.json"
    tco = json.loads(datei.read_text(encoding="utf-8"))
    tco["erfassung"] = erfassung
    datei.write_text(json.dumps(tco), encoding="utf-8")
    shutil.rmtree(site)
    render_site(site, wurzel / "data" / "reports")
    return BeautifulSoup((site / "geraete.html").read_text("utf-8"), "html.parser")


def _zeile(suppe: BeautifulSoup, anbieter: str):
    return suppe.select_one(f'#messdatum li[data-anbieter="{anbieter}"]')


def test_messdatum_zeile_nennt_den_ungeprueften_kaufweg(tmp_path):
    suppe = _seite(tmp_path, {"o2|kaufweg": SATZ})
    o2 = _zeile(suppe, "o2")
    marke = o2.select_one(".gr-md-kaufweg")
    assert marke is not None
    assert marke.get_text(strip=True) == "Kaufweg nicht geprüft"
    assert SATZ in o2.get("title", "")
    assert _zeile(suppe, "Vodafone").select_one(".gr-md-kaufweg") is None


def test_gegenprobe_ohne_satz_keine_marke(tmp_path):
    suppe = _seite(tmp_path, {})
    assert _zeile(suppe, "o2") is not None
    assert suppe.select_one("#messdatum .gr-md-kaufweg") is None
    assert "Kaufweg" not in suppe.select_one("#messdatum").get_text()
