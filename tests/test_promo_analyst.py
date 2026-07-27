"""Tests fuer die Promo-LLM-Extraktion (analyze/promo_analyst.py), vor allem
die neue Link-Kandidaten-Auswahl (claude/promo-tiefenlinks-konzept.md).

Der Netzwerk-/Modellaufruf selbst wird gemockt (monkeypatch auf `complete`
im Modul-Namensraum, gleiches Muster wie tests/test_llm_fallback.py) - keine
echten LLM-Kosten oder Netzabhaengigkeit fuer diese Tests.
"""
import json

from telco_radar.analyze import promo_analyst
from telco_radar.analyze.promo_analyst import _resolve_link_index, extract_promos

_LINKS = [
    {"href": "https://example.test/geraet-a", "text": "Galaxy A57 - Nur 27,49 EUR"},
    {"href": "https://example.test/geraet-b", "text": "iPhone 17 - Nur 34,99 EUR"},
]


def _stub_complete(monkeypatch, response_rows, capture_calls=None):
    def fake(system, user, model, max_tokens):
        if capture_calls is not None:
            capture_calls.append({"system": system, "user": user})
        return json.dumps(response_rows)
    monkeypatch.setattr(promo_analyst, "complete", fake)


def test_extract_promos_resolves_valid_link_index(monkeypatch):
    _stub_complete(monkeypatch, [
        {"headline": "Galaxy A57 Aktion", "description": "...", "link_index": 1},
    ])
    items = extract_promos("O2", "irgendein Seitentext", "test-model", links=_LINKS)
    assert items[0]["url"] == "https://example.test/geraet-a"


def test_extract_promos_ignores_out_of_range_link_index(monkeypatch):
    _stub_complete(monkeypatch, [
        {"headline": "Galaxy A57 Aktion", "description": "...", "link_index": 99},
    ])
    items = extract_promos("O2", "irgendein Seitentext", "test-model", links=_LINKS)
    assert "url" not in items[0]


def test_extract_promos_ignores_missing_or_null_link_index(monkeypatch):
    _stub_complete(monkeypatch, [
        {"headline": "Galaxy A57 Aktion", "description": "..."},
        {"headline": "Andere Aktion", "description": "...", "link_index": None},
    ])
    items = extract_promos("O2", "irgendein Seitentext", "test-model", links=_LINKS)
    assert all("url" not in it for it in items)


def test_extract_promos_accepts_numeric_string_index():
    """Modelle liefern JSON-Zahlen gelegentlich als String - defensiv genau
    wie das bestehende valid_until-Handling in diesem Modul."""
    assert _resolve_link_index({"link_index": "2"}, _LINKS) == "https://example.test/geraet-b"


def test_extract_promos_rejects_non_integer_float_index():
    assert _resolve_link_index({"link_index": 1.5}, _LINKS) is None


def test_extract_promos_never_trusts_a_free_form_url_from_the_model(monkeypatch):
    """Selbst wenn das Modell zusaetzlich zu link_index ein eigenes "url"-
    oder "link"-Feld mit einer frei erfundenen Adresse zurueckgibt, darf das
    NIE uebernommen werden - der einzige Weg zu einer URL ist ein Index in
    die tatsaechlich von der Seite gelieferte Kandidatenliste."""
    _stub_complete(monkeypatch, [
        {"headline": "Galaxy A57 Aktion", "description": "...",
         "url": "https://boese-phishing-seite.example/galaxy",
         "link": "https://noch-eine-erfundene-url.example"},
    ])
    items = extract_promos("O2", "irgendein Seitentext", "test-model", links=_LINKS)
    assert "url" not in items[0]


def test_extract_promos_works_without_link_candidates(monkeypatch):
    """Kein Kandidat vorhanden (leere Liste/None) -> unveraendertes
    Verhalten wie vor diesem Feature, kein Crash, kein "url"-Feld."""
    _stub_complete(monkeypatch, [{"headline": "Aktion ohne Links", "description": "..."}])
    items = extract_promos("O2", "irgendein Seitentext", "test-model", links=None)
    assert items[0]["headline"] == "Aktion ohne Links"
    assert "url" not in items[0]


def test_extract_promos_only_sends_candidate_list_when_links_present(monkeypatch):
    """Der Prompt soll nur dann von Link-Kandidaten sprechen, wenn welche
    vorliegen - kein aufgeblaehter/irrefuehrender Prompt im Fallback-Fall."""
    calls = []
    _stub_complete(monkeypatch, [{"headline": "X", "description": "..."}], capture_calls=calls)
    extract_promos("O2", "Seitentext", "test-model", links=None)
    assert "LINK-KANDIDATEN" not in calls[0]["user"]
    assert "link_index" not in calls[0]["system"]

    calls.clear()
    _stub_complete(monkeypatch, [{"headline": "X", "description": "..."}], capture_calls=calls)
    extract_promos("O2", "Seitentext", "test-model", links=_LINKS)
    assert "LINK-KANDIDATEN" in calls[0]["user"]
    assert "geraet-a" in calls[0]["user"]
    assert "link_index" in calls[0]["system"]
