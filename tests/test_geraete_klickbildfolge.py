"""Bildfolge je Preisposition (Auftrag 08.11.2026), gegen die Beispielseite, ohne Netz.

Die Seite unter ``tests/fixtures/klickcrawler/`` ist ein BEISPIEL, kein Anbieter. Ein
lokaler Server auf 127.0.0.1 liefert sie; keine Anfrage verlässt den Rechner.
"""

from __future__ import annotations

import dataclasses
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml
from belegbau import ZEIT, paket, png, quelle
from klickserver import Antwort, html, klickserver
from PIL import Image

from telco_radar.collect.geraete.belegablage import LokaleAblage
from telco_radar.collect.geraete.belegarchiv import archiviere
from telco_radar.collect.geraete.belegmanifest import (
    ManifestFehler,
    lies_manifest,
    manifestpfad,
    pruefe_manifest,
)
from telco_radar.collect.geraete.klickbeleg import baue_beleg
from telco_radar.collect.geraete.klickbildfolge import (
    HOECHSTE_BREITE,
    HOECHSTE_HOEHE,
    PREIS,
    SCHRITTE,
    Folgebild,
    lies_folge,
    schritttext,
    umfang,
)
from telco_radar.collect.geraete.klickcrawler import klicke_durch
from telco_radar.collect.geraete.klickecho import Variante
from telco_radar.collect.geraete.klickkarte import (
    KlickkartenFehler,
    klickkarte_aus_daten,
)
from telco_radar.collect.geraete.klicklauf import (
    BELEG_OFFEN,
    ERFASST,
    Klicklauf,
    Kombiergebnis,
)
from telco_radar.collect.geraete.klickpreistext import TEXT_OHNE_BETRAG
from telco_radar.collect.geraete.klicktext import (
    Buendelwerte,
    Preiswerte,
    betraege_im_text,
)
from telco_radar.collect.geraete.klicktor import Hostschleuse
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.tarif_model import Preisphase

FIXTURES = Path(__file__).parent / "fixtures" / "klickcrawler"
PRODUKTPFAD = "/handy/beispielhandy-x"
JETZT = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)
ROBOTS = "User-agent: *\nDisallow: /privat/json/\n"


def _karte(**ersetzt):
    daten = yaml.safe_load((FIXTURES / "beispiel_karte.yaml").read_text("utf-8"))
    for pfad, wert in ersetzt.items():
        *weg, letztes = pfad.split("__")
        knoten = daten
        for teil in weg:
            knoten = knoten[teil]
        knoten[letztes] = wert
    return klickkarte_aus_daten(daten, "Beispielkarte")


def _antworte():
    preise = json.loads((FIXTURES / "beispiel_preise.json").read_text("utf-8"))
    seite = (FIXTURES / "beispiel_produktseite.html").read_text("utf-8")

    def antworte(pfad: str) -> Antwort:
        teile = urlsplit(pfad)
        if teile.path == "/api/preis":
            frage = parse_qs(teile.query)
            teil = ("speicher", "tarif", "laufzeit")
            antwort = preise.get("|".join(frage.get(t, [""])[0] for t in teil))
            if antwort is None:
                return Antwort(404)
            return Antwort(200, "application/json", json.dumps(antwort))
        return html(seite) if teile.path == PRODUKTPFAD else Antwort(404)

    return antworte


def _laufe(chromium, *, karte=None, **weiter):
    def hole(url: str) -> tuple[int, str]:
        return (200, ROBOTS) if urlsplit(url).hostname == "127.0.0.1" else (404, "")

    waechter = RobotsWaechter(hole=hole)
    with klickserver(_antworte()) as server:
        lauf = klicke_durch(
            chromium,
            server.adresse(PRODUKTPFAD),
            karte or _karte(),
            waechter,
            lambda: JETZT,
            schleuse=Hostschleuse(waechter, lambda: JETZT),
            frist_ms=5000,
            **weiter,
        )
    return lauf, server, None


def _erste_position(chromium, **karte):
    """Die erste Position (128 GB, Tarif S, 24 Monate) des Beispiellaufs."""
    lauf, _, _ = _laufe(chromium, karte=_karte(**karte), hoechste=1)
    ergebnis = lauf.ergebnisse[0]
    assert (ergebnis.variante.speicher, ergebnis.variante.tarif) == ("128", "S")
    assert ergebnis.beleg is not None
    return ergebnis.beleg


def _bild(daten: bytes) -> Image.Image:
    return Image.open(io.BytesIO(daten))


def test_eine_position_liefert_vier_bilder_in_reihenfolge_mit_schrittnamen(chromium):
    fertig = _erste_position(chromium)
    beleg = fertig.beleg

    assert [b.schritt for b in beleg.bildfolge] == [
        "geraet_speicher",
        "tarif",
        "laufzeit",
        "preis",
    ]
    assert beleg.bildfolge_status == "vollstaendig"
    assert beleg.bildfolge_fehlt == ()
    texte = {b.schritt: b.text for b in beleg.bildfolge}
    assert "128" in texte["geraet_speicher"]
    assert "S" in texte["tarif"]
    assert "24 Monate" in texte["laufzeit"]
    assert "Zuzahlung" in texte["preis"]
    assert "Monatsrate" in texte["preis"]
    folge = {b.schritt: b for b in beleg.bildfolge}
    assert folge["preis"].datei == beleg.bild.name
    assert len(fertig.folgebilder) == 3
    for schritt in ("geraet_speicher", "tarif", "laufzeit"):
        daten = fertig.folgebilder[folge[schritt].datei]
        assert len(daten) == folge[schritt].groesse
        breite, hoehe = _bild(daten).size
        assert 0 < breite <= HOECHSTE_BREITE
        assert 0 < hoehe <= HOECHSTE_HOEHE
    assert len({b.datei for b in beleg.bildfolge}) == 4


def test_fehlt_ein_schritt_ist_die_folge_unvollstaendig_und_nie_aufgefuellt(chromium):
    fertig = _erste_position(chromium, knoepfe__laufzeit={"fest": "24"})
    beleg = fertig.beleg

    assert beleg.bildfolge_status == "unvollstaendig"
    assert [b.schritt for b in beleg.bildfolge] == ["geraet_speicher", "tarif", "preis"]
    assert len(beleg.bildfolge_fehlt) == 1
    assert beleg.bildfolge_fehlt[0].startswith("laufzeit: ")
    assert len(fertig.folgebilder) == 2


def test_karte_nennt_den_selektor_einer_dimension_ohne_knopf(chromium):
    fertig = _erste_position(
        chromium,
        knoepfe__laufzeit={"fest": "24"},
        bildfolge={"laufzeit": "#laufzeit"},
    )

    assert fertig.beleg.bildfolge_status == "vollstaendig"
    assert [b.schritt for b in fertig.beleg.bildfolge] == list(SCHRITTE)


def test_falsch_markierte_option_gibt_kein_bild(chromium):
    ziel = {"speicher": "256", "tarif": "S", "laufzeit": "24"}
    with klickserver(_antworte()) as server:
        seite = chromium.new_page()
        try:
            seite.goto(server.adresse(PRODUKTPFAD))
            bilder, luecken = lies_folge(seite, _karte(), ziel, 5000)
        finally:
            seite.close()

    assert sorted(bilder) == ["laufzeit", "tarif"]
    assert list(luecken) == ["geraet_speicher"]
    assert "Seite markiert ['128'] statt 256" in luecken["geraet_speicher"]


def test_schritt_ohne_bild_nennt_den_grund_der_karte_und_wird_nicht_aufgenommen(
    chromium,
):
    grund = "Die Ratenwahl steht nur auf der Produktseite"
    fertig = _erste_position(chromium, bildfolge={"laufzeit": {"ohne": grund}})
    beleg = fertig.beleg

    assert beleg.bildfolge_status == "unvollstaendig"
    assert [b.schritt for b in beleg.bildfolge] == ["geraet_speicher", "tarif", "preis"]
    assert beleg.bildfolge_fehlt == (f"laufzeit: {grund}",)
    assert len(fertig.folgebilder) == 2


def test_ohne_gilt_auch_wenn_die_seite_die_option_markiert():
    karte = _karte(bildfolge={"tarif": {"ohne": "Tarifname fehlt"}})

    assert dict(karte.bildfolge_ohne) == {"tarif": "Tarifname fehlt"}
    assert dict(karte.bildfolge) == {}


@pytest.mark.parametrize(
    "bildfolge",
    [
        {"tarif": {"grund": "x"}},
        {"tarif": {"ohne": ""}},
        {"tarif": {"ohne": "x", "selektor": "#tarif"}},
        {"tarif": ["x"]},
    ],
)
def test_karte_lehnt_kaputtes_ohne_ab(bildfolge):
    with pytest.raises(KlickkartenFehler):
        _karte(bildfolge=bildfolge)


_HOHE_SEITE = """<!doctype html><meta charset="utf-8">
<body style="margin:0;font:16px sans-serif">
<div style="height:{oben}px"></div>
<h1 id="titel" style="margin:0;height:40px;width:300px">Beispielhandy X</h1>
<div style="height:{luft}px"></div>
<div id="speicher" style="display:flex;gap:8px;width:300px">
  <button style="height:60px;border:3px solid #e20074">128 GB</button>
  <button style="height:60px">256 GB</button>
</div>
<div style="height:2000px"></div></body>"""


@pytest.mark.parametrize(("oben", "luft"), [(300, 500), (30, 500), (700, 300)])
def test_ausschnitt_umfasst_titel_und_knoepfe_auch_ueber_den_fensterrand(
    chromium, oben, luft
):
    from telco_radar.collect.geraete.klickbildfolge import schnappe

    seite = chromium.new_page(viewport={"width": 1280, "height": 900})
    try:
        seite.set_content(_HOHE_SEITE.format(oben=oben, luft=luft))
        bild = schnappe(seite, "#titel, #speicher button", "geraet_speicher", 5000)
    finally:
        seite.close()

    assert isinstance(bild, Folgebild)
    breite, hoehe = _bild(bild.png).size
    erwartet = 40 + luft + 60
    assert erwartet <= hoehe <= erwartet + 30
    assert hoehe > 360 and hoehe <= HOECHSTE_HOEHE
    assert breite >= 300


def test_verborgener_erster_treffer_haelt_den_ausschnitt_nicht_auf(chromium):
    from telco_radar.collect.geraete.klickbildfolge import schnappe

    seite = chromium.new_page(viewport={"width": 1280, "height": 900})
    try:
        seite.set_content(
            '<div class="kachel" style="display:none">versteckt</div>'
            '<div class="kachel" style="height:80px;width:200px">sichtbar</div>'
        )
        bild = schnappe(seite, ".kachel", "tarif", 1000)
    finally:
        seite.close()

    assert isinstance(bild, Folgebild)
    assert _bild(bild.png).size[1] >= 80


def test_karte_lehnt_unbekannten_schritt_der_bildfolge_ab():
    with pytest.raises(KlickkartenFehler):
        _karte(bildfolge={"farbe": "#x"})


def test_ausschnitt_bleibt_im_fenster_und_unter_der_grenze():
    boxen = [{"x": -50.0, "y": 5.0, "width": 3000.0, "height": 900.0}]

    rahmen = umfang(boxen, 1280, 900)

    assert rahmen is not None
    assert rahmen["x"] == 0.0
    assert rahmen["width"] <= HOECHSTE_BREITE
    assert rahmen["height"] <= HOECHSTE_HOEHE
    assert umfang([], 1280, 900) is None


def _folgequelle(**ersetzt):
    folge = {s: Folgebild(s, png((n * 40, 20, 20))) for n, s in enumerate(SCHRITTE[:3])}
    return quelle(folge=folge, modell="Beispielhandy X", **ersetzt)


def test_ohne_aufnahme_nennt_der_beleg_jeden_fehlenden_schritt():
    fertig, grund = baue_beleg(quelle(), _karte(), ZEIT)

    assert grund is None
    beleg = fertig.beleg
    assert beleg.bildfolge_status == "unvollstaendig"
    assert [b.schritt for b in beleg.bildfolge] == ["preis"]
    assert len(beleg.bildfolge_fehlt) == 3
    assert fertig.folgebilder == {}


def test_zu_grosses_bild_fehlt_mit_grund(monkeypatch):
    monkeypatch.setattr("telco_radar.collect.geraete.klickbeleg.HOECHSTE_BYTES", 1)

    fertig, _ = baue_beleg(_folgequelle(), _karte(), ZEIT)

    assert fertig.beleg.bildfolge_status == "unvollstaendig"
    assert all("größer" in f for f in fertig.beleg.bildfolge_fehlt)


def _archiv(tmp_path, fertig):
    ablage = LokaleAblage(tmp_path / "ablage")
    lauf = Klicklauf("Beispielanbieter", "http://127.0.0.1:8000/handy/beispielhandy-x")
    lauf.ergebnisse.append(
        Kombiergebnis(
            Variante("256", "S", 24), ERFASST, beleg=fertig, beleg_status=BELEG_OFFEN
        )
    )
    archiviere(lauf, ablage, tmp_path / "m", ZEIT, stempler=lambda d: ())
    pfad = manifestpfad(tmp_path / "m", "Beispielanbieter", date(2026, 10, 3))
    return ablage, pfad


def test_manifest_traegt_bildfolge_und_prueft_ihre_dateien(tmp_path):
    fertig, _ = baue_beleg(_folgequelle(), _karte(), ZEIT)
    ablage, pfad = _archiv(tmp_path, fertig)

    zeile = json.loads(pfad.read_text("utf-8").splitlines()[0])
    assert [b["schritt"] for b in zeile["bildfolge"]] == list(SCHRITTE)
    assert set(zeile["bildfolge"][0]) == {
        "datei",
        "schritt",
        "text",
        "sha256",
        "groesse",
    }
    assert zeile["bildfolge_status"] == "vollstaendig"
    assert lies_manifest(pfad).belege[0] == fertig.beleg
    assert pruefe_manifest(pfad, ablage.lies) == []

    erste = fertig.beleg.bildfolge[0]
    ziel = ablage.ordner / "beispielanbieter" / "2026-10-03" / erste.datei
    ziel.unlink()
    befunde = pruefe_manifest(pfad, ablage.lies)
    assert any("fehlt in der Ablage" in b and "geraet_speicher" in b for b in befunde)


def test_alte_zeile_ohne_bildfolge_bleibt_lesbar(tmp_path):
    ablage, pfad = _archiv(tmp_path, paket())
    zeilen = [json.loads(z) for z in pfad.read_text("utf-8").splitlines()]
    for feld in ("bildfolge", "bildfolge_status", "bildfolge_fehlt"):
        del zeilen[0][feld]
    pfad.write_text("\n".join(json.dumps(z) for z in zeilen) + "\n", encoding="utf-8")

    beleg = lies_manifest(pfad).belege[0]

    assert beleg.bildfolge == ()
    assert beleg.bildfolge_status is None


def test_manifest_lehnt_widerspruechliche_bildfolge_ab(tmp_path):
    fertig, _ = baue_beleg(_folgequelle(), _karte(), ZEIT)
    _, pfad = _archiv(tmp_path, fertig)
    zeile = json.loads(pfad.read_text("utf-8").splitlines()[0])
    zeile["bildfolge"] = zeile["bildfolge"][1:]
    pfad.write_text(json.dumps(zeile) + "\n", encoding="utf-8")

    with pytest.raises(ManifestFehler, match="vollstaendig"):
        lies_manifest(pfad)


def test_beleg_traegt_felder_unveraendert_neben_der_bildfolge():
    fertig, _ = baue_beleg(_folgequelle(), _karte(), ZEIT)
    alt, _ = baue_beleg(quelle(), _karte(), ZEIT)

    felder = {f.name for f in dataclasses.fields(fertig.beleg)}
    assert {"bild", "mitschnitt", "bildfolge", "bildfolge_status"} <= felder
    assert fertig.beleg.beleg_id == alt.beleg.beleg_id
    assert fertig.beleg.bild == alt.beleg.bild


def test_aufbewahrung_loescht_die_bilder_der_folge_mit_ihrem_beleg():
    from telco_radar.collect.geraete.belegaufbewahrung import aufbewahrung

    fertig, _ = baue_beleg(_folgequelle(), _karte(), ZEIT)

    entscheidung = aufbewahrung([fertig.beleg], date(2026, 10, 4))[0]

    namen = {d.rsplit("/", 1)[1] for d in entscheidung.dateien}
    assert {b.datei for b in fertig.beleg.bildfolge} <= namen
    assert len(namen) == 5


TELEKOM_BILD = (
    "EINMALIGE\nZAHLUNG\n138,95 €\ninkl. Bereitstellung\n39,95 €\n"
    "GESAMTPREIS\nMONATLICH\n76,85 €\nMonatlich\nPreisübersicht anzeigen"
)
GERAET_BILD = "Anzahlung 99,00 €\nMonatsrate 26,90 € x 36\nTarif 49,95 €"
BUENDEL_BILD = "Einmalig 49,00 €\nMonatlich 44,99 €"
GERAET = Preiswerte(
    anzahlung=99.0,
    rate=26.9,
    ratenzahl=36,
    anschluss=39.95,
    tarifphasen=(Preisphase(1, None, 49.95),),
)
VARIANTE = Variante("256 GB", "M", 36)
PREISBILD_FAELLE = {
    "summe": (GERAET, None, TELEKOM_BILD),
    "geraet": (GERAET, None, GERAET_BILD),
    "buendel": (Preiswerte(), Buendelwerte(44.99, 49.0), BUENDEL_BILD),
    "nur_monat": (GERAET, None, "Gesamtpreis monatlich 76,85 €"),
    "ohne_betrag": (GERAET, None, "Preis wird berechnet"),
    "ohne_text": (GERAET, None, None),
}


def _preistext(werte, buendel, bildtext):
    return schritttext(PREIS, VARIANTE, None, werte, buendel, bildtext)


def test_preistext_nennt_die_summe_die_das_bild_zeigt_nicht_die_geraetewerte():
    text = _preistext(GERAET, None, TELEKOM_BILD)

    assert text == (
        "Im Bild: einmalig 138,95 € · monatlich 76,85 € (Gerät und Tarif zusammen)"
    )
    assert "26,90" not in text
    assert "99,00" not in text


def test_preistext_nennt_geraetewerte_wenn_das_bild_sie_zeigt():
    text = _preistext(GERAET, None, GERAET_BILD)

    assert text == "Im Bild: Zuzahlung 99,00 € · Monatsrate 26,90 € × 36"


def test_preistext_haengt_die_ratenzahl_nur_an_die_gezeigte_monatsrate():
    text = _preistext(GERAET, None, "Anzahlung 99,00 €\n36 Raten")

    assert text == "Im Bild: Zuzahlung 99,00 €"


def test_preistext_nennt_buendelwerte_als_summe():
    text = _preistext(Preiswerte(), Buendelwerte(44.99, 49.0), BUENDEL_BILD)

    assert text == (
        "Im Bild: einmalig 49,00 € · monatlich 44,99 € (Gerät und Tarif zusammen)"
    )


def test_preistext_ohne_sichere_betraege_nennt_keine_zahl():
    for bildtext in (None, "", "Preis wird berechnet"):
        assert _preistext(GERAET, None, bildtext) == TEXT_OHNE_BETRAG
    assert not betraege_im_text(TEXT_OHNE_BETRAG)


@pytest.mark.parametrize("fall", PREISBILD_FAELLE)
def test_jeder_betrag_im_preistext_steht_im_bild(fall):
    werte, buendel, bildtext = PREISBILD_FAELLE[fall]

    text = _preistext(werte, buendel, bildtext)

    assert betraege_im_text(text) <= betraege_im_text(bildtext or "")
    assert text.startswith("Im Bild: ") or text == TEXT_OHNE_BETRAG


def test_preistext_der_position_stimmt_mit_dem_text_des_bildes(chromium):
    lauf, _, _ = _laufe(chromium, karte=_karte(), hoechste=1)
    ergebnis = lauf.ergebnisse[0]
    preis = {b.schritt: b.text for b in ergebnis.beleg.beleg.bildfolge}["preis"]

    assert preis.startswith("Im Bild: ")
    assert betraege_im_text(preis)
    assert betraege_im_text(preis) <= betraege_im_text(ergebnis.text)
