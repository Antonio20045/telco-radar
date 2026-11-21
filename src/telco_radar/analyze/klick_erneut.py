"""Eigener Abruf eines Klick-Anbieters, wenn das Nachholen vom Zweig nichts brachte.

``klick_nachholen`` holt nur den Stand, den der Klick-Tageslauf auf ``origin`` ablegte.
Endete der Lauf eines Anbieters sofort gestört (1&1, 21.11.2026: HTTP 502 auf der
Übersicht, 21 Seiten ``nicht_besucht``, 14 Pflichtmodelle ohne Bündel), blieb er den
ganzen Tag ohne Klick-Messung. ``Erneut`` ruft den Anbieter dann selbst ab: dasselbe
Skript wie der Tageslauf (``scripts/klick_tageslauf.py``, robots.txt, Crawl-delay und
ehrliche Kennung gelten unverändert), NUR für die Schlüssel dieses einen Anbieters, in
einen Wegwerfordner.

- Nur Anbieter aus ``ANBIETER``; Telekom, o2 und die übrigen bleiben beim Stand des
  Tageslaufs.
- Höchstens ``VERSUCHE`` Abrufe, dazwischen ``PAUSE_S``. Wiederholt wird nur nach einer
  Störung ohne Bot-Schutz (5xx, Zeitüberschreitung); eine Schutzantwort (202, 403, 406,
  429, ``sperre``) bleibt bei genau einer Anfrage (CLAUDE.md Regel 4).
- Vor jedem Abruf fragt die Prüfung (``laufpruefung_aus_umgebung``), ob Klick-Tageslauf,
  Klick-Erkundung oder Radarlauf anstehen oder laufen; der eigene Gerätelauf zählt
  nicht mit. Ohne lesbare Auskunft kein Abruf (Regel 9).
- Kein Abruf unter ``MINDEST_S`` Restzeit (Regel 8); das Skript bekommt die Restzeit als
  Budget, der Prozess ``SCHLUSS_S`` darüber als harte Grenze.
- Das neue Ergebnis ersetzt die Datei nur, wenn sie nach ``veraltet`` zählt (mindestens
  eine ganz gelesene Seite); sonst bleibt der Stand vom Zweig. Belegbilder bleiben aus:
  sie legt allein der Tageslauf ab.

Die Bilanz je Anbieter (``versuche``, ``gelesen``, ``grund``) steht unter
``nachholen.erneut``; scheitert der Abruf, steht dort der Grund, nie ein leeres
Ergebnis.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from pathlib import Path

import yaml

from ..collect.geraete.klickparallel import (
    API,
    API_VARIABLE,
    GRUND_API,
    REPO_VARIABLE,
    TAGESLAUF_WORKFLOWS,
    TOKEN_VARIABLE,
    GithubLaeufe,
    Laufpruefung,
    hole,
)
from ..collect.geraete.klicktageslauf import RESERVE_S
from ..collect.geraete.klickziele import KARTEN, TAGESDATEI
from ..klick_vertrag import CHALLENGE_STATUS, ganz_gelesen, lies_ergebnisse

log = logging.getLogger(__name__)

ANBIETER = frozenset({"1&1"})
"""Namen (``klick_tageslauf.yaml``), die ``Erneut`` selbst abruft; zuerst nur 1&1."""
VERSUCHE = 3
PAUSE_S = 120.0
SCHARD_PAUSE_S = 30.0
"""Pause zwischen den Schlüsseln eines Anbieters (1&1 hat zwei Dateien)."""
MINDEST_S = 180.0
SCHLUSS_S = 60.0
INSTALL_S = 300.0
SKRIPT = Path("scripts") / "klick_tageslauf.py"
SCHUTZ_STATUS = frozenset({CHALLENGE_STATUS, 403, 406, 429})
GRUND_SCHUTZ = "Schutzantwort: kein zweiter Abruf (CLAUDE.md Regel 4)"
GRUND_KEIN_ZIEL = "kein Klick-Ziel in config/klick_tageslauf.yaml"
GRUND_NICHTS = "kein Satz gelesen"
PARALLEL_WORKFLOWS = {
    **{k: v for k, v in TAGESLAUF_WORKFLOWS.items() if k != "geraete.yml"},
    "klick.yml": "Klick-Tageslauf",
}
"""Wie ``TAGESLAUF_WORKFLOWS`` ohne den Gerätelauf, in dem ``Erneut`` selbst läuft, und
mit dem Klick-Tageslauf (derselbe Host)."""

Abruf = Callable[[str, Path, float], str | None]
Veraltet = Callable[[Path, str, list[str]], list[str]]
Schlafe = Callable[[float], None]
Uhr = Callable[[], float]


def schluessel_des_anbieters(root: Path, name: str) -> list[str]:
    """Die Schlüssel der Einträge von ``name`` (Shards) mit Karte; leer ohne Eintrag."""
    try:
        roh = yaml.safe_load((root / TAGESDATEI).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    eintraege = roh.get("anbieter") if isinstance(roh, dict) else None
    return [
        str(e["schluessel"])
        for e in eintraege or []
        if isinstance(e, dict)
        and e.get("name") == name
        and e.get("schluessel")
        and (root / KARTEN / f"{e.get('karte', e['schluessel'])}.yaml").is_file()
    ]


def abruf_im_repo(root: Path) -> Abruf:
    """Der Abruf über ``scripts/klick_tageslauf.py`` in einem Unterprozess.

    Gibt ``None`` zurück, wenn das Skript endete (auch mit gestörtem Anbieter: das
    steht in der Ergebnisdatei), sonst den Grund. Fehlt Chromium im Job, wird es
    einmal installiert (``playwright install chromium``, ``INSTALL_S``) und der Abruf
    wiederholt.
    """
    installiert = False

    def lauf(schluessel: str, ausgabe: Path, frist_s: float) -> str | None:
        nonlocal installiert
        argumente = [
            sys.executable,
            str(root / SKRIPT),
            "--root",
            str(root),
            "--anbieter",
            schluessel,
            "--ausgabe",
            str(ausgabe),
            "--job-frist-sekunden",
            str(frist_s + RESERVE_S),
            "--ohne-parallelpruefung",
        ]
        umgebung = {**os.environ, "PYTHONPATH": str(root / "src")}
        try:
            ergebnis = subprocess.run(
                argumente,
                cwd=root,
                env=umgebung,
                capture_output=True,
                text=True,
                timeout=frist_s + SCHLUSS_S,
            )
        except subprocess.TimeoutExpired:
            return f"Abruf nach {frist_s + SCHLUSS_S:.0f} s abgebrochen"
        except OSError as fehler:
            return f"Abruf nicht gestartet: {fehler}"
        if ergebnis.returncode == 0:
            return None
        letzte = (ergebnis.stderr or ergebnis.stdout).strip().splitlines()[-1:]
        if "playwright install" in ergebnis.stderr and not installiert:
            installiert = True
            if (grund := _installiere_chromium()) is not None:
                return grund
            return lauf(schluessel, ausgabe, frist_s - INSTALL_S)
        return f"Abruf endete mit Exit {ergebnis.returncode}: {''.join(letzte)}"

    return lauf


def _installiere_chromium() -> str | None:
    """Grund, wenn Chromium sich nicht installieren ließ, sonst ``None``."""
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            timeout=INSTALL_S,
        )
    except (OSError, subprocess.SubprocessError) as fehler:
        return f"Chromium nicht installiert: {type(fehler).__name__}"
    return None


def laufpruefung_aus_umgebung(
    umgebung: Mapping[str, str] | None = None,
    holer=hole,
    uhr: Callable[[], datetime] | None = None,
) -> Laufpruefung:
    """Die Prüfung auf parallele Läufe; ``None`` heißt frei, sonst steht der Grund da.

    Mit ``GITHUB_TOKEN`` wie die Klick-Erkundung, ohne Token (``geraete.yml`` reicht
    keines herein, das Repo ist öffentlich) ohne Kopfzeile ``Authorization``. Ohne
    ``GITHUB_REPOSITORY`` oder bei unlesbarer Antwort ist das ein Grund, nie „frei“.
    Ohne ``uhr`` (der Wächter erlaubt keine Wanduhr in ``src/``) sperrt jeder
    wartende Lauf, auch ein hängender: der Abruf entfällt dann, er wird nie früher.
    """
    umg = os.environ if umgebung is None else umgebung
    repo = umg.get(REPO_VARIABLE, "")
    if not repo:
        grund = f"{GRUND_API} ({REPO_VARIABLE} fehlt)"
        return lambda: grund
    token = umg.get(TOKEN_VARIABLE, "")

    def ohne_token(url: str, kopf: dict[str, str]) -> tuple[int, str]:
        return holer(url, {k: v for k, v in kopf.items() if k != "Authorization"})

    return GithubLaeufe(
        repo,
        token,
        umg.get(API_VARIABLE) or API,
        holer=holer if token else ohne_token,
        workflows=PARALLEL_WORKFLOWS,
        uhr=uhr,
    )


def _schutz(wert: object) -> bool:
    """Trägt irgendwo in den Ergebnisdaten eine Seite eine Schutzantwort?"""
    if isinstance(wert, dict):
        if wert.get("sperre") or wert.get("http_status") in SCHUTZ_STATUS:
            return True
        return any(_schutz(v) for v in wert.values())
    if isinstance(wert, list):
        return any(_schutz(v) for v in wert)
    return False


class Erneut:
    """Ruft die veralteten Anbieter aus ``anbieter`` selbst ab, mit Wiederholung."""

    def __init__(
        self,
        root: Path,
        abruf: Abruf,
        laeufe: Laufpruefung,
        veraltet: Veraltet,
        *,
        anbieter: Iterable[str] = ANBIETER,
        versuche: int = VERSUCHE,
        pause_s: float = PAUSE_S,
        schlafe: Schlafe = time.sleep,
        uhr: Uhr = time.monotonic,
    ) -> None:
        self.root = root
        self.abruf = abruf
        self.laeufe = laeufe
        self.veraltet = veraltet
        self.anbieter = frozenset(anbieter)
        self.versuche = versuche
        self.pause_s = pause_s
        self.schlafe = schlafe
        self.uhr = uhr

    def __call__(
        self, namen: list[str], ziel: Path, heute: str, frist_s: float
    ) -> dict[str, dict]:
        """Bilanz je betroffenem Anbieter aus ``namen``; leer, wenn keiner dazugehört.

        Gelesene Dateien liegen danach in ``ziel`` (ersetzen dort die alten).
        """
        ende = self.uhr() + frist_s
        bilanz = {
            name: self._anbieter(name, ziel, heute, ende)
            for name in namen
            if name in self.anbieter
        }
        for name, eintrag in bilanz.items():
            log.info(
                "Klick-Stand erneut %s: %d Abruf(e), %s%s",
                name,
                eintrag["versuche"],
                "gelesen" if eintrag["gelesen"] else "nicht gelesen",
                f" ({eintrag['grund']})" if eintrag["grund"] else "",
            )
        return bilanz

    def _anbieter(self, name: str, ziel: Path, heute: str, ende: float) -> dict:
        schluessel = schluessel_des_anbieters(self.root, name)
        eintrag: dict[str, object] = {
            "versuche": 0,
            "gelesen": False,
            "grund": GRUND_KEIN_ZIEL,
        }
        if not schluessel:
            return eintrag
        with tempfile.TemporaryDirectory(prefix="klick-erneut-") as tmp:
            for versuch in range(1, self.versuche + 1):
                rest = ende - self.uhr()
                if rest < MINDEST_S:
                    eintrag["grund"] = f"Restzeit {rest:.0f} s unter {MINDEST_S:.0f} s"
                    break
                if (parallel := self.laeufe()) is not None:
                    eintrag["grund"] = parallel
                    break
                eintrag["versuche"] = versuch
                aus = Path(tmp) / str(versuch)
                grund = self._fahre(schluessel, aus, ende)
                if grund is None and not self.veraltet(aus, heute, [name]):
                    for datei in aus.glob("*.json"):
                        shutil.copyfile(datei, ziel / datei.name)
                    eintrag.update(gelesen=True, grund=None)
                    break
                eintrag["grund"] = grund or self._grund(aus)
                if grund is not None or self._schutzantwort(aus):
                    if grund is None:
                        eintrag["grund"] = f"{eintrag['grund']}; {GRUND_SCHUTZ}"
                    break
                if versuch < self.versuche:
                    if ende - self.uhr() - self.pause_s < MINDEST_S:
                        break
                    self.schlafe(self.pause_s)
        return eintrag

    def _fahre(self, schluessel: list[str], aus: Path, ende: float) -> str | None:
        """Ruft alle Schlüssel nacheinander ab; der Grund des ersten Scheiterns."""
        for stelle, einer in enumerate(schluessel):
            if stelle:
                self.schlafe(SCHARD_PAUSE_S)
            rest = ende - self.uhr()
            if rest < MINDEST_S:
                return f"Restzeit {rest:.0f} s unter {MINDEST_S:.0f} s"
            if (grund := self.abruf(einer, aus, rest)) is not None:
                return grund
            if not self._gelesen(aus, einer):
                return None
        return None

    @staticmethod
    def _gelesen(aus: Path, schluessel: str) -> bool:
        """Hat der Abruf dieses Schlüssels mindestens eine Seite ganz gelesen?

        Sonst folgt kein zweiter Schlüssel desselben Hosts: der Versuch ist gescheitert.
        """
        dateien, _ = lies_ergebnisse(aus)
        return any(
            d.get("anbieter") == schluessel and ganz_gelesen(d.get("seiten") or [])
            for d in dateien
        )

    @staticmethod
    def _grund(aus: Path) -> str:
        dateien, _ = lies_ergebnisse(aus)
        gruende = [str(d["grund"]) for d in dateien if d.get("grund")]
        return gruende[0] if gruende else GRUND_NICHTS

    @staticmethod
    def _schutzantwort(aus: Path) -> bool:
        dateien, _ = lies_ergebnisse(aus)
        return any(_schutz(d) for d in dateien)
