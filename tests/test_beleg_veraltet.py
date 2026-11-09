"""Frühere Positionen eines Paares fallen erst aus dem Manifest, dann aus dem Release.

Befund N1 (Prüfung PR 73, 09.11.2026): Ein zweiter Klick-Lauf am selben Tag mit neuer
Position löschte die Bilder der ersten; das eingecheckte Manifest zeigte bis zum
nächsten Gerätelauf auf gelöschte Dateien. Jetzt löscht der Klick-Job nichts: der
Manifest-Schritt schreibt das Manifest auf die jüngere Position und löscht danach die
frühere. Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7).
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from beleg_attrappe import AttrappeReleases
from test_beleg_skripte import HEUTE, lade_skript

from telco_radar.beleg_ablage import GhFehler
from telco_radar.beleg_manifest import MANIFEST_DATEI
from telco_radar.beleg_regeln import folge_dateiname, ist_gross_tag
from telco_radar.beleg_veraltet import finde_veraltete, streitpaare

TAG = date(2026, 11, 10)
RELEASE = "belege-2026-11-10"
GROSS = "belege-gross-2026-11"
K1, K2, K3 = "1" * 64, "2" * 64, "3" * 64
SCHRITTE = ("preis", "geraet_speicher", "tarif", "laufzeit")


def namen(beleg_id: str, schritte=SCHRITTE) -> list[str]:
    return [folge_dateiname("g", "o2", TAG, s, beleg_id) for s in schritte]


def lies(wurzel) -> dict:
    return json.loads((wurzel / MANIFEST_DATEI).read_text(encoding="utf-8"))


def kennungen(manifest: dict) -> set[str]:
    (eintrag,) = manifest["belege"]
    urls = [eintrag["url"], *(b["datei"] for b in eintrag.get("bildfolge", []))]
    return {u.rsplit("__", 1)[1].removesuffix(".webp") for u in urls}


def manifest_lauf(wurzel, gh, *extra) -> int:
    modul = lade_skript("belege_manifest")
    argv = ["--root", str(wurzel), "--heute", HEUTE.isoformat(), *extra]
    return modul.main(argv, gh=gh)


class ProtokollGh(AttrappeReleases):
    """Hält fest, worauf das Manifest beim ersten Löschen zeigte."""

    def __init__(self, wurzel, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.wurzel = wurzel
        self.manifest_beim_loeschen: list[set[str]] = []

    def asset_loeschen(self, tag: str, datei: str) -> None:
        self.manifest_beim_loeschen.append(kennungen(lies(self.wurzel)))
        super().asset_loeschen(tag, datei)


def test_das_manifest_zeigt_auf_die_neue_position_bevor_die_alte_geloescht_wird(
    tmp_path,
):
    gh = ProtokollGh(tmp_path, {RELEASE: [*namen(K1), *namen(K2, SCHRITTE[:3])]})
    assert manifest_lauf(tmp_path, gh) == 0
    assert gh.manifest_beim_loeschen, "die frühere Position wurde gelöscht"
    assert all(k == {K2[:16]} for k in gh.manifest_beim_loeschen)
    assert sorted(gh.stand[RELEASE]) == sorted(namen(K2, SCHRITTE[:3]))
    manifest = lies(tmp_path)
    assert kennungen(manifest) == {K2[:16]} and "folge_verworfen" not in manifest
    (eintrag,) = manifest["belege"]
    assert [b["schritt"] for b in eintrag["bildfolge"]] == [
        "geraet_speicher",
        "tarif",
        "preis",
    ]
    assert eintrag["bildfolge_fehlt"][0].startswith("laufzeit:")


def test_ohne_neues_einzelbild_bleibt_die_alte_position_unangetastet(tmp_path):
    """Teilausfall: von K2 kamen nur Schritte an. K1 bleibt vollständig stehen."""
    gh = ProtokollGh(tmp_path, {RELEASE: [*namen(K1), *namen(K2, SCHRITTE[1:])]})
    assert manifest_lauf(tmp_path, gh) == 0
    assert gh.assets_geloescht == []
    assert kennungen(lies(tmp_path)) == {K1[:16]}


def test_die_juengste_von_drei_positionen_gilt(tmp_path):
    gh = ProtokollGh(
        tmp_path, {RELEASE: [*namen(K1), *namen(K2), *namen(K3, ("preis",))]}
    )
    assert manifest_lauf(tmp_path, gh) == 0
    assert sorted(gh.stand[RELEASE]) == sorted(namen(K3, ("preis",)))
    assert kennungen(lies(tmp_path)) == {K3[:16]}


def test_die_reihenfolge_kommt_aus_der_uploadzeit_nicht_aus_dem_namen(tmp_path):
    """Die größere Kennung ist die ältere: gilt trotzdem die jüngere Uploadzeit."""
    gh = ProtokollGh(tmp_path, {RELEASE: [*namen(K2, ("preis",))]})
    gh.release_anlegen(RELEASE, "x")
    gh.stand[RELEASE].extend(namen(K1, ("preis",)))
    gh._stempel(RELEASE, namen(K1, ("preis",))[0])
    assert manifest_lauf(tmp_path, gh) == 0
    assert kennungen(lies(tmp_path)) == {K1[:16]}
    assert gh.stand[RELEASE] == namen(K1, ("preis",))


@pytest.mark.parametrize("fehler", ["lesefehler", "gleiche_zeit"])
def test_ohne_beweisbare_reihenfolge_wird_nichts_geloescht(tmp_path, fehler):
    gh = ProtokollGh(tmp_path, {RELEASE: [*namen(K1), *namen(K2)]})
    if fehler == "lesefehler":
        gh.scheitern_bei = ("zeiten",)
    else:
        for stelle in gh.zeiten:
            gh.zeiten[stelle] = "2026-11-09T00:00:00Z"
    assert manifest_lauf(tmp_path, gh) == 0
    assert gh.assets_geloescht == []
    assert sorted(gh.stand[RELEASE]) == sorted([*namen(K1), *namen(K2)])
    assert lies(tmp_path)["belege"] == [] and lies(tmp_path)["folge_verworfen"] == 1


def test_nur_lesen_loescht_nichts_zeigt_aber_auf_die_neue_position(tmp_path):
    gh = ProtokollGh(tmp_path, {RELEASE: [*namen(K1), *namen(K2)]})
    assert manifest_lauf(tmp_path, gh, "--nur-lesen") == 0
    assert gh.assets_geloescht == []
    assert kennungen(lies(tmp_path)) == {K2[:16]}


def test_scheitert_das_loeschen_zeigt_das_manifest_trotzdem_auf_die_neue(tmp_path):
    class Haengt(ProtokollGh):
        def asset_loeschen(self, tag: str, datei: str) -> None:
            raise GhFehler(f"gh release delete-asset {tag}: Exit 1: kaputt")

    gh = Haengt(tmp_path, {RELEASE: [*namen(K1), *namen(K2)]})
    assert manifest_lauf(tmp_path, gh) == 0
    manifest = lies(tmp_path)
    assert kennungen(manifest) == {K2[:16]}
    assert "Löschen gescheitert" in manifest["ausfall"]


def test_monats_release_wird_mitgeraeumt(tmp_path):
    """Die große Änderung liegt in Tag und Monat: beide Stellen der alten Position
    gehen, beide der neuen bleiben."""
    gh = ProtokollGh(
        tmp_path,
        {RELEASE: [*namen(K1), *namen(K2)], GROSS: [*namen(K1), *namen(K2)]},
    )
    assert manifest_lauf(tmp_path, gh) == 0
    assert sorted(gh.stand[RELEASE]) == sorted(namen(K2))
    assert sorted(gh.stand[GROSS]) == sorted(namen(K2))
    (eintrag,) = lies(tmp_path)["belege"]
    assert ist_gross_tag(eintrag["url"].rsplit("/", 2)[-2])


def test_ohne_streit_liest_das_skript_keine_uploadzeiten(tmp_path):
    class ZeitenVerboten(ProtokollGh):
        def hochgeladen_am(self):
            raise AssertionError("Uploadzeiten ohne Streit gelesen")

    gh = ZeitenVerboten(tmp_path, {RELEASE: namen(K1)})
    assert manifest_lauf(tmp_path, gh) == 0
    assert kennungen(lies(tmp_path)) == {K1[:16]}


def test_andere_paare_und_tage_sind_kein_streit():
    anh = {
        RELEASE: [
            folge_dateiname("g", "o2", TAG, "preis", K1),
            folge_dateiname("g", "telekom", TAG, "preis", K2),
            folge_dateiname("g", "o2", date(2026, 11, 9), "preis", K2),
        ]
    }
    assert streitpaare(anh) == set()
    assert finde_veraltete(anh, {}).loeschen == []
