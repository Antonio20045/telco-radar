"""Der Anthropic-Anker und der Kostenzaehler (E1-E3, Strategie 27.08.2026).

Der Befund dahinter: vom 15. bis zum 27.08.2026 lief JEDER Lauf ohne
Redaktion. DeepSeeks Guthaben war leer (HTTP 402), und ein Ausweg existierte
strukturell nicht - `llm._dispatch` waehlte sein Backend EINMAL je Prozess
aus der Umgebung, und `pipeline._waehle_anbieter` loeschte den vorhandenen
ANTHROPIC_API_KEY aktiv. Das Secret kam im Workflow an und wurde verworfen.

Dazu der zweite Befund: der Lauf vom 27.08. kostete 1,95 $, und es liess sich
hinterher nicht sagen, wofuer - `usage` wurde nur im Fehlerfall gelesen.
"""
from __future__ import annotations

import pytest

from telco_radar.analyze import llm


ALLE_SCHLUESSEL = ("AWS_BEARER_TOKEN_BEDROCK", "LLM_API_KEY", "ANTHROPIC_API_KEY")


@pytest.fixture(autouse=True)
def _sauber(monkeypatch):
    llm.reset_model_health()
    llm._FALLBACKS.clear()
    llm.kosten_reset()
    llm.budget_setzen(0, {})
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    yield
    llm.reset_model_health()
    llm._FALLBACKS.clear()
    llm.kosten_reset()
    llm.budget_setzen(0, {})


# ============================================================ (a) Routing
def test_dispatch_schickt_ein_claude_modell_an_anthropic(monkeypatch):
    """Der Kern von E2: das MODELL entscheidet, nicht die Umgebung.

    Hier sind Bedrock- UND OpenAI-Schluessel gesetzt, beide haetten nach der
    alten Env-Reihenfolge gewonnen. Genau das war der Zustand eines
    DeepSeek-Laufs mit leerem Guthaben.
    """
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock")
    monkeypatch.setenv("LLM_API_KEY", "deepseek")
    monkeypatch.setenv("LLM_API_BASE", "https://api.deepseek.invalid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic")
    gewaehlt: list[str] = []
    for name in ("_complete_anthropic", "_complete_openai", "_complete_bedrock"):
        monkeypatch.setattr(llm, name,
                            lambda s, u, m, t, r, _n=name: gewaehlt.append(_n))

    llm._dispatch("sys", "user", "claude-sonnet-5", 100, 1)
    assert gewaehlt == ["_complete_anthropic"]


def test_dispatch_laesst_ein_fremdes_modell_beim_gewaehlten_anbieter(monkeypatch):
    """Gegenprobe: der Anker uebernimmt NICHT den ganzen Lauf."""
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "deepseek")
    monkeypatch.setenv("LLM_API_BASE", "https://api.deepseek.invalid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic")
    gewaehlt: list[str] = []
    for name in ("_complete_anthropic", "_complete_openai", "_complete_bedrock"):
        monkeypatch.setattr(llm, name,
                            lambda s, u, m, t, r, _n=name: gewaehlt.append(_n))

    llm._dispatch("sys", "user", "deepseek-v4-flash", 100, 1)
    assert gewaehlt == ["_complete_openai"]


def test_eine_bedrock_id_bleibt_bei_bedrock(monkeypatch):
    """Bedrock-IDs beginnen mit "anthropic.", nicht mit "claude" - sonst
    zoege der Anker die Bedrock-Kette an die falsche API."""
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic")
    gewaehlt: list[str] = []
    for name in ("_complete_anthropic", "_complete_openai", "_complete_bedrock"):
        monkeypatch.setattr(llm, name,
                            lambda s, u, m, t, r, _n=name: gewaehlt.append(_n))

    llm._dispatch("sys", "user", "anthropic.claude-sonnet-4-5-20250929-v1:0",
                  100, 1)
    assert gewaehlt == ["_complete_bedrock"]


def test_ohne_anthropic_schluessel_bleibt_alles_beim_alten(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "deepseek")
    monkeypatch.setenv("LLM_API_BASE", "https://api.deepseek.invalid")
    gewaehlt: list[str] = []
    for name in ("_complete_anthropic", "_complete_openai", "_complete_bedrock"):
        monkeypatch.setattr(llm, name,
                            lambda s, u, m, t, r, _n=name: gewaehlt.append(_n))

    llm._dispatch("sys", "user", "claude-sonnet-5", 100, 1)
    assert gewaehlt == ["_complete_openai"]


# ================================================ (b) Der Schluessel bleibt
def test_deepseek_loescht_den_anthropic_schluessel_nicht_mehr(monkeypatch):
    """Ohne diesen Schluessel in der Umgebung ist der Anker nicht erreichbar -
    llm._dispatch fragt genau danach."""
    from telco_radar.pipeline import _waehle_anbieter

    for name in ALLE_SCHLUESSEL:
        monkeypatch.setenv(name, f"test-{name.lower()}")
    import os

    _waehle_anbieter({"deepseek_api_base": "https://deepseek.invalid",
                      "llm_provider": "deepseek"})
    assert os.environ.get("ANTHROPIC_API_KEY") == "test-anthropic_api_key"
    # Die Schluessel der VERLIERER verschwinden weiterhin.
    assert "AWS_BEARER_TOKEN_BEDROCK" not in os.environ


# ==================================================== (c) Die Ankerketten
def _anker(**settings):
    from telco_radar.pipeline import _registriere_anker

    return _registriere_anker(settings, "flash", "pro", "flash")


def test_die_kette_der_redaktion_endet_im_grossen_claude_modell():
    _anker()
    assert llm._chain_from("pro") == ["pro", "claude-sonnet-5"]


def test_die_kette_des_analysten_endet_im_kleinen_claude_modell():
    _anker()
    assert llm._chain_from("flash") == ["flash", "claude-haiku-4-5-20251001"]


def test_der_anker_ist_abschaltbar():
    assert _anker(llm_anker=False) == {}
    assert llm._chain_from("pro") == ["pro"]


def test_ein_totes_primaermodell_landet_wirklich_beim_anker(monkeypatch):
    """Der Fall vom 27.08.2026: HTTP 402 auf dem Konto toetet BEIDE
    DeepSeek-Modelle zugleich (das Guthaben ist eins). Ohne Anker war die
    Kette danach leer, und `complete()` versuchte das tote Primaermodell
    erneut - "try the preferred one anyway"."""
    from telco_radar.pipeline import _registriere_anker

    _registriere_anker({}, "flash", "pro", "flash")
    versucht: list[str] = []

    def fake(system, user, model, max_tokens, retries):
        versucht.append(model)
        if model in ("pro", "flash"):
            raise llm.LLMModelUnavailable("HTTP 402 Payment Required")
        return f"antwort von {model}"

    monkeypatch.setattr(llm, "_dispatch", fake)

    assert llm.complete("s", "u", "pro") == "antwort von claude-sonnet-5"
    # Zweite Stufe: das tote Modell wird nicht noch einmal gefragt.
    assert llm.complete("s", "u", "pro") == "antwort von claude-sonnet-5"
    assert versucht == ["pro", "claude-sonnet-5", "claude-sonnet-5"]


def test_das_ausweichmodell_desselben_anbieters_wird_gar_nicht_erst_gesetzt():
    """Ein Ausweichmodell auf demselben leeren Konto ist keins - aber die
    Entscheidung gehoert dorthin, wo bekannt ist, dass beide Modelle demselben
    Anbieter gehoeren. `_registriere_anker` sieht nur Namen und hat die
    Zusicherung frueher nachtraeglich UEBERSCHRIEBEN; genau daran ging eine
    echte Praeferenzkette mit verloren (siehe den Bedrock-Test unten)."""
    from telco_radar.pipeline import _registriere_ausweichmodell

    assert _registriere_ausweichmodell({}, "flash", "pro") is False
    assert llm._chain_from("pro") == ["pro"]


def test_ohne_anker_bleibt_das_ausweichmodell_des_anbieters_bestehen():
    """Gegenprobe: ist der Anker abgeschaltet, ist das anbietereigene
    Ausweichmodell das einzige, was es gibt - dann gilt es weiter."""
    from telco_radar.pipeline import _registriere_ausweichmodell

    assert _registriere_ausweichmodell({"llm_anker": False}, "flash", "pro") is True
    assert llm._chain_from("pro") == ["pro", "flash"]


def test_der_anker_haengt_hinter_die_bedrock_kette_statt_sie_zu_ersetzen():
    """`set_fallback(modell, anker)` ERSETZT den Nachfolger, den `modell`
    schon hatte. Bei `bedrock_model_chain` ist dieser Nachfolger aber die
    Antwort auf eine ganz andere Frage als ein leeres Guthaben: ein
    Bedrock-403 ("not available for this account") betrifft genau EIN Modell,
    und die Kette ist die Liste derer, die das Konto stattdessen bedient.
    Ein Anker am Kopf warf sie still weg. Gegen den alten Stand faellt dieser
    Test."""
    from telco_radar.pipeline import _registriere_anker

    kopf = llm.set_model_chain(["anthropic.gross", "anthropic.mittel",
                                "anthropic.klein"])
    _registriere_anker({}, kopf, kopf, kopf)
    assert llm._chain_from(kopf) == ["anthropic.gross", "anthropic.mittel",
                                     "anthropic.klein", "claude-sonnet-5"]


def test_kein_anker_haengt_hinter_einem_anker():
    """Sonst fuehrte der Ausfall des Anbieters ueber Sonnet nach Haiku - die
    Redaktion landete am Ende doch im kleinen Modell."""
    from telco_radar.pipeline import _registriere_anker

    _registriere_anker({}, "pro", "pro", "pro")
    assert llm._chain_from("pro") == ["pro", "claude-sonnet-5"]


# ------------------------------------------- (d) Der Anker JE AUFRUF
def test_der_analyst_endet_bei_haiku_und_die_redaktion_bei_sonnet(monkeypatch):
    """Der Kern von Befund 1: `_FALLBACKS` haengt am MODELLNAMEN, und in jeder
    heutigen Anbieter-Konfiguration ist analyst_model == editor_model. Der
    Analyst - die mit Abstand aufrufstaerkste Stufe - erbte damit den
    REDAKTIONSanker (Sonnet). Gegen den alten Stand faellt dieser Test.
    """
    from telco_radar.pipeline import _registriere_anker

    modell = "deepseek-v4-pro"
    _registriere_anker({}, modell, modell, "deepseek-v4-flash")
    versucht: list[str] = []

    def fake(system, user, model, max_tokens, retries):
        versucht.append(model)
        if model.startswith("deepseek"):
            raise llm.LLMModelUnavailable("HTTP 402 Payment Required")
        return f"antwort von {model}"

    monkeypatch.setattr(llm, "_dispatch", fake)

    # Der Analyst nennt seinen Anker je Aufruf.
    assert llm.complete("s", "u", modell,
                        ausweich="claude-haiku-4-5-20251001") == \
        "antwort von claude-haiku-4-5-20251001"
    # Die Redaktion folgt der registrierten Kette und bleibt gross.
    assert llm.complete("s", "u", modell) == "antwort von claude-sonnet-5"
    assert versucht == [modell, "claude-haiku-4-5-20251001",
                        "claude-sonnet-5"]


def test_der_aufrufanker_wird_nirgends_registriert():
    """Er gilt fuer DIESEN Aufruf. Wuerde er registriert, waere die naechste
    Redaktionsanfrage desselben Modellnamens klein beantwortet."""
    from telco_radar.pipeline import _registriere_anker

    _registriere_anker({}, "pro", "pro", "flash")
    assert llm._kette("pro", "claude-haiku-4-5-20251001") == \
        ["pro", "claude-haiku-4-5-20251001"]
    assert llm._chain_from("pro") == ["pro", "claude-sonnet-5"]


def test_der_aufrufanker_nimmt_die_kette_des_ankers_mit():
    """Ein Anker, der selbst einen Nachfolger hat, behaelt ihn."""
    llm.set_fallback("klein", "noch-kleiner")
    assert llm._kette("pro", "klein") == ["pro", "klein", "noch-kleiner"]


def test_die_analysten_stufe_reicht_ihren_anker_bis_zum_aufruf_durch(monkeypatch):
    """Der Parameter nuetzt nur, wenn `analyze_region` ihn wirklich
    weitergibt - eine Positivliste wie `_items_payload` vergisst so etwas
    lautlos."""
    from datetime import datetime, timezone

    from telco_radar.analyze import agents
    from telco_radar.models import Item

    gesehen: dict = {}

    def fake_complete(system, user, model, max_tokens=4096, ausweich=""):
        gesehen["ausweich"] = ausweich
        return '{"region_summary": "", "highlights": []}'

    monkeypatch.setattr(agents, "complete", fake_complete)
    agents.analyze_region(
        "Europa",
        [Item(title="t", url="https://x/1", source_name="Q",
              published=datetime(2026, 8, 27, tzinfo=timezone.utc))],
        model="pro", ausweich="claude-haiku-4-5-20251001")
    assert gesehen["ausweich"] == "claude-haiku-4-5-20251001"


def test_gleicher_analyst_und_editor_name_bekommt_den_redaktionsanker():
    """Der Kollisionsfall, den `_anker()` oben NICHT abdeckt: in JEDER
    heutigen Provider-Konfiguration ist analyst_model == editor_model
    (deepseek_analyst_model UND deepseek_editor_model stehen beide auf
    "deepseek-v4-pro", ebenso beide openai_*_model). `llm._FALLBACKS` haengt
    am MODELLNAMEN, nicht an der Rolle - fuer denselben Namen registrierte
    die urspruengliche Fassung von `_registriere_anker` erst die Redaktion,
    dann ueberschrieb die Analysten-Zeile denselben Schluessel mit dem
    Mechanik-Anker (claude-haiku): die Redaktion haette im Ernstfall NIE bei
    "einem grossen Modell" geendet, obwohl der Docstring genau das
    verspricht. Gegen den alten Stand faellt dieser Test."""
    from telco_radar.pipeline import _registriere_anker

    gesetzt = _registriere_anker({}, "deepseek-v4-pro", "deepseek-v4-pro",
                                 "deepseek-v4-flash")
    assert llm._chain_from("deepseek-v4-pro") == ["deepseek-v4-pro",
                                                   "claude-sonnet-5"]
    assert gesetzt["deepseek-v4-pro"] == "claude-sonnet-5"
    # Ein WIRKLICH eigener Mechanik-Name behaelt trotzdem seinen eigenen,
    # billigeren Anker - die Kollision betrifft nur den geteilten Namen.
    assert llm._chain_from("deepseek-v4-flash") == ["deepseek-v4-flash",
                                                     "claude-haiku-4-5-20251001"]


# ==================================================== (e) Der Kostenzaehler
def _openai_antwort(prompt=1000, completion=2000, inhalt="ok"):
    return {"choices": [{"message": {"content": inhalt}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}


def _als_antwort(monkeypatch, daten):
    """Ersetzt den HTTP-Aufruf, laesst aber `parse` - und damit den Zaehler -
    wirklich laufen."""
    monkeypatch.setattr(llm, "_post_with_retries",
                        lambda url, payload, headers, retries, parse: parse(daten))


def test_kosten_summieren_usage_je_modell(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_API_BASE", "https://example.invalid/v1")
    llm.budget_setzen(0, {"deepseek-v4-flash": {"ein": 0.14, "aus": 0.28}})
    _als_antwort(monkeypatch, _openai_antwort(1000, 2000))

    llm._complete_openai("s", "u", "deepseek-v4-flash", 100, 1)
    llm._complete_openai("s", "u", "deepseek-v4-flash", 100, 1)

    stand = llm.kosten_stand()
    eintrag = stand["modelle"]["deepseek-v4-flash"]
    assert eintrag["aufrufe"] == 2
    assert eintrag["prompt_tokens"] == 2000
    assert eintrag["completion_tokens"] == 4000
    # 2000 * 0,14/1M + 4000 * 0,28/1M
    assert eintrag["usd"] == pytest.approx(0.00140)
    assert stand["summe_usd"] == pytest.approx(0.00140)


def test_die_denkspur_zaehlt_auch_ohne_verwertbare_antwort(monkeypatch):
    """Eine Antwort, die nur aus Denkspur besteht, ist bezahlt (Laeufe
    #83-85, #97). Der teuerste Fehlerfall darf nicht kostenlos aussehen."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_API_BASE", "https://example.invalid/v1")
    daten = _openai_antwort(500, 9000, inhalt="")
    daten["choices"][0]["message"]["reasoning_content"] = "x" * 500
    daten["choices"][0]["finish_reason"] = "length"
    _als_antwort(monkeypatch, daten)

    with pytest.raises(ValueError):
        llm._complete_openai("s", "u", "deepseek-v4-pro", 100, 1)
    assert llm.kosten_stand()["modelle"]["deepseek-v4-pro"]["completion_tokens"] == 9000


def test_anthropic_usage_heisst_anders_und_zaehlt_trotzdem(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    llm.budget_setzen(0, {"claude-sonnet-5": {"ein": 2.0, "aus": 10.0}})
    _als_antwort(monkeypatch, {
        "content": [{"type": "text", "text": "ok"}],
        "usage": {"input_tokens": 1_000_000, "output_tokens": 100_000}})

    llm._complete_anthropic("s", "u", "claude-sonnet-5", 100, 1)

    eintrag = llm.kosten_stand()["modelle"]["claude-sonnet-5"]
    assert eintrag["prompt_tokens"] == 1_000_000
    assert eintrag["usd"] == pytest.approx(3.0)


def test_ein_modell_ohne_preiszeile_wird_gezaehlt_aber_nicht_geraten(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_API_BASE", "https://example.invalid/v1")
    llm.budget_setzen(1.0, {})
    _als_antwort(monkeypatch, _openai_antwort(10, 20))

    llm._complete_openai("s", "u", "unbekanntes-modell", 100, 1)

    stand = llm.kosten_stand()
    assert stand["modelle"]["unbekanntes-modell"]["usd"] is None
    assert stand["ohne_preis"] == ["unbekanntes-modell"]
    assert stand["summe_usd"] == 0.0
    assert not stand["budget_ueberschritten"]


def test_ohne_usage_wird_nichts_gezaehlt(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_API_BASE", "https://example.invalid/v1")
    _als_antwort(monkeypatch, {"choices": [{"message": {"content": "ok"},
                                            "finish_reason": "stop"}]})

    llm._complete_openai("s", "u", "m", 100, 1)
    assert llm.kosten_stand()["modelle"] == {}


def test_die_warnschwelle_schlaegt_erst_bei_erreichung_an(monkeypatch):
    """Die Schwelle warnt nur - was sie NICHT tut, steht in
    tests/test_analyst_budget.py."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_API_BASE", "https://example.invalid/v1")
    llm.budget_setzen(1.0, {"m": {"ein": 0.0, "aus": 1.0}})
    _als_antwort(monkeypatch, _openai_antwort(0, 400_000))

    llm._complete_openai("s", "u", "m", 100, 1)          # 0,40 $
    assert not llm.budget_ueberschritten()
    llm._complete_openai("s", "u", "m", 100, 1)          # 0,80 $
    assert not llm.budget_ueberschritten()
    llm._complete_openai("s", "u", "m", 100, 1)          # 1,20 $
    assert llm.budget_ueberschritten()
    assert llm.kosten_stand()["budget_ueberschritten"] is True


def test_ohne_schwelle_wird_nie_gewarnt(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_API_BASE", "https://example.invalid/v1")
    llm.budget_setzen(0, {"m": {"ein": 1000.0, "aus": 1000.0}})
    _als_antwort(monkeypatch, _openai_antwort(1_000_000, 1_000_000))

    llm._complete_openai("s", "u", "m", 100, 1)
    assert llm.kosten_stand()["summe_usd"] == pytest.approx(2000.0)
    assert not llm.budget_ueberschritten()
