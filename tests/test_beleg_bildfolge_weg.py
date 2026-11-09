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

import functools
import http.server
import json
import os
import shutil
import threading
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

from telco_radar.beleg_bildfolge import (
    ADRESSE_ANFANG,
    fremd_zur_kennung,
    kennung_der_adresse,
    normalisiere,
)
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


class Mitschnitt(AttrappeReleases):
    """Die Attrappe, die zusätzlich die hochgeladenen Bytes je Dateiname behält."""

    def __init__(self) -> None:
        super().__init__()
        self.inhalte: dict[str, bytes] = {}

    def hochladen(self, tag, dateien):
        self.inhalte.update({d.name: d.read_bytes() for d in dateien})
        super().hochladen(tag, dateien)


@pytest.fixture(scope="module")
def weg(tmp_path_factory):
    return baue_weg(tmp_path_factory.mktemp("bildfolge_weg"))


def baue_weg(ordner: Path) -> SimpleNamespace:
    """Der ganze Weg einmal: Erfassung, Artefakt, Trockenlauf der Veröffentlichung,
    Manifest. Das Klick-Ergebnis der Fixture hat nicht alle Felder einer ganzen Seite;
    es wird nach dem Manifest entfernt, damit es den Gerätelauf nicht stört."""
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
    gh = Mitschnitt()
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


def baue_seite(ordner: Path, manifest: dict, beleg_id: str) -> Path:
    """Baut die Seite frisch in ``ordner`` mit diesem Manifest; o2 hat die Position
    des Belegs. Gibt den Seitenordner zurück."""
    site = kopf._baue(ordner)
    state = site.parent / "data" / "state"
    bestand = json.loads((state / "geraete_tco.json").read_text(encoding="utf-8"))
    vodafone = [b for b in bestand["buendel"] if b["anbieter"] == "Vodafone"]
    o2 = pos._satz("o2", "O2 Mobile Klein", "o2:klein", 24, 18.0, beleg_id)
    (state / "geraete_tco.json").write_text(
        json.dumps({"updated": pos.HEUTE, "buendel": [o2, *vodafone]}),
        encoding="utf-8",
    )
    (state / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    render_site(site, site.parent / "data" / "reports")
    return site


def _seite(ordner: Path, manifest: dict, beleg_id: str) -> BeautifulSoup:
    site = baue_seite(ordner, manifest, beleg_id)
    return BeautifulSoup(
        (site / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )


def _zeile(seite: BeautifulSoup):
    paar = next(
        li for li in seite.select(".gr-beleg-paar") if li["data-anbieter"] == "o2"
    )
    return paar.select_one(".gr-beleg-zeile")


@pytest.fixture(scope="module")
def seitenordner(weg, tmp_path_factory) -> Path:
    return baue_seite(tmp_path_factory.mktemp("seite"), weg.manifest, weg.beleg_id)


@pytest.fixture(scope="module")
def seite(seitenordner) -> BeautifulSoup:
    return BeautifulSoup(
        (seitenordner / "geraete.html").read_text(encoding="utf-8"), "html.parser"
    )


def test_folgebilder_gehen_mit_dem_einzelbild_in_dasselbe_release(weg):
    erwartet = {
        folge_dateiname(pos.MODELL, "o2", TAG, "preis", weg.beleg_id),
        folge_dateiname(pos.MODELL, "o2", TAG, "geraet_speicher", weg.beleg_id),
        folge_dateiname(pos.MODELL, "o2", TAG, "laufzeit", weg.beleg_id),
    }
    assert [tag for tag, _ in weg.gh.hochgeladen] == [TAGES_RELEASE]
    assert set(weg.gh.stand[TAGES_RELEASE]) == erwartet
    assert all(zerlege_folgename(n) for n in erwartet), "jeder Name liegt im Schema"
    assert {zerlege_folgename(n).kennung for n in erwartet} == {weg.beleg_id[:16]}, (
        "auch das Einzelbild (preis) trägt die Kennung: eine Position, eine Kennung"
    )
    assert dateiname(pos.MODELL, "o2", TAG) not in weg.gh.stand[TAGES_RELEASE]


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


def test_nicht_veroeffentlichte_datei_ergibt_kein_bild_sondern_den_vermerk(
    weg, tmp_path
):
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
    seite = _seite(tmp_path, manifest, weg.beleg_id)
    zeile = _zeile(seite)
    assert len(zeile.select("img")) == 2
    assert not any(laufzeit in (i.get("data-src") or "") for i in zeile.select("img"))
    assert "Kein Bild: Bild nicht veröffentlicht" in zeile.get_text(" ", strip=True)


def test_alter_eintrag_mit_dateinamen_statt_adressen_zeigt_nur_das_einzelbild(
    weg, tmp_path
):
    """Der Fehler von #70: ``<beleg_id>_<schritt>.webp`` neben dem Einzelbild gab
    Links auf Anhänge, die es nie gab. Ein Name ohne Adresse fällt weg."""
    manifest = json.loads(json.dumps(weg.manifest))
    manifest["belege"][0]["bildfolge"] = [
        {"datei": f"{weg.beleg_id}_{s}.webp", "schritt": s, "text": "t"}
        for s in ("geraet_speicher", "tarif", "laufzeit")
    ]
    manifest["belege"][0]["bildfolge_fehlt"] = []
    seite = _seite(tmp_path, manifest, weg.beleg_id)
    zeile = _zeile(seite)
    assert not zeile.select(".gr-bildfolge")
    assert [i["data-src"] for i in zeile.select("img")] == [
        weg.manifest["belege"][0]["url"]
    ]


def test_ohne_folgebilder_im_release_bleibt_es_ein_einzelbild(weg):
    stand = {
        t: [n for n in d if zerlege_folgename(n).schritt == "preis"]
        for t, d in weg.gh.stand.items()
    }
    (eintrag,) = baue_manifest(stand, TAG, lies_folgen([weg.klick]))["belege"]
    assert "bildfolge" not in eintrag
    assert eintrag["url"].endswith(
        folge_dateiname(pos.MODELL, "o2", TAG, "preis", weg.beleg_id)
    )


def test_zwei_positionen_mit_einzelbild_am_selben_tag_ergeben_keine_folge(weg):
    """Zwei Einzelbilder (zwei Kennungen) desselben Paares: nicht beweisbar, welches
    gilt. Kein Einzelbild, keine Folge, gezählt."""
    stand = {t: list(d) for t, d in weg.gh.stand.items()}
    stand[TAGES_RELEASE] += [
        folge_dateiname(pos.MODELL, "o2", TAG, "preis", "f" * 64),
        folge_dateiname(pos.MODELL, "o2", TAG, "tarif", "f" * 64),
    ]
    manifest = baue_manifest(stand, TAG, lies_folgen([weg.klick]))
    assert manifest["belege"] == [] and manifest["folge_verworfen"] == 1


def test_folgebilder_ohne_ihr_einzelbild_zaehlen_nicht(weg):
    """Die Folge einer Kennung ohne Einzelbild (nicht angekommen) ist keine: das
    Einzelbild der anderen Position zeigt nur seine eigenen Schritte."""
    stand = {t: list(d) for t, d in weg.gh.stand.items()}
    fremd = folge_dateiname(pos.MODELL, "o2", TAG, "tarif", "f" * 64)
    stand[TAGES_RELEASE].append(fremd)
    (eintrag,) = baue_manifest(stand, TAG, lies_folgen([weg.klick]))["belege"]
    assert fremd not in json.dumps(eintrag)
    assert {kennung_der_adresse(b["datei"]) for b in eintrag["bildfolge"]} == {
        weg.beleg_id[:16]
    }


def test_s1_folge_entsteht_nur_aus_bildern_derselben_kennung():
    """Zeitfenster eines zweiten Laufs: das neue Einzelbild (K2) liegt, die Schritte
    der früheren Position (K1) stehen noch. Keine Mischfolge aus K2 und K1."""
    k1, k2 = "1" * 64, "2" * 64
    stand = {
        TAGES_RELEASE: [
            folge_dateiname(pos.MODELL, "o2", TAG, "preis", k2),
            folge_dateiname(pos.MODELL, "o2", TAG, "tarif", k1),
            folge_dateiname(pos.MODELL, "o2", TAG, "laufzeit", k1),
        ]
    }
    (eintrag,) = baue_manifest(stand, TAG, {})["belege"]
    assert "bildfolge" not in eintrag
    assert kennung_der_adresse(eintrag["url"]) == k2[:16]


def test_s1_einzelbild_ohne_kennung_bleibt_einzelbild_und_bildet_keine_folge(weg):
    """Bestand von vor der Einführung: nichts geht verloren, nichts zugeschlagen."""
    alt = dateiname(pos.MODELL, "o2", TAG)
    stand = {
        TAGES_RELEASE: [
            alt,
            folge_dateiname(pos.MODELL, "o2", TAG, "tarif", weg.beleg_id),
        ]
    }
    (eintrag,) = baue_manifest(stand, TAG, lies_folgen([weg.klick]))["belege"]
    assert eintrag["url"].endswith(f"/{alt}") and "bildfolge" not in eintrag


def test_s1_das_einzelbild_wird_mit_der_kennung_der_position_benannt():
    modul = lade_skript("belege_veroeffentlichen")
    plain = dateiname(pos.MODELL, "o2", TAG)
    zeilen: list[str] = []
    gut = modul.einzelbild_name(SimpleNamespace(beleg_id="ab" * 32), plain, zeilen)
    assert gut == folge_dateiname(pos.MODELL, "o2", TAG, "preis", "ab" * 32)
    assert zerlege_folgename(gut).kennung == "ab" * 8 and zeilen == []
    kaputt = modul.einzelbild_name(SimpleNamespace(beleg_id="kein-hex"), plain, zeilen)
    assert kaputt == plain and "ohne Kennung" in zeilen[0]


def test_s2_die_seite_zeigt_kein_bild_einer_anderen_messung(weg, tmp_path):
    """Folge der Kennung K, die Zeile gehört zu einer anderen ``beleg_id``: kein Bild,
    ein Vermerk statt des fremden Bilds (kein Bild unter der falschen Zeile)."""
    fremd_id = "9" * 64
    assert fremd_id[:16] != weg.beleg_id[:16]
    seite = _seite(tmp_path, weg.manifest, fremd_id)
    paar = next(
        li for li in seite.select(".gr-beleg-paar") if li["data-anbieter"] == "o2"
    )
    assert paar.select("img") == [] and paar.select(".gr-bildfolge") == []
    keins = paar.select_one(".gr-beleg-keins")
    assert "hidden" not in keins.attrs
    text = keins.get_text(" ", strip=True)
    assert "gehört zu einer anderen Messung" in text
    assert weg.beleg_id[:16] not in text and fremd_id[:16] not in text, text
    assert "Messung " + fremd_id[:4] not in text


def _adr(name: str) -> str:
    return f"{ADRESSE_ANFANG}{TAG}/{name}"


def test_s2_ein_fremder_schritt_verwirft_die_ganze_folge():
    eigene = "ab" * 8
    folge = [
        {"url": _adr(folge_dateiname(pos.MODELL, "o2", TAG, s, k)), "schritt": s}
        for s, k in (("tarif", eigene), ("preis", eigene), ("laufzeit", "cd" * 8))
    ]
    einzel = folge[1]["url"]
    assert "laufzeit" in fremd_zur_kennung(einzel, folge, eigene)
    assert fremd_zur_kennung(einzel, folge[:2], eigene) == ""
    assert "gehört zur Messung" in fremd_zur_kennung(einzel, folge[:2], "cd" * 8)
    alt = _adr(dateiname(pos.MODELL, "o2", TAG))
    assert fremd_zur_kennung(alt, [], eigene) == "", "altes Einzelbild: nicht beweisbar"
    ohne_namen = [{"url": _adr("x__y__2026-11-08.webp"), "schritt": "tarif"}]
    assert fremd_zur_kennung(alt, ohne_namen, eigene)


def test_s2_mischfolge_aus_zwei_kennungen_liest_die_seite_nicht(weg):
    manifest = json.loads(json.dumps(weg.manifest))
    b = manifest["belege"][0]
    b["bildfolge"][0]["datei"] = _adr(
        folge_dateiname(pos.MODELL, "o2", TAG, "geraet_speicher", "7" * 64)
    )
    assert normalisiere(b["bildfolge"], b["bildfolge_fehlt"]) == ()


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


@pytest.mark.browser
def test_folge_im_browser_ohne_querscrollen_mit_den_veroeffentlichten_bildern(
    weg, seitenordner, chromium
):
    """Im echten Chromium bei 1440 und 390 px: aufklappen, drei Bilder laden (die
    Adressen liefert die Fixture mit den hochgeladenen Bytes), der Lückenvermerk
    steht da, die Seite scrollt nicht quer."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(seitenordner)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def liefere(route):
        name = route.request.url.rsplit("/", 1)[1]
        route.fulfill(body=weg.gh.inhalte[name], content_type="image/webp")

    try:
        for breite in (1440, 390):
            ctx = chromium.new_context(viewport={"width": breite, "height": 900})
            try:
                ctx.route("https://github.com/**", liefere)
                s = ctx.new_page()
                meldungen: list[str] = []
                s.on("console", lambda m, k=meldungen: k.append(m.text))
                s.on("pageerror", lambda e, k=meldungen: k.append(str(e)))
                port = httpd.server_address[1]
                s.goto(f"http://127.0.0.1:{port}/geraete.html")
                s.click("#gr-zr-laufzeiten button[data-lz='24']")
                s.locator("#gr-bnd-gruppe .gr-beleg-zeile summary").first.click()
                s.wait_for_function(
                    "[...document.querySelectorAll('.gr-bildfolge img')]"
                    ".every(i => i.hasAttribute('src'))"
                )
                geladen = s.evaluate(
                    "[...document.querySelectorAll('.gr-bildfolge img')]"
                    ".filter(i => i.complete && i.naturalWidth > 0).length"
                )
                assert geladen == 3, breite
                luecke = s.locator(".gr-bildfolge-luecke .gr-bildfolge-text")
                assert luecke.inner_text() == f"Kein Bild: {GRUND}"
                assert s.evaluate("document.documentElement.scrollWidth") <= breite
                assert meldungen == [], breite
            finally:
                ctx.close()
    finally:
        httpd.shutdown()


VERMERK = "Bild nicht mehr verfügbar"


def _zustand(s) -> dict:
    return s.evaluate(
        """() => {
          const z = document.querySelector(
            '#gr-bnd-gruppe .gr-beleg-zeile:not([hidden])');
          const bilder = [...z.querySelectorAll('img')];
          return {
            summary: z.querySelector('summary').textContent,
            kaputt: bilder.filter(i => !(i.complete && i.naturalWidth > 0)).length,
            bilder: bilder.length,
            schritte: [...z.querySelectorAll('.gr-bildfolge > li')].map(li => ({
              kopf: li.querySelector('.gr-bildfolge-schritt').textContent,
              vermerk: (li.querySelector('.gr-bild-fehlt') || {}).textContent || null,
              bild: !!li.querySelector('img'),
            })),
            direkt: [...z.querySelectorAll('details > .gr-bild-fehlt')]
              .map(v => v.textContent),
            quer: document.documentElement.scrollWidth,
          };
        }"""
    )


def _pruefe_ladefehler(
    weg, ordner, chromium, manifest, tot, erwartet, breiten, label="schritt"
):
    """Öffnet die Zeile im Chromium; Adressen, deren Dateiname ``tot`` enthält, geben
    404 (gelöschte Release-Datei), alle anderen die hochgeladenen Bytes."""
    site = baue_seite(ordner, manifest, weg.beleg_id)
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def liefere(route):
        name = route.request.url.rsplit("/", 1)[1]
        if any(t in name for t in tot):
            route.fulfill(status=404, body="Not Found", content_type="text/plain")
        else:
            route.fulfill(body=weg.gh.inhalte[name], content_type="image/webp")

    ergebnis = {}
    try:
        for breite in breiten:
            ctx = chromium.new_context(viewport={"width": breite, "height": 900})
            try:
                ctx.route("https://github.com/**", liefere)
                s = ctx.new_page()
                s.goto(f"http://127.0.0.1:{httpd.server_address[1]}/geraete.html")
                s.click("#gr-zr-laufzeiten button[data-lz='24']")
                s.locator("#gr-bnd-gruppe .gr-beleg-zeile summary").first.click()
                s.wait_for_function(
                    "[...document.querySelectorAll('.gr-beleg-zeile img')]"
                    ".every(i => i.complete)"
                )
                s.wait_for_timeout(300)
                zustand = _zustand(s)
                assert zustand["quer"] <= breite, (breite, zustand)
                assert zustand["kaputt"] == 0, (breite, "kaputtes Bild", zustand)
                erwartet(zustand, breite)
                ergebnis[breite] = zustand
                ablage = os.environ.get("BELEG_ABNAHME_ORDNER")
                if ablage:
                    s.locator(".gr-beleg-paar[data-anbieter='o2']").screenshot(
                        path=f"{ablage}/{label}-{breite}.png"
                    )
            finally:
                ctx.close()
    finally:
        httpd.shutdown()
    return ergebnis


@pytest.mark.browser
def test_ein_geloeschtes_folgebild_wird_zum_vermerk_an_derselben_stelle(
    weg, tmp_path, chromium
):
    """Befund N1: die Datei eines Schritts ist weg (404). Statt des kaputten Bilds
    steht an derselben Stelle der Vermerk, der Zähler nennt die Bilder, die da sind."""

    def erwartet(z, breite):
        assert z["summary"].count("2 von 4 Schritten mit Bild") == 1, z["summary"]
        assert z["bilder"] == 2
        verteilt = [(x["kopf"].split(": ")[0], x["vermerk"]) for x in z["schritte"]]
        assert ("Schritt 3 von 4", VERMERK) in verteilt, verteilt
        assert sum(1 for x in z["schritte"] if x["vermerk"] == VERMERK) == 1
        ort = [x["vermerk"] for x in z["schritte"]].index(VERMERK)
        assert z["schritte"][ort]["bild"] is False
        assert z["schritte"][ort]["kopf"].startswith("Schritt")

    _pruefe_ladefehler(
        weg, tmp_path, chromium, weg.manifest, ["laufzeit"], erwartet, (1440, 390)
    )


@pytest.mark.browser
def test_fehlen_alle_bilder_der_folge_sagt_der_zaehler_null_von_n(
    weg, tmp_path, chromium
):
    def erwartet(z, breite):
        assert "0 von 4 Schritten mit Bild" in z["summary"], z["summary"]
        assert z["bilder"] == 0
        assert [x["vermerk"] for x in z["schritte"]].count(VERMERK) == 3

    _pruefe_ladefehler(
        weg, tmp_path, chromium, weg.manifest, ["__"], erwartet, (390,), "alle"
    )


@pytest.mark.browser
def test_ein_geloeschtes_einzelbild_wird_zum_vermerk(weg, tmp_path, chromium):
    manifest = json.loads(json.dumps(weg.manifest))
    for eintrag in manifest["belege"]:
        eintrag.pop("bildfolge", None)
        eintrag.pop("bildfolge_fehlt", None)

    def erwartet(z, breite):
        assert z["bilder"] == 0 and z["direkt"] == [VERMERK], z
        assert "Screenshot zu dieser Preiszeile" in z["summary"]

    _pruefe_ladefehler(
        weg, tmp_path, chromium, manifest, ["__"], erwartet, (1440, 390), "einzel"
    )
