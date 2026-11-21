"""Der nächtliche Gerätelauf als Ganzes: Stufe, Soll/Ist-Zählung, Lauf-Datei.

``python -m telco_radar.geraete_pipeline`` (Schritt „Run geraete stage“ in
``.github/workflows/geraete.yml``) ruft ``main``: erst ``run_geraete_stage`` wie bisher,
dann ``schliesse_ab``: Soll je Anbieter zählen (``geraete_soll``), Ist und Lücken
rechnen (``geraete_vollstaendigkeit``), die Angebotszählung des Messtags aus dem
Browser einhängen (``geraete_angebot.einhaengen``; fehlt sie, „Angebot heute nicht
gezählt“ mit Grund) und Bilanz samt ``vollstaendigkeit`` in die Lauf-Datei schreiben
(``geraete_lauf``).

Zeitbudget (CLAUDE.md Regel 8): die Tarifwelt-Stufe hält nach sich
``RESERVE_NACH_STUFE_SEKUNDEN`` frei; die Soll-Zählung nimmt davon nur, was über
``NACH_SCHRITTE_SEKUNDEN`` (alle Workflow-Schritte nach der Stufe) hinausgeht, gerechnet
gegen die Restzeit des Jobs ab dem Start dieses Prozesses (``rest_sekunden``). Reicht
sie für einen Abruf nicht, steht das Soll als „Zeitbudget erschöpft“ da, nie als 0.

Ein Fehler in ``schliesse_ab`` kostet weder Messtag noch Commit: er geht über die
Absicherung der Pipeline in eine Lauf-Datei mit ``vollstaendigkeit.fehler`` (der
Wächter wird rot), der Schritt selbst bleibt grün.
"""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from . import geraete_abruf, geraete_lauf, geraete_soll, geraete_tarifwelt
from .analyze.klick_nachholen import nachholen_aus_umgebung
from .analyze.tco_store import TcoDB
from .geraete_angebot.einhaengen import haenge_ein
from .geraete_config import lade_katalog, lade_quellen
from .geraete_vollstaendigkeit import Signale, baue

log = logging.getLogger(__name__)

AUSFALL_BESTAND = "Bündelbestand des Messtags nicht gespeichert"


def rest_sekunden(vergangen: float) -> float:
    """Restzeit des Jobs nach ``vergangen`` Sekunden Pipeline, ohne die Schritte
    danach: ``JOB_FRIST`` - ``VORLAUF`` - vergangen - ``NACH_SCHRITTE``."""
    tw = geraete_tarifwelt
    return (
        tw.JOB_FRIST_SEKUNDEN
        - tw.VORLAUF_SEKUNDEN
        - vergangen
        - tw.NACH_SCHRITTE_SEKUNDEN
    )


def mindest_sekunden(http_cfg: dict) -> float:
    """Höchstdauer eines Abrufs: robots.txt und Liste je ein Timeout, plus 5 s."""
    return 2 * float(http_cfg.get("timeout_seconds", 20)) + 5.0


def schliesse_ab(
    root: Path,
    heute: str,
    bilanz: dict,
    hole: Callable,
    rest: Callable[[], float],
    mindest: float,
    uhr: Callable[[], datetime],
) -> Path:
    """Soll zählen, Ist und Lücken rechnen, Lauf-Datei schreiben."""
    zustand = Path(root) / "data" / "state"
    katalog = lade_katalog(Path(root))
    soll = geraete_soll.zaehle_alle(
        lade_quellen(Path(root)), hole, uhr, katalog, rest, mindest
    )
    tco = TcoDB(zustand / "geraete_tco.json")
    signale = Signale(
        erfassung=dict(tco.erfassung or {}),
        tarifwelt=dict(bilanz.get("tarifwelt") or {}),
        tarifwelt_modelle=tuple(geraete_tarifwelt.modelle_der_stufe()),
        ausfall=None if tco.updated == heute else AUSFALL_BESTAND,
    )
    namen = {g.device_id: geraete_soll.anzeigename(g) for g in katalog.geraete}
    buendel = list(tco.buendel())
    voll = baue(
        heute,
        uhr().isoformat(timespec="seconds"),
        buendel,
        {name: s.als_dict() for name, s in soll.items()},
        signale,
        namen,
    )
    haenge_ein(voll, zustand, heute, buendel, signale, katalog, namen)
    for zeile in voll["anbieter"]:
        modelle = zeile["ebenen"]["modelle"]
        log.info(
            "Vollstaendigkeit %s: Soll %s, Ist %s, erfasst %s, %s Luecken "
            "(%d unbenannt)%s",
            zeile["name"],
            modelle["soll"],
            modelle["ist"],
            modelle["erfasst"],
            modelle["luecken_zahl"],
            zeile["unbenannt"],
            f" - Soll nicht zaehlbar: {modelle['soll_grund']}"
            if modelle["soll"] is None
            else "",
        )
    return geraete_lauf.schreibe(
        zustand, heute, {"bilanz": bilanz, "vollstaendigkeit": voll}
    )


def schreibe_fehler(root: Path, heute: str, bilanz: dict, fehler: Exception) -> None:
    """Die Lauf-Datei trotz gescheiterter Zählung: Bilanz plus benannter Fehler."""
    text = f"Zählung gescheitert: {type(fehler).__name__}: {fehler}"[:400]
    log.error("Vollstaendigkeit: %s", text)
    voll = {"datum": heute, "fehler": text, "anbieter": []}
    geraete_lauf.schreibe(
        Path(root) / "data" / "state",
        heute,
        {"bilanz": bilanz, "vollstaendigkeit": voll},
    )


def main(
    stufe: Callable[..., dict],
    abgesichert: Callable,
    frist: float,
    uhr: Callable[[], datetime],
) -> None:
    """Einstieg des Nachtlaufs; ``stufe`` ist ``run_geraete_stage``, ``abgesichert``
    die Absicherung der Pipeline (``geraete_pipeline.abgesichert``), ``frist`` die
    Standardfrist der Sammelphase (``--frist``), ``uhr`` die Uhr des Einstiegs."""
    p = argparse.ArgumentParser(description="Geraete- und Preisradar")
    p.add_argument("--root", default=".")
    p.add_argument("--frist", type=float, default=frist)
    p.add_argument("--klick", type=Path, default=None)
    args = p.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    from .config import load_config

    beginn = time.monotonic()
    root = Path(args.root)
    http = load_config(root).settings.get("http", {})
    jetzt = uhr()
    heute = jetzt.strftime("%Y-%m-%d")
    bilanz = stufe(
        root,
        http,
        heute,
        jetzt=jetzt,
        frist_sekunden=args.frist,
        klick=args.klick,
        klick_nachholen=nachholen_aus_umgebung(root),
    )
    abgesichert(
        lambda: schliesse_ab(
            root,
            heute,
            bilanz,
            geraete_abruf.hole_fabrik(http),
            lambda: rest_sekunden(time.monotonic() - beginn),
            mindest_sekunden(http),
            uhr,
        ),
        lambda exc: schreibe_fehler(root, heute, bilanz, exc),
    )
