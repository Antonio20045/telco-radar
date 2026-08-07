"""Eine leere Antwort mit HTTP 200 muss sich selbst erklaeren.

Der Ausfall aus Lauf #84: der Lauf lief gegen api.deepseek.com mit
deepseek-v4-pro, und GENAU die Stufen mit kleinem Token-Budget lieferten
nichts - Promo-Extraktion (1800), Kategorie-Sweep (2000), Promo-Bewertung
(2200), Promo-Redaktion (3200). Analyst (8000) und Redaktion (32000) liefen
sauber durch. 15 von 19 gelesenen Promo-Seiten fielen dadurch aus.

Die Ursache: `chat_template_kwargs={"thinking": False}` schaltet die Denkspur
nur auf NVIDIAs NIM-Endpunkt ab. Auf DeepSeeks eigener API wird der Parameter
ignoriert, das Modell denkt trotzdem, und bei zu knappem Budget ist es fertig,
bevor die eigentliche Antwort anfaengt: `content` kommt leer zurueck.

Sichtbar war davon nur ein "JSONDecodeError: Expecting value: line 1 column 1
(char 0)" auf einem leeren String - eine Meldung, aus der niemand den Grund
ableiten kann. Genau das pruefen die Tests hier.
"""
from __future__ import annotations

import json

import httpx
import pytest

from telco_radar.analyze import llm


@pytest.fixture(autouse=True)
def _umgebung(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://api.deepseek.com")
    yield


def _antwort(monkeypatch, message: dict, finish_reason: str = "length"):
    """Ersetzt den HTTP-Aufruf durch eine feste Provider-Antwort."""
    nutzlast = {"choices": [{"message": message, "finish_reason": finish_reason}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(
            200, content=_dumps(nutzlast),
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)


def _dumps(obj) -> bytes:
    return json.dumps(obj).encode("utf-8")


def test_leere_antwort_mit_denkspur_nennt_das_token_budget(monkeypatch):
    _antwort(monkeypatch, {"content": "",
                           "reasoning_content": "Ich ueberlege lange. " * 40})
    with pytest.raises(ValueError) as fehler:
        llm._complete_openai("system", "user", "deepseek-v4-pro",
                             max_tokens=1800, retries=2)
    text = str(fehler.value)
    # Die Meldung muss die drei Dinge nennen, die man zum Handeln braucht:
    # dass nur gedacht wurde, wie knapp das Budget war, und was zu tun ist.
    assert "Denkspur" in text
    assert "1800" in text
    assert "erhoehen" in text


def test_leere_antwort_ohne_denkspur_meldet_sich_trotzdem(monkeypatch):
    _antwort(monkeypatch, {"content": ""}, finish_reason="stop")
    with pytest.raises(ValueError) as fehler:
        llm._complete_openai("system", "user", "deepseek-v4-pro",
                             max_tokens=8000, retries=2)
    assert "leere Antwort" in str(fehler.value)


def test_leere_antwort_wird_NICHT_wiederholt(monkeypatch):
    """Ein zu kleines Budget wird beim vierten Versuch nicht groesser. Der
    Retry-Wrapper faengt ValueError bewusst nicht - jede Wiederholung waere
    nur teurer und wuerde am Ende dieselbe leere Antwort liefern."""
    versuche = []

    nutzlast = {"choices": [{"message": {"content": "",
                                         "reasoning_content": "denk denk"},
                             "finish_reason": "length"}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        versuche.append(1)
        return httpx.Response(200, content=_dumps(nutzlast),
                              headers={"content-type": "application/json"},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(ValueError):
        llm._complete_openai("system", "user", "deepseek-v4-pro",
                             max_tokens=1800, retries=5)
    assert len(versuche) == 1


def test_normale_antwort_kommt_unveraendert_durch(monkeypatch):
    _antwort(monkeypatch, {"content": '[{"headline": "Aktion"}]',
                           "reasoning_content": "kurz gedacht"},
             finish_reason="stop")
    assert llm._complete_openai("system", "user", "deepseek-v4-pro",
                               max_tokens=8000, retries=2) == '[{"headline": "Aktion"}]'


def test_die_stufen_mit_kleinem_budget_sind_hochgezogen():
    """Die eigentliche Behebung von #84 - als Zahl festgehalten, damit sie
    niemand versehentlich zurueckdreht. 8000 ist das Budget, mit dem der
    Analyst in denselben Laeufen zuverlaessig durchlief."""
    from telco_radar.analyze import category_sweep, promo_analyst, promo_ranker
    import inspect

    assert inspect.signature(
        promo_analyst.extract_promos).parameters["max_tokens"].default >= 8000
    assert inspect.signature(
        promo_ranker.judge_offers).parameters["max_tokens"].default >= 8000
    quelle = inspect.getsource(category_sweep)
    assert "max_tokens=8000" in quelle
