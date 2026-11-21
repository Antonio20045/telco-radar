"""Der Klick-Stand des Tages im Gerätelauf: nachholen, bevor ein Tag als gemessen zählt.

Fehler vom 10.11.2026 (Gerätelauf 42793801318): der Lauf checkte ``main`` um 09:49:21
UTC aus, der Klick-Tageslauf legte seinen Stand um 09:50:37 ab. Der Merge fand lauter
Dateien „vom 09.11.“, übernahm kein Klick-Bündel, und die Klick-Anbieter (Telekom nur
über Klick) blieben den ganzen Tag auf dem Vortag. Gleiches am 07. und 08.11.

``Nachholen`` prüft vor dem Merge, ob jede Klick-Datei der geplanten Anbieter vom
Messtag ist UND wirklich etwas gemessen hat. Eine Datei von heute, deren Laufstatus
``gestoert`` ist und die keine einzige Seite ganz gelesen hat (``klick_vertrag.
ganz_gelesen``, 0 Seiten), zählt dabei wie eine veraltete Datei: ein Abruf, der sofort
scheitert (etwa HTTP 502), lieferte sonst gar nichts, und das Datum allein hätte ihn
als „vom Messtag“ durchgehen lassen (1&1, 21.11.2026: ``gestoert``, 0 Seiten, Datei
trotzdem von heute). Wenn nicht, holt es den neuesten Stand NUR von
``klick_vertrag.ORDNER`` von ``origin/<Zweig>`` (``git fetch`` und ``git archive`` in
einen Wegwerfordner): der Arbeitsbaum und der Index bleiben unberührt, darum kann der
``git pull --rebase`` am Ende von ``geraete.yml`` an diesem Pfad nicht in Konflikt
geraten. Ist der Stand noch alt und läuft der Klick-Tageslauf (``klick.yml``) oder ist
die GitHub-Auskunft nicht lesbar, wartet es in Abständen (``ABSTAND_S``) höchstens
``WARTEN_HOECHSTENS_S``, aber nie über die Restzeit des Jobs hinaus (Regel 8: ``JOB_S``
abzüglich Vor- und Nachlauf). Läuft kein Klick-Lauf des Tages, bleibt es bei einem
Abruf. Eine GitHub-Auskunft „fertig“ für den gesamten Tageslauf ist dafür kein
verlässlicher Schlusspunkt: ihren Commit schreibt erst der letzte Job ``ablegen``
(``klick.yml``), der nach allen Anbietern läuft, sein Push kann der Auskunft also noch
nachhinken (1&1, Messlauf 21.11.2026, Lauf 44840854026: „fertig“ stand schon, der
Stand blieb noch einen Abruf lang beim Vortag). „Fertig“ muss sich darum einmal
wiederholen, bevor es den noch veralteten Anbieter endgültig aufgibt; „keiner“ (kein
Lauf heute) bleibt dagegen beim ersten Abruf.

Bleibt ein Anbieter nach dem Abruf vom Zweig veraltet oder leer gestört und läuft kein
Klick-Tageslauf, ruft ``klick_erneut.Erneut`` ihn selbst ab (zuerst 1&1, mit
Wiederholung und Pause, nur dieser Anbieter); die Bilanz steht unter
``nachholen.erneut``.

Bleibt eine Datei alt, ändert sich nichts am Merge: sie liefert nichts
(``klick_zusammenfuehrung.GRUND_NICHT_HEUTE``), der Bestand behält die Klick-Messung mit
ihrem Datum (Vorrang), kein Preis rückt auf heute. Die Bilanz nennt die Anbieter unter
``nachholen.veraltet``. Sind alle Dateien vom Messtag, tut das Nachholen nichts.
"""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ..collect import http
from ..collect.geraete.klickparallel import API, API_VARIABLE, REPO_VARIABLE, hole
from ..collect.geraete.klickziele import geplante_anbieter
from ..klick_vertrag import (
    LAUF_GESTOERT,
    ORDNER,
    STAND_DATEI,
    ganz_gelesen,
    lies_ergebnisse,
)
from .klick_erneut import Erneut, abruf_im_repo, laufpruefung_aus_umgebung
from .klick_zusammenfuehrung import alter_tage, klickordner

log = logging.getLogger(__name__)

WARTEN_HOECHSTENS_S = 1200.0
ABSTAND_S = 60.0
JOB_S = 2400.0
"""``timeout-minutes: 40`` des Jobs in ``geraete.yml``."""
VORLAUF_S = 180.0
NACHLAUF_S = 900.0
"""Checkout und Installation vor der Stufe; danach alles, was dem Merge noch folgt:
die Tarifwelt-Stufe im selben Aufruf (ohne eigene Frist), Bestand sichern, Seite
bauen, Hook, Wächter, dazu ein Abruf, der ``GIT_FRIST_S`` ausschöpft. Gemessen im
Lauf 43578115434 (14.11.2026): 87 s davor, 468 s Tarifwelt und 261 s Schritte
danach. Beides gehört nicht dem Warten."""
GIT_FRIST_S = 60.0
WORKFLOW = "klick.yml"
ZWEIG_VARIABLE = "GITHUB_REF_NAME"
ZWEIG_STANDARD = "main"
LAEUFT = "laeuft"
FERTIG = "fertig"
KEINER = "keiner"
UNBEKANNT = "unbekannt"
LAUFENDE_ZUSTAENDE = frozenset(
    {"queued", "in_progress", "waiting", "requested", "pending"}
)

Git = Callable[[list[str]], bytes]
KlickLauf = Callable[[str], str]
Schlafe = Callable[[float], None]
Uhr = Callable[[], float]


def veraltet(ordner: Path, heute: str, geplant: list[str] | None) -> list[str]:
    """Die Anbieter, deren Klick-Datei fehlt, nicht vom Messtag ist, oder deren Lauf
    gestört ohne eine einzige ganz gelesene Seite endete.

    Ohne Liste der geplanten Anbieter zählen die Dateien im Ordner. Hat ein
    Anbieter mehrere Dateien (Shards), genügt eine alte oder leer gestörte. Eine
    Datei „nach heute“ ist nicht veraltet. Eine Datei von heute mit Laufstatus
    ``gestoert`` und 0 Seiten (``klick_vertrag.ganz_gelesen``) zählt wie eine
    veraltete: ein sofort gescheiterter Abruf (etwa HTTP 502) lieferte nichts, auch
    wenn das Datum „heute“ heißt (CLAUDE.md §5 „Scheitern ist kein leeres Ergebnis“).
    """
    dateien, _ = lies_ergebnisse(ordner)
    stand: dict[str, list[tuple[int | None, bool]]] = {}
    for d in dateien:
        alter = alter_tage(d.get("datum"), heute)
        leer_gestoert = d.get("laufstatus") == LAUF_GESTOERT and not ganz_gelesen(
            d.get("seiten") or []
        )
        stand.setdefault(str(d.get("name")), []).append((alter, leer_gestoert))
    namen = list(dict.fromkeys(geplant if geplant is not None else sorted(stand)))
    return [n for n in namen if _veraltet(stand.get(n))]


def _veraltet(stand: list[tuple[int | None, bool]] | None) -> bool:
    """Fehlt die Datei, ist ein Datum unlesbar, liegt eine Datei vor heute, oder
    endete ein Lauf von heute gestört ohne eine einzige ganz gelesene Seite?"""
    return not stand or any(
        alter is None or alter > 0 or leer_gestoert for alter, leer_gestoert in stand
    )


def git_im_repo(root: Path) -> Git:
    """``git`` im Repo; Ausgabe als Bytes, Fehler als ``subprocess``-Ausnahme."""

    def lauf(argumente: list[str]) -> bytes:
        ergebnis = subprocess.run(
            ["git", *argumente],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=GIT_FRIST_S,
        )
        return ergebnis.stdout

    return lauf


def klicklauf_aus_umgebung(
    umgebung: Mapping[str, str] | None = None,
    holer: Callable[[str, dict[str, str]], tuple[int, str]] = hole,
) -> KlickLauf:
    """Fragt GitHub nach dem Klick-Tageslauf: ``laeuft``, ``fertig``, ``keiner`` des
    Tages oder ``unbekannt`` (Repo nicht genannt, API nicht lesbar, Antwort unlesbar).

    Ohne Token: das Repo ist öffentlich, ``geraete.yml`` reicht keines herein.
    """
    umg = os.environ if umgebung is None else umgebung

    def frage(heute: str) -> str:
        repo = umg.get(REPO_VARIABLE, "")
        if not repo:
            return UNBEKANNT
        api = umg.get(API_VARIABLE) or API
        url = f"{api}/repos/{repo}/actions/workflows/{WORKFLOW}/runs?per_page=5"
        try:
            status, text = holer(url, {"Accept": "application/vnd.github+json"})
            laeufe = json.loads(text)["workflow_runs"] if status == 200 else None
        except (http.HttpFehler, OSError, ValueError, KeyError, TypeError) as fehler:
            log.warning("Klick-Lauf: GitHub-Auskunft gescheitert (%s)", fehler)
            return UNBEKANNT
        if not isinstance(laeufe, list):
            return UNBEKANNT
        if any(
            isinstance(r, dict) and r.get("status") in LAUFENDE_ZUSTAENDE
            for r in laeufe
        ):
            return LAEUFT
        neueste = next((r for r in laeufe if isinstance(r, dict)), None)
        if neueste and str(neueste.get("created_at", ""))[:10] == heute:
            return FERTIG
        return KEINER

    return frage


@dataclass
class Nachholen:
    """Holt den Klick-Stand von ``origin/<zweig>``, wenn der Arbeitsbaum zu alt ist."""

    root: Path
    git: Git
    klicklauf: KlickLauf
    zweig: str = ZWEIG_STANDARD
    schlafe: Schlafe = time.sleep
    uhr: Uhr = time.monotonic
    warten_s: float = WARTEN_HOECHSTENS_S
    abstand_s: float = ABSTAND_S
    bilanz: dict = field(default_factory=dict)
    gestartet: float | None = None
    """Beginn der Stufe auf ``uhr``; ohne Angabe der Zeitpunkt der Anlage."""
    erneut: Erneut | None = None
    """Ruft einen noch veralteten Anbieter selbst ab (``klick_erneut``)."""

    def __post_init__(self) -> None:
        if self.gestartet is None:
            self.gestartet = self.uhr()

    def rest(self) -> float:
        """Sekunden, die dem Warten bleiben (``restzeit``)."""
        return restzeit(self.uhr() - (self.gestartet or 0.0))

    @contextmanager
    def __call__(self, heute: str, restzeit_s: float) -> Iterator[Path | None]:
        """Der Ordner mit dem frischeren Stand oder ``None`` (Arbeitsbaum bleibt).

        Wegwerfordner und Bilanz (``self.bilanz``, leer ohne Nachholen) leben bis zum
        Ende des ``with``-Blocks.
        """
        self.bilanz = {}
        geplant = geplante_anbieter(self.root)
        vorher = veraltet(self.root / ORDNER, heute, geplant)
        if not vorher:
            yield None
            return
        with tempfile.TemporaryDirectory(prefix="klick-stand-") as tmp:
            ziel = Path(tmp)
            geholt = self._warte(ziel, heute, restzeit_s, geplant, vorher)
            yield ziel if geholt else None

    def _warte(
        self,
        ziel: Path,
        heute: str,
        restzeit_s: float,
        geplant: list[str] | None,
        vorher: list[str],
    ) -> bool:
        """Holt, prüft und wartet; ``True``, wenn ``ziel`` einen Klick-Stand trägt."""
        beginn = self.uhr()
        frist = max(0.0, min(self.warten_s, restzeit_s))
        bilanz = self.bilanz = {
            "veraltet_vorher": vorher,
            "veraltet": vorher,
            "abrufe": 0,
            "gewartet_s": 0.0,
            "klicklauf": UNBEKANNT,
            "grund": None,
        }
        geholt = False
        fertig_bestaetigt = False
        while True:
            bilanz["klicklauf"] = zustand = self.klicklauf(heute)
            try:
                dateien = self._hole(ziel)
            except (OSError, subprocess.SubprocessError, tarfile.TarError) as fehler:
                bilanz["grund"] = f"Abruf von origin/{self.zweig} gescheitert: {fehler}"
                log.warning("Klick-Stand nicht nachgeholt: %s", bilanz["grund"])
                break
            bilanz["abrufe"] += 1
            geholt = dateien > 0
            bilanz["veraltet"] = veraltet(ziel, heute, geplant) if geholt else vorher
            if not bilanz["veraltet"] or zustand == KEINER:
                break
            if zustand == FERTIG:
                if fertig_bestaetigt:
                    break
                fertig_bestaetigt = True
            if (gewartet := self.uhr() - beginn) + self.abstand_s > frist:
                bilanz["grund"] = f"nach {gewartet:.0f} s nicht vom Messtag"
                break
            self.schlafe(self.abstand_s)
        if geholt and bilanz["veraltet"] and bilanz["klicklauf"] != LAEUFT:
            self._abruf_selbst(ziel, heute, restzeit_s - (self.uhr() - beginn), geplant)
        bilanz["gewartet_s"] = round(self.uhr() - beginn, 1)
        log.info(
            "Klick-Stand: %d von %d veraltet, %d Abruf(e), %.0f s (Klick-Lauf %s)%s",
            len(bilanz["veraltet"]),
            len(vorher),
            bilanz["abrufe"],
            bilanz["gewartet_s"],
            bilanz["klicklauf"],
            f": {', '.join(bilanz['veraltet'])}" if bilanz["veraltet"] else "",
        )
        return geholt

    def _abruf_selbst(
        self, ziel: Path, heute: str, frist_s: float, geplant: list[str] | None
    ) -> None:
        """Der Anbieter, den der Zweig nicht frisch lieferte, wird selbst abgerufen.

        Nur bei erreichtem ``origin`` (``ziel`` trägt dann alle Dateien) und ohne
        laufenden Klick-Tageslauf, der denselben Host liest.
        """
        if self.erneut is None:
            return
        ergebnis = self.erneut(self.bilanz["veraltet"], ziel, heute, frist_s)
        if not ergebnis:
            return
        self.bilanz["erneut"] = ergebnis
        self.bilanz["veraltet"] = veraltet(ziel, heute, geplant)
        if not self.bilanz["veraltet"]:
            self.bilanz["grund"] = None

    def _hole(self, ziel: Path) -> int:
        """Fetch, dann ``ORDNER`` von ``FETCH_HEAD`` nach ``ziel``; Zahl der Dateien."""
        self.git(["fetch", "--no-tags", "--quiet", "origin", self.zweig])
        tar = self.git(["archive", "--format=tar", "FETCH_HEAD", ORDNER.as_posix()])
        ordnername = PurePosixPath(ORDNER.as_posix())
        for alt in ziel.glob("*.json"):
            alt.unlink()
        anzahl = 0
        with tarfile.open(fileobj=io.BytesIO(tar)) as archiv:
            for eintrag in archiv:
                name = PurePosixPath(eintrag.name)
                if not eintrag.isfile() or name.parent != ordnername:
                    continue
                if name.suffix != ".json" or name.name == STAND_DATEI:
                    continue
                inhalt = archiv.extractfile(eintrag)
                if inhalt is not None:
                    (ziel / name.name).write_bytes(inhalt.read())
                    anzahl += 1
        return anzahl


def restzeit(seit_beginn_s: float) -> float:
    """Sekunden, die dem Warten bleiben: Job abzüglich Vor-, Nachlauf und Gelaufenem."""
    return JOB_S - VORLAUF_S - NACHLAUF_S - seit_beginn_s


@contextmanager
def frischer_ordner(
    nachholen: Nachholen | None, ordner: Path | None, root: Path, heute: str
) -> Iterator[Path | None]:
    """Der Wegwerfordner mit dem frischeren Klick-Stand oder ``None``.

    Nur für den Standardordner im Arbeitsbaum: ein genannter Ordner und
    ``TELCO_KLICK_ERGEBNISSE`` gehen vor und bleiben, wie sie sind.
    """
    if nachholen is not None:
        nachholen.bilanz = {}
    if (
        nachholen is None
        or ordner is not None
        or klickordner()
        or not (root / ORDNER).is_dir()
    ):
        yield None
    else:
        with nachholen(heute, nachholen.rest()) as frisch:
            yield frisch


def nachholen_aus_umgebung(
    root: Path, umgebung: Mapping[str, str] | None = None
) -> Nachholen:
    """Das Nachholen mit echtem ``git`` und der GitHub-Auskunft aus der Umgebung."""
    umg = os.environ if umgebung is None else umgebung
    return Nachholen(
        root,
        git_im_repo(root),
        klicklauf_aus_umgebung(umg),
        zweig=umg.get(ZWEIG_VARIABLE) or ZWEIG_STANDARD,
        erneut=Erneut(
            root, abruf_im_repo(root), laufpruefung_aus_umgebung(umg), veraltet
        ),
    )
