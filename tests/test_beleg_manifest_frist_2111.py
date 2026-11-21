"""Belege-Manifest: erst das Manifest, dann das Löschen, das Löschen mit Budget.

Lauf 44858465074 (21.11.2026): fünf abgelaufene Tages-Releases mit je 824 bis 900
Bildern (``belege-2026-11-09`` bis ``-13``); ``gh release delete`` antwortet auf jedes
seit dem 20.11. mit HTTP 502. Je Release drei Versuche, und jeder Wiederholversuch
bekam das Timeout, das vor dem ersten Versuch galt: das Löschen lief über die Frist,
der Wachhund schlug nach 200 s zu, bevor das Manifest geschrieben war, und „Render
site“ meldete AUSFALL Belegbilder. Feste Daten, nie das heutige Datum.
"""

from __future__ import annotations

import json
import signal
import subprocess
import time
from datetime import date
from time import sleep as echt_schlafen

import pytest
from beleg_attrappe import AttrappeReleases
from test_beleg_skripte import HEUTE, kurze_frist, lade_skript

from telco_radar.beleg_manifest import MANIFEST_DATEI, lies, lies_manifest
from telco_radar.beleg_regeln import dateiname

AKTUELL = dateiname("g", "o2", date(2026, 11, 10))
ABGELAUFEN = ["belege-2026-10-30", "belege-2026-11-01", "belege-2026-11-02"]


def _anhaenge() -> dict[str, list[str]]:
    stand = {"belege-2026-11-10": [AKTUELL]}
    for tag in ABGELAUFEN:
        stand[tag] = [dateiname("g", "o2", date.fromisoformat(tag[7:]))]
    return stand


def _lauf(modul, tmp_path, gh=None, lauf=None) -> int:
    argv = ["--root", str(tmp_path), "--heute", HEUTE.isoformat()]
    if gh is not None:
        return modul.main(argv, gh=gh)
    return modul.main(argv, lauf=lauf)


def test_das_manifest_steht_bevor_das_erste_release_geloescht_wird(tmp_path):
    """Gegenprobe zum alten Stand: dort lief ``raeume_auf`` vor ``schreibe``."""
    pfad = tmp_path / MANIFEST_DATEI

    class Merkt(AttrappeReleases):
        manifest_beim_loeschen: list[bool] = []

        def release_loeschen(self, tag: str) -> None:
            self.manifest_beim_loeschen.append(pfad.exists())
            super().release_loeschen(tag)

    gh = Merkt(_anhaenge())
    assert _lauf(lade_skript("belege_manifest"), tmp_path, gh=gh) == 0
    assert gh.manifest_beim_loeschen == [True, True, True]
    assert gh.releases_geloescht == ABGELAUFEN
    assert [b.datum for b in lies(pfad)] == [HEUTE]


def test_ohne_loeschbudget_wird_nichts_geloescht_und_der_aufschub_benannt(
    tmp_path, monkeypatch, capsys
):
    """Das Budget ist aufgebraucht: kein ``gh``-Löschaufruf, das Manifest ist
    vollständig (kein Ausfall), das Protokoll nennt die aufgeschobenen Löschungen."""
    modul = lade_skript("belege_manifest")
    monkeypatch.setattr(modul, "LOESCH_BUDGET_S", 0.0)
    gh = AttrappeReleases(_anhaenge())
    assert _lauf(modul, tmp_path, gh=gh) == 0
    assert gh.releases_geloescht == []
    manifest = lies_manifest(tmp_path / MANIFEST_DATEI)
    assert manifest.ausfall is None
    assert [b.datum for b in manifest.belege] == [HEUTE]
    ausgabe = capsys.readouterr()
    assert "3 Löschungen aufgeschoben (Zeit)" in ausgabe.out + ausgabe.err


def test_gegenprobe_mit_budget_wird_geloescht(tmp_path, monkeypatch):
    modul = lade_skript("belege_manifest")
    monkeypatch.setattr(modul, "LOESCH_BUDGET_S", 60.0)
    gh = AttrappeReleases(_anhaenge())
    assert _lauf(modul, tmp_path, gh=gh) == 0
    assert gh.releases_geloescht == ABGELAUFEN


@pytest.mark.skipif(not hasattr(signal, "SIGALRM"), reason="Wachhund braucht SIGALRM")
def test_dauerhafter_502_beim_loeschen_kostet_nie_das_manifest(
    tmp_path, monkeypatch, capsys
):
    """Wie Lauf 44858465074, in klein: jedes ``gh release delete`` braucht 0,45 s und
    endet mit HTTP 502, die Frist ist 1 s (0,5 s Reserve). Jeder Wiederholversuch
    rechnet die Restzeit neu, das Manifest steht vorher; der Lauf endet vor dem
    Wachhund und ohne Ausfall."""
    modul = lade_skript("belege_manifest")
    kurze_frist(modul, monkeypatch)
    monkeypatch.setattr(modul.time, "sleep", lambda sekunden: None)
    zeile = "\n".join(
        json.dumps({"tag": t, "dateien": d}) for t, d in _anhaenge().items()
    )

    def lauf(argv, *, timeout, **_):
        if argv[1] == "api":
            return subprocess.CompletedProcess(argv, 0, stdout=zeile + "\n", stderr="")
        if argv[1:3] == ["release", "delete"]:
            if timeout < 0.45:
                echt_schlafen(max(timeout, 0.0))
                raise subprocess.TimeoutExpired(argv, timeout)
            echt_schlafen(0.45)
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="HTTP 502")
        raise AssertionError(f"unerwarteter Aufruf: {argv}")

    beginn = time.monotonic()
    assert _lauf(modul, tmp_path, lauf=lauf) == 0
    assert time.monotonic() - beginn < modul.GESAMT_FRIST_S
    manifest = lies_manifest(tmp_path / MANIFEST_DATEI)
    assert manifest.ausfall is None
    assert [b.datum for b in manifest.belege] == [HEUTE]
    assert "::error::Belege: Löschen gescheitert" in capsys.readouterr().err
