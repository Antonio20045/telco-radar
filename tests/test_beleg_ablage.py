"""Ablage der Belegbilder in Releases: Hochladen, Aufräumen, Fehler, Zeit.

Eine Attrappe ersetzt GitHub; feste Daten, nie das heutige Datum.
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import pytest
from beleg_attrappe import AttrappeReleases

from telco_radar import beleg_ablage
from telco_radar.beleg_ablage import (
    Bild,
    Gh,
    GhFehler,
    raeume_auf,
    veroeffentliche,
)
from telco_radar.beleg_bilanz import Bilanz
from telco_radar.beleg_regeln import dateiname

HEUTE = date(2026, 11, 10)


def bild(tmp_path: Path, geraet: str, anbieter: str, gross: bool = False) -> Bild:
    datei = tmp_path / dateiname(geraet, anbieter, HEUTE)
    datei.write_bytes(b"RIFF")
    return Bild(datei, gross)


def test_bild_geht_ins_tagesrelease_und_legt_es_an(tmp_path):
    gh = AttrappeReleases()
    bilanz = veroeffentliche([bild(tmp_path, "g", "o2")], HEUTE, gh)
    assert gh.angelegt == ["belege-2026-11-10"]
    assert gh.hochgeladen == [("belege-2026-11-10", ["g__o2__2026-11-10.webp"])]
    assert (bilanz.hochgeladen, bilanz.gross, bilanz.fehler) == (1, 0, [])


def test_grosse_aenderung_geht_zusaetzlich_ins_monatsrelease(tmp_path):
    gh = AttrappeReleases()
    bilder = [bild(tmp_path, "g", "o2", gross=True), bild(tmp_path, "g", "telekom")]
    bilanz = veroeffentliche(bilder, HEUTE, gh)
    assert sorted(gh.stand) == ["belege-2026-11-10", "belege-gross-2026-11"]
    assert gh.stand["belege-gross-2026-11"] == ["g__o2__2026-11-10.webp"]
    assert len(gh.stand["belege-2026-11-10"]) == 2
    assert (bilanz.hochgeladen, bilanz.gross) == (2, 1)


def test_derselbe_dateiname_geht_nie_zweimal_in_ein_paket(tmp_path):
    """Regression 04./05.11.2026: mehrere Telekom-Jobs liefern dasselbe Bild; zweimal
    derselbe Name im Paket scheiterte bei GitHub mit HTTP 404 (``--clobber``)."""
    erstes, zweites = tmp_path / "a", tmp_path / "b"
    erstes.mkdir()
    zweites.mkdir()
    bilder = [bild(erstes, "g", "telekom"), bild(zweites, "g", "telekom")]
    bilder.append(bild(tmp_path, "h", "telekom", gross=True))
    gh = AttrappeReleases()
    bilanz = veroeffentliche(bilder, HEUTE, gh)
    assert bilanz.fehler == [] and bilanz.fehlgeschlagen == 0
    assert gh.hochgeladen[0][1] == [
        "g__telekom__2026-11-10.webp",
        "h__telekom__2026-11-10.webp",
    ]
    assert (bilanz.hochgeladen, bilanz.gross) == (2, 1)


def test_doppelte_namen_stehen_in_einer_protokollzeile(tmp_path):
    ordner = []
    for name in ("a", "b", "c"):
        (tmp_path / name).mkdir()
        ordner.append(tmp_path / name)
    bilder = [bild(o, g, "telekom") for o in ordner for g in ("g1", "g2")]
    bilanz = veroeffentliche(bilder, HEUTE, AttrappeReleases())
    assert bilanz.doppelt == [
        "g1__telekom__2026-11-10.webp",
        "g2__telekom__2026-11-10.webp",
    ]
    zeilen = bilanz.hinweise()
    assert len(zeilen) == 1
    assert "2 Dateinamen mehrfach" in zeilen[0]
    assert "g1__telekom__2026-11-10.webp" in zeilen[0]


def test_ohne_doppelte_namen_keine_hinweiszeile(tmp_path):
    bilanz = veroeffentliche([bild(tmp_path, "g", "o2")], HEUTE, AttrappeReleases())
    assert bilanz.doppelt == [] and bilanz.hinweise() == []


def test_hinweiszeile_kuerzt_lange_listen():
    bilanz = Bilanz(doppelt=[f"g{i}.webp" for i in range(8)])
    (zeile,) = bilanz.hinweise()
    assert "8 Dateinamen mehrfach" in zeile and zeile.endswith("und 3 weitere")


def test_attrappe_scheitert_wie_github_bei_doppeltem_namen(tmp_path):
    """Gegenprobe: ohne die Zusammenführung wäre der Test oben rot."""
    erstes, zweites = tmp_path / "a", tmp_path / "b"
    erstes.mkdir()
    zweites.mkdir()
    doppelt = [bild(erstes, "g", "o2").datei, bild(zweites, "g", "o2").datei]
    with pytest.raises(GhFehler, match="HTTP 404"):
        AttrappeReleases().hochladen("belege-2026-11-10", doppelt)


def test_vorhandenes_release_wird_nicht_neu_angelegt(tmp_path):
    gh = AttrappeReleases({"belege-2026-11-10": ["x__y__2026-11-10.webp"]})
    veroeffentliche([bild(tmp_path, "g", "o2")], HEUTE, gh)
    assert gh.angelegt == []


def test_ohne_bilder_kein_zugriff_auf_github():
    gh = AttrappeReleases(lesefehler=True)
    bilanz = veroeffentliche([], HEUTE, gh)
    assert bilanz.fehler == [] and gh.angelegt == [] and gh.hochgeladen == []


def test_pakete_und_volles_release_bekommt_zaehler(tmp_path, monkeypatch):
    monkeypatch.setattr(beleg_ablage, "PAKET", 2)
    monkeypatch.setattr(beleg_ablage, "MAX_ANHAENGE_JE_RELEASE", 3)
    gh = AttrappeReleases()
    bilder = [bild(tmp_path, f"g{i}", "o2") for i in range(5)]
    veroeffentliche(bilder, HEUTE, gh)
    assert sorted(gh.stand) == ["belege-2026-11-10", "belege-2026-11-10-2"]
    assert [len(gh.stand[t]) for t in sorted(gh.stand)] == [3, 2]
    assert [len(d) for _, d in gh.hochgeladen] == [2, 1, 2]


def test_lesefehler_laedt_nichts_hoch_und_steht_in_der_bilanz(tmp_path):
    gh = AttrappeReleases(lesefehler=True)
    bilanz = veroeffentliche([bild(tmp_path, "g", "o2")], HEUTE, gh)
    assert gh.hochgeladen == []
    assert (bilanz.fehlgeschlagen, bilanz.ausgelassen) == (1, 0)
    assert "nicht lesbar" in bilanz.fehler[0]


def test_fehler_im_tagesrelease_stoppt_das_monatsrelease_nicht(tmp_path):
    gh = AttrappeReleases(scheitern_bei=("belege-2026-11-10",))
    bilanz = veroeffentliche([bild(tmp_path, "g", "o2", gross=True)], HEUTE, gh)
    assert gh.stand.get("belege-gross-2026-11") == ["g__o2__2026-11-10.webp"]
    assert len(bilanz.fehler) == 1
    assert (bilanz.fehlgeschlagen, bilanz.ausgelassen) == (1, 0)
    assert bilanz.gross == 1


def test_frist_vorbei_laesst_aus_und_zaehlt(tmp_path):
    gh = AttrappeReleases()
    bilder = [bild(tmp_path, "g", "o2"), bild(tmp_path, "g", "telekom")]
    bilanz = veroeffentliche(bilder, HEUTE, gh, frist_ende=100.0, uhr=lambda: 100.0)
    assert gh.angelegt == [] and gh.hochgeladen == []
    assert (bilanz.hochgeladen, bilanz.ausgelassen) == (0, 2)


def test_frist_laeuft_zwischen_den_paketen_ab(tmp_path, monkeypatch):
    monkeypatch.setattr(beleg_ablage, "PAKET", 1)
    gh = AttrappeReleases()
    zeiten = iter([0.0, 0.0, 200.0, 300.0])
    bilder = [bild(tmp_path, f"g{i}", "o2") for i in range(3)]
    bilanz = veroeffentliche(
        bilder, HEUTE, gh, frist_ende=100.0, uhr=lambda: next(zeiten)
    )
    assert bilanz.hochgeladen == 1
    assert bilanz.ausgelassen == 2


def test_aufraeumen_loescht_abgelaufene_releases_nur_im_schema():
    gh = AttrappeReleases()
    anhaenge = {
        "belege-2026-11-02": ["a__b__2026-11-02.webp"],
        "belege-2026-11-03": ["a__b__2026-11-03.webp"],
        "belege-gross-2026-07": ["a__b__2026-07-10.webp"],
        "belege-gross-2026-09": ["a__b__2026-09-10.webp"],
    }
    bilanz, rest = raeume_auf(anhaenge, HEUTE, gh)
    assert gh.releases_geloescht == ["belege-2026-11-02", "belege-gross-2026-07"]
    assert sorted(rest) == ["belege-2026-11-03", "belege-gross-2026-09"]
    assert bilanz.releases_geloescht == gh.releases_geloescht


def test_aufraeumen_loescht_alte_bilder_im_jungen_monatsrelease():
    gh = AttrappeReleases({"belege-gross-2026-11": ["a__b__2026-11-02.webp"]})
    anhaenge = {
        "belege-gross-2026-11": [
            "a__b__2026-11-02.webp",
            "a__o2__2026-11-09.webp",
            "foto.webp",
        ]
    }
    bilanz, rest = raeume_auf(anhaenge, HEUTE, gh)
    assert gh.assets_geloescht == []
    assert len(rest["belege-gross-2026-11"]) == 3
    assert bilanz.assets_geloescht == 0


def test_aufraeumen_loescht_einzelne_alte_bilder_ueber_neunzig_tage():
    heute = date(2027, 2, 15)
    gh = AttrappeReleases(
        {"belege-gross-2026-11": ["a__b__2026-11-02.webp", "a__b__2026-11-20.webp"]}
    )
    anhaenge = gh.anhaenge()
    bilanz, rest = raeume_auf(anhaenge, heute, gh)
    assert gh.assets_geloescht == [("belege-gross-2026-11", "a__b__2026-11-02.webp")]
    assert rest == {"belege-gross-2026-11": ["a__b__2026-11-20.webp"]}
    assert bilanz.assets_geloescht == 1


def test_aufraeumen_fasst_fremde_dateien_nie_an():
    gh = AttrappeReleases({"belege-2026-11-10": ["foto.webp"]})
    bilanz, rest = raeume_auf(gh.anhaenge(), HEUTE, gh)
    assert gh.assets_geloescht == [] and gh.releases_geloescht == []
    assert rest == {"belege-2026-11-10": ["foto.webp"]}
    assert bilanz.fehler == []


def test_loeschfehler_steht_in_der_bilanz_und_der_rest_laeuft_weiter():
    gh = AttrappeReleases(scheitern_bei=("belege-2026-11-01",))
    anhaenge = {
        "belege-2026-11-01": ["a__b__2026-11-01.webp"],
        "belege-2026-10-30": ["a__b__2026-10-30.webp"],
    }
    bilanz, rest = raeume_auf(anhaenge, HEUTE, gh)
    assert gh.releases_geloescht == ["belege-2026-10-30"]
    assert len(bilanz.fehler) == 1
    assert "belege-2026-11-01" in rest


class Lauf:
    """Fängt die gh-Aufrufe ab."""

    def __init__(self, antwort: str = "", code: int = 0, stderr: str = "") -> None:
        self.aufrufe: list[list[str]] = []
        self.antwort = subprocess.CompletedProcess([], code, antwort, stderr)

    def __call__(self, argv):
        self.aufrufe.append(list(argv))
        return self.antwort


def test_gh_liest_nur_belege_releases_aus_jsonzeilen():
    zeilen = "\n".join(
        [
            '{"tag":"belege-2026-11-10","dateien":["b.webp","a.webp"]}',
            '{"tag":"v1.0","dateien":["programm.zip"]}',
            "",
            '{"tag":"belege-gross-2026-11","dateien":[]}',
        ]
    )
    gh = Gh(runner=Lauf(zeilen))
    assert gh.anhaenge() == {
        "belege-2026-11-10": ["a.webp", "b.webp"],
        "belege-gross-2026-11": [],
    }


def test_gh_fehler_wird_zur_benannten_ausnahme_ohne_token():
    gh = Gh(runner=Lauf(code=1, stderr="x\nHTTP 403: Resource not accessible"))
    with pytest.raises(GhFehler) as fehler:
        gh.anhaenge()
    assert "403" in str(fehler.value)


def test_gh_unlesbare_antwort_ist_kein_leeres_ergebnis():
    with pytest.raises(GhFehler):
        Gh(runner=Lauf("kein json")).anhaenge()


def test_gh_timeout_wird_zur_ausnahme():
    def runner(argv):
        raise subprocess.TimeoutExpired(argv, 1)

    with pytest.raises(GhFehler):
        Gh(runner=runner).anhaenge()


def test_gh_aufrufe_pre_release_clobber_und_cleanup():
    lauf = Lauf()
    gh = Gh(runner=lauf, repo="o/r")
    gh.release_anlegen("belege-2026-11-10", "Belege 2026-11-10")
    gh.hochladen("belege-2026-11-10", [Path("a.webp")])
    gh.release_loeschen("belege-2026-11-10")
    gh.asset_loeschen("belege-gross-2026-11", "a.webp")
    anlegen, hoch, weg, asset = lauf.aufrufe
    assert "--prerelease" in anlegen and "--latest=false" in anlegen
    assert "--clobber" in hoch and hoch[hoch.index("--repo") + 1] == "o/r"
    assert "--cleanup-tag" in weg and "--yes" in weg
    assert asset[:3] == ["gh", "release", "delete-asset"]


def test_runner_mit_frist_nimmt_die_restzeit_als_timeout():
    gesehen: list[float] = []

    def lauf(argv, *, timeout, **_):
        gesehen.append(timeout)
        return subprocess.CompletedProcess(argv, 0, "", "")

    runner = beleg_ablage.runner_mit_frist(1000.0, uhr=lambda: 990.0, lauf=lauf)
    runner(["gh", "api"])
    fern = beleg_ablage.runner_mit_frist(1e9, uhr=lambda: 990.0, lauf=lauf)
    fern(["gh", "api"])
    assert gesehen == [10.0, beleg_ablage.ZEIT_JE_AUFRUF_S]


def test_runner_mit_frist_startet_nach_ablauf_kein_gh_mehr():
    def lauf(argv, **_):
        raise AssertionError("gh darf nicht mehr starten")

    runner = beleg_ablage.runner_mit_frist(1000.0, uhr=lambda: 1000.0, lauf=lauf)
    with pytest.raises(subprocess.TimeoutExpired):
        runner(["gh", "api"])
    with pytest.raises(beleg_ablage.GhFehler, match="^gh "):
        beleg_ablage.Gh(runner).release_loeschen("belege-2026-11-01")


class FlakyReleases(AttrappeReleases):
    """Wie GitHub kurz nach dem Anlegen: die ersten Uploads scheitern, ein Teil der
    Dateien kommt trotzdem an (``gh`` lädt parallel, bricht beim ersten Fehler ab)."""

    def __init__(self, meldung: str, scheitert: int, teilweise: int = 0, **kw) -> None:
        super().__init__(**kw)
        self.meldung, self.scheitert, self.teilweise = meldung, scheitert, teilweise
        self.versuche = 0

    def hochladen(self, tag, dateien):
        self.versuche += 1
        if self.versuche <= self.scheitert:
            namen = (
                [d.name for d in dateien][: self.teilweise]
                if self.versuche == 1
                else []
            )
            self.stand.setdefault(tag, []).extend(namen)
            raise GhFehler(f"gh release upload: Exit 1: {self.meldung}")
        super().hochladen(tag, dateien)


def viele(tmp_path: Path, anzahl: int) -> list[Bild]:
    return [bild(tmp_path, f"g{i}", "o2") for i in range(anzahl)]


def test_404_nach_dem_anlegen_wird_mit_pause_wiederholt(tmp_path):
    gh = FlakyReleases("HTTP 404: Not Found (https://uploads.github.com/x)", 2)
    pausen: list[float] = []
    bilanz = veroeffentliche(viele(tmp_path, 3), HEUTE, gh, schlaf=pausen.append)
    assert len(gh.stand["belege-2026-11-10"]) == 3
    assert (bilanz.hochgeladen, bilanz.fehlgeschlagen, bilanz.fehler) == (3, 0, [])
    assert pausen == [beleg_ablage.PAUSE_S, 2 * beleg_ablage.PAUSE_S]


def test_halb_angekommenes_paket_zaehlt_und_laedt_nur_den_rest_nach(tmp_path):
    gh = FlakyReleases("HTTP 404: Not Found", 1, teilweise=2)
    bilanz = veroeffentliche(viele(tmp_path, 5), HEUTE, gh, schlaf=lambda s: None)
    assert (bilanz.hochgeladen, bilanz.fehlgeschlagen) == (5, 0)
    assert len(gh.stand["belege-2026-11-10"]) == 5
    assert [len(d) for _, d in gh.hochgeladen] == [3]


def test_already_exists_nach_teilerfolg_ist_erfolg_ohne_doppelzaehlung(tmp_path):
    gh = FlakyReleases("ReleaseAsset.name already exists", 1, teilweise=4)
    bilanz = veroeffentliche(viele(tmp_path, 4), HEUTE, gh, schlaf=lambda s: None)
    assert gh.versuche == 1
    assert (bilanz.hochgeladen, bilanz.fehlgeschlagen, bilanz.fehler) == (4, 0, [])


def test_dauerhafter_404_bleibt_benannter_fehler_ohne_falsche_zeit(tmp_path):
    gh = FlakyReleases("HTTP 404: Not Found", 99, teilweise=1)
    bilanz = veroeffentliche(viele(tmp_path, 3), HEUTE, gh, schlaf=lambda s: None)
    assert gh.versuche == beleg_ablage.VERSUCHE
    assert (bilanz.hochgeladen, bilanz.fehlgeschlagen, bilanz.ausgelassen) == (1, 2, 0)
    assert len(bilanz.fehler) == 1 and "2 von 3" in bilanz.fehler[0]
    assert "2 fehlgeschlagen" in bilanz.zeilen()[0]
    assert "0 ausgelassen (Zeit)" in bilanz.zeilen()[0]


def test_dauerhafter_fehler_wird_nicht_wiederholt(tmp_path):
    gh = FlakyReleases("HTTP 401: Bad credentials", 99)
    bilanz = veroeffentliche(viele(tmp_path, 2), HEUTE, gh, schlaf=lambda s: None)
    assert gh.versuche == 1
    assert (bilanz.fehlgeschlagen, bilanz.ausgelassen) == (2, 0)


def test_wiederholung_beachtet_die_frist(tmp_path):
    gh = FlakyReleases("HTTP 404: Not Found", 99)
    pausen: list[float] = []
    bilanz = veroeffentliche(
        viele(tmp_path, 2),
        HEUTE,
        gh,
        frist_ende=100.0,
        uhr=lambda: 99.0,
        schlaf=pausen.append,
    )
    assert pausen == [] and gh.versuche == 1
    assert (bilanz.fehlgeschlagen, bilanz.ausgelassen) == (2, 0)


def test_vorhandene_datei_gilt_nicht_als_angekommen(tmp_path):
    """Gegenprobe: ein Name von einem früheren Lauf beweist keinen neuen Upload."""
    name = dateiname("g0", "o2", HEUTE)
    gh = FlakyReleases(
        "HTTP 404: Not Found", 99, anhaenge={"belege-2026-11-10": [name]}
    )
    bilanz = veroeffentliche(viele(tmp_path, 1), HEUTE, gh, schlaf=lambda s: None)
    assert (bilanz.hochgeladen, bilanz.fehlgeschlagen) == (0, 1)


class RennenReleases(AttrappeReleases):
    """Das Rennen vom 05.11.2026: ein anderer Lauf ersetzt das Release mitten im
    Hochladen. Wie GitHub: Upload auf ein Release, das es nicht (mehr) gibt, ist
    HTTP 404 mit der alten ID; ein neu angelegtes Release hat eine neue ID und ist
    leer."""

    def __init__(self, ersetze_nach: int, **kw) -> None:
        super().__init__(**kw)
        self.ersetze_nach, self.aufrufe = ersetze_nach, 0
        self.weg: set[str] = set()

    def hochladen(self, tag, dateien):
        self.aufrufe += 1
        if self.aufrufe == self.ersetze_nach + 1:
            self.stand.pop(tag, None)
            self.weg.add(tag)
        if tag not in self.stand:
            raise GhFehler(
                "gh release upload: Exit 1: HTTP 404: Not Found "
                f"(https://uploads.github.com/repos/o/r/releases/{self._id(tag)}/assets)"
            )
        super().hochladen(tag, dateien)

    def release_anlegen(self, tag, titel):
        super().release_anlegen(tag, titel)
        self.ids[tag] = 5000 + len(self.angelegt)


def test_release_mitten_im_hochladen_ersetzt_alle_bilder_landen(tmp_path, monkeypatch):
    monkeypatch.setattr(beleg_ablage, "PAKET", 2)
    bilder = viele(tmp_path, 7)
    gh = RennenReleases(ersetze_nach=2)
    bilanz = veroeffentliche(bilder, HEUTE, gh, schlaf=lambda s: None)
    tag = "belege-2026-11-10"
    assert sorted(gh.stand[tag]) == sorted(b.datei.name for b in bilder)
    assert (bilanz.hochgeladen, bilanz.fehlgeschlagen, bilanz.fehler) == (7, 0, [])
    assert gh.releases_geloescht == []
    assert gh.angelegt == [tag, tag]
    zeilen = "\n".join(bilanz.protokollzeilen())
    assert "HTTP 404" in zeilen and "Release-ID gewechselt" in zeilen
    assert "erneut hochgeladen" in zeilen


def test_ohne_den_404_pfad_gingen_die_ersten_bilder_verloren(tmp_path, monkeypatch):
    """Gegenprobe: ohne Abgleich nach dem Wechsel läge nur der Rest im neuen Release."""
    monkeypatch.setattr(beleg_ablage, "PAKET", 2)
    monkeypatch.setattr(beleg_ablage, "_hole_verlorene_nach", lambda *a, **k: None)
    gh = RennenReleases(ersetze_nach=2)
    veroeffentliche(viele(tmp_path, 7), HEUTE, gh, schlaf=lambda s: None)
    assert len(gh.stand["belege-2026-11-10"]) < 7


def test_release_anlegen_schon_da_ist_kein_fehler(tmp_path):
    """Ein anderer Lauf legt das Release zwischen Suche und Anlegen an."""

    class Schneller(AttrappeReleases):
        def release_info(self, tag):
            gefunden = super().release_info(tag)
            if gefunden is None and not self.angelegt:
                self.stand[tag] = []
            return gefunden

    gh = Schneller()
    bilanz = veroeffentliche(viele(tmp_path, 2), HEUTE, gh, schlaf=lambda s: None)
    assert (bilanz.hochgeladen, bilanz.fehlgeschlagen, bilanz.fehler) == (2, 0, [])
    assert "schon angelegt" in "\n".join(bilanz.protokollzeilen())


def test_anlegen_scheitert_dauerhaft_bleibt_benannter_fehler(tmp_path):
    gh = AttrappeReleases(scheitern_bei=("anlegen",))
    bilanz = veroeffentliche(viele(tmp_path, 2), HEUTE, gh, schlaf=lambda s: None)
    assert bilanz.fehlgeschlagen == 2 and "kaputt" in bilanz.fehler[0]


def test_entwurf_steht_im_protokoll(tmp_path):
    gh = AttrappeReleases({"belege-2026-11-10": []})
    gh.entwuerfe.add("belege-2026-11-10")
    bilanz = veroeffentliche(viele(tmp_path, 1), HEUTE, gh, schlaf=lambda s: None)
    assert "ist ein Entwurf" in "\n".join(bilanz.protokollzeilen())
    assert bilanz.hochgeladen == 1


def test_gh_release_info_liest_id_und_entwurf_und_kennt_fehlendes():
    lauf = Lauf('{"id": 434989383, "draft": false}\n')
    info = Gh(runner=lauf, repo="o/r").release_info("belege-2026-11-05")
    assert (info.id, info.entwurf) == (434989383, False)
    assert Gh(runner=Lauf("")).release_info("belege-2026-11-05") is None
    with pytest.raises(GhFehler, match="unlesbar"):
        Gh(runner=Lauf("kein json\n")).release_info("belege-2026-11-05")
