"""Manifest und Archiv der Belege (Datenkonzept Geräteradar, Abschnitt 10), ohne Netz.

Die Belege sind ein BEISPIEL (``tests/belegbau.py``); die Ablage ist ein Ordner, der
Stempel ein fester Ersatz, damit kein Test ins Netz geht.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest
from belegbau import ZEIT, antwortkopie, paket, png

from telco_radar.collect.geraete.belegablage import ArchivFehler, LokaleAblage
from telco_radar.collect.geraete.belegarchiv import (
    ARCHIVIERT,
    GESTOERT,
    NICHT_ABGELEGT,
    OHNE_BELEG,
    archiviere,
)
from telco_radar.collect.geraete.belegmanifest import (
    ManifestFehler,
    ablageschluessel,
    lies_manifest,
    manifestpfad,
    pruefe_manifest,
)
from telco_radar.collect.geraete.belegstempel import AUSGEFALLEN, Stempel
from telco_radar.collect.geraete.klickecho import Variante
from telco_radar.collect.geraete.klicklauf import (
    BEFUND,
    BELEG_FEHLT,
    BELEG_OFFEN,
    BELEGT,
    ERFASST,
    NICHT_ANGEBOTEN,
    Klicklauf,
    Kombiergebnis,
)

AUSFALL = (Stempel("rfc3161", "http://127.0.0.1:9/tsr", AUSGEFALLEN, "HTTP 500"),)


def _stempler(digests: list[str]):
    def stempel(digest: str) -> tuple[Stempel, ...]:
        digests.append(digest)
        return AUSFALL

    return stempel


def _lauf(*pakete) -> Klicklauf:
    lauf = Klicklauf("Beispielanbieter", "http://127.0.0.1:8000/handy/beispielhandy-x")
    for nummer, fertig in enumerate(pakete):
        variante = Variante("256", "S", 24 + nummer)
        offen = Kombiergebnis(variante, ERFASST, beleg=fertig, beleg_status=BELEG_OFFEN)
        lauf.ergebnisse.append(offen)
    lauf.ergebnisse.append(Kombiergebnis(Variante("128", "S", 36), NICHT_ANGEBOTEN))
    return lauf


def _archiv(tmp_path, *pakete):
    ablage = LokaleAblage(tmp_path / "ablage")
    digests: list[str] = []
    bericht = archiviere(
        _lauf(*pakete), ablage, tmp_path / "manifest", ZEIT, stempler=_stempler(digests)
    )
    pfad = manifestpfad(tmp_path / "manifest", "Beispielanbieter", date(2026, 10, 3))
    return bericht, ablage, pfad, digests


def _zweiter() -> object:
    return paket(
        screenshot_png=png((10, 10, 200)), antwort=antwortkopie(None, etag="b")
    )


def test_archiv_legt_dateien_ab_und_schreibt_eine_zeile_je_beleg(tmp_path):
    erster, zweiter = paket(), _zweiter()

    bericht, ablage, pfad, digests = _archiv(tmp_path, erster, zweiter)

    assert bericht.zustand == ARCHIVIERT
    assert bericht.belege == 2
    assert bericht.fehlend == ()
    assert bericht.manifeste == (pfad,)
    assert pfad.relative_to(tmp_path).as_posix() == (
        "manifest/beispielanbieter/2026-10-03.jsonl"
    )
    manifest = lies_manifest(pfad)
    assert [b.beleg_id for b in manifest.belege] == [
        erster.beleg.beleg_id,
        zweiter.beleg.beleg_id,
    ]
    assert manifest.belege[0] == erster.beleg
    schluessel = ablageschluessel(erster.beleg, erster.beleg.bild)
    assert schluessel == f"beispielanbieter/2026-10-03/{erster.beleg.beleg_id}.webp"
    assert ablage.lies(schluessel) == erster.bild
    assert pruefe_manifest(pfad, ablage.lies) == []
    zeilen = [json.loads(z) for z in pfad.read_text("utf-8").splitlines()]
    assert [z["art"] for z in zeilen] == ["beleg", "beleg", "stempel"]
    assert [z["version"] for z in zeilen] == [2, 2, 1]
    assert len(digests) == 1


def test_ausgefallener_stempel_steht_benannt_im_manifest(tmp_path):
    _, ablage, pfad, digests = _archiv(tmp_path, paket())

    stempelzeile = lies_manifest(pfad).stempel[0]

    assert stempelzeile.stempel == AUSFALL
    assert stempelzeile.stempel[0].zustand == "ausgefallen"
    assert stempelzeile.digest == digests[0]
    assert stempelzeile.zeilen == 1
    assert stempelzeile.zeitpunkt == "2026-10-03T05:00:00Z"
    assert pruefe_manifest(pfad, ablage.lies) == []


def test_zweiter_lauf_desselben_tages_haengt_an_und_stempelt_neu(tmp_path):
    _archiv(tmp_path, paket())
    _, ablage, pfad, digests = _archiv(tmp_path, _zweiter())

    manifest = lies_manifest(pfad)

    assert len(manifest.belege) == 2
    assert [s.zeilen for s in manifest.stempel] == [1, 3]
    assert pruefe_manifest(pfad, ablage.lies) == []


def test_falscher_hash_oder_fehlende_datei_schlagen_an(tmp_path):
    erster = paket()
    _, ablage, pfad, _ = _archiv(tmp_path, erster)
    bild = ablageschluessel(erster.beleg, erster.beleg.bild)
    har = ablageschluessel(erster.beleg, erster.beleg.mitschnitt)

    ablage.lege(bild, erster.bild + b"x", "image/webp")
    ablage.loesche(har)
    befunde = pruefe_manifest(pfad, ablage.lies)

    assert "Zeile 1: Bild" in befunde[0]
    assert any("SHA-256 passt nicht" in b for b in befunde)
    assert any("Größe passt nicht" in b for b in befunde)
    assert any(f"{erster.beleg.beleg_id}.har fehlt in der Ablage" in b for b in befunde)


def test_beleg_id_die_nicht_zu_den_dateien_passt_schlaegt_an(tmp_path):
    erster = paket()
    _, ablage, pfad, _ = _archiv(tmp_path, erster)
    zeilen = pfad.read_text("utf-8").splitlines()
    daten = json.loads(zeilen[0])
    daten["beleg_id"] = "f" * 64
    pfad.write_text(json.dumps(daten) + "\n", "utf-8")

    befunde = pruefe_manifest(pfad, ablage.lies)

    assert "Zeile 1: beleg_id passt nicht zu den Dateien" in befunde


def test_cookie_im_gespeicherten_mitschnitt_schlaegt_an(tmp_path):
    erster = paket()
    _, ablage, pfad, _ = _archiv(tmp_path, erster)
    har = json.loads(erster.mitschnitt)
    har["log"]["entries"][0]["request"]["headers"].append(
        {"name": "Cookie", "value": "a=b"}
    )
    roh = json.dumps(har).encode()
    ablage.lege(ablageschluessel(erster.beleg, erster.beleg.mitschnitt), roh, "x")

    befunde = pruefe_manifest(pfad, ablage.lies)

    assert "Zeile 1: Mitschnitt trägt request: Kopf cookie" in befunde


@pytest.mark.parametrize(
    ("aendere", "befund"),
    [
        (lambda d: d.pop("seite"), "Zeile 1: Feld fehlt: seite"),
        (lambda d: d.update(adresse=" "), "Zeile 1: Feld adresse ist leer"),
        (lambda d: d.update(version=9), "Zeile 1: unbekannte Version 9"),
        (lambda d: d.update(neu=1), "Zeile 1: unbekanntes Feld: neu"),
        (lambda d: d.update(zeitpunkt="03.10.2026"), "keine UTC-Zeit"),
        (lambda d: d["fundstellen"].pop(), "Wert volumen_gb ohne vollständige"),
        (lambda d: d["fundstellen"][0].update(ausschnitt=""), "Wert anzahlung ohne"),
        (lambda d: d["werte"].pop("rate"), "werte nennt nicht genau die Wertfelder"),
    ],
)
def test_unvollstaendige_zeile_schlaegt_an(tmp_path, aendere, befund):
    _, ablage, pfad, _ = _archiv(tmp_path, paket())
    daten = json.loads(pfad.read_text("utf-8").splitlines()[0])
    aendere(daten)
    pfad.write_text(json.dumps(daten, ensure_ascii=False) + "\n", "utf-8")

    befunde = pruefe_manifest(pfad, ablage.lies)

    assert any(befund in b for b in befunde), befunde


def _als_version_1(daten: dict) -> None:
    daten.update(version=1)
    for feld in ("buendelbetrag", "einmalzahlung"):
        del daten["werte"][feld]


def test_beleg_version_1_ohne_buendelwerte_bleibt_lesbar(tmp_path):
    _, ablage, pfad, _ = _archiv(tmp_path, paket())
    zeilen = pfad.read_text("utf-8").splitlines(keepends=True)
    daten = json.loads(zeilen[0])
    assert (daten["version"], daten["werte"]["buendelbetrag"]) == (2, None)
    _als_version_1(daten)
    zeilen[0] = json.dumps(daten, ensure_ascii=False) + "\n"
    pfad.write_text("".join(zeilen), "utf-8")

    alt = lies_manifest(pfad).belege[0]

    assert alt.version == 1
    assert "buendelbetrag" not in alt.werte
    assert pruefe_manifest(pfad, ablage.lies) == ["Zeile 2: Stempel-Digest passt nicht"]


@pytest.mark.parametrize(
    "aendere",
    [
        lambda d: d["werte"].pop("einmalzahlung"),
        lambda d: (_als_version_1(d), d["werte"].update(buendelbetrag=None)),
    ],
)
def test_buendelfelder_muessen_zur_version_passen(tmp_path, aendere):
    _, ablage, pfad, _ = _archiv(tmp_path, paket())
    daten = json.loads(pfad.read_text("utf-8").splitlines()[0])
    aendere(daten)
    pfad.write_text(json.dumps(daten, ensure_ascii=False) + "\n", "utf-8")

    with pytest.raises(ManifestFehler, match="werte nennt nicht genau die Wertfelder"):
        lies_manifest(pfad)


def test_zeile_vor_dem_stempel_geaendert_bricht_den_digest(tmp_path):
    _, ablage, pfad, _ = _archiv(tmp_path, paket())
    zeilen = pfad.read_text("utf-8").splitlines(keepends=True)
    zeilen[0] = zeilen[0].replace('"status": "erfasst"', '"status": "befund"')
    pfad.write_text("".join(zeilen), "utf-8")

    befunde = pruefe_manifest(pfad, ablage.lies)

    assert befunde == ["Zeile 2: Stempel-Digest passt nicht"]


def test_lies_manifest_nennt_die_kaputte_zeile(tmp_path):
    _, _, pfad, _ = _archiv(tmp_path, paket())
    with pfad.open("a", encoding="utf-8") as datei:
        datei.write("kein json\n")

    with pytest.raises(ManifestFehler) as fehler:
        lies_manifest(pfad)

    assert fehler.value.zeile == 3
    assert "kein JSON" in str(fehler.value)


def test_lauf_ohne_beleg_heisst_ohne_beleg_nicht_archiviert(tmp_path):
    ablage = LokaleAblage(tmp_path / "ablage")

    bericht = archiviere(_lauf(), ablage, tmp_path / "m", ZEIT, stempler=lambda d: ())

    assert bericht.zustand == OHNE_BELEG
    assert bericht.grund == "keine Belege im Lauf"
    assert not (tmp_path / "m").exists()


class _Kaputt(LokaleAblage):
    def lege(self, schluessel: str, daten: bytes, typ: str) -> None:
        if schluessel.endswith(".har") and b'"etag"' in daten:
            raise ArchivFehler(f"{schluessel}: Ablage antwortet HTTP 503")
        super().lege(schluessel, daten, typ)


def test_gestoerte_ablage_heisst_gestoert_und_haelt_nur_ganze_belege(tmp_path):
    erster, zweiter = paket(), _zweiter()
    ablage = _Kaputt(tmp_path / "ablage")

    bericht = archiviere(
        _lauf(erster, zweiter), ablage, tmp_path / "m", ZEIT, stempler=lambda d: ()
    )

    assert bericht.zustand == GESTOERT
    assert "HTTP 503" in bericht.grund
    assert bericht.belege == 1
    pfad = bericht.manifeste[0]
    assert [b.beleg_id for b in lies_manifest(pfad).belege] == [erster.beleg.beleg_id]
    assert pruefe_manifest(pfad, ablage.lies) == []


def test_beleg_ohne_ablage_und_manifest_fehlt_und_ist_nicht_gueltig(tmp_path):
    erster, zweiter, dritter = paket(), _zweiter(), paket(screenshot_png=png((9, 9, 9)))
    lauf = _lauf(erster, zweiter, dritter)
    ablage = _Kaputt(tmp_path / "ablage")

    bericht = archiviere(lauf, ablage, tmp_path / "m", ZEIT, stempler=lambda d: ())

    belegt, *fehlt = lauf.ergebnisse[:3]
    assert (belegt.beleg_status, belegt.gueltig) == (BELEGT, True)
    assert [e.beleg_status for e in fehlt] == [BELEG_FEHLT, BELEG_FEHLT]
    assert not any(e.gueltig for e in fehlt)
    assert all(e.status == BEFUND for e in fehlt)
    assert all(e.grund.startswith(f"{NICHT_ABGELEGT}: Archiv gestört") for e in fehlt)
    assert [e.beleg for e in fehlt] == [zweiter, dritter]
    assert bericht.fehlend == tuple(e.variante for e in fehlt)
    assert lauf.ergebnisse[3].beleg_status != BELEG_FEHLT


def test_manifest_nicht_schreibbar_heisst_jeder_beleg_fehlt(tmp_path):
    lauf = _lauf(paket(), _zweiter())
    (tmp_path / "m").write_text("kein Ordner", "utf-8")

    bericht = archiviere(
        lauf, LokaleAblage(tmp_path / "a"), tmp_path / "m", ZEIT, stempler=lambda d: ()
    )

    assert bericht.zustand == GESTOERT
    assert bericht.grund.startswith("Archiv gestört: Manifest 2026-10-03.jsonl")
    assert (bericht.belege, bericht.manifeste) == (0, ())
    assert [e.beleg_status for e in lauf.ergebnisse[:2]] == [BELEG_FEHLT] * 2
    assert bericht.fehlend == (Variante("256", "S", 24), Variante("256", "S", 25))


@pytest.mark.parametrize("name", ["a b.webp", "x/../y.webp", "../../x.webp"])
def test_ungueltiger_dateiname_im_manifest_ist_ein_befund(tmp_path, name):
    _, ablage, pfad, _ = _archiv(tmp_path, paket(), _zweiter())
    zeilen = pfad.read_text("utf-8").splitlines()
    erste = json.loads(zeilen[0])
    erste["bild"]["name"] = name
    zeilen[0] = json.dumps(erste, ensure_ascii=False)
    pfad.write_text("\n".join(zeilen[:2]) + "\n", "utf-8")

    befunde = pruefe_manifest(pfad, ablage.lies)

    assert befunde[0].startswith("Zeile 1:"), befunde
    assert not any(b.startswith("Zeile 2:") for b in befunde)


def test_ablage_die_beim_lesen_scheitert_ist_ein_befund(tmp_path):
    _, _, pfad, _ = _archiv(tmp_path, paket())

    def lies(schluessel: str) -> bytes | None:
        raise ArchivFehler(f"{schluessel}: Ablage antwortet HTTP 503")

    befunde = pruefe_manifest(pfad, lies)

    assert any("nicht lesbar" in b and "HTTP 503" in b for b in befunde), befunde


def test_beleg_nach_mitternacht_landet_im_manifest_seines_tages(tmp_path):
    spaet = paket(datetime(2026, 10, 3, 23, 59, 59, tzinfo=UTC))
    frueh = paket(datetime(2026, 10, 4, 0, 0, 1, tzinfo=UTC))

    bericht, ablage, _, _ = _archiv(tmp_path, spaet, frueh)

    namen = [p.name for p in bericht.manifeste]
    assert namen == ["2026-10-03.jsonl", "2026-10-04.jsonl"]
    assert all(pruefe_manifest(p, ablage.lies) == [] for p in bericht.manifeste)
    assert ablageschluessel(frueh.beleg, frueh.beleg.bild).startswith(
        "beispielanbieter/2026-10-04/"
    )
