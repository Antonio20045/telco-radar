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

from .collect.geraete import tarifwelt_lauf
from .collect.geraete.basis import GeraeteAbrufFehler
from .collect.geraete.buendel_prioritaet import pflicht_modelle
from .geraete_abruf import hole_fuer_anbieter
from .report.geraete_tco_band import tarifleiter
from .tco_model import Buendel

log = logging.getLogger(__name__)

METHODE = "mediamarkt_tarifwelt"


@dataclass
class Ergebnis:
    """Was die Stufe liefert; `status`: "aus", "ok", "keine_leiter", "abgebrochen"."""

    status: str = "aus"
    buendel: list[Buendel] = field(default_factory=list)
    tarife: dict[str, dict] = field(default_factory=dict)
    luecken: list[tuple[str, str]] = field(default_factory=list)
    abrufe: int = 0
    modelle: int = 0
    grund: str = ""

    def als_dict(self) -> dict:
        """Die Zahlen der Stufe fuer die Tagesbilanz."""
        return {
            "status": self.status,
            "buendel": len(self.buendel),
            "tarife": len(self.tarife),
            "luecken": len(self.luecken),
            "abrufe": self.abrufe,
            "modelle": self.modelle,
            "grund": self.grund,
        }


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
) -> Ergebnis:
    """Alle Pflichtmodelle der Tarifwelt, wenn die Quelle aktiv ist."""
    warte = warte or time.sleep
    ergebnis = Ergebnis()
    if not quelle_aktiv(quellen):
        return ergebnis
    leiter = tuple((s.key, s.gb) for s in tarifleiter(tarife_je_id) if s.gb is not None)
    if not leiter:
        ergebnis.status = "keine_leiter"
        ergebnis.grund = "keine Vodafone-Tarifleiter im Tarifbestand - kein Abruf"
        return ergebnis
    modelle = [m for m in tarifwelt_lauf.MODELL_SLUGS if m in pflicht_modelle()]
    ergebnis.status = "ok"
    for modell in modelle:
        try:
            teil = tarifwelt_lauf.lies_modell(
                modell, leiter, hole, abgerufen_am, warte=warte
            )
        except GeraeteAbrufFehler as fehler:
            ergebnis.status = "abgebrochen"
            ergebnis.grund = str(fehler)
            log.warning("Tarifwelt: Lauf abgebrochen bei %s: %s", modell, fehler)
            break
        ergebnis.modelle += 1
        ergebnis.buendel.extend(teil.buendel)
        ergebnis.tarife.update(teil.tarife)
        ergebnis.luecken.extend(teil.luecken)
        ergebnis.abrufe += teil.abrufe
    return ergebnis


def stufe(
    quellen, bestand, hole: Callable, uhr: Callable, heute: str, zustand, tco
) -> dict:
    """Die Stufe im Tageslauf (`geraete_pipeline.run_geraete_stage`): lesen,
    Buendel und Stammdaten der Tarife (`TcoDB.haendler_tarife`) in den TCO-Store;
    `tco.save` sichert beides in `geraete_tco.json`.
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
        )
        if ergebnis.buendel:
            tco.upsert_buendel(ergebnis.buendel, heute)
            tco.haendler_tarife.update(ergebnis.tarife)
        log.info(
            "Tarifwelt: %s, %d Buendel, %d Luecken, %d Abrufe%s",
            ergebnis.status,
            len(ergebnis.buendel),
            len(ergebnis.luecken),
            ergebnis.abrufe,
            f" ({ergebnis.grund})" if ergebnis.grund else "",
        )
        return ergebnis.als_dict()
    except (OSError, ValueError, TypeError, StopIteration) as exc:
        log.warning("Tarifwelt: Stufe gescheitert (%s)", exc)
        return {"status": "fehler", "grund": str(exc)}
