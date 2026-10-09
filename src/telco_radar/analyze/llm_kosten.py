"""Verbrauch und Kosten eines LLM-Laufs, je Modell in Token und USD.

Aus ``llm.py`` ausgelagert; ``llm`` reicht die öffentlichen Namen weiter.
"""

from __future__ import annotations

import logging

from . import llm_frei
from .llm_sitzung import LlmSitzung

log = logging.getLogger(__name__)


def _s() -> LlmSitzung:
    return LlmSitzung.aktive()


def _zaehle_usage(model: str, data: dict) -> None:
    """Den Verbrauch EINER Antwort mitschreiben.

    Gezaehlt wird, bevor der Aufrufer den Inhalt beurteilt: eine Antwort, die
    nur aus Denkspur besteht (Laeufe #83-85, #97), ist bezahlt und muss im
    Zaehler stehen - sonst waere ausgerechnet der teuerste Fehlerfall
    kostenlos.

    DeepSeek weist die Denkspur nicht getrennt aus, sie steckt in
    `completion_tokens` und wird als Ausgabe abgerechnet. Genau das ist der
    Posten, den dieser Zaehler sichtbar machen soll.
    """
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return
    ein = usage.get("prompt_tokens")
    if ein is None:
        ein = usage.get("input_tokens") or 0
    aus = usage.get("completion_tokens")
    if aus is None:
        aus = usage.get("output_tokens") or 0
    ein = (
        int(ein)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
    )
    eintrag = _s().verbrauch.setdefault(
        model, {"aufrufe": 0, "prompt_tokens": 0, "completion_tokens": 0}
    )
    eintrag["aufrufe"] += 1
    eintrag["prompt_tokens"] += ein
    eintrag["completion_tokens"] += int(aus)


def _usd(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """USD-Schaetzung, oder None fuer ein Modell ohne Preiszeile."""
    preis = _s().preise.get(model)
    if not preis:
        return None
    return (
        prompt_tokens * preis.get("ein", 0.0)
        + completion_tokens * preis.get("aus", 0.0)
    ) / 1_000_000


def _summe_usd() -> float:
    return sum(
        _usd(name, v["prompt_tokens"], v["completion_tokens"]) or 0.0
        for name, v in _s().verbrauch.items()
    )


def kosten_reset() -> None:
    """Zaehler leeren. Ein Lauf zaehlt seinen eigenen Verbrauch."""
    _s().verbrauch.clear()


def budget_setzen(usd_limit: float | None, preistabelle: dict | None = None) -> None:
    """Warnschwelle und Preistabelle setzen. 0/leer heisst: keine Schwelle.

    Warnschwelle, nicht Not-Aus: der Zaehler greift NIE in den Lauf ein
    (Antonios Entscheidung vom 27.08.2026). Siehe budget_ueberschritten().
    """
    sitzung = _s()
    try:
        limit = float(usd_limit or 0)
    except (TypeError, ValueError):
        limit = 0.0
    sitzung.budget_usd = limit if limit > 0 else None
    sitzung.preise.clear()
    tabelle = {**(preistabelle or {}), **llm_frei.preise()}
    for name, preis in tabelle.items():
        if not isinstance(preis, dict):
            continue
        try:
            sitzung.preise[str(name)] = {
                "ein": float(preis.get("ein", preis.get("input", 0)) or 0),
                "aus": float(preis.get("aus", preis.get("output", 0)) or 0),
            }
        except (TypeError, ValueError):
            log.warning(
                "Unbrauchbare Preiszeile fuer %s - Modell bleibt unbeziffert", name
            )


def budget_ueberschritten() -> bool:
    """True, sobald die BEZIFFERBAREN Kosten die Warnschwelle erreichen.

    Es passiert dann NICHTS ausser einer Zeile im Protokoll und einer auf
    transparenz.html. Die erste Fassung dieses Zaehlers stoppte weitere
    Analysten-Stapel; Antonio hat das am 27.08.2026 verworfen, und die
    Begruendung steht in den degenerierten Laeufen vom 15.-27.08.: ein Lauf,
    der auf halber Strecke aufhoert zu lesen, ist von einer duennen
    Nachrichtenwoche nicht zu unterscheiden. Die harte Grenze ist das
    Guthaben des Anbieters; stirbt es, faengt der Anker die sichtbaren
    Stufen.

    Ein Modell ohne Preiszeile geht mit 0 $ ein - geraten wird nichts. Die
    Luecke steht als `ohne_preis` im Kostenblock und faellt am Token-Ist auf.
    """
    budget = _s().budget_usd
    return budget is not None and budget > 0 and _summe_usd() >= budget


def kosten_stand() -> dict:
    """Was der Lauf bisher verbraucht hat - je Modell, in Token und USD."""
    modelle: dict[str, dict] = {}
    ohne_preis: list[str] = []
    for name, v in sorted(_s().verbrauch.items()):
        usd = _usd(name, v["prompt_tokens"], v["completion_tokens"])
        modelle[name] = {**v, "usd": None if usd is None else round(usd, 4)}
        if usd is None:
            ohne_preis.append(name)
    return {
        "modelle": modelle,
        "summe_usd": round(_summe_usd(), 4),
        "ohne_preis": ohne_preis,
        "budget_usd": _s().budget_usd,
        "budget_ueberschritten": budget_ueberschritten(),
    }
