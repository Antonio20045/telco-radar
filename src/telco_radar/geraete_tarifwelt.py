"""Tarifwelt (Saturn/MediaMarkt) im Tageslauf des Geraeteradars.

Der Leser selbst steht in `collect/geraete/tarifwelt_lauf.py`; dieses Modul
haengt ihn an die Stelle, an der die uebrigen Buendel entstehen
(`geraete_pipeline.run_geraete_stage`): es liefert fertige `Buendel` plus die
Stammdaten ihrer Tarife (`TcoDB.haendler_tarife`, `tarifwelt_bestand`; Grundlage
der Band-Zuordnung im Bericht). Aktivschalten ist nur der Wert `aktiv: true` der
Quelle in `config/geraete_quellen.yaml` (Methode `mediamarkt_tarifwelt`); ist sie
inaktiv oder fehlt sie, passiert nichts - kein Abruf, keine Datei.

Wirft nie ausser dem einen Fall, der den Lauf beenden soll: eine Schutzantwort
beendet NUR diese Stufe (kein Wiederholen, kein weiterer Abruf), schon fertig
gelesene Modelle bleiben, der Abbruch steht in der Bilanz. Die Leiter der
Baender kommt aus dem Tarifbestand (Vodafone "mit Smartphone", wie im
Bericht); fehlt sie, gibt es keine Baender und keinen Abruf.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from . import tarifwelt_bestand, tarifwelt_lieferbar
from .collect.geraete import tarifwelt_lauf
from .collect.geraete.basis import GeraeteAbrufFehler
from .geraete_abruf import hole_fuer_anbieter
from .report.geraete_tco_band import tarifleiter
from .tco_model import Buendel

log = logging.getLogger(__name__)

METHODE = tarifwelt_bestand.METHODE

JOB_FRIST_SEKUNDEN = 70 * 60.0
"""`timeout-minutes: 70` von `.github/workflows/geraete.yml` (Test: gleicher Wert)."""
RESERVE_NACH_STUFE_SEKUNDEN = 600.0
"""Was nach der Stufe noch laeuft (Speichern, Seite bauen, Commit) und was vor dem
Lauf an Einrichtung (checkout, pip) schon verbraucht ist: nie in die Stufe."""
MAX_STUFE_SEKUNDEN = 1500.0
"""Obergrenze der Stufe, auch wenn die Restzeit des Jobs mehr hergibt."""


def stufen_frist(vergangen_sekunden: float) -> float:
    """Das Zeitbudget der Stufe: die Restzeit des Jobs (`JOB_FRIST_SEKUNDEN` minus
    schon vergangene Zeit minus `RESERVE_NACH_STUFE_SEKUNDEN`), hoechstens
    `MAX_STUFE_SEKUNDEN`, nie unter null."""
    rest = JOB_FRIST_SEKUNDEN - vergangen_sekunden - RESERVE_NACH_STUFE_SEKUNDEN
    return max(0.0, min(MAX_STUFE_SEKUNDEN, rest))


@dataclass
class Ergebnis:
    """Was die Stufe liefert; `status`: "aus", "ok", "keine_leiter", "abgebrochen",
    "frist" (Zeitbudget aufgebraucht, `ungelesen` nennt die Modelle, die nicht
    mehr drankamen)."""

    status: str = "aus"
    buendel: list[Buendel] = field(default_factory=list)
    tarife: dict[str, dict] = field(default_factory=dict)
    luecken: list[tuple[str, str]] = field(default_factory=list)
    nicht_lieferbar: list[tuple[str, int]] = field(default_factory=list)
    abrufe: int = 0
    modelle: int = 0
    ungelesen: list[str] = field(default_factory=list)
    grund: str = ""

    def als_dict(self) -> dict:
        """Die Zahlen der Stufe fuer die Tagesbilanz."""
        return {
            "status": self.status,
            "buendel": len(self.buendel),
            "tarife": len(self.tarife),
            "luecken": len(self.luecken),
            "nicht_lieferbar": len(self.nicht_lieferbar),
            "abrufe": self.abrufe,
            "modelle": self.modelle,
            "ungelesen": list(self.ungelesen),
            "grund": self.grund,
        }


def modelle_der_stufe() -> list[str]:
    """Die Modelle, die die Stufe liest: ALLE Katalogmodelle mit Tarifwelt-Seite
    (`tarifwelt_modelle.MODELL_SLUGS`), Pflichtmodelle zuerst. Frueher gefiltert
    auf die Pflichtmodelle des Waechters - dann blieben die 20 weiteren,
    sitemap-bestaetigten Modelle (Baupaket P6) fuer immer ungelesen."""
    return list(tarifwelt_lauf.MODELL_SLUGS)


def quelle_aktiv(quellen) -> bool:
    """Ist die Tarifwelt-Quelle eingetragen UND `aktiv`? Die einzige Stelle."""
    return any(
        a.methode == METHODE and a.aktiv for a in getattr(quellen, "anbieter", [])
    )


def lauf(
    quellen,
    tarife_je_id: dict,
    hole: Callable,
    abgerufen_am: str,
    warte: Callable[[float], None] | None = None,
    frist_sekunden: float | None = None,
    monoton: Callable[[], float] = time.monotonic,
) -> Ergebnis:
    """ALLE Modelle der Tarifwelt (`MODELL_SLUGS`, Pflichtmodelle zuerst), wenn die
    Quelle aktiv ist - nicht nur die Pflichtmodelle des Waechters. Bricht eine
    Schutzantwort ein Modell ab, bleiben davon nur die schon gelesenen nicht
    lieferbaren Stufen, nie halbe Preise. `frist_sekunden`: das Zeitbudget der
    Stufe; vor jedem Modell geprueft, ein laufendes Modell wird zu Ende gelesen.
    Ist es aufgebraucht, steht der Rest in `ungelesen` (Status "frist")."""
    warte = warte or time.sleep
    ergebnis = Ergebnis()
    if not quelle_aktiv(quellen):
        return ergebnis
    leiter = tuple((s.key, s.gb) for s in tarifleiter(tarife_je_id) if s.gb is not None)
    if not leiter:
        ergebnis.status = "keine_leiter"
        ergebnis.grund = "keine Vodafone-Tarifleiter im Tarifbestand - kein Abruf"
        return ergebnis
    modelle = modelle_der_stufe()
    ergebnis.status = "ok"
    beginn = monoton()
    for stelle, modell in enumerate(modelle):
        if frist_sekunden is not None and monoton() - beginn >= frist_sekunden:
            ergebnis.status = "frist"
            ergebnis.ungelesen = modelle[stelle:]
            ergebnis.grund = (
                f"Zeitbudget {frist_sekunden:.0f} s aufgebraucht, "
                f"{len(ergebnis.ungelesen)} Modelle nicht gelesen"
            )
            log.warning("Tarifwelt: %s", ergebnis.grund)
            break
        teil = tarifwelt_lauf.Lauf()
        try:
            tarifwelt_lauf.lies_modell(
                modell, leiter, hole, abgerufen_am, warte=warte, lauf=teil
            )
        except GeraeteAbrufFehler as fehler:
            ergebnis.nicht_lieferbar.extend(teil.nicht_lieferbar)
            ergebnis.status = "abgebrochen"
            ergebnis.grund = str(fehler)
            log.warning("Tarifwelt: Lauf abgebrochen bei %s: %s", modell, fehler)
            break
        ergebnis.modelle += 1
        ergebnis.buendel.extend(teil.buendel)
        ergebnis.tarife.update(teil.tarife)
        ergebnis.luecken.extend(teil.luecken)
        ergebnis.nicht_lieferbar.extend(teil.nicht_lieferbar)
        ergebnis.abrufe += teil.abrufe
    return ergebnis


def stufe(
    quellen,
    bestand,
    hole: Callable,
    uhr: Callable,
    heute: str,
    zustand,
    tco,
    beginn: float | None = None,
) -> dict:
    """Die Stufe im Tageslauf (`geraete_pipeline.run_geraete_stage`): lesen,
    Buendel und Stammdaten der Tarife (`TcoDB.haendler_tarife`) in den TCO-Store,
    aeltere Buendel nicht lieferbarer Stufen markiert (`tarifwelt_lieferbar`);
    `tco.save` sichert alles in `geraete_tco.json`. `beginn` ist `time.monotonic()`
    beim Start des Tageslaufs; daraus rechnet `stufen_frist` das Zeitbudget der
    Stufe gegen die Restzeit des Jobs (ohne `beginn` gibt es keins).
    Die Abrufe gehen durch dieselbe `Abrufschleuse` (robots.txt, Besuchsfenster)
    wie die uebrigen Quellen. Wirft nie: ein Fehler kostet nur diese Stufe."""
    if not quelle_aktiv(quellen):
        return {"status": "aus"}
    try:
        anbieter = next(a for a in quellen.anbieter if a.methode == METHODE)
        ergebnis = lauf(
            quellen,
            bestand.je_id_aktuell,
            hole_fuer_anbieter(hole, anbieter, uhr),
            heute,
            frist_sekunden=(
                None if beginn is None else stufen_frist(time.monotonic() - beginn)
            ),
        )
        if ergebnis.buendel:
            tco.upsert_buendel(ergebnis.buendel, heute)
            tco.haendler_tarife.update(ergebnis.tarife)
        markiert = tarifwelt_lieferbar.markiere(
            tco.buendel(), ergebnis.nicht_lieferbar, heute
        )
        log.info(
            "Tarifwelt: %s, %d Buendel, %d Luecken, %d nicht lieferbar markiert, "
            "%d Abrufe%s",
            ergebnis.status,
            len(ergebnis.buendel),
            len(ergebnis.luecken),
            markiert,
            ergebnis.abrufe,
            f" ({ergebnis.grund})" if ergebnis.grund else "",
        )
        return ergebnis.als_dict()
    except (OSError, ValueError, TypeError, StopIteration) as exc:
        log.warning("Tarifwelt: Stufe gescheitert (%s)", exc)
        return {"status": "fehler", "grund": str(exc)}
