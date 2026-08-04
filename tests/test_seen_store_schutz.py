"""Ungelesene Meldungen duerfen nicht im Seen-Store landen.

Der Seen-Store ist ein Einbahnschild: was drin ist, wird nie wieder gesammelt.
Lauf #64 (04.08.2026) lief mit leerem Anthropic-Guthaben, jeder Analysten-
Stapel scheiterte mit HTTP 400 - und trotzdem wanderten 223 ungelesene
Meldungen hinein. Beim naechsten Lauf mit Guthaben waeren sie fuer immer weg
gewesen. Diese Tests halten die Absicherung fest.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from telco_radar.models import Item


def _item(url: str, region: str) -> Item:
    return Item(title=f"Titel {url}", url=url, source_name="q", region=region,
                operator="Op", published=datetime.now(timezone.utc),
                summary="", origin="operator")


class _Seen:
    """Minimaler Ersatz fuer den Seen-Store; merkt sich, was ankam."""

    def __init__(self):
        self.gemerkt: list[Item] = []

    def add(self, items):
        self.gemerkt.extend(items)


def _persistiere(new_items, unanalysierte, seen):
    """Der Persistenz-Schritt der Pipeline, isoliert nachgebildet.

    Bewusst als eigene Funktion geprueft: den ganzen Lauf zu starten braucht
    Netz und ein Modell, und die Regel selbst ist eine reine Mengenoperation.
    """
    zu_merken = [i for i in new_items if i.region not in unanalysierte]
    seen.add(zu_merken)
    return len(new_items) - len(zu_merken)


def test_meldungen_einer_gescheiterten_region_werden_nicht_gemerkt():
    items = [_item("u1", "europe"), _item("u2", "asia")]
    seen = _Seen()
    uebersprungen = _persistiere(items, {"asia"}, seen)
    assert [i.url for i in seen.gemerkt] == ["u1"]
    assert uebersprungen == 1


def test_ohne_ausfall_wird_alles_gemerkt():
    items = [_item("u1", "europe"), _item("u2", "asia")]
    seen = _Seen()
    assert _persistiere(items, set(), seen) == 0
    assert len(seen.gemerkt) == 2


def test_totalausfall_merkt_gar_nichts():
    """Der Fall aus Lauf #64: kein Guthaben, keine Region analysiert."""
    items = [_item(f"u{n}", r) for n, r in
             enumerate(["europe", "asia", "global", "north_america"])]
    seen = _Seen()
    uebersprungen = _persistiere(items, {"europe", "asia", "global",
                                         "north_america"}, seen)
    assert seen.gemerkt == []
    assert uebersprungen == 4


@pytest.mark.parametrize("batches,batches_ok,gilt_als_ausgefallen", [
    (4, 0, True),    # jeder Stapel gescheitert
    (4, 1, False),   # teilweise durch - der Rest ist der alte Kompromiss
    (0, 0, False),   # nichts zu tun, kein Ausfall
    (1, 1, False),
])
def test_ausfallkriterium(batches, batches_ok, gilt_als_ausgefallen):
    """Genau das Kriterium, das die Pipeline auf der Telemetrie auswertet."""
    assert bool(batches and not batches_ok) is gilt_als_ausgefallen
