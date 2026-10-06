"""Regeln der Klick-Erkundung im Browser: Bot-Schutz sofort, nichts Geheimes, Lücken.

Ein lokaler Server auf 127.0.0.1 liefert BEISPIEL-Seiten (wie in
``test_geraete_klickerkundung``). Geprüft wird: nach einer 403 der eigenen Website geht
keine Anfrage mehr hinaus, weder eine danach gestellte noch eine, die schon auf den Host
wartete; ein per Set-Cookie erneuerter Cookie-Wert, ein Token in einem Link und eine
Sitzungskennung in einer JSON-Antwort stehen in keiner Datei; eine leere Seite heißt
``leer`` mit Grund; ein Gerätelauf vor der zweiten Seite verschiebt den Rest ohne
Anfrage; vom Ergebnis kommen nur Strukturdaten auf den öffentlichen Zweig.
"""

from __future__ import annotations

import gzip
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from klickserver import JETZT, Antwort, html, klickserver

from scripts import erkundung_ablegen
from telco_radar.collect.geraete.klickerkundung import VERSCHOBEN, erkunde_anbieter
from telco_radar.collect.geraete.klickseite import LAUF_LEER
from telco_radar.collect.geraete.klickziele import Erkundungsziel, Seitenziel

OFFEN = "User-agent: *\nDisallow:\n"
TAG = JETZT.date().isoformat()
SPEICHER = """<div id="speicher" aria-label="Speicher">
 <button aria-pressed="false">128 GB</button><button aria-pressed="true">256 GB</button>
</div><p>Monatliche Rate <span id="rate">35,00 €</span></p>"""


def _alle_texte(ordner: Path) -> str:
    texte = []
    for datei in sorted(ordner.iterdir()):
        roh = datei.read_bytes()
        if datei.name.endswith(".gz"):
            roh = gzip.decompress(roh)
        texte.append(roh.decode("utf-8", errors="replace"))
    return "\n".join(texte)


def _ziel(server, *pfade: str, abstand: float = 0.0) -> Erkundungsziel:
    seiten = tuple(Seitenziel("beispielhandy-x", 256, server.adresse(p)) for p in pfade)
    return Erkundungsziel("beispiel", "Beispielanbieter", seiten, None, abstand)


def _erkunde(chromium, ziel, ausgabe, **weiter) -> dict:
    def hole(url: str) -> tuple[int, str]:
        return 200, OFFEN

    ende = time.monotonic() + 300
    return erkunde_anbieter(
        chromium, ziel, lambda: JETZT, hole, ausgabe, ende, **weiter
    )


def _seite_mit(skript: str) -> str:
    return (
        f"<!doctype html><html><body>{SPEICHER}<script>{skript}</script></body></html>"
    )


def _mit_sperre(seite: str, **weitere: Antwort):
    def antworte(pfad: str) -> Antwort:
        teil = urlsplit(pfad).path
        if teil.startswith("/handy/"):
            return html(seite)
        if teil in weitere:
            return weitere[teil]
        return Antwort(200, "application/json", "{}")

    return antworte


SPERRE = Antwort(403, "application/json", json.dumps({"fehler": "verboten"}))


@pytest.mark.parametrize("abstand", [0.0, 2.0], ids=["ohne_abstand", "abstand_2s"])
def test_nach_403_geht_keine_folgeanfrage_hinaus(chromium, tmp_path, abstand):
    folge = 'fetch("/api/preis").then(() => fetch("/api/nachher")).catch(() => {});'
    antworte = _mit_sperre(_seite_mit(folge), **{"/api/preis": SPERRE})
    with klickserver(antworte) as server:
        index = _erkunde(
            chromium, _ziel(server, "/handy/x", "/handy/y", abstand=abstand), tmp_path
        )
        sperre = next(t for t, p in server.fertig if p.startswith("/api/preis"))
        danach = [p for t, p in server.zeiten if t > sperre]

    assert danach == []
    erste = index["seiten"][0]
    assert (erste["status"], erste["bot_schutz"]) == ("gestoert", True)
    assert "HTTP 403" in erste["grund"]


def test_wartende_anfrage_geht_nach_der_403_nicht_hinaus(chromium, tmp_path):
    zwei = 'setTimeout(() => fetch("/api/zwei").catch(() => {}), 100);'
    skript = 'fetch("/api/preis").catch(() => {});' + zwei
    langsam = Antwort(403, "application/json", '{"fehler": 1}', verzug=1.0)
    antworte = _mit_sperre(_seite_mit(skript), **{"/api/preis": langsam})
    with klickserver(antworte) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x"), tmp_path)

    assert server.mit("/api/zwei") == []
    assert index["seiten"][0]["bot_schutz"] is True


ALT, NEU = "ALTERKEKSWERT1234", "NEUERKEKSWERT5678"


def test_erneuerter_cookie_wert_steht_in_keiner_datei(chromium, tmp_path):
    skript = (
        'fetch("/api/eins").then(r => r.text()).then(t => {'
        ' document.getElementById("rate").innerText = t;'
        ' return fetch("/api/zwei"); }).catch(() => {});'
    )

    def antworte(pfad: str) -> Antwort:
        teil = urlsplit(pfad).path
        if teil.startswith("/handy/"):
            kopf = {"Set-Cookie": f"sitzung={ALT}; Path=/"}
            return Antwort(200, "text/html; charset=utf-8", _seite_mit(skript), kopf)
        if teil == "/api/eins":
            return Antwort(200, "application/json", json.dumps({"sitzung": ALT}))
        kopf = {"Set-Cookie": f"sitzung={NEU}; Path=/"}
        return Antwort(200, "application/json", "{}", kopf)

    with klickserver(antworte) as server:
        _erkunde(chromium, _ziel(server, "/handy/x"), tmp_path)

    alles = _alle_texte(tmp_path / "beispiel" / TAG)
    assert ALT not in alles and NEU not in alles
    assert "[Cookie entfernt]" in alles


def test_token_im_link_und_sitzungskennung_stehen_in_keiner_datei(chromium, tmp_path):
    link = '<a href="/konto?token=LINKTOKEN4711&ziel=start">Mein Konto</a>'
    skript = 'fetch("/api/sitzung").catch(() => {});'
    seite = link + _seite_mit(skript)
    sitzung = Antwort(
        200, "application/json", json.dumps({"sessionId": "SITZUNG0815", "rate": 35})
    )
    with klickserver(_mit_sperre(seite, **{"/api/sitzung": sitzung})) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x"), tmp_path)

    alles = _alle_texte(tmp_path / "beispiel" / TAG)
    assert "LINKTOKEN4711" not in alles and "SITZUNG0815" not in alles
    assert "token=ENTFERNT&ziel=start" in alles
    assert '\\"sessionId\\": \\"ENTFERNT\\", \\"rate\\": 35' in alles
    assert index["seiten"][0]["zaehlung"]["mitschnitt"] >= 1


def test_leere_seite_heisst_leer_mit_grund(chromium, tmp_path):
    huelle = '<!doctype html><html><body><div id="app"></div></body></html>'
    with klickserver(lambda pfad: html(huelle)) as server:
        index = _erkunde(chromium, _ziel(server, "/handy/x", "/handy/y"), tmp_path)

    assert [s["status"] for s in index["seiten"]] == [LAUF_LEER] * 2
    grund = "kein Bedienelement und kein Preis-Kandidat"
    assert index["seiten"][0]["grund"] == grund
    assert (index["status"], index["grund"]) == (LAUF_LEER, f"Seite 1: {grund}")


def test_geraetelauf_vor_der_zweiten_seite_verschiebt_den_rest(chromium, tmp_path):
    antworten = iter([None, "Gerätelauf läuft (geraete.yml, queued)"])
    with klickserver(_mit_sperre(_seite_mit(""))) as server:
        ziel = _ziel(server, "/handy/x", "/handy/y")
        index = _erkunde(chromium, ziel, tmp_path, laeufe=lambda: next(antworten))

    assert server.mit("/handy/y") == []
    assert [s["status"] for s in index["seiten"]] == ["gelesen", VERSCHOBEN]
    assert index["status"] == VERSCHOBEN
    assert index["grund"] == "Seite 2: Gerätelauf läuft (geraete.yml, queued)"


def test_auf_den_zweig_kommen_nur_strukturdaten_ohne_leck(chromium, tmp_path):
    with klickserver(_mit_sperre(_seite_mit(""))) as server:
        artefakt = tmp_path / "neu" / "erkundung-beispiel"
        _erkunde(chromium, _ziel(server, "/handy/x"), artefakt)

    abgelegt = erkundung_ablegen.einsortieren(tmp_path / "neu", tmp_path / "zweig")

    assert abgelegt == ["beispiel"]
    namen = sorted(p.name for p in (tmp_path / "zweig" / "beispiel" / TAG).iterdir())
    assert namen == [
        "bedienelemente-1.json",
        "index.json",
        "klicks-1.json",
        "mitschnitt-1.json",
        "preise-1.json",
    ]
    assert erkundung_ablegen.pruefe(tmp_path / "zweig") == []
