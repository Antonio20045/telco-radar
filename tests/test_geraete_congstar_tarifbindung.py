"""congstar-Adapter: die Mindestlaufzeit des Tarifs steht im Bündelsatz.

BEFUND 21.11.2026 (Vergleich Adapter gegen Klick, alle 712 Zwillinge des Messtags):
Rate, Anzahlung, Tarifpreis, Anschluss, Listenpreis und Preisphasen sind in allen 712
gleich. Einziger Unterschied: der Klick nennt die Tarifbindung (24 Monate, bei Flex
0), der Adapter nennt keine (``None``). Die Produktseite zeigt sie sichtbar („24
Monate Laufzeit“ und „Ohne Laufzeit (mtl. kündbar)“, Browser 21.11.2026), die
Nutzlast trägt sie je PlanVariant als ``minimumContractDuration`` (24 bzw. 0). Ohne
diesen Wert verlöre jede congstar-Zeile beim Wechsel auf den Adapter ihre Bindung.
"""

from __future__ import annotations

import gzip
from pathlib import Path

from telco_radar.collect.geraete import congstar

_FIXTURE = Path(__file__).parent / "fixtures" / "geraete"
_SEITE = "congstar_produkt_galaxy_s26_20261116.html.gz"


def _text() -> str:
    with gzip.open(_FIXTURE / _SEITE, "rt", encoding="utf-8") as fh:
        return fh.read()


def _saetze() -> list[dict]:
    return congstar.lies_buendel(_text(), "https://www.congstar.de/geraete/x/")


def test_jeder_satz_nennt_die_bindung_seines_tarifs():
    saetze = _saetze()
    assert saetze
    flex = {s["tarif_bindung_monate"] for s in saetze if "Flex" in s["tarif_name"]}
    fest = {s["tarif_bindung_monate"] for s in saetze if "Flex" not in s["tarif_name"]}
    assert (fest, flex) == ({24}, {0})


def test_gegenprobe_ein_tarif_ohne_angabe_bleibt_eine_luecke():
    plan = {
        "title": "Allnet Flat M",
        "prices": {"recurring": {"discounted": 25.0}, "activation": {"discounted": 0}},
        "devices": [],
    }
    assert congstar._bindung(plan) is None
    assert congstar._bindung({**plan, "minimumContractDuration": 24}) == 24
    assert congstar._bindung({**plan, "minimumContractDuration": 0}) == 0
    for unlesbar in ("24", -1, True, 24.5):
        assert congstar._bindung({**plan, "minimumContractDuration": unlesbar}) is None


def test_die_nutzlast_der_fixture_traegt_die_angabe():
    """Gegenprobe gegen die Rohdaten: 24 bei festen, 0 bei Flex-Tarifen."""
    plaene = congstar._json_unter(congstar._nutzlast(_text()), "prefetchedPlans")
    werte = {
        pv["title"]: pv["minimumContractDuration"]
        for tarif in plaene
        for pv in tarif["variants"]
    }
    assert werte["Allnet Flat M"] == 24 and werte["Allnet Flat M Flex"] == 0
