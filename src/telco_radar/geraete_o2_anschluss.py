"""o2: offene Anschlusspreise abgeleiteter Bündel nachmessen, nach der Tarifwelt-Stufe.

DER BEFUND (21.11.2026)
-----------------------
Die o2-Antwort nennt den berechneten Anschlusspreis nur für den gewählten Tarif;
abgeleitete Bündel (``o2.HERLEITUNG_TARIFSUMME``) mit einem Listenpreis über 0 € in
der Fußnote tragen ihn als Lücke (``o2_anschluss``), am 21.11. 568 von 2233. Die
Gegenprobe fand 65 davon, deren Seite mit gewähltem Tarif den Betrag zeigt. Die
Seite jedes Bündels (``quelle_url`` mit Speicher, Tarif und Raten,
``o2_referenz.belegadresse``) nennt ihn in ihrer Preiszusammenfassung. Lokal am
21.11.: 568 Abrufe, alle 568 bestätigt, 2,1 s je Abruf; in der Nacht 3,9 s, zusammen
rund 2 200 s.

DIE ZEIT
--------
Die Stufe läuft NACH der Tarifwelt-Stufe (die die Restzeit des Jobs braucht, seit PR 185
rund 813 s) und nimmt nur, was danach bleibt: dieselbe Regel wie
``geraete_tarifwelt.stufen_frist`` (Jobfrist minus Vorlauf minus vergangene Zeit minus
``RESERVE_NACH_NACHMESSUNG_SEKUNDEN``). Damit der Rückstand trotzdem schrumpft, gilt
ein gemessener Anschlusspreis ``ANSCHLUSS_GUELTIG_TAGE`` Tage (der Betrag ändert sich
selten; Zeile und Historie nennen sein Messdatum, ``Buendel.anschluss_gemessen_am``),
nur zum selben Angebot (``ANGEBOT``). Gemessen wird zuerst die Lücke, dann der
Fußnotenwert ohne Messung, dann die älteste Messung (``_rang``).

Bestätigt die Seite Raten, Tarif, Gerätrate, Anzahlung und Tarifbetrag des Bündels,
gilt ihr Anschlusspreis und das Bündel ist gemessen (ohne ``herleitung``); sonst
bleibt es, wie es war.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import date

from . import geraete_tarifwelt
from .collect.geraete import o2
from .collect.geraete.basis import GeraeteAbrufFehler, _gleich, antwort_text
from .collect.http import HttpFehler, SchutzAntwort
from .geraete_abruf import hole_fuer_anbieter
from .tco_model import Buendel

log = logging.getLogger(__name__)

ANBIETER = "o2"
ANSCHLUSS_GUELTIG_TAGE = 7
RESERVE_NACH_NACHMESSUNG_SEKUNDEN = geraete_tarifwelt.RESERVE_NACH_STUFE_SEKUNDEN
"""Was nach dieser Stufe im Job noch läuft: dieselbe Reserve wie nach der Tarifwelt
(Prüfstelle, Speichern und alle Schritte nach „Run geraete stage“)."""


def frist(vergangen_sekunden: float) -> float:
    """Restzeit des Jobs für die Nachmessung, nie unter null (Regel 8)."""
    rest = (
        geraete_tarifwelt.JOB_FRIST_SEKUNDEN
        - geraete_tarifwelt.VORLAUF_SEKUNDEN
        - vergangen_sekunden
        - RESERVE_NACH_NACHMESSUNG_SEKUNDEN
    )
    return max(0.0, rest)


def _offen(b: Buendel) -> bool:
    return (
        b.anbieter == ANBIETER
        and b.herleitung == o2.HERLEITUNG_TARIFSUMME
        and bool(b.quelle_url)
    )


def _tage(von: str, bis: str) -> int | None:
    try:
        return (date.fromisoformat(bis) - date.fromisoformat(von)).days
    except ValueError:
        return None


ANGEBOT = (
    "laufzeit_monate",
    "geraet_monatsrate",
    "geraet_zuzahlung",
    "tarif_monatlich",
)
"""Das Angebot, für das ein Anschlusspreis gemessen ist. Es steht in derselben
Bestandszeile wie Betrag und Datum: gemessen und übernommen wird nur zum selben
Angebot, also trägt die Zeile bis zur nächsten Messung genau das gemessene."""


def _gleiches_angebot(b: Buendel, alt: dict) -> bool:
    for feld in ANGEBOT:
        heute_wert, damals = getattr(b, feld), alt.get(feld)
        if heute_wert is None or damals is None or not _gleich(heute_wert, damals):
            return False
    return True


def uebernimm(b: Buendel, alt: dict | None, heute: str) -> Buendel:
    """Ein offenes Bündel mit dem gemessenen Anschlusspreis seines Bestandseintrags,
    solange die Messung höchstens ``ANSCHLUSS_GUELTIG_TAGE`` alt ist und das Angebot
    (``ANGEBOT``) dasselbe; sonst bleibt die Lücke und wird nachgemessen."""
    if not _offen(b) or b.anschlusspreis is not None or not alt:
        return b
    am, betrag = str(alt.get("anschluss_gemessen_am") or ""), alt.get("anschlusspreis")
    alter = _tage(am, heute) if am else None
    if betrag is None or alter is None or not 0 <= alter <= ANSCHLUSS_GUELTIG_TAGE:
        return b
    if not _gleiches_angebot(b, alt):
        return b
    return replace(b, anschlusspreis=betrag, anschluss_gemessen_am=am)


def _rang(b: Buendel) -> tuple[int, str]:
    """Lücke zuerst, dann Fußnotenwerte ohne Messung, dann die ältesten Messungen."""
    if b.anschlusspreis is None:
        return (0, "")
    if not b.anschluss_gemessen_am:
        return (1, "")
    return (2, b.anschluss_gemessen_am)


def reihenfolge(saetze: list[Buendel]) -> list[int]:
    """Stellen der abgeleiteten Bündel in Nachmess-Reihenfolge (``_rang``)."""
    stellen = [i for i, b in enumerate(saetze) if _offen(b)]
    return sorted(stellen, key=lambda i: _rang(saetze[i]))


def bestaetigt(b: Buendel, g: dict | None) -> bool:
    """Nennt die Messung der Seite dasselbe Bündel (Raten, Tarif, Beträge)?"""
    if g is None or g.get("anschluss") is None:
        return False
    slug = b.tarif_id.split(":", 1)[-1]
    return (
        g.get("laufzeit") == b.laufzeit_monate
        and g.get("slug") == slug
        and _gleich(g.get("rate"), b.geraet_monatsrate)
        and _gleich(g.get("anzahlung"), b.geraet_zuzahlung)
        and _gleich(g.get("tarif_rate"), b.tarif_monatlich)
    )


def nachmessen(
    saetze: list[Buendel],
    lies: Callable[[str], str],
    heute: str,
    weiter: Callable[[], bool],
    zaehler: dict,
) -> list[Buendel]:
    """Je offenem Bündel (``reihenfolge``) seine Seite, solange ``weiter()``."""
    out = list(saetze)
    for i in reihenfolge(out):
        if not weiter():
            zaehler["frist"] = zaehler.get("frist", 0) + 1
            continue
        b = out[i]
        try:
            g = o2._gemessen(o2.lies_konfiguration(lies(b.quelle_url)))
        except SchutzAntwort as exc:
            log.warning("o2-Anschluss: Schutzantwort, Nachmessung endet (%s)", exc)
            zaehler["schutz"] = 1
            break
        except (GeraeteAbrufFehler, HttpFehler, OSError) as exc:
            log.info("o2-Anschluss: %s nicht lesbar (%s)", b.quelle_url, exc)
            g = None
        if g is None:
            name = "nicht_gelesen"
        elif bestaetigt(b, g):
            out[i] = replace(
                b,
                anschlusspreis=g["anschluss"],
                anschluss_gemessen_am=heute,
                herleitung="",
            )
            name = "gemessen"
        else:
            name = "widerspricht"
        zaehler[name] = zaehler.get(name, 0) + 1
    return out


def stufe(
    saetze: list[Buendel],
    tco,
    quellen,
    hole: Callable,
    uhr: Callable,
    heute: str,
    beginn: float | None = None,
) -> tuple[list[Buendel], dict]:
    """Übernahme gültiger Messungen aus dem Bestand ``tco``, dann Nachmessung gegen
    die Restzeit des Jobs (ohne ``beginn`` keine Nachmessung). Wirft nie wegen eines
    Abrufs: ein unlesbarer bleibt offen; ein anderer Fehler wird protokolliert und
    gibt die Bündel unverändert zurück."""
    zaehler: dict = {}
    anbieter = quellen.nach_name(ANBIETER)
    if anbieter is None or not anbieter.crawlbar:
        return saetze, {"status": "aus"}
    out = [uebernimm(b, tco.nach_id(b.id), heute) for b in saetze]
    zaehler["uebernommen"] = sum(
        1 for a, b in zip(saetze, out, strict=True) if a is not b
    )
    if beginn is None:
        return out, {"status": "ohne_frist", **zaehler}
    try:
        lies = hole_fuer_anbieter(hole, anbieter, uhr)

        def weiter() -> bool:
            return frist(time.monotonic() - beginn) > 0

        out = nachmessen(out, lambda u: antwort_text(lies(u)), heute, weiter, zaehler)
    except (OSError, ValueError, TypeError, HttpFehler) as exc:
        log.warning("o2-Anschluss: Nachmessung gescheitert (%s)", exc)
        return out, {"status": "fehler", "grund": str(exc), **zaehler}
    log.info("o2-Anschluss: %s", zaehler)
    return out, {"status": "ok", **zaehler}


def speichere(bilanz, tco, quellen, hole, uhr, heute: str, beginn=None) -> int:
    """Die Bündel der Tagesbilanz (``Buendelbilanz``) nach ``stufe`` in den Bestand;
    gibt die Zahl der neu aufgenommenen zurück. Läuft nach der Tarifwelt-Stufe
    (``geraete_pipeline.run_geraete_stage``)."""
    if bilanz is None or not bilanz.buendel:
        return 0
    bilanz.buendel, _ = stufe(bilanz.buendel, tco, quellen, hole, uhr, heute, beginn)
    neu, _ = tco.upsert_buendel(bilanz.buendel, heute)
    return neu
