"""Was die Sammelphase je Quelle protokolliert - und warum es gebraucht wird.

Drei Dinge haengen daran:
  * `source_url` je Meldung  -> Trefferquote je KANAL (ein Betreiber mit
    Newsroom und Investor Relations traegt in beiden denselben Anzeigenamen)
  * `seconds` je Quelle      -> bei 1000 Quellen ist sonst nicht zu sehen,
    WELCHE Quelle die Sammelphase aufhaelt
  * `new` je Quelle          -> der Nenner der Trefferquote; seit dem
    kompakten Seen-Store steht die Zuordnung Meldung->Quelle nirgends sonst
"""
from __future__ import annotations

from pathlib import Path

import pytest

from telco_radar.collect import collect_all, collect_source
from telco_radar.config import Source


@pytest.fixture
def quelle():
    return Source(type="rss", url="https://beispiel.de/feed", name="Beispiel")


@pytest.fixture(autouse=True)
def _gate_zuruecksetzen():
    """collect_all setzt ein PROZESSWEITES Gate. Ohne Zuruecksetzen haengt das
    Ergebnis anderer Tests davon ab, in welcher Reihenfolge pytest laeuft."""
    from telco_radar.collect import http as http_mod
    vorher = http_mod.active_gate()
    yield
    http_mod._gate = vorher


def test_collect_source_stempelt_die_quellen_url(monkeypatch, quelle):
    from telco_radar.models import Item
    import telco_radar.collect as collect_mod

    monkeypatch.setattr(collect_mod, "collect_rss",
                        lambda *a, **k: [Item(title="Eine Meldung",
                                              url="https://beispiel.de/1",
                                              source_name="Beispiel")])
    items = collect_source(quelle, "europa")
    assert [i.source_url for i in items] == ["https://beispiel.de/feed"]


def test_stempel_ueberlebt_den_ausschlussfilter(monkeypatch):
    """exclude_url_pattern laeuft NACH dem Sammeln - der Stempel danach."""
    from telco_radar.models import Item
    import telco_radar.collect as collect_mod

    quelle = Source(type="rss", url="https://beispiel.de/feed", name="Beispiel",
                    exclude_url_pattern=r"/es/")
    monkeypatch.setattr(collect_mod, "collect_rss", lambda *a, **k: [
        Item(title="Deutsch", url="https://beispiel.de/de/1", source_name="B"),
        Item(title="Spanisch", url="https://beispiel.de/es/1", source_name="B"),
    ])
    items = collect_source(quelle, "europa")
    assert len(items) == 1
    assert items[0].source_url == "https://beispiel.de/feed"


class _Cfg:
    """Minimale Config-Attrappe - collect_all liest nur diese Felder."""

    def __init__(self, settings=None):
        self.settings = settings or {"collect_max_workers": 2}
        self.operators = []
        self.news_sources = [Source(type="rss", url="https://presse.de/feed",
                                    name="Presse", kind="trade_press")]
        self.tech_sources = []


def test_laufprotokoll_haelt_dauer_und_status_fest(monkeypatch):
    from telco_radar.models import Item
    import telco_radar.collect as collect_mod

    monkeypatch.setattr(collect_mod, "collect_rss",
                        lambda *a, **k: [Item(title="Meldung",
                                              url="https://presse.de/1",
                                              source_name="Presse")])
    items, results = collect_all(_Cfg())
    assert len(items) == 1
    assert results[0]["status"] == "ok"
    assert results[0]["count"] == 1
    assert isinstance(results[0]["seconds"], float)


def test_gescheiterte_quelle_bekommt_trotzdem_eine_dauer(monkeypatch):
    """Ohne das faellt genau die Quelle aus der Messung, die am laengsten
    gebraucht hat - ein Timeout ist der teuerste Fall, nicht der billigste."""
    import telco_radar.collect as collect_mod

    def kaputt(*a, **k):
        raise TimeoutError("read timeout")

    monkeypatch.setattr(collect_mod, "collect_rss", kaputt)
    _, results = collect_all(_Cfg())
    assert results[0]["status"] == "fail"
    assert "TimeoutError" in results[0]["error"]
    assert isinstance(results[0]["seconds"], float)


def test_eine_kaputte_quelle_stoppt_den_lauf_nicht(monkeypatch):
    from telco_radar.models import Item
    import telco_radar.collect as collect_mod

    cfg = _Cfg()
    cfg.news_sources.append(Source(type="rss", url="https://kaputt.de/feed",
                                   name="Kaputt", kind="trade_press"))

    def mal_so_mal_so(source, *a, **k):
        if "kaputt" in source.url:
            raise ValueError("unparseable feed")
        return [Item(title="Meldung", url="https://presse.de/1",
                     source_name="Presse")]

    monkeypatch.setattr(collect_mod, "collect_rss", mal_so_mal_so)
    items, results = collect_all(cfg)
    assert len(items) == 1
    assert sorted(r["status"] for r in results) == ["fail", "ok"]


def test_drosselung_wird_aus_den_settings_gesetzt(monkeypatch):
    from telco_radar.collect.http import active_gate
    import telco_radar.collect as collect_mod

    monkeypatch.setattr(collect_mod, "collect_rss", lambda *a, **k: [])
    collect_all(_Cfg({"collect_max_workers": 2,
                      "collect_host_max_parallel": 3,
                      "collect_host_min_interval_seconds": 0.25}))
    assert active_gate().max_parallel == 3
    assert active_gate().min_interval == 0.25


def test_headless_renderings_werden_getrennt_begrenzt(monkeypatch):
    """Ein newsroom_js-Abruf ist keine reine Wartezeit: er startet einen
    Chromium. Im Diagnoselauf #74 fiel bei 64 Workern eine Quelle mit
    "Page.goto: Timeout 16000ms exceeded" aus, die bei 8 Workern durchlief -
    die Seite war nicht langsamer, der Runner war voll."""
    import telco_radar.collect as collect_mod
    from telco_radar.models import Item

    gleichzeitig = {"jetzt": 0, "max": 0}
    sperre = __import__("threading").Lock()

    def _render(source, *a, **k):
        with sperre:
            gleichzeitig["jetzt"] += 1
            gleichzeitig["max"] = max(gleichzeitig["max"], gleichzeitig["jetzt"])
        __import__("time").sleep(0.05)
        with sperre:
            gleichzeitig["jetzt"] -= 1
        return [Item(title="Meldung", url=source.url + "/1", source_name="X")]

    monkeypatch.setattr(collect_mod, "collect_newsroom_js", _render)
    cfg = _Cfg({"collect_max_workers": 16})
    cfg.news_sources = [Source(type="newsroom_js", url=f"https://js{i}.de/news",
                               name=f"JS{i}", kind="newsroom_js")
                        for i in range(12)]

    items, _ = collect_all(cfg)
    assert len(items) == 12
    assert gleichzeitig["max"] <= 4
