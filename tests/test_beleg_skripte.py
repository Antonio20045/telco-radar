"""Die zwei Workflow-Skripte der Belege, mit der Attrappe statt GitHub.

`belege_veroeffentlichen.py` (Klick-Job) und `belege_manifest.py` (Geräte-Job).
Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7).
"""

from __future__ import annotations

import importlib.util
import json
import signal
import subprocess
import time
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from beleg_attrappe import AttrappeReleases

from telco_radar.beleg_ablage import ZEIT_JE_AUFRUF_S
from telco_radar.beleg_bilanz import Bilanz
from telco_radar.beleg_manifest import MANIFEST_DATEI, lies, lies_manifest
from telco_radar.beleg_regeln import dateiname
from telco_radar.klick_vertrag import FORMAT

WURZEL = Path(__file__).resolve().parents[1]
HEUTE = date(2026, 11, 10)
GERAET = "apple-iphone-17"


def lade_skript(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        name, WURZEL / "scripts" / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def manifest_lauf(tmp_path: Path, gh: AttrappeReleases, *extra: str) -> int:
    modul = lade_skript("belege_manifest")
    argv = ["--root", str(tmp_path), "--heute", HEUTE.isoformat(), *extra]
    return modul.main(argv, gh=gh)


def test_manifest_aus_den_anhaengen_und_aufraeumen(tmp_path):
    neu = dateiname("g", "o2", date(2026, 11, 10))
    gh = AttrappeReleases(
        {
            "belege-2026-11-10": [neu, "foto.webp"],
            "belege-2026-11-01": [dateiname("g", "o2", date(2026, 11, 1))],
        }
    )
    assert manifest_lauf(tmp_path, gh) == 0
    assert gh.releases_geloescht == ["belege-2026-11-01"]
    belege = lies(tmp_path / MANIFEST_DATEI)
    assert [(b.geraet_id, b.anbieter_id, b.datum) for b in belege] == [
        ("g", "o2", HEUTE)
    ]
    daten = json.loads((tmp_path / MANIFEST_DATEI).read_text(encoding="utf-8"))
    assert daten["fremd"] == 1


def test_von_hand_hochgeladenes_bild_steht_im_manifest(tmp_path):
    hand = dateiname("g", "vodafone", date(2026, 11, 9))
    gh = AttrappeReleases({"belege-2026-11-09": [hand]})
    assert manifest_lauf(tmp_path, gh) == 0
    assert [b.anbieter_id for b in lies(tmp_path / MANIFEST_DATEI)] == ["vodafone"]


def test_nur_lesen_loescht_nichts(tmp_path):
    gh = AttrappeReleases(
        {"belege-2026-11-01": [dateiname("g", "o2", date(2026, 11, 1))]}
    )
    assert manifest_lauf(tmp_path, gh, "--nur-lesen") == 0
    assert gh.releases_geloescht == []
    assert lies(tmp_path / MANIFEST_DATEI) == []


def test_lesefehler_laesst_die_bilder_stehen_vermerkt_den_ausfall_und_endet_mit_null(
    tmp_path,
):
    pfad = tmp_path / MANIFEST_DATEI
    pfad.parent.mkdir(parents=True)
    pfad.write_text("STAND VON GESTERN", encoding="utf-8")
    assert manifest_lauf(tmp_path, AttrappeReleases(lesefehler=True)) == 0
    assert pfad.read_text(encoding="utf-8") == "STAND VON GESTERN"


def test_loeschfehler_endet_mit_null_manifest_wird_geschrieben_und_nennt_ihn(tmp_path):
    gh = AttrappeReleases(
        {"belege-2026-11-01": [dateiname("g", "o2", date(2026, 11, 1))]},
        scheitern_bei=("loeschen",),
    )
    assert manifest_lauf(tmp_path, gh) == 0
    assert lies(tmp_path / MANIFEST_DATEI) == []
    ausfall = lies_manifest(tmp_path / MANIFEST_DATEI).ausfall
    assert ausfall is not None and "Löschen gescheitert" in ausfall


def satz(tarif: float, beleg_id: str, anbieter: str = "Telekom") -> dict:
    return {
        "sku_id": "sku-1",
        "device_id": GERAET,
        "speicher_gb": 256,
        "anbieter": anbieter,
        "tarif_name": "M",
        "tarif_monatlich": tarif,
        "tarif_bindung_monate": 24,
        "geraet_zuzahlung": 100.0,
        "geraet_monatsrate": 20.0,
        "laufzeit_monate": 24,
        "anschlusspreis": 0.0,
        "beleg_id": beleg_id,
        "quelle_art": "klick",
        "zustand": "neu",
        "abgerufen_am": "2026-11-09",
    }


@pytest.fixture
def aufbau(tmp_path, monkeypatch):
    """Wurzel mit Bestand, ein Artefaktordner mit Ergebnis und Bild; Modul."""
    wurzel = tmp_path / "wurzel"
    (wurzel / "data" / "state").mkdir(parents=True)
    quelle = tmp_path / "artefakt" / "telekom"
    quelle.mkdir(parents=True)
    modul = lade_skript("belege_veroeffentlichen")
    monkeypatch.setattr(modul, "lade_katalog", lambda root: None)
    monkeypatch.setattr(modul, "geraet_aus_sku", lambda sku, katalog: (GERAET, 256))
    monkeypatch.setattr(
        modul,
        "ausbeute",
        lambda daten, katalog: SimpleNamespace(rohsaetze=daten["roh"]),
    )

    def lege(bestand: list[dict], roh: list[dict]) -> Path:
        bestand_pfad = wurzel / modul.TCO_DATEI
        bestand_pfad.write_text(json.dumps({"buendel": bestand}), encoding="utf-8")
        (quelle / "ergebnis.json").write_text(
            json.dumps({"format": FORMAT, "anbieter": "Telekom", "roh": roh}),
            encoding="utf-8",
        )
        for eintrag in roh:
            (quelle / f"{eintrag['beleg_id']}.webp").write_bytes(b"RIFFxxxxWEBP")
        return wurzel

    return SimpleNamespace(modul=modul, lege=lege, quelle=quelle.parent)


def veroeffentliche(aufbau, wurzel: Path, gh: AttrappeReleases) -> int:
    argv = ["--root", str(wurzel), "--quelle", str(aufbau.quelle)]
    argv += ["--heute", HEUTE.isoformat()]
    return aufbau.modul.main(argv, gh=gh)


def test_kleine_aenderung_nur_im_tagesrelease_mit_katalognamen(aufbau):
    bestand = [{**satz(30.0, "alt"), "pruefung": "gueltig"}]
    wurzel = aufbau.lege(bestand, [satz(29.0, "b1")])
    gh = AttrappeReleases()
    assert veroeffentliche(aufbau, wurzel, gh) == 0
    name = "apple-iphone-17-256__telekom__2026-11-10.webp"
    assert gh.stand == {"belege-2026-11-10": [name]}


def test_grosse_aenderung_zusaetzlich_im_monatsrelease(aufbau):
    bestand = [{**satz(30.0, "alt"), "pruefung": "gueltig"}]
    wurzel = aufbau.lege(bestand, [satz(24.0, "b1")])
    gh = AttrappeReleases()
    assert veroeffentliche(aufbau, wurzel, gh) == 0
    name = "apple-iphone-17-256__telekom__2026-11-10.webp"
    assert gh.stand == {"belege-2026-11-10": [name], "belege-gross-2026-11": [name]}


def test_billigerer_fremder_tarif_im_bestand_macht_nichts_gross(aufbau):
    """Vorher: Minimum aller Tarife, 30 € gegen 20 € galt als groß."""
    bestand = [
        {**satz(30.0, "alt"), "pruefung": "gueltig"},
        {**satz(20.0, "alt2"), "tarif_name": "L", "pruefung": "gueltig"},
    ]
    wurzel = aufbau.lege(bestand, [satz(30.0, "b1")])
    gh = AttrappeReleases()
    assert veroeffentliche(aufbau, wurzel, gh) == 0
    assert sorted(gh.stand) == ["belege-2026-11-10"]


def test_unbrauchbarer_anbietername_stoppt_die_anderen_bilder_nicht(aufbau):
    """Ein Name ohne ASCII-Zeichen ergab einen ValueError und brach ab."""
    wurzel = aufbau.lege([], [satz(30.0, "b1", anbieter="Телеком")])
    (aufbau.quelle / "telekom" / "ergebnis2.json").write_text(
        json.dumps(
            {"format": FORMAT, "anbieter": "o2", "roh": [satz(20.0, "b2", "o2")]}
        ),
        encoding="utf-8",
    )
    (aufbau.quelle / "telekom" / "b2.webp").write_bytes(b"RIFFxxxxWEBP")
    gh = AttrappeReleases()
    assert veroeffentliche(aufbau, wurzel, gh) == 0
    namen = [n for _, liste in gh.hochgeladen for n in liste]
    assert any("__o2__" in n for n in namen)
    assert any("__anbieter-" in n for n in namen)


def test_ausfall_wird_im_manifest_vermerkt_und_haengt_nicht_an_der_seite(tmp_path):
    """Scheitert der Schritt, kennt die Seite den Grund (CLAUDE.md Regel 6)."""
    alt = dateiname("g", "o2", date(2026, 11, 9))
    assert manifest_lauf(tmp_path, AttrappeReleases({"belege-2026-11-09": [alt]})) == 0
    assert manifest_lauf(tmp_path, AttrappeReleases(lesefehler=True)) == 0
    manifest = lies_manifest(tmp_path / MANIFEST_DATEI)
    assert [b.anbieter_id for b in manifest.belege] == ["o2"]
    assert manifest.ausfall is not None and "Releases nicht lesbar" in manifest.ausfall
    assert manifest_lauf(tmp_path, AttrappeReleases({"belege-2026-11-09": [alt]})) == 0
    assert lies_manifest(tmp_path / MANIFEST_DATEI).ausfall is None


def _api_antwort(tag: str, datei: str) -> subprocess.CompletedProcess:
    zeile = json.dumps({"tag": tag, "dateien": [datei]})
    return subprocess.CompletedProcess([], 0, stdout=zeile + "\n", stderr="")


def test_ein_voruebergehender_502_bei_release_delete_wird_wiederholt_kein_ausfall(
    tmp_path, monkeypatch
):
    """Lauf 43581672834: ein einzelner 502 bei `gh release delete` machte den
    Schritt und danach „Render site“ rot. Ein Retry rettet ihn."""
    modul = lade_skript("belege_manifest")
    monkeypatch.setattr(modul.time, "sleep", lambda sekunden: None)
    tag, datei = "belege-2026-11-01", dateiname("g", "o2", date(2026, 11, 1))
    versuche = {"delete": 0}

    def lauf(argv, **kwargs):
        if argv[1] == "api":
            return _api_antwort(tag, datei)
        if argv[1:3] == ["release", "delete"]:
            versuche["delete"] += 1
            if versuche["delete"] == 1:
                return subprocess.CompletedProcess(
                    argv, 1, stdout="", stderr="HTTP 502"
                )
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise AssertionError(f"unerwarteter Aufruf: {argv}")

    argv = ["--root", str(tmp_path), "--heute", HEUTE.isoformat()]
    assert modul.main(argv, lauf=lauf) == 0
    assert versuche["delete"] == 2
    assert lies_manifest(tmp_path / MANIFEST_DATEI).ausfall is None


def test_dauerhafter_502_bei_release_delete_bleibt_ein_ausfall(tmp_path, monkeypatch):
    """Nach erschöpften Versuchen gilt weiter Regel 6: der Ausfall steht im
    Manifest, nicht „still“ weiterlaufen."""
    modul = lade_skript("belege_manifest")
    monkeypatch.setattr(modul.time, "sleep", lambda sekunden: None)
    tag, datei = "belege-2026-11-01", dateiname("g", "o2", date(2026, 11, 1))
    versuche = {"delete": 0}

    def lauf(argv, **kwargs):
        if argv[1] == "api":
            return _api_antwort(tag, datei)
        if argv[1:3] == ["release", "delete"]:
            versuche["delete"] += 1
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="HTTP 502")
        raise AssertionError(f"unerwarteter Aufruf: {argv}")

    argv = ["--root", str(tmp_path), "--heute", HEUTE.isoformat()]
    assert modul.main(argv, lauf=lauf) == 0
    assert versuche["delete"] == modul.VERSUCHE_GH
    ausfall = lies_manifest(tmp_path / MANIFEST_DATEI).ausfall
    assert ausfall is not None and "Löschen gescheitert" in ausfall


def test_403_bei_release_delete_wird_nicht_wiederholt(tmp_path, monkeypatch):
    """Ein Logikfehler (403) ist kein Netzproblem: kein Retry, sofort der Ausfall."""
    modul = lade_skript("belege_manifest")
    monkeypatch.setattr(modul.time, "sleep", lambda sekunden: None)
    tag, datei = "belege-2026-11-01", dateiname("g", "o2", date(2026, 11, 1))
    versuche = {"delete": 0}

    def lauf(argv, **kwargs):
        if argv[1] == "api":
            return _api_antwort(tag, datei)
        if argv[1:3] == ["release", "delete"]:
            versuche["delete"] += 1
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="HTTP 403")
        raise AssertionError(f"unerwarteter Aufruf: {argv}")

    argv = ["--root", str(tmp_path), "--heute", HEUTE.isoformat()]
    assert modul.main(argv, lauf=lauf) == 0
    assert versuche["delete"] == 1
    ausfall = lies_manifest(tmp_path / MANIFEST_DATEI).ausfall
    assert ausfall is not None and "Löschen gescheitert" in ausfall


def test_melde_ausfall_ohne_netz_vermerkt_den_grund(tmp_path):
    modul = lade_skript("belege_manifest")
    argv = ["--root", str(tmp_path), "--heute", HEUTE.isoformat()]
    assert modul.main([*argv, "--melde-ausfall", "Exit 124"], gh=None) == 0
    ausfall = lies_manifest(tmp_path / MANIFEST_DATEI).ausfall
    assert ausfall == "2026-11-10: Exit 124"


def test_ohne_bestandssatz_ist_nichts_gross(aufbau):
    wurzel = aufbau.lege([], [satz(5.0, "b1")])
    gh = AttrappeReleases()
    assert veroeffentliche(aufbau, wurzel, gh) == 0
    assert sorted(gh.stand) == ["belege-2026-11-10"]


def test_nur_der_billigste_preis_je_geraet_und_anbieter_bekommt_ein_bild(aufbau):
    wurzel = aufbau.lege([], [satz(30.0, "teuer"), satz(25.0, "billig")])
    gh = AttrappeReleases()
    assert veroeffentliche(aufbau, wurzel, gh) == 0
    assert len(gh.hochgeladen) == 1


def test_mehrere_jobs_desselben_anbieters_ergeben_ein_bild_mit_dem_niedrigsten_preis(
    aufbau,
):
    """Regression 04./05.11.2026: telekom, telekom-2 … messen dasselbe Gerät; jeder
    Name geht einmal hoch, mit dem billigsten Preis über alle Ergebnisse."""
    wurzel = aufbau.lege([], [satz(30.0, "job1")])
    zweiter = aufbau.quelle / "telekom-2"
    zweiter.mkdir()
    (zweiter / "ergebnis.json").write_text(
        json.dumps(
            {"format": FORMAT, "anbieter": "Telekom", "roh": [satz(25.0, "job2")]}
        ),
        encoding="utf-8",
    )
    (zweiter / "job2.webp").write_bytes(b"RIFFyyyyWEBP")
    hochgeladen: list[bytes] = []

    class Mitschnitt(AttrappeReleases):
        def hochladen(self, tag, dateien):
            hochgeladen.extend(d.read_bytes() for d in dateien)
            super().hochladen(tag, dateien)

    gh = Mitschnitt()
    assert veroeffentliche(aufbau, wurzel, gh) == 0
    assert [len(namen) for _, namen in gh.hochgeladen] == [1]
    assert hochgeladen == [b"RIFFyyyyWEBP"]


def _zweiter_job(aufbau, roh: dict, inhalt: bytes) -> None:
    zweiter = aufbau.quelle / "telekom-2"
    zweiter.mkdir()
    (zweiter / "ergebnis.json").write_text(
        json.dumps({"format": FORMAT, "anbieter": "Telekom", "roh": [roh]}),
        encoding="utf-8",
    )
    (zweiter / f"{roh['beleg_id']}.webp").write_bytes(inhalt)


def _hochgeladene_inhalte(aufbau, wurzel: Path) -> list[bytes]:
    inhalte: list[bytes] = []

    class Mitschnitt(AttrappeReleases):
        def hochladen(self, tag, dateien):
            inhalte.extend(d.read_bytes() for d in dateien)
            super().hochladen(tag, dateien)

    assert veroeffentliche(aufbau, wurzel, Mitschnitt()) == 0
    return inhalte


@pytest.mark.parametrize("erst,zweit", [("a1", "b2"), ("b2", "a1")])
def test_gleicher_preis_ueber_jobs_nimmt_die_kleinere_beleg_id_in_jeder_reihenfolge(
    aufbau, erst, zweit
):
    wurzel = aufbau.lege([], [satz(30.0, erst)])
    (aufbau.quelle / "telekom" / f"{erst}.webp").write_bytes(f"RIFF{erst}".encode())
    _zweiter_job(aufbau, satz(30.0, zweit), f"RIFF{zweit}".encode())
    assert _hochgeladene_inhalte(aufbau, wurzel) == [b"RIFFa1"]


@pytest.mark.parametrize("job_ohne_preis", ["telekom", "telekom-2"])
def test_zahl_schlaegt_luecke_ueber_jobs_in_jeder_reihenfolge(aufbau, job_ohne_preis):
    """Ein Satz ohne Tarifpreis (Gesamtkosten ``None``) verliert gegen jede Zahl,
    auch gegen eine teure, egal ob sein Job zuerst oder zuletzt kommt."""
    ohne = {**satz(30.0, "a1"), "tarif_monatlich": None}
    mit = satz(90.0, "b2")
    erster, zweiter = (ohne, mit) if job_ohne_preis == "telekom" else (mit, ohne)
    wurzel = aufbau.lege([], [erster])
    (aufbau.quelle / "telekom" / f"{erster['beleg_id']}.webp").write_bytes(
        f"RIFF{erster['beleg_id']}".encode()
    )
    _zweiter_job(aufbau, zweiter, f"RIFF{zweiter['beleg_id']}".encode())
    assert _hochgeladene_inhalte(aufbau, wurzel) == [b"RIFFb2"]


def test_fehlt_das_bild_wird_nichts_vorgetaeuscht(aufbau):
    wurzel = aufbau.lege([], [satz(30.0, "b1")])
    (aufbau.quelle / "telekom" / "b1.webp").unlink()
    gh = AttrappeReleases()
    assert veroeffentliche(aufbau, wurzel, gh) == 0
    assert gh.stand == {}


def test_github_fehler_gibt_exit_eins(aufbau):
    wurzel = aufbau.lege([], [satz(30.0, "b1")])
    assert veroeffentliche(aufbau, wurzel, AttrappeReleases(lesefehler=True)) == 1


def test_fehlender_artefaktordner_ist_nichts_zu_tun(aufbau, tmp_path):
    wurzel = aufbau.lege([], [])
    argv = ["--root", str(wurzel), "--quelle", str(tmp_path / "gibt-es-nicht")]
    assert aufbau.modul.main(argv, gh=AttrappeReleases()) == 0


def test_fehlender_bestand_ist_exit_zwei(aufbau, tmp_path):
    argv = ["--root", str(tmp_path / "leer"), "--quelle", str(aufbau.quelle)]
    assert aufbau.modul.main(argv, gh=AttrappeReleases()) == 2


def haengendes_gh(argv, *, timeout, **_):
    """Wie ``subprocess.run``, wenn ``gh`` hängt: schläft bis zum Timeout (höchstens
    5 s, damit ein Fehler den Test nicht blockiert), dann ``TimeoutExpired``."""
    time.sleep(min(timeout, 5.0))
    raise subprocess.TimeoutExpired(argv, timeout)


def kurze_frist(modul, monkeypatch, gesamt: float = 1.0, reserve: float = 0.5) -> None:
    monkeypatch.setattr(modul, "GESAMT_FRIST_S", gesamt)
    monkeypatch.setattr(modul, "SCHREIB_RESERVE_S", reserve)


def test_haengendes_gh_endet_in_der_frist_mit_null_und_vermerkt_den_ausfall(
    tmp_path, monkeypatch, capsys
):
    """Der Schritt in geraete.yml darf den Commit des Messtags nie sperren."""
    modul = lade_skript("belege_manifest")
    kurze_frist(modul, monkeypatch)
    alt = dateiname("g", "o2", date(2026, 11, 9))
    assert manifest_lauf(tmp_path, AttrappeReleases({"belege-2026-11-09": [alt]})) == 0
    argv = ["--root", str(tmp_path), "--heute", HEUTE.isoformat()]
    beginn = time.monotonic()
    assert modul.main(argv, lauf=haengendes_gh) == 0
    assert time.monotonic() - beginn < 3.0
    manifest = lies_manifest(tmp_path / MANIFEST_DATEI)
    assert [b.anbieter_id for b in manifest.belege] == ["o2"]
    assert manifest.ausfall is not None and "Releases nicht lesbar" in manifest.ausfall
    assert "Belege-Manifest nicht erneuert" in capsys.readouterr().err


@pytest.mark.skipif(not hasattr(signal, "SIGALRM"), reason="Wachhund braucht SIGALRM")
def test_gh_das_sein_timeout_ignoriert_trifft_den_wachhund(tmp_path, monkeypatch):
    modul = lade_skript("belege_manifest")
    kurze_frist(modul, monkeypatch)

    def taub(argv, *, timeout, **_):
        time.sleep(5.0)
        raise AssertionError("der Wachhund hätte vorher zuschlagen müssen")

    argv = ["--root", str(tmp_path), "--heute", HEUTE.isoformat()]
    beginn = time.monotonic()
    assert modul.main(argv, lauf=taub) == 0
    assert time.monotonic() - beginn < 3.0
    ausfall = lies_manifest(tmp_path / MANIFEST_DATEI).ausfall
    assert ausfall is not None and "Gesamtfrist von 1 s überschritten" in ausfall
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0.0


def test_unerwarteter_dateifehler_endet_mit_null_und_steht_im_manifest(tmp_path):
    class Kaputt(AttrappeReleases):
        def anhaenge(self):
            raise OSError("Platte voll")

    assert manifest_lauf(tmp_path, Kaputt()) == 0
    ausfall = lies_manifest(tmp_path / MANIFEST_DATEI).ausfall
    assert ausfall is not None and "OSError: Platte voll" in ausfall


def test_frist_des_skripts_liegt_deutlich_unter_dem_schritt_timeout():
    modul = lade_skript("belege_manifest")
    assert modul.GESAMT_FRIST_S + 60 <= modul.SCHRITT_FRIST_S
    assert 0 < modul.SCHREIB_RESERVE_S < modul.GESAMT_FRIST_S


def test_wirksame_frist_zieht_die_zeit_eines_aufrufs_ab():
    """2100 ist die Frist in klick.yml; zu große und kleine Werte: Gegenprobe."""
    modul = lade_skript("belege_veroeffentlichen")
    assert modul.wirksame_frist(2100) == 1800
    assert modul.wirksame_frist(1800) == 1500
    assert modul.wirksame_frist(modul.JOB_ENDE_S) == modul.JOB_FRIST_S
    assert modul.wirksame_frist(9999) == modul.JOB_FRIST_S
    assert modul.wirksame_frist(100) == 0.0


def test_ein_letzter_aufruf_endet_vor_dem_job_timeout():
    modul = lade_skript("belege_veroeffentlichen")
    job_s = modul.JOB_MINUTEN * 60
    for uebergeben in (0, 600, 1800, 2100, 2399, 2400, 5000):
        letzter_beginn = modul.wirksame_frist(uebergeben)
        assert letzter_beginn + ZEIT_JE_AUFRUF_S + modul.PUFFER_S <= job_s


def test_veroeffentlichen_rechnet_die_wirksame_frist_ab_jobstart(aufbau, monkeypatch):
    """Zweiter Aufruf: der Job lief schon 600 s (Start 9400 statt 10000)."""
    wurzel = aufbau.lege([], [])
    modul = aufbau.modul
    gesehen: list[float] = []

    def merke(bilder, heute, gh, frist_ende=None, **_):
        gesehen.append(frist_ende)
        return Bilanz()

    monkeypatch.setattr(modul, "veroeffentliche", merke)
    monkeypatch.setattr(
        modul,
        "time",
        SimpleNamespace(time=lambda: 10_000.0, monotonic=lambda: 50.0),
    )
    argv = ["--root", str(wurzel), "--quelle", str(aufbau.quelle)]
    argv += ["--job-frist-sekunden", "2100", "--job-start", "10000"]
    assert modul.main(argv, gh=AttrappeReleases()) == 0
    argv[-1] = "9400"
    assert modul.main(argv, gh=AttrappeReleases()) == 0
    assert gesehen == [50.0 + 1800, 50.0 + 1200]


def test_jobstart_in_der_zukunft_verlaengert_die_frist_nicht(aufbau, monkeypatch):
    """Uhrversatz zwischen Läufern: die Frist bleibt höchstens ``JOB_FRIST_S``."""
    wurzel = aufbau.lege([], [])
    modul = aufbau.modul
    gesehen: list[float] = []

    def merke(bilder, heute, gh, frist_ende=None, **_):
        gesehen.append(frist_ende)
        return Bilanz()

    monkeypatch.setattr(modul, "veroeffentliche", merke)
    monkeypatch.setattr(
        modul, "time", SimpleNamespace(time=lambda: 10_000.0, monotonic=lambda: 50.0)
    )
    argv = ["--root", str(wurzel), "--quelle", str(aufbau.quelle)]
    argv += ["--job-frist-sekunden", "2100", "--job-start", "10100"]
    assert modul.main(argv, gh=AttrappeReleases()) == 0
    assert gesehen == [50.0 + modul.JOB_FRIST_S]


def test_klick_job_loescht_keine_bilder_einer_frueheren_position(aufbau):
    """Zweiter Klick-Lauf am selben Tag mit neuer Position (Befund N1): der Job lädt das
    neue Einzelbild hoch und lässt die früheren Bilder liegen. Gelöscht wird erst im
    Gerätelauf, nachdem das Manifest auf die neuen zeigt (``test_beleg_veraltet``)."""
    alt = "apple-iphone-17-256__telekom__2026-11-10__{}__" + "1" * 16 + ".webp"
    liegt = [alt.format(s) for s in ("preis", "tarif")]
    gh = AttrappeReleases({"belege-2026-11-10": list(liegt)})
    wurzel = aufbau.lege([], [satz(29.0, "2" * 64)])
    assert veroeffentliche(aufbau, wurzel, gh) == 0
    neu = "apple-iphone-17-256__telekom__2026-11-10__preis__" + "2" * 16 + ".webp"
    assert gh.assets_geloescht == []
    assert sorted(gh.stand["belege-2026-11-10"]) == sorted([*liegt, neu])
