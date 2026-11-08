"""Die Bildfolge kommt vom Klick-Lauf bis auf die Seite (Schnittstelle #69 -> #70).

Ein Durchlauf mit Fixture ohne Netz: Erfassung (Beleg mit Bildfolge, vier Schritte,
einer fehlt mit Grund) -> Artefakt des Klick-Jobs (``speichere_bilder``) ->
Veröffentlichung im Trockenlauf (Attrappe statt GitHub) -> Manifest
(``belege_manifest.py``) -> Seite (``render_site``). Die Seite zeigt Bilder nur aus
veröffentlichten Dateien, nennt einen fehlenden Schritt mit Grund und zeigt für eine
nicht veröffentlichte Datei kein Bild.
Feste Daten, nie das heutige Datum (CLAUDE.md Regel 7).
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import belegbau
import pytest
import test_beleg_position as pos
import test_geraete_buendel_kopf_zeitraum as kopf
from beleg_attrappe import AttrappeReleases
from bs4 import BeautifulSoup
from test_beleg_skripte import lade_skript, satz

from telco_radar.beleg_folgen import lies_folgen
from telco_radar.beleg_manifest import MANIFEST_DATEI, MANIFEST_NAME, baue_manifest
from telco_radar.beleg_regeln import (
    dateiname,
    datum_der_datei,
    folge_dateiname,
    ist_sichtbar,
    zerlege_dateiname,
    zerlege_folgename,
)
from telco_radar.collect.geraete.belegbild import speichere_bilder
from telco_radar.collect.geraete.klickbeleg import baue_beleg
from telco_radar.collect.geraete.klickbildfolge import Folgebild
from telco_radar.collect.geraete.klickecho import Variante
from telco_radar.collect.geraete.klickergebnis import kombination_als_daten
from telco_radar.collect.geraete.klicklauf import (
    BELEG_OFFEN,
    ERFASST,
    Klicklauf,
    Kombiergebnis,
)
from telco_radar.klick_vertrag import FORMAT
from telco_radar.report.html import render_site

GRUND = "Seite markiert keine Option"
TAG = pos.TAG
TAGES_RELEASE = f"belege-{pos.HEUTE}"


def _folgebild(nr: int) -> Folgebild:
    return Folgebild("x", belegbau.png((nr * 50, 30, 30)))


@pytest.fixture(scope="module")
def weg(tmp_path_factory):
    """Der ganze Weg einmal: Erfassung, Artefakt, Trockenlauf der Veröffentlichung,
    Manifest, Seite. Das Klick-Ergebnis der Fixture hat nicht alle Felder einer ganzen
    Seite; es wird nach dem Manifest entfernt, damit es den Gerätelauf nicht stört."""
    ordner = tmp_path_factory.mktemp("bildfolge_weg")
    folge = {"geraet_speicher": _folgebild(1), "laufzeit": _folgebild(3)}
    fertig, grund = baue_beleg(
        belegbau.quelle(
            folge=folge, folge_fehlt={"tarif": GRUND}, modell="Apple iPhone 17 Pro"
        ),
        belegbau.karte(),
        belegbau.ZEIT,
    )
    assert grund is None and fertig is not None
    beleg_id = fertig.beleg.beleg_id
    lauf = Klicklauf("o2", "http://127.0.0.1:8000/handy/x")
    lauf.ergebnisse.append(
        Kombiergebnis(
            Variante("256", "S", 24),
            ERFASST,
            screenshot_png=belegbau.png(),
            beleg=fertig,
            beleg_status=BELEG_OFFEN,
        )
    )
    artefakt = ordner / "artefakt" / "o2"
    speichere_bilder(lauf, artefakt / "belege")
    klick = {
        "format": FORMAT,
        "anbieter": "o2",
        "roh": [{**satz(18.0, beleg_id, anbieter="o2"), "device_id": kopf.DEVICE}],
        "seiten": [
            {"kombinationen": [kombination_als_daten(e) for e in lauf.ergebnisse]}
        ],
    }
    (artefakt / "ergebnis.json").write_text(json.dumps(klick), encoding="utf-8")
    wurzel_pub = ordner / "pub"
    (wurzel_pub / "data" / "state").mkdir(parents=True)
    (wurzel_pub / "data" / "state" / "geraete_tco.json").write_text(
        json.dumps({"buendel": []}), encoding="utf-8"
    )
    modul = lade_skript("belege_veroeffentlichen")
    mp = pytest.MonkeyPatch()
    mp.setattr(modul, "lade_katalog", lambda root: None)
    mp.setattr(modul, "geraet_aus_sku", lambda sku, katalog: (kopf.DEVICE, 256))
    mp.setattr(
        modul,
        "ausbeute",
        lambda daten, katalog: SimpleNamespace(rohsaetze=daten["roh"]),
    )
    gh = AttrappeReleases()
    try:
        code = modul.main(
            ["--root", str(wurzel_pub), "--quelle", str(artefakt.parent)]
            + ["--heute", pos.HEUTE],
            gh=gh,
        )
    finally:
        mp.undo()
    assert code == 0
    site = kopf._baue(ordner)
    wurzel = site.parent
    state = wurzel / "data" / "state"
    (state / "klick").mkdir()
    (state / "klick" / "o2.json").write_text(json.dumps(klick), encoding="utf-8")
    manifest_skript = lade_skript("belege_manifest")
    assert (
        manifest_skript.main(["--root", str(wurzel), "--heute", pos.HEUTE], gh=gh) == 0
    )
    manifest = json.loads((wurzel / MANIFEST_DATEI).read_text(encoding="utf-8"))
    (state / "klick" / "o2.json").unlink()
    return SimpleNamespace(
        ordner=ordner,
        site=site,
        wurzel=wurzel,
        gh=gh,
        manifest=manifest,
        beleg_id=beleg_id,
        fertig=fertig,
        klick=klick,
    )


def _seite(wurzel: Path, site: Path, manifest: dict, beleg_id: str) -> BeautifulSoup:
    """Baut ``geraete.html`` mit diesem Manifest; o2 hat die Position des Belegs."""
    state = wurzel / "data" / "state"
    bestand = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    vodafone = [b for b in bestand["buendel"] if b["anbieter"] == "Vodafone"]
    o2 = pos._satz("o2", "O2 Mobile Klein", "o2:klein", 24, 18.0, beleg_id)
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": pos.HEUTE, "buendel": [o2, *vodafone]}),
        encoding="utf-8",
    )
    (state / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    render_site(site, wurzel / "data" / "reports")
    return BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )


def _zeile(seite: BeautifulSoup):
    paar = next(
        li for li in seite.select(".gr-beleg-paar") if li["data-anbieter"] == "o2"
    )
    return paar.select_one(".gr-beleg-zeile")


@pytest.fixture(scope="module")
def seite(weg) -> BeautifulSoup:
    return _seite(weg.wurzel, weg.site, weg.manifest, weg.beleg_id)


def test_folgebilder_gehen_mit_dem_einzelbild_in_dasselbe_release(weg):
    einzel = dateiname(pos.MODELL, "o2", TAG)
    erwartet = {
        einzel,
        folge_dateiname(pos.MODELL, "o2", TAG, "geraet_speicher", weg.beleg_id),
        folge_dateiname(pos.MODELL, "o2", TAG, "laufzeit", weg.beleg_id),
    }
    assert [tag for tag, _ in weg.gh.hochgeladen] == [TAGES_RELEASE]
    assert set(weg.gh.stand[TAGES_RELEASE]) == erwartet
    assert all(zerlege_folgename(n) or zerlege_dateiname(n) for n in erwartet), (
        "jeder Name liegt im Schema"
    )


def test_manifest_nennt_die_folge_mit_gueltigen_adressen_und_dem_fehlenden_schritt(weg):
    (eintrag,) = weg.manifest["belege"]
    assert [b["schritt"] for b in eintrag["bildfolge"]] == [
        "geraet_speicher",
        "laufzeit",
        "preis",
    ]
    assert eintrag["bildfolge_fehlt"] == [f"tarif: {GRUND}"]
    liegt = set(weg.gh.stand[TAGES_RELEASE])
    for b in eintrag["bildfolge"]:
        prefix, name = b["datei"].rsplit("/", 1)
        assert prefix.endswith(f"/releases/download/{TAGES_RELEASE}")
        assert name in liegt, "nur Dateien, die wirklich im Release liegen"
    assert eintrag["bildfolge"][-1]["datei"] == eintrag["url"]
    assert eintrag["bildfolge"][0]["text"].startswith("Gerät und Speicher gewählt")
    assert eintrag["bildfolge"][-1]["text"], "der Preisschritt trägt seinen Text"


def test_seite_zeigt_drei_bilder_in_reihenfolge_und_den_fehlenden_schritt(weg, seite):
    zeile = _zeile(seite)
    schritte = zeile.select(".gr-bildfolge > li")
    assert [li.select_one(".gr-bildfolge-schritt").get_text() for li in schritte] == [
        "Schritt 1 von 4: Gerät und Speicher gewählt",
        "Schritt 2 von 4: Tarif gewählt",
        "Schritt 3 von 4: Laufzeit und Raten gewählt",
        "Schritt 4 von 4: Zuzahlung und Monatsrate",
    ]
    assert [bool(li.select_one("img")) for li in schritte] == [True, False, True, True]
    assert (
        schritte[1].select_one(".gr-bildfolge-text").get_text() == f"Kein Bild: {GRUND}"
    )
    liegt = set(weg.gh.stand[TAGES_RELEASE])
    bilder = [
        li.select_one("img")["data-src"] for li in schritte if li.select_one("img")
    ]
    assert all(url.rsplit("/", 1)[1] in liegt for url in bilder)
    assert "3 von 4 Schritten mit Bild" in zeile.summary.get_text(" ", strip=True)
    assert len(zeile.select("img")) == 3


def test_nicht_veroeffentlichte_datei_ergibt_kein_bild_sondern_den_vermerk(weg):
    """Die Klick-Ergebnisse kennen den Schritt, der Release nicht: kein Link."""
    stand = {t: list(d) for t, d in weg.gh.stand.items()}
    laufzeit = folge_dateiname(pos.MODELL, "o2", TAG, "laufzeit", weg.beleg_id)
    stand[TAGES_RELEASE].remove(laufzeit)
    manifest = baue_manifest(stand, TAG, lies_folgen([weg.klick]))
    (eintrag,) = manifest["belege"]
    assert [b["schritt"] for b in eintrag["bildfolge"]] == ["geraet_speicher", "preis"]
    assert eintrag["bildfolge_fehlt"] == [
        f"tarif: {GRUND}",
        "laufzeit: Bild nicht veröffentlicht",
    ]
    seite = _seite(weg.wurzel, weg.site, manifest, weg.beleg_id)
    zeile = _zeile(seite)
    assert len(zeile.select("img")) == 2
    assert not any(laufzeit in (i.get("data-src") or "") for i in zeile.select("img"))
    assert "Kein Bild: Bild nicht veröffentlicht" in zeile.get_text(" ", strip=True)


def test_alter_eintrag_mit_dateinamen_statt_adressen_zeigt_nur_das_einzelbild(weg):
    """Der Fehler von #70: ``<beleg_id>_<schritt>.webp`` neben dem Einzelbild gab
    Links auf Anhänge, die es nie gab. Ein Name ohne Adresse fällt weg."""
    manifest = json.loads(json.dumps(weg.manifest))
    manifest["belege"][0]["bildfolge"] = [
        {"datei": f"{weg.beleg_id}_{s}.webp", "schritt": s, "text": "t"}
        for s in ("geraet_speicher", "tarif", "laufzeit")
    ]
    manifest["belege"][0]["bildfolge_fehlt"] = []
    seite = _seite(weg.wurzel, weg.site, manifest, weg.beleg_id)
    zeile = _zeile(seite)
    assert not zeile.select(".gr-bildfolge")
    assert [i["data-src"] for i in zeile.select("img")] == [
        weg.manifest["belege"][0]["url"]
    ]


def test_ohne_folgebilder_im_release_bleibt_es_ein_einzelbild(weg):
    stand = {t: [n for n in d if zerlege_dateiname(n)] for t, d in weg.gh.stand.items()}
    (eintrag,) = baue_manifest(stand, TAG, lies_folgen([weg.klick]))["belege"]
    assert "bildfolge" not in eintrag


def test_zwei_positionen_am_selben_tag_ergeben_keine_folge(weg):
    """Folgebilder zweier Positionen: nicht beweisbar, welche zum Einzelbild gehören."""
    stand = {t: list(d) for t, d in weg.gh.stand.items()}
    stand[TAGES_RELEASE].append(
        folge_dateiname(pos.MODELL, "o2", TAG, "tarif", "f" * 64)
    )
    manifest = baue_manifest(stand, TAG, lies_folgen([weg.klick]))
    (eintrag,) = manifest["belege"]
    assert "bildfolge" not in eintrag and manifest["folge_verworfen"] == 1


def test_veraltetes_folgebild_wird_beim_naechsten_lauf_geloescht(weg):
    modul = lade_skript("belege_veroeffentlichen")
    alt = folge_dateiname(pos.MODELL, "o2", TAG, "tarif", "f" * 64)
    gh = AttrappeReleases({TAGES_RELEASE: [alt]})
    neu = Path(dateiname(pos.MODELL, "o2", TAG))
    bilder = [SimpleNamespace(datei=neu, gross=False)]
    assert modul.raeume_veraltete_folgen(bilder, gh) == []
    assert gh.assets_geloescht == [(TAGES_RELEASE, alt)]


def test_aufbewahrung_loescht_das_folgebild_mit_dem_einzelbild():
    from telco_radar.beleg_ablage import raeume_auf

    alt = date(2026, 11, 1)
    einzel = dateiname(pos.MODELL, "o2", alt)
    folge = folge_dateiname(pos.MODELL, "o2", alt, "tarif", "a" * 64)
    gh = AttrappeReleases({"belege-2026-11-10": [einzel, folge]})
    _, rest = raeume_auf({"belege-2026-11-10": [einzel, folge]}, date(2026, 11, 10), gh)
    assert rest["belege-2026-11-10"] == []
    assert sorted(d for _, d in gh.assets_geloescht) == sorted([einzel, folge])
    assert datum_der_datei(folge) == alt
    assert not ist_sichtbar("belege-2026-11-10", folge, date(2026, 11, 10))
    assert ist_sichtbar("belege-2026-11-10", folge, date(2026, 11, 5))


def test_folgename_ist_eindeutig_und_nimmt_nur_hex_kennungen():
    name = folge_dateiname("g-1", "o2", TAG, "geraet_speicher", "ab" * 32)
    teile = zerlege_folgename(name)
    assert teile is not None and teile.schritt == "geraet_speicher"
    assert teile.kennung == "ab" * 8 and teile.paar == ("g-1", "o2", TAG.isoformat())
    assert zerlege_dateiname(name) is None
    with pytest.raises(ValueError):
        folge_dateiname("g-1", "o2", TAG, "tarif", "keine-hex-id")
    assert zerlege_folgename(dateiname("g-1", "o2", TAG)) is None


def test_klick_ergebnis_ohne_die_position_gibt_keine_beschriftung(weg):
    assert lies_folgen([{"seiten": [{"kombinationen": []}]}]) == {}
    stand = {t: list(d) for t, d in weg.gh.stand.items()}
    (eintrag,) = baue_manifest(stand, TAG, {})["belege"]
    assert eintrag["bildfolge_fehlt"] == ["tarif: Bild nicht veröffentlicht"]
    assert all(b["text"] == "" for b in eintrag["bildfolge"])


def test_das_klick_ergebnis_traegt_die_bildfolge_ohne_bilder(weg):
    (kombi,) = weg.klick["seiten"][0]["kombinationen"]
    assert [b["schritt"] for b in kombi["beleg"]["bildfolge"]] == [
        "geraet_speicher",
        "laufzeit",
        "preis",
    ]
    assert kombi["beleg"]["bildfolge_fehlt"] == [f"tarif: {GRUND}"]
    assert "png" not in json.dumps(kombi).lower()


def test_artefakt_traegt_nur_geschriebene_folgebilder(weg):
    dateien = sorted(
        p.name for p in (weg.ordner / "artefakt" / "o2" / "belege").glob("*.webp")
    )
    assert dateien == sorted(
        [
            f"{weg.beleg_id}.webp",
            f"{weg.beleg_id}_geraet_speicher.webp",
            f"{weg.beleg_id}_laufzeit.webp",
        ]
    )
    assert shutil.disk_usage(weg.ordner).free > 0
