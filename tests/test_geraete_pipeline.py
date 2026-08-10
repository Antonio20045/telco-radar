"""Die Geraetestufe als Ganzes: sammeln, aufnehmen, altern, speichern.

Die eine Regel, die diese Datei traegt: `mark_stale` laeuft NUR fuer
Anbieter, deren Bilanz vollstaendig ist. Ein Teilausfall, ein Fristablauf,
eine gesperrte oder ausserhalb ihrer Besuchszeit liegende Quelle heissen
alle "nicht gelesen" - und was nicht gelesen wurde, altert nicht.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from telco_radar.analyze.geraete_store import (
    GeraeteDB,
    STATUS_AKTIV,
    STATUS_VERMUTLICH,
)
from telco_radar.geraete_pipeline import run_geraete_stage

_FIX = Path(__file__).parent / "fixtures" / "geraete"

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro Max", "generation": 17,
     "speicher": [256, 512, 1024], "segment": "flagship"},
    {"hersteller": "Samsung", "modell": "Galaxy A57", "generation": 57,
     "speicher": [128, 256], "segment": "mid"},
]}

_FARBEN = {"farben": {"titan-natur": ["Titannatur"], "schwarz": ["Black"]}}

_QUELLEN = {"anbieter": [
    {"name": "Medimax", "typ": "handel", "methode": "ldjson", "rang": 1,
     "basis_url": "https://www.medimax.de", "rate_limit_sekunden": 0,
     "einstiege": [{"url": "https://www.medimax.de/c/116/smartphones",
                    "label": "Smartphones", "pfadmuster": "/p/"}]},
    {"name": "Amazon", "typ": "handel", "methode": "deaktiviert", "rang": 2,
     "aktiv": False, "grund": "erfordert Product-Advertising-API-Zugang"},
]}

_SEITEN = {
    "https://www.medimax.de/c/116/smartphones":
        (_FIX / "medimax_kategorie.html").read_text(encoding="utf-8"),
    "https://www.medimax.de/p/1518897/galaxy-a57-5g-a576b-128gb":
        (_FIX / "medimax_produkt_a57.html").read_text(encoding="utf-8"),
    "https://www.medimax.de/p/1514136/iphone-17-pro-max-256gb":
        (_FIX / "medimax_produkt.html").read_text(encoding="utf-8"),
    "https://www.medimax.de/p/1514200/huelle-iphone-17":
        "<html><body>Zubehör</body></html>",
}


def _root(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(exist_ok=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (tmp_path / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    return tmp_path


def _hole(seiten=None, protokoll=None):
    seiten = _SEITEN if seiten is None else seiten

    def hole(url):
        if protokoll is not None:
            protokoll.append(url)
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /cart\n")
        return (200, seiten[url]) if url in seiten else (404, "")
    return hole


def _jetzt(stunde=3):
    return datetime(2026, 8, 11, stunde, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------

def test_lauf_schreibt_datenbank_und_historie(tmp_path):
    root = _root(tmp_path)
    bilanz = run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(),
                               hole=_hole())
    assert bilanz["status"] == "ok"
    assert bilanz["listungen"] == 2 and bilanz["neu"] == 2
    assert bilanz["preispunkte"] == 2

    db = json.loads((root / "data" / "state" / "geraete_db.json").read_text(encoding="utf-8"))
    assert db["updated"] == "2026-08-11" and len(db["listungen"]) == 2
    zeilen = (root / "data" / "state" / "geraete_preise.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 2
    preise = sorted(json.loads(z)["preis_ohne_vertrag"] for z in zeilen)
    assert preise == [349.0, 1449.0]


def test_jeder_anbieter_taucht_in_der_bilanz_auf(tmp_path):
    """Akzeptanzkriterium aus Teil E: kein Anbieter fehlt stillschweigend."""
    bilanz = run_geraete_stage(_root(tmp_path), {}, "2026-08-11",
                               jetzt=_jetzt(), hole=_hole())
    namen = {a["anbieter"] for a in bilanz["anbieter"]}
    assert namen == {"Medimax", "Amazon"}
    amazon = [a for a in bilanz["anbieter"] if a["anbieter"] == "Amazon"][0]
    assert amazon["status"] == "uebersprungen" and amazon["grund"]


def test_zweiter_lauf_ohne_treffer_altert_nur_eine_stufe(tmp_path):
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    leer = dict(_SEITEN)
    leer["https://www.medimax.de/c/116/smartphones"] = "<html><body></body></html>"
    bilanz = run_geraete_stage(root, {}, "2026-08-14", jetzt=_jetzt(),
                               hole=_hole(leer))
    assert bilanz["gealtert"] == 2
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert {e["status"] for e in db.eintraege()} == {STATUS_VERMUTLICH}


def test_ein_ausgefallener_anbieter_altert_nichts(tmp_path):
    """Der Kern: 404 auf die Einstiegsseite heisst 'nicht gelesen', nicht
    'keine Geraete mehr da'."""
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    bilanz = run_geraete_stage(root, {}, "2026-08-14", jetzt=_jetzt(),
                               hole=_hole({}))
    assert bilanz["gealtert"] == 0
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert {e["status"] for e in db.eintraege()} == {STATUS_AKTIV}
    medimax = [a for a in bilanz["anbieter"] if a["anbieter"] == "Medimax"][0]
    assert medimax["status"] == "fehler" and medimax["vollstaendig"] is False


def test_ausserhalb_der_besuchszeit_wird_weder_geholt_noch_gealtert(tmp_path):
    """Der Befund, der den Zeitplan bestimmt: medimax.de erlaubt Abrufe nur
    zwischen 02:00 und 08:00 UTC, der Wochenlauf startet 08:30."""
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(3), hole=_hole())

    protokoll = []

    def hole(url):
        protokoll.append(url)
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nVisit-time: 0200-0800\n")
        return (200, _SEITEN[url]) if url in _SEITEN else (404, "")

    bilanz = run_geraete_stage(root, {}, "2026-08-14", jetzt=_jetzt(8),
                               hole=hole)
    assert bilanz["gealtert"] == 0
    assert [u for u in protokoll if "/p/" in u] == []
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert {e["status"] for e in db.eintraege()} == {STATUS_AKTIV}


def test_unveraenderter_preis_schreibt_keinen_zweiten_punkt(tmp_path):
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    bilanz = run_geraete_stage(root, {}, "2026-08-14", jetzt=_jetzt(),
                               hole=_hole())
    assert bilanz["preispunkte"] == 0
    zeilen = (root / "data" / "state" / "geraete_preise.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 2


def test_zeitbudget_bricht_sauber_ab(tmp_path):
    """Teil F: bei Fristablauf sauber abbrechen, Teilergebnis speichern, im
    Protokoll vermerken - und nichts altern."""
    root = _root(tmp_path)
    bilanz = run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(),
                               hole=_hole(), frist_sekunden=0.0001)
    medimax = [a for a in bilanz["anbieter"] if a["anbieter"] == "Medimax"][0]
    assert medimax["status"] == "frist"
    assert medimax["vollstaendig"] is False
    assert bilanz["gealtert"] == 0


def test_ohne_konfiguration_tut_die_stufe_nichts(tmp_path):
    (tmp_path / "config").mkdir()
    bilanz = run_geraete_stage(tmp_path, {}, "2026-08-11", jetzt=_jetzt(),
                               hole=_hole())
    assert bilanz["status"] == "keine Konfiguration"
    assert not (tmp_path / "data").exists()


def test_hardware_vermarktung_zaehlt_nur_gelesene_laeufe(tmp_path):
    """Ein ausgefallener Abruf darf keine Marke zum SIM-only-Anbieter
    erklaeren."""
    root = _root(tmp_path)
    for tag in ("2026-08-11", "2026-08-14", "2026-08-18"):
        run_geraete_stage(root, {}, tag, jetzt=_jetzt(), hole=_hole({}))
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert db.hardware_vermarktung("Medimax") == "unbekannt"


def test_drei_leere_aber_gelesene_laeufe_ergeben_sim_only(tmp_path):
    root = _root(tmp_path)
    leer = dict(_SEITEN)
    leer["https://www.medimax.de/c/116/smartphones"] = "<html><body></body></html>"
    for tag in ("2026-08-11", "2026-08-14", "2026-08-18"):
        run_geraete_stage(root, {}, tag, jetzt=_jetzt(), hole=_hole(leer))
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert db.hardware_vermarktung("Medimax") == "nein"


def test_nichts_wird_ausserhalb_von_data_state_geschrieben(tmp_path):
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    geschrieben = {p.relative_to(root).as_posix()
                   for p in root.rglob("*") if p.is_file()}
    ausserhalb = {p for p in geschrieben
                  if not p.startswith(("config/", "data/state/"))}
    assert ausserhalb == set()
