"""Paket 36: Quellenabrufe außerhalb von ``collect.http`` gehen über dessen Naht.

Vorher holten ``ct_log.hole`` mit ``httpx.get`` und ``category_sweep.brave_search``
mit ``urllib.request`` an ``collect.http.TRANSPORT`` vorbei; der goldene Lauf
und die Netzsperre der Tests sahen diese Abrufe nicht.
"""

from __future__ import annotations

import httpx
import pytest

from telco_radar.analyze import category_sweep
from telco_radar.collect import ct_log, http


@pytest.fixture
def naht(monkeypatch):
    gesehen: list[httpx.Request] = []

    def setze(antwort: httpx.Response | Exception):
        def antworte(anfrage: httpx.Request) -> httpx.Response:
            gesehen.append(anfrage)
            if isinstance(antwort, Exception):
                raise antwort
            return antwort

        monkeypatch.setattr(http, "TRANSPORT", httpx.MockTransport(antworte))
        return gesehen

    return setze


def test_ct_log_holt_ueber_die_naht(naht):
    gesehen = naht(httpx.Response(200, json=[{"dns_names": ["neu.congstar.de"]}]))
    daten = ct_log.hole(ct_log.Domain(marke="congstar", domain="congstar.de"), {})
    assert daten == [{"dns_names": ["neu.congstar.de"]}]
    assert gesehen[0].url.host == "api.certspotter.com"
    assert gesehen[0].url.params["domain"] == "congstar.de"


def test_ct_log_zeitueberschreitung_ueber_die_naht(naht):
    naht(httpx.ReadTimeout("zu langsam"))
    with pytest.raises(ct_log.CTZeitueberschreitung):
        ct_log.hole(ct_log.Domain(marke="congstar", domain="congstar.de"), {})


def test_ct_log_verbindungsfehler_ist_ctfehler(naht):
    naht(httpx.ConnectError("weg"))
    with pytest.raises(ct_log.CTFehler):
        ct_log.hole(ct_log.Domain(marke="congstar", domain="congstar.de"), {})


def test_brave_suche_ueber_die_naht(naht):
    treffer = {"web": {"results": [{"title": "T", "url": "https://a.de/x"}, {}]}}
    gesehen = naht(httpx.Response(200, json=treffer))
    ergebnis = category_sweep.brave_search("telco ki", "geheim", count=3)
    assert [e["url"] for e in ergebnis] == ["https://a.de/x"]
    assert gesehen[0].url.params["q"] == "telco ki"
    assert gesehen[0].url.params["count"] == "3"
    assert gesehen[0].headers["X-Subscription-Token"] == "geheim"


def test_brave_suche_http_fehler_ist_leer(naht):
    naht(httpx.Response(500))
    assert category_sweep.brave_search("telco ki", "geheim") == []


def test_ct_log_ohne_llm_funktion_ueberspringt_die_modellstufe(tmp_path, naht):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "ct_domains.yaml").write_text(
        "domains:\n  - marke: congstar\n    domain: congstar.de\n", encoding="utf-8"
    )
    (tmp_path / "data" / "state").mkdir(parents=True)
    (tmp_path / "data" / "state" / "ct_seen.jsonl").write_text(
        '{"domain": "congstar.de", "namen": [], "stand": "2026-08-01"}\n',
        encoding="utf-8",
    )
    naht(httpx.Response(200, json=[{"dns_names": ["aktion.congstar.de"]}]))
    items, bilanz = ct_log.sammle(tmp_path, {}, modell="m")
    assert [i.title for i in items] and bilanz["meldungen"] == 1
