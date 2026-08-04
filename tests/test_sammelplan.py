"""Sammelphase: Parallelitaet MIT Host-Drosselung (Auftrag Skalierung 3.1).

Ohne Netz. Der Collector wird ersetzt, gemessen wird der Ablaufplan:
laufen zwei Quellen desselben Hosts je gleichzeitig, wird eingehalten,
was `collect_host_delay_seconds` verspricht, und verschwindet eine
stillgelegte Quelle still aus dem Protokoll.
"""
from __future__ import annotations

import threading
import time

import pytest

from telco_radar.collect import collect_all, sammelplan
from telco_radar.config import Config, Operator, Source
from telco_radar.models import Item


def _quelle(url: str, name: str = "Q") -> Source:
    return Source(type="rss", url=url, name=name)


def _config(urls: list[str], **settings) -> Config:
    """Eine Konfiguration mit je einem Betreiber je URL."""
    operators = [
        Operator(name=f"Op{i}", region_key="europe", region_name="Europa",
                 sources=[_quelle(u, f"Op{i}")])
        for i, u in enumerate(urls)
    ]
    return Config(root=None, settings=settings, operators=operators,
                  news_sources=[], region_names={"europe": "Europa"})


def _urls(gruppen) -> list[list[str]]:
    return [[job[0].url for job in g] for g in gruppen]


# ------------------------------------------------------------------ Plan

def test_gleicher_host_landet_in_einer_gruppe():
    jobs = [(_quelle(u), "europe", "Op", "operator") for u in [
        "https://blog.google/a", "https://blog.google/b",
        "https://blog.google/c", "https://example.com/feed",
    ]]
    gruppen = _urls(sammelplan(jobs, host_parallel=1))

    assert len(gruppen) == 2
    assert gruppen[0] == ["https://blog.google/a", "https://blog.google/b",
                          "https://blog.google/c"]      # groesste zuerst (LPT)
    assert gruppen[1] == ["https://example.com/feed"]


def test_www_und_port_zaehlen_als_derselbe_host():
    jobs = [(_quelle(u), "europe", "Op", "operator") for u in [
        "https://www.example.com/a", "https://example.com/b",
        "https://example.com:443/c",
    ]]
    assert len(sammelplan(jobs, host_parallel=1)) == 1


def test_host_parallel_teilt_die_gruppe_auf():
    jobs = [(_quelle(f"https://example.com/{i}"), "europe", "Op", "operator")
            for i in range(4)]
    gruppen = _urls(sammelplan(jobs, host_parallel=2))

    assert len(gruppen) == 2
    assert sorted(len(g) for g in gruppen) == [2, 2]
    # keine Quelle geht verloren und keine kommt doppelt
    assert sorted(u for g in gruppen for u in g) == \
        [f"https://example.com/{i}" for i in range(4)]


def test_host_parallel_groesser_als_die_quellenzahl_erzeugt_keine_leerlaeufe():
    jobs = [(_quelle("https://example.com/a"), "europe", "Op", "operator")]
    assert _urls(sammelplan(jobs, host_parallel=8)) == [["https://example.com/a"]]


# --------------------------------------------------------------- Ablauf

def test_kein_host_wird_gleichzeitig_angefasst(monkeypatch):
    """Der Kern der Drosselung: 429/403 entstehen durch Gleichzeitigkeit."""
    aktiv: dict[str, int] = {}
    ueberlappungen: list[str] = []
    sperre = threading.Lock()

    def fake_collect(source, region, operator, origin, http_cfg):
        host = source.url.split("/")[2]
        with sperre:
            aktiv[host] = aktiv.get(host, 0) + 1
            if aktiv[host] > 1:
                ueberlappungen.append(host)
        time.sleep(0.02)
        with sperre:
            aktiv[host] -= 1
        return [Item(title="Eine Meldung mit ausreichender Laenge",
                     url=source.url + "/1", source_name=source.name)]

    monkeypatch.setattr("telco_radar.collect._collect_source", fake_collect)
    cfg = _config([f"https://eng.example.com/{i}" for i in range(6)]
                  + [f"https://anders{i}.example/feed" for i in range(6)],
                  collect_max_workers=12)

    items, results = collect_all(cfg)

    assert ueberlappungen == []
    assert len(items) == len(results) == 12
    assert {r["status"] for r in results} == {"ok"}
    assert all("seconds" in r for r in results)


def test_verschiedene_hosts_laufen_wirklich_parallel(monkeypatch):
    """Sonst waere die Drosselung eine Bremse statt einer Absicherung."""
    def fake_collect(source, region, operator, origin, http_cfg):
        time.sleep(0.05)
        return []

    monkeypatch.setattr("telco_radar.collect._collect_source", fake_collect)
    cfg = _config([f"https://host{i}.example/feed" for i in range(8)],
                  collect_max_workers=8)

    t0 = time.monotonic()
    collect_all(cfg)
    dauer = time.monotonic() - t0

    assert dauer < 0.05 * 8 / 2, f"kaum Parallelitaet: {dauer:.2f}s"


def test_abstand_gilt_nur_zwischen_quellen_desselben_hosts(monkeypatch):
    geschlafen: list[float] = []
    monkeypatch.setattr("telco_radar.collect.time.sleep", geschlafen.append)
    monkeypatch.setattr("telco_radar.collect._collect_source",
                        lambda *a, **k: [])
    cfg = _config(["https://example.com/a", "https://example.com/b",
                   "https://example.com/c", "https://andere.example/x"],
                  collect_max_workers=4, collect_host_delay_seconds=1.5)

    collect_all(cfg)

    # drei Quellen auf einem Host -> zwei Pausen; die vierte Quelle liegt
    # auf einem anderen Host und wartet auf niemanden.
    assert geschlafen == [1.5, 1.5]


# ------------------------------------------------------------ Quarantaene

def test_stillgelegte_quelle_wird_nicht_abgerufen_aber_protokolliert(monkeypatch):
    abgerufen: list[str] = []

    def fake_collect(source, region, operator, origin, http_cfg):
        abgerufen.append(source.url)
        return []

    monkeypatch.setattr("telco_radar.collect._collect_source", fake_collect)
    cfg = _config(["https://tot.example/feed", "https://lebt.example/feed"],
                  collect_max_workers=4)

    items, results = collect_all(cfg, ueberspringen={"https://tot.example/feed"})

    assert abgerufen == ["https://lebt.example/feed"]
    nach_url = {r["url"]: r for r in results}
    assert nach_url["https://tot.example/feed"]["status"] == "quarantaene"
    assert nach_url["https://lebt.example/feed"]["status"] == "empty"
    assert items == []


def test_fehler_einer_quelle_stoppt_die_gruppe_nicht(monkeypatch):
    def fake_collect(source, region, operator, origin, http_cfg):
        if source.url.endswith("/b"):
            raise RuntimeError("kaputt")
        return [Item(title="Eine Meldung mit ausreichender Laenge",
                     url=source.url + "/1", source_name="Q")]

    monkeypatch.setattr("telco_radar.collect._collect_source", fake_collect)
    cfg = _config(["https://example.com/a", "https://example.com/b",
                   "https://example.com/c"], collect_max_workers=2)

    items, results = collect_all(cfg)

    nach_url = {r["url"]: r for r in results}
    assert nach_url["https://example.com/b"]["status"] == "fail"
    assert "kaputt" in nach_url["https://example.com/b"]["error"]
    # die Quelle NACH der kaputten wurde trotzdem abgerufen
    assert nach_url["https://example.com/c"]["status"] == "ok"
    assert len(items) == 2


@pytest.mark.parametrize("workers", [1, 3, 16])
def test_jede_quelle_erscheint_genau_einmal(monkeypatch, workers):
    monkeypatch.setattr("telco_radar.collect._collect_source",
                        lambda *a, **k: [])
    urls = [f"https://h{i % 5}.example/{i}" for i in range(20)]
    cfg = _config(urls, collect_max_workers=workers)

    _, results = collect_all(cfg)

    assert sorted(r["url"] for r in results) == sorted(urls)
