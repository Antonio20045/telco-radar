"""Rahmen der Tests: hermetisch, Uhr aus dem Schnappschuss, Chromium je Worker.

Ein Audit-Hook lässt jeden Zugriff auf ``data/`` und ``site/`` scheitern, außer aus den
Testdateien in ``pruef/tests-mit-bestand.txt``, und jede Namensauflösung oder Verbindung
außer zu 127.0.0.1. Ein geschluckter Verstoß macht den Test im Abbau rot. Tests lesen
den Bestand aus ``tests/fixtures/bestand/<datum>/`` (``scripts/schnappschuss.py``), die
Uhr kommt aus dessen ``_herkunft.json``.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
TESTS = f"{WURZEL / 'tests'}{os.sep}"
GESPERRT = tuple(f"{WURZEL / name}" for name in ("data", "site"))
ALTLASTEN = WURZEL / "pruef" / "tests-mit-bestand.txt"
SCHNAPPSCHUSS = WURZEL / "tests" / "fixtures" / "bestand" / "2026-10-03"
PROTOKOLL_VARIABLE = "TELCO_TESTS_BESTAND_PROTOKOLL"
REGEL_BESTAND = (
    "Regel hermetisch: Tests lesen nur Schnappschüsse, siehe tests/fixtures/bestand"
)
REGEL_NETZ = "Regel hermetisch: Tests rufen kein Netz, erlaubt ist nur 127.0.0.1"
PROXY_VARIABLEN = frozenset({"http_proxy", "https_proxy", "all_proxy"})
LOKAL = frozenset({"127.0.0.1", "localhost", "::1", ""})
DATEI_EREIGNISSE = frozenset(
    {
        "open",
        "os.chdir",
        "os.listdir",
        "os.scandir",
        "os.remove",
        "os.rename",
        "os.mkdir",
        "os.rmdir",
        "os.truncate",
        "os.utime",
        "os.chmod",
        "os.link",
        "os.symlink",
        "shutil.rmtree",
        "glob.glob",
    }
)
NETZ_EREIGNISSE = frozenset(
    {"socket.getaddrinfo", "socket.gethostbyname", "socket.connect", "socket.sendto"}
)
CHROMIUM_ORTE = (
    "/opt/pw-browsers/chromium-*/chrome-linux/chrome",
    str(Path.home() / ".cache/ms-playwright" / "chromium*/chrome-linux*/chrome"),
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
# Chromium löst keinen Namen außer localhost auf und schickt alles, was nicht lokal
# ist, an einen toten Proxy; 127.0.0.1 umgeht den Proxy von selbst.
CHROMIUM_NUR_LOKAL = (
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
    "--proxy-server=http://127.0.0.1:9",
)


class HermetikVerstoss(RuntimeError):
    """Ein Test griff auf den echten Bestand oder ins Netz."""


_altlasten = frozenset(
    ALTLASTEN.read_text(encoding="utf-8").split() if ALTLASTEN.exists() else ()
)
_verstoesse: list[str] = []
_gemeldet = [0]
_protokolliert: set[str] = set()
_aktiv = [True]


def _testdatei() -> str | None:
    """Nennt die Testdatei des laufenden Tests, sonst (beim Sammeln) die äußerste
    Testdatei im Aufrufstapel; ein Helfer aus einer anderen Datei erbt nichts."""
    laufend = os.environ.get("PYTEST_CURRENT_TEST", "")
    if laufend:
        return laufend.split("::", 1)[0]
    gefunden = None
    rahmen = sys._getframe(2)
    while rahmen is not None:
        name = rahmen.f_code.co_filename
        if name.startswith(TESTS) and not name.endswith(f"{os.sep}conftest.py"):
            gefunden = Path(name).relative_to(WURZEL).as_posix()
        rahmen = rahmen.f_back
    return gefunden


def _gesperrt(name: str) -> str | None:
    for pfad in {os.path.abspath(name), os.path.realpath(name)}:
        if any(pfad == g or pfad.startswith(f"{g}{os.sep}") for g in GESPERRT):
            return pfad
    return None


def _gesperrter_pfad(ereignis: str, argumente: tuple[object, ...]) -> str | None:
    """Ein Name ohne Trenner aus ``os.open`` oder mit ``dir_fd`` kann relativ zu einem
    Ordner-Deskriptor sein (``rmtree``) statt zum Arbeitsordner; er zählt nicht."""
    mit_fd = ereignis == "open" or any(type(a) is int for a in argumente[1:])
    for argument in argumente:
        if isinstance(argument, str | bytes | os.PathLike):
            name = os.fsdecode(argument)
            if mit_fd and os.sep not in name:
                continue
            pfad = _gesperrt(name)
            if pfad is not None:
                return pfad
    return None


def _kindprozess_pfad(argumente: tuple[object, ...]) -> str | None:
    """Pfade in den Argumenten oder im Arbeitsordner eines Kindprozesses."""
    _, befehl, ordner, _ = (*argumente, None, None, None, None)[:4]
    teile = befehl if isinstance(befehl, list | tuple) else [befehl]
    basis = os.fsdecode(ordner) if ordner is not None else os.getcwd()
    for teil in [*teile, basis]:
        if isinstance(teil, str | bytes | os.PathLike):
            for name in os.fsdecode(teil).split():
                ort = os.path.join(basis, name)
                if os.sep in name and (pfad := _gesperrt(ort)) is not None:
                    return pfad
    return None


def _fremder_host(ereignis: str, argumente: tuple[object, ...]) -> str | None:
    if ereignis in ("socket.connect", "socket.sendto"):
        adresse = argumente[1] if len(argumente) > 1 else None
        if not isinstance(adresse, tuple) or not adresse:
            return None
        host = adresse[0]
    else:
        host = argumente[0] if argumente else None
    if host is None:
        return None
    name = os.fsdecode(host) if isinstance(host, str | bytes) else str(host)
    return None if name in LOKAL else name


def _protokolliere(datei: str) -> None:
    ordner = os.environ.get(PROTOKOLL_VARIABLE)
    if not ordner or datei in _protokolliert:
        return
    _protokolliert.add(datei)
    kennung = os.open(
        os.path.join(ordner, f"{os.getpid()}.txt"),
        os.O_WRONLY | os.O_APPEND | os.O_CREAT,
        0o600,
    )
    try:
        os.write(kennung, f"{datei}\n".encode())
    finally:
        os.close(kennung)


def _verstoss(meldung: str) -> None:
    _verstoesse.append(meldung)
    raise HermetikVerstoss(meldung)


def _hermetik(ereignis: str, argumente: tuple[object, ...]) -> None:
    if not _aktiv[0]:
        return
    if ereignis in DATEI_EREIGNISSE or ereignis == "subprocess.Popen":
        if ereignis == "subprocess.Popen":
            pfad = _kindprozess_pfad(argumente)
        else:
            pfad = _gesperrter_pfad(ereignis, argumente)
        if pfad is None:
            return
        datei = _testdatei()
        if datei in _altlasten:
            _protokolliere(datei)
            return
        relativ = os.path.relpath(pfad, os.path.dirname(GESPERRT[0]))
        _verstoss(f"{REGEL_BESTAND} ({datei or 'unbekannt'} griff auf {relativ})")
    elif ereignis in NETZ_EREIGNISSE:
        host = _fremder_host(ereignis, argumente)
        if host is not None:
            _verstoss(f"{REGEL_NETZ} ({_testdatei() or 'unbekannt'} wollte {host})")


# Ein pytest im Kindprozess erbt die Variable des Elternlaufs; sie gilt hier nicht.
os.environ.pop("PYTEST_CURRENT_TEST", None)
# Ein lokaler Proxy würde jeden Abruf über 127.0.0.1 leiten und so an der Sperre
# vorbeiführen; ohne ihn löst der Client den Namen selbst auf und scheitert hier.
for _variable in [v for v in os.environ if v.lower() in PROXY_VARIABLEN]:
    del os.environ[_variable]
sys.addaudithook(_hermetik)


def pytest_unconfigure(config: pytest.Config) -> None:
    _aktiv[0] = False


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Setzt den Marker ``browser`` an jedem Test mit der Fixture ``chromium``."""
    for item in items:
        if "chromium" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.browser)


@pytest.fixture(autouse=True)
def _hermetisch_geblieben():
    """Macht einen Verstoß rot, den der Code unter Test geschluckt hat."""
    yield
    neu = _verstoesse[_gemeldet[0] :]
    _gemeldet[0] = len(_verstoesse)
    if neu:
        pytest.fail("\n".join(neu), pytrace=False)


@pytest.fixture(scope="session")
def herkunft() -> dict:
    """Die ``_herkunft.json`` des Schnappschusses, aus dem die Tests lesen."""
    return json.loads((SCHNAPPSCHUSS / "_herkunft.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def bestand() -> Path:
    """Ordner des Schnappschusses; enthält ``state/`` und ``reports/`` wie ``data/``."""
    return SCHNAPPSCHUSS


@pytest.fixture(scope="session")
def jetzt(herkunft: dict) -> dt.datetime:
    """Die Uhr der Tests: Zeit des Bot-Commits, aus dem der Schnappschuss stammt."""
    return dt.datetime.fromisoformat(herkunft["zeit"]).astimezone(dt.UTC)


@pytest.fixture(scope="session")
def heute(jetzt: dt.datetime) -> dt.date:
    """Der Tag der Tests in UTC, aus dem Schnappschuss."""
    return jetzt.date()


def chromium_pfad() -> str | None:
    for muster in CHROMIUM_ORTE:
        treffer = sorted(glob.glob(muster))
        if treffer:
            return treffer[-1]
    return None


@pytest.fixture(scope="session")
def chromium():
    """Ein Chromium je Worker, das nur lokale Adressen erreicht; Tests öffnen darin
    eigene Seiten oder Kontexte und schließen sie selbst, nie den Browser."""
    sync_api = pytest.importorskip("playwright.sync_api", reason="playwright fehlt")
    with sync_api.sync_playwright() as playwright:
        pfad = chromium_pfad()
        browser = playwright.chromium.launch(
            args=list(CHROMIUM_NUR_LOKAL), **({"executable_path": pfad} if pfad else {})
        )
        try:
            yield browser
        finally:
            browser.close()
