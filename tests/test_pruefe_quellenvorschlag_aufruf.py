from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

from telco_radar.models import Item

WURZEL = Path(__file__).resolve().parents[1]


def _lade():
    spec = importlib.util.spec_from_file_location(
        "pruefe_quellenvorschlag_aufruf",
        WURZEL / "scripts" / "pruefe_quellenvorschlag.py",
    )
    modul = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modul
    spec.loader.exec_module(modul)
    return modul


def test_kommandozeile_prueft_datierte_meldungen_ohne_absturz(monkeypatch, capsys):
    pq = _lade()
    stand = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    items = [
        Item(
            source_name="Beispiel",
            title=f"Meldung Nummer {i} mit einer echten Ueberschrift",
            url=f"https://example.com/news/{i}",
            published=stand,
        )
        for i in range(8)
    ]
    monkeypatch.setattr(pq, "collect_source", lambda *a, **k: items)
    rc = pq.main(
        [
            "--root",
            str(WURZEL),
            "--url",
            "https://example.com/feed",
            "--type",
            "rss",
            "--no-overlap",
            "--einmal",
            "--workers",
            "1",
        ]
    )
    ausgabe = capsys.readouterr().out
    assert rc in (0, 1)
    assert "8" in ausgabe
