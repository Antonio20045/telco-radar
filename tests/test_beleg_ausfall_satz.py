"""Issue #130: kein Befehl und kein Statuscode als Erstes auf der Geräteseite.

Am 14.11.2026 stand unter dem Kopfbild „Nicht neu gebaut: Belegbilder (Manifest nicht
erneuert, … gh release delete: Exit 1: HTTP 502 …)“, obwohl das Manifest frisch war und
nur das Löschen einer abgelaufenen Bildersammlung gescheitert war.

Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7).
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import date

from test_beleg_bildfolge_weg import baue_seite
from test_beleg_skripte import HEUTE as LAUFTAG
from test_beleg_skripte import lade_skript

from telco_radar.beleg_manifest import (
    MANIFEST_DATEI,
    MANIFEST_NAME,
    baue_manifest,
    lies_manifest,
    schreibe,
)
from telco_radar.beleg_regeln import dateiname
from telco_radar.report import geraete_belege
from telco_radar.report.geraete_belege import SATZ_FEHLEN, TEIL

TECHNIK = "belege-2026-11-06 nicht gelöscht: gh release delete: Exit 1: HTTP 502"
STAND = date(2026, 11, 13)
SATZ = (
    "Die Belegbilder sind auf dem Stand vom 13.11.2026; "
    "die Preise sind davon nicht betroffen."
)


def test_gescheitertes_loeschen_ist_kein_ausfall_der_seite_und_steht_im_protokoll(
    tmp_path, monkeypatch, capsys
):
    modul = lade_skript("belege_manifest")
    monkeypatch.setattr(modul.time, "sleep", lambda sekunden: None)
    alt = dateiname("g", "o2", date(2026, 11, 1))
    neu = dateiname("g", "o2", LAUFTAG)
    geloescht: list[str] = []

    def lauf(argv, **kwargs):
        if argv[1] == "api":
            zeilen = [
                json.dumps({"tag": "belege-2026-11-01", "dateien": [alt]}),
                json.dumps({"tag": f"belege-{LAUFTAG.isoformat()}", "dateien": [neu]}),
            ]
            return subprocess.CompletedProcess(
                argv, 0, stdout="\n".join(zeilen) + "\n", stderr=""
            )
        if argv[1:3] == ["release", "delete"]:
            geloescht.append(argv[3])
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="HTTP 502")
        raise AssertionError(f"unerwarteter Aufruf: {argv}")

    argv = ["--root", str(tmp_path), "--heute", LAUFTAG.isoformat()]
    assert modul.main(argv, lauf=lauf) == 0
    manifest = lies_manifest(tmp_path / MANIFEST_DATEI)
    assert [(b.geraet_id, b.datum) for b in manifest.belege] == [("g", LAUFTAG)]
    assert manifest.ausfall is None
    assert manifest.erstellt == LAUFTAG
    assert geloescht and set(geloescht) == {"belege-2026-11-01"}
    fehler = capsys.readouterr().err
    assert "::error::" in fehler and "nicht gelöscht" in fehler and "502" in fehler


def test_gegenprobe_releases_nicht_lesbar_bleibt_ein_ausfall(tmp_path):
    modul = lade_skript("belege_manifest")
    schreibe(tmp_path / MANIFEST_DATEI, baue_manifest({}, STAND))

    def lauf(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="HTTP 403")

    argv = ["--root", str(tmp_path), "--heute", LAUFTAG.isoformat()]
    assert modul.main(argv, lauf=lauf) == 0
    manifest = lies_manifest(tmp_path / MANIFEST_DATEI)
    assert manifest.ausfall is not None and "Releases nicht lesbar" in manifest.ausfall
    assert manifest.erstellt == STAND


class Umgebung:
    """Mimt die Jinja-Umgebung, die `installiere` mit `env.globals` füllt."""

    def __init__(self) -> None:
        self.globals: dict = {}


def manifest_vom_13(grund: str | None) -> dict:
    """Manifest vom 13.11. mit einem Bild; ``grund`` vermerkt den Ausfall vom 14.11."""
    bild = dateiname("g", "o2", STAND)
    manifest = baue_manifest({f"belege-{STAND.isoformat()}": [bild]}, STAND)
    if grund:
        manifest["ausfall"] = f"2026-11-14: {grund}"
    return manifest


def ausfaelle_fuer(ordner, manifest: dict | str) -> list:
    inhalt = manifest if isinstance(manifest, str) else json.dumps(manifest)
    (ordner / MANIFEST_NAME).write_text(inhalt, encoding="utf-8")
    return geraete_belege.installiere(Umgebung(), ordner, [{"date": "2026-11-14"}])


def hinweis(site) -> str:
    seite = (site / "geraete.html").read_text(encoding="utf-8")
    if 'id="ausfaelle"' not in seite:
        return ""
    anfang = seite.index('id="ausfaelle"')
    return seite[anfang : seite.index("</p>", anfang)]


def test_ausfall_traegt_den_satz_und_behaelt_den_technischen_grund(tmp_path):
    (ausfall,) = ausfaelle_fuer(tmp_path, manifest_vom_13(TECHNIK))
    assert (ausfall.teil, ausfall.satz) == (TEIL, SATZ)
    assert TECHNIK in ausfall.grund


def test_vermerk_ohne_bilder_nennt_fehlende_bilder_statt_eines_stands(tmp_path):
    leer = {**baue_manifest({}, STAND), "ausfall": f"2026-11-14: {TECHNIK}"}
    (ausfall,) = ausfaelle_fuer(tmp_path, leer)
    assert ausfall.satz == SATZ_FEHLEN


def test_unlesbares_manifest_nennt_fehlende_bilder_ohne_technik(tmp_path):
    (ausfall,) = ausfaelle_fuer(tmp_path, "{kaputt")
    assert ausfall.satz == SATZ_FEHLEN
    assert "BelegManifestFehler" in ausfall.grund


def test_gegenprobe_ohne_vermerk_kein_ausfall(tmp_path):
    assert ausfaelle_fuer(tmp_path, manifest_vom_13(None)) == []


def test_seite_zeigt_den_satz_ohne_befehl_und_statuscode(tmp_path, caplog):
    with caplog.at_level(logging.ERROR):
        site = baue_seite(tmp_path, manifest_vom_13(TECHNIK), "0" * 16)
    text = hinweis(site)
    assert SATZ in text
    for wort in ("gh release", "HTTP 502", "Exit 1", "Manifest nicht erneuert"):
        assert wort not in text, wort
    assert TECHNIK in caplog.text


def test_gegenprobe_seite_ohne_vermerk_nennt_keine_belegbilder(tmp_path):
    site = baue_seite(tmp_path, manifest_vom_13(None), "0" * 16)
    assert "Belegbilder" not in hinweis(site)
