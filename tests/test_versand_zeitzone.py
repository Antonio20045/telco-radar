"""Abnahme V1: das Zustellbuch merkt den Versandzeitpunkt mit Zeitzone (UTC).

Geprüft wird nur von außen: ``Zustellbuch`` und ``versende`` schreiben
``versand.json``, der Test liest die Datei zurück. Kein Wert hängt von der
Uhrzeit ab; verlangt wird nur, dass ``gesendet`` eine UTC-Angabe trägt.
"""

from __future__ import annotations

import json
import socket
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from telco_radar import versand

BERICHT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "bestand"
    / "2026-10-03"
    / "reports"
    / "2026-10-02.json"
)


def _versatz(eintrag: dict) -> timedelta | None:
    """UTC-Versatz von ``gesendet``; ``None``, wenn keine Zeitzone dabeisteht."""
    return datetime.fromisoformat(str(eintrag.get("gesendet"))).utcoffset()


def _lies(pfad: Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


def test_merke_schreibt_gesendet_mit_utc(tmp_path):
    pfad = tmp_path / "versand.json"
    buch = versand.Zustellbuch(pfad)
    buch.merke("mail", "2026-10-02", "Betreff")
    buch.merke("teams", "https://x.test/a", "Titel")

    daten = _lies(pfad)
    for eintrag in (daten["mail"]["2026-10-02"], daten["teams"]["https://x.test/a"]):
        assert _versatz(eintrag) is not None, (
            f"gesendet ohne Zeitzone: {eintrag['gesendet']!r}"
        )
        assert _versatz(eintrag) == timedelta(0), (
            f"gesendet nicht in UTC: {eintrag['gesendet']!r}"
        )


def test_versende_merkt_mail_mit_utc(tmp_path, monkeypatch):
    report = json.loads(BERICHT.read_text(encoding="utf-8"))
    monkeypatch.setattr(versand, "sende_mail", lambda *a, **k: "an 1 Empfänger")
    bilanz = versand.versende(
        tmp_path, report, {"versand": {"teams_aktiv": False}}, erzwinge=True
    )
    assert bilanz["mail"] == "an 1 Empfänger"

    daten = _lies(tmp_path / "data" / "state" / "versand.json")
    eintrag = daten["mail"][report["date"]]
    assert _versatz(eintrag) is not None, (
        f"gesendet ohne Zeitzone: {eintrag['gesendet']!r}"
    )
    assert _versatz(eintrag) == timedelta(0), (
        f"gesendet nicht in UTC: {eintrag['gesendet']!r}"
    )


def test_wiederholung_ersetzt_nur_den_eigenen_eintrag(tmp_path):
    pfad = tmp_path / "versand.json"
    buch = versand.Zustellbuch(pfad)
    buch.merke("mail", "a", "erste")
    buch.merke("mail", "b", "andere")
    vorher_b = _lies(pfad)["mail"]["b"]

    buch.merke("mail", "a", "zweite")

    daten = _lies(pfad)
    assert daten["mail"]["a"]["notiz"] == "zweite"
    assert daten["mail"]["b"] == vorher_b
    assert sorted(daten["mail"]) == ["a", "b"]
    assert versand.Zustellbuch(pfad).schon_raus("mail", "a")


def test_mail_und_teams_bleiben_getrennt(tmp_path):
    pfad = tmp_path / "versand.json"
    buch = versand.Zustellbuch(pfad)
    buch.merke("mail", "x", "mail-notiz")
    buch.merke("teams", "x", "teams-notiz")

    daten = _lies(pfad)
    assert daten["mail"]["x"]["notiz"] == "mail-notiz"
    assert daten["teams"]["x"]["notiz"] == "teams-notiz"
    neu = versand.Zustellbuch(pfad)
    assert neu.schon_raus("mail", "x") and neu.schon_raus("teams", "x")


def test_merke_ruft_kein_netz(tmp_path, monkeypatch):
    def kein_netz(*a, **k):
        raise AssertionError("merke hat das Netz gerufen")

    monkeypatch.setattr(httpx, "post", kein_netz)
    monkeypatch.setattr(socket.socket, "connect", kein_netz)
    monkeypatch.setattr(socket, "create_connection", kein_netz)

    versand.Zustellbuch(tmp_path / "versand.json").merke("mail", "a", "n")


def test_schreibfehler_geht_an_den_aufrufer(tmp_path):
    sperre = tmp_path / "state"
    sperre.write_text("eine Datei, kein Ordner", encoding="utf-8")
    buch = versand.Zustellbuch(sperre / "versand.json")
    with pytest.raises(OSError):
        buch.merke("mail", "a", "n")
