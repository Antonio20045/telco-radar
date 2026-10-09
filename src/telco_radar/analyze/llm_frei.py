"""Anbieter ``frei``: kostenlose Modelle mehrerer Anbieter als eine Kette.

Jedes Glied heißt ``<anbieter>:<modell>`` und spricht die OpenAI-kompatible
Schnittstelle seines Anbieters mit eigenem Schlüssel. Fehlt der Schlüssel, ist
das Glied für den Lauf tot, ohne Anfrage; ``llm.complete`` geht dann zum
nächsten. Die Reihenfolge der Ketten ist die Reihenfolge in
``config/settings.yaml`` (``frei_endpunkte``), getrennt nach Stufe:
``mechanik`` (viele kurze Aufrufe, auch der Analyst) und ``redaktion`` (wenige
lange Aufrufe, danach die Mechanik-Kette als Reserve).

Herkunft: Antonios Recherche „KI-Auswertung kostenlos“ vom 09.10.2026
(``/mnt/project-files/pitches/4-meldungen-kostenlos-design.md``).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

MECHANIK = "mechanik"
REDAKTION = "redaktion"
STUFEN = (MECHANIK, REDAKTION)


@dataclass(frozen=True)
class Endpunkt:
    """Ein Modell bei einem Anbieter, wie es in ``frei_endpunkte`` steht."""

    name: str
    base_url: str
    key_env: str
    modell: str
    stufen: tuple[str, ...]
    rpm: float | None = None
    max_output: int | None = None
    system_im_user: bool = False
    params: dict = field(default_factory=dict)

    def schluessel(self) -> str | None:
        """Der Schlüssel, ``""`` für anonym, ``None`` wenn er fehlt."""
        if not self.key_env:
            return ""
        wert = (os.environ.get(self.key_env) or "").strip().strip("'\"").strip()
        return wert if wert else None

    def url(self) -> str:
        """Chat-Adresse; ``{VARIABLE}`` in der Basis kommt aus der Umgebung."""
        basis = self.base_url.format_map(os.environ)
        return basis.rstrip("/") + "/chat/completions"


_ENDPUNKTE: dict[str, Endpunkt] = {}
_TAKT: dict[str, float] = {}
_SPERRE = threading.Lock()


def _endpunkt(anbieter: dict, eintrag: dict) -> Endpunkt:
    name_anbieter = str(eintrag["anbieter"])
    a = anbieter[name_anbieter]
    rpm = eintrag.get("rpm", a.get("rpm"))
    max_out = eintrag.get("max_output")
    return Endpunkt(
        name=f"{name_anbieter}:{eintrag['modell']}",
        base_url=str(a["base_url"]),
        key_env=str(a.get("key_env") or ""),
        modell=str(eintrag["modell"]),
        stufen=tuple(str(s) for s in eintrag.get("stufen") or (MECHANIK,)),
        rpm=float(rpm) if rpm else None,
        max_output=int(max_out) if max_out else None,
        system_im_user=bool(eintrag.get("system_im_user", False)),
        params=dict(eintrag.get("params") or {}),
    )


def registrieren(anbieter: dict | None, endpunkte: list[dict] | None) -> list[str]:
    """Liest die Konfiguration ein (ersetzt die vorige); gibt die Namen zurück."""
    _ENDPUNKTE.clear()
    _TAKT.clear()
    for eintrag in endpunkte or []:
        if eintrag.get("enabled", True) is False:
            continue
        ep = _endpunkt(anbieter or {}, eintrag)
        _ENDPUNKTE[ep.name] = ep
    return list(_ENDPUNKTE)


def endpunkt(name: str) -> Endpunkt | None:
    """Das Glied dieses Namens, ``None`` für ein Modell anderer Anbieter."""
    return _ENDPUNKTE.get(name)


def registriert() -> bool:
    """Ob der Anbieter ``frei`` für diesen Lauf eingerichtet ist."""
    return bool(_ENDPUNKTE)


def verfuegbar() -> bool:
    """Mindestens ein Glied mit eigenem Schlüssel; anonyme zählen nicht."""
    return any(ep.key_env and ep.schluessel() for ep in _ENDPUNKTE.values())


def ketten() -> dict[str, list[str]]:
    """Je Stufe die Glieder; die Redaktion fällt zuletzt auf die Mechanik.

    Ein Glied hat in ``llm`` genau EINEN Nachfolger. Die Redaktionskette ist
    deshalb ihre eigenen Glieder und danach die ganze Mechanikkette; ein Glied
    beider Stufen steht an seinem Platz in der Mechanik.
    """
    mechanik = [n for n, ep in _ENDPUNKTE.items() if MECHANIK in ep.stufen]
    eigene = [
        n
        for n, ep in _ENDPUNKTE.items()
        if REDAKTION in ep.stufen and n not in mechanik
    ]
    return {MECHANIK: mechanik, REDAKTION: eigene + mechanik}


def einrichten(settings: dict, kette_setzen, fallback: str) -> tuple[str, str]:
    """Liest ``frei_*`` aus den Settings, setzt beide Ketten; (Analyst, Redaktion).

    ``kette_setzen`` ist ``llm.set_model_chain`` (``llm`` importiert dieses Modul).
    Der Analyst läuft auf der Mechanik-Kette: er macht die meisten Aufrufe.
    """
    registrieren(settings.get("frei_anbieter"), settings.get("frei_endpunkte"))
    if not verfuegbar():
        log.warning("llm_provider=frei, aber kein Schluessel gesetzt - Notfall-Digest")
    k = ketten()
    mechanik = kette_setzen(k[MECHANIK]) or fallback
    return mechanik, kette_setzen(k[REDAKTION]) or mechanik


def preise() -> dict[str, dict[str, float]]:
    """Alle Glieder kosten 0 $, damit der Kostenblock nicht „ohne Preis“ meldet."""
    return {name: {"ein": 0.0, "aus": 0.0} for name in _ENDPUNKTE}


def drosseln(ep: Endpunkt) -> None:
    """Hält ``rpm`` ein: Anfragen desselben Glieds starten im Abstand 60/rpm s."""
    if not ep.rpm:
        return
    abstand = 60.0 / ep.rpm
    with _SPERRE:
        jetzt = time.monotonic()
        start = max(jetzt, _TAKT.get(ep.name, 0.0))
        _TAKT[ep.name] = start + abstand
    if start > jetzt:
        time.sleep(start - jetzt)


def nutzlast(ep: Endpunkt, system: str, user: str, max_tokens: int) -> dict:
    """Die Chat-Anfrage für dieses Glied."""
    if ep.system_im_user:
        nachrichten = [{"role": "user", "content": f"{system}\n\n{user}"}]
    else:
        nachrichten = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    grenze = min(max_tokens, ep.max_output) if ep.max_output else max_tokens
    return {
        "model": ep.modell,
        "messages": nachrichten,
        "max_tokens": grenze,
        **ep.params,
    }
