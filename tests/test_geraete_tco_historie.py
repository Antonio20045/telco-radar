"""P2 (Strategie Geraeteseite, 11.09.2026): die Buendel-Preishistorie.

Der Befund DAT-2: `geraete_tco.json` haelt je Buendel genau EINEN Satz,
und jeder Lauf ueberschreibt ihn (`TcoDB.save` schreibt die ganze Datei
neu). `geraete_tco_band._reihe()` kann daraus nur Einzelpunkte bauen - die
Leserfrage des Auftrags §1 („wann senken Wettbewerber Preise") hat keine
Datenbasis, und ein ueberschriebener Messtag ist nicht nachholbar.

Diese Tests pinnen die Schreibregeln der Append-Historie
`data/state/geraete_tco_historie.jsonl` (P2, Entscheidung 2):

  eine Zeile je (buendel_id, datum) mit den Messfeldern, der gerechneten
  Leitzahl `gesamt` und `abgerufen_am`;
  gleiches Datum je Buendel -> die Zeile wird ERSETZT (idempotent, kein
  Duplikat - derselbe Schutz wie `versand.json` gegen den zweiten Lauf);
  neues Datum -> neue Zeile dazu, alte Tage bleiben unveraendert;
  `geraete_tco.json` bleibt der aktuelle Stand je Buendel - die Seite
  liest WEITER daraus, keine Zeile Historie veraendert die Stand-Datei.

Und die Grenze aus Entscheidung 3: die Historie beginnt ehrlich mit dem
ersten Lauf nach der Umstellung - nichts wird aus den alten Stand-Commits
zurueckerfunden.
"""
from __future__ import annotations

import json
import pathlib

from telco_radar.analyze.tco_store import TcoDB
from telco_radar.tco_model import Buendel, tco_24

TAG0 = "2026-09-04"
TAG1 = "2026-09-11"
TAG2 = "2026-09-12"

SKU = "apple-iphone-15-128gb-schwarz"


# --------------------------------------------------------------------------
# Bausteine
# --------------------------------------------------------------------------

def _o2(datum: str, rate: float = 20.0) -> Buendel:
    """Die aufgeteilte Preisform: Tarifgrundpreis und Geraeterate getrennt."""
    return Buendel(sku_id=SKU, anbieter="o2",
                   tarif_name="O2 Mobile on Demand M Plus mit 50 GB+ (24 Mon.)",
                   tarif_id="o2:on-demand-m", tarif_id_guete="hoch",
                   tarif_monatlich=14.99, tarif_bindung_monate=24,
                   geraet_zuzahlung=1.0, geraet_monatsrate=rate,
                   laufzeit_monate=36, anschlusspreis=39.99, zustand="neu",
                   quelle_url=f"https://example.de/o2/{SKU}",
                   abgerufen_am=datum)


def _vodafone(datum: str, tarif: float = 29.95) -> Buendel:
    return Buendel(sku_id=SKU, anbieter="Vodafone",
                   tarif_name="Vodafone Mobil XS", tarif_id="vf:xs",
                   tarif_id_guete="hoch", tarif_monatlich=tarif,
                   tarif_bindung_monate=24, geraet_zuzahlung=0.0,
                   geraet_monatsrate=25.0, laufzeit_monate=24,
                   anschlusspreis=0.0, zustand="neu",
                   quelle_url=f"https://example.de/vf/{SKU}",
                   abgerufen_am=datum)


def _einsundeins(datum: str, monatlich: float = 44.99) -> Buendel:
    """Die zusammengefasste Preisform (§ 13.2): EIN Monatsbetrag fuer Tarif
    und Geraet plus Zuzahlung. P5 muss auch diese Reihe ueber die Zeit
    zeichnen koennen, deshalb steht die Form von Anfang an in der Historie."""
    return Buendel(sku_id=SKU, anbieter="1&1",
                   tarif_name="1&1 All-Net-Flat S",
                   tarif_id="einsundeins:all-net-s", tarif_id_guete="hoch",
                   buendel_monatlich=monatlich, laufzeit_monate=36,
                   geraet_zuzahlung=360.0, anschlusspreis=39.90,
                   zustand="neu",
                   quelle_url=f"https://example.de/einsundeins/{SKU}",
                   abgerufen_am=datum)


def _lauf(pfad: pathlib.Path, buendel: list[Buendel], datum: str) -> None:
    """Ein Lauf ist ein PROZESS: frischer Store, upsert, save.

    Der zweite Lauf laedt die Stand-Datei des ersten - genau wie der
    naechtliche Lauf des folgenden Tages den Stand der vorigen Nacht
    vorfindet.
    """
    db = TcoDB(pfad)
    db.upsert_buendel(buendel, datum)
    assert db.save(datum)


def _historie(pfad: pathlib.Path) -> list[dict]:
    historie = TcoDB(pfad).historie_path
    assert historie.exists(), f"{historie} fehlt"
    return [json.loads(zeile) for zeile in
            historie.read_text(encoding="utf-8").splitlines()
            if zeile.strip()]


# --------------------------------------------------------------------------
# Erster Lauf, zweiter Lauf, anderer Tag
# --------------------------------------------------------------------------

def test_erster_lauf_schreibt_je_buendel_eine_zeile(tmp_path):
    pfad = tmp_path / "geraete_tco.json"
    saetze = [_o2(TAG1), _vodafone(TAG1), _einsundeins(TAG1)]
    _lauf(pfad, saetze, TAG1)

    zeilen = _historie(pfad)
    assert len(zeilen) == 3
    nach_id = {z["id"]: z for z in zeilen}
    assert set(nach_id) == {s.id for s in saetze}

    for satz in saetze:
        zeile = nach_id[satz.id]
        assert zeile["datum"] == TAG1
        assert zeile["abgerufen_am"] == TAG1
        # Die Leitzahl steht FERTIG in der Zeile: P5 zeichnet die Reihe,
        # ohne die Rechnung des damaligen Laufs nachbauen zu muessen. Sie
        # bleibt eine Ableitung von `tco_model` - hier nur eingefroren.
        assert zeile["gesamt"] == tco_24(satz).gesamt

    o2 = nach_id[_o2(TAG1).id]
    assert o2["tarif_monatlich"] == 14.99
    assert o2["geraet_monatsrate"] == 20.0
    assert o2["geraet_zuzahlung"] == 1.0
    assert o2["anschlusspreis"] == 39.99
    assert o2["laufzeit_monate"] == 36
    assert o2["zustand"] == "neu"
    eins = nach_id[_einsundeins(TAG1).id]
    assert eins["buendel_monatlich"] == 44.99


def test_zweiter_lauf_am_selben_tag_ersetzt_statt_zu_duplizieren(tmp_path):
    pfad = tmp_path / "geraete_tco.json"
    _lauf(pfad, [_o2(TAG1), _vodafone(TAG1)], TAG1)
    historie = TcoDB(pfad).historie_path

    # Derselbe Tag, dieselben Werte: die Datei bleibt wortgleich.
    identisch = historie.read_text(encoding="utf-8")
    _lauf(pfad, [_o2(TAG1), _vodafone(TAG1)], TAG1)
    assert historie.read_text(encoding="utf-8") == identisch, \
        "ein wiederholter Lauf am selben Tag darf die Historie nicht aendern"

    # Derselbe Tag, korrigierte Werte: die Zeile wird aktualisiert - kein
    # zweiter Punkt fuer denselben Messtag (sonst luege die Reihe ab P5
    # um die Zahl der Nachtlaeufe, nicht um den Markt).
    _lauf(pfad, [_o2(TAG1, rate=18.0), _vodafone(TAG1, tarif=27.95)], TAG1)
    zeilen = _historie(pfad)
    assert len(zeilen) == 2
    nach_id = {z["id"]: z for z in zeilen}
    assert nach_id[_o2(TAG1).id]["geraet_monatsrate"] == 18.0
    assert nach_id[_o2(TAG1).id]["gesamt"] == \
        tco_24(_o2(TAG1, rate=18.0)).gesamt
    assert nach_id[_vodafone(TAG1).id]["tarif_monatlich"] == 27.95
    assert nach_id[_vodafone(TAG1, tarif=27.95).id]["gesamt"] == \
        tco_24(_vodafone(TAG1, tarif=27.95)).gesamt


def test_lauf_mit_anderem_datum_haengt_an_und_laesst_alte_tage_ruhen(tmp_path):
    pfad = tmp_path / "geraete_tco.json"
    _lauf(pfad, [_o2(TAG1), _vodafone(TAG1)], TAG1)
    alte_zeilen = _historie(pfad)

    _lauf(pfad, [_o2(TAG2, rate=18.0), _vodafone(TAG2)], TAG2)
    zeilen = _historie(pfad)
    assert len(zeilen) == 4
    # Die Zeilen von TAG1 stehen unveraendert da - auch nach der Korrektur
    # am folgenden Tag bleibt der gestrige Messtag der gemessene.
    assert zeilen[:2] == alte_zeilen
    assert {z["datum"] for z in zeilen[2:]} == {TAG2}
    assert next(z for z in zeilen[2:] if z["id"] == _o2(TAG2).id)[
        "geraet_monatsrate"] == 18.0


def test_zwei_laeufe_mit_verschiedenen_daten_ergeben_zwei_punkte(tmp_path):
    """Die Abnahme von P2 (Strategiedokument): nach zwei Laeufen existieren
    zwei Messpunkte je Buendel - hier an drei Beispiel-Buendeln, je eine
    Preisform. Kein Netz, die Daten sind injiziert."""
    pfad = tmp_path / "geraete_tco.json"
    _lauf(pfad, [_o2(TAG1, rate=20.0), _vodafone(TAG1),
                 _einsundeins(TAG1, monatlich=44.99)], TAG1)
    _lauf(pfad, [_o2(TAG2, rate=19.0), _vodafone(TAG2, tarif=28.95),
                 _einsundeins(TAG2, monatlich=42.99)], TAG2)

    je_id: dict[str, list[str]] = {}
    for zeile in _historie(pfad):
        je_id.setdefault(zeile["id"], []).append(zeile["datum"])
    for satz in (_o2(TAG1), _vodafone(TAG1), _einsundeins(TAG1)):
        assert sorted(je_id[satz.id]) == [TAG1, TAG2], satz.id


# --------------------------------------------------------------------------
# Die Stand-Datei und der ehrliche Anfang
# --------------------------------------------------------------------------

def test_die_stand_datei_bleibt_ein_satz_je_buendel(tmp_path):
    """`geraete_tco.json` behaelt seine Semantik: aktueller Stand, eine
    Messung je Buendel. Die Seite liest WEITER aus dieser Datei - die
    Historie waechst daneben, ohne den Leser zu aendern."""
    pfad = tmp_path / "geraete_tco.json"
    _lauf(pfad, [_o2(TAG1), _einsundeins(TAG1)], TAG1)
    _lauf(pfad, [_o2(TAG2), _einsundeins(TAG2)], TAG2)

    roh = json.loads(pfad.read_text(encoding="utf-8"))
    ids = [b["id"] for b in roh["buendel"]]
    assert len(ids) == len(set(ids)) == 2
    assert roh["updated"] == TAG2
    # Kein Historienfeld ist in den Stand gerutscht - „datum" ist der
    # Schluessel der Historiendatei, „gesamt" ihre gerechnete Spalte.
    for eintrag in roh["buendel"]:
        assert "datum" not in eintrag
        assert "gesamt" not in eintrag
        assert eintrag["last_verified"] == TAG2


def test_die_historie_beginnt_mit_dem_ersten_lauf_nicht_in_der_vergangenheit(tmp_path):
    """Entscheidung 3: keine Rekonstruktion aus den Stand-Commits.

    Der Bestand kennt `first_seen` vom 04.09. - die Historie tut so, als
    haette sie nie gemessen, bis dieser erste Lauf sie oeffnet. Keine
    zurueckerfundene Zeitreihe: ein Punkt ohne Messung ist eine Luecke,
    die niemand mehr pruefen kann."""
    pfad = tmp_path / "geraete_tco.json"
    bestand = {"updated": TAG0, "buendel": [], "sim_only": []}
    db = TcoDB(pfad)
    db.upsert_buendel([_o2(TAG0)], TAG0)
    db.save(TAG0)
    # Der simulierte Stand von frueher - ohne jede Historiendatei, so
    # liegt das Repo vor dieser Umstellung.
    TcoDB(pfad).historie_path.unlink(missing_ok=True)

    _lauf(pfad, [_o2(TAG1)], TAG1)
    assert [z["datum"] for z in _historie(pfad)] == [TAG1]


def test_eine_unlesbare_historie_wird_nicht_angefasst(tmp_path):
    """Die Historie ist das Einzige, was nicht neu entstehen kann. Ein
    Lesefehler darf sie deshalb nicht UEBERSCHREIBEN: das Zusammenfuegen
    liest-alt-und-schreibt-neu darf eine unlesbare Datei nicht durch eine
    nur-neue ersetzen - das waere der Totalverlust, gegen den P2 gebaut
    ist. Der Lauf wirft nicht; der Stand wird trotzdem gesichert."""
    pfad = tmp_path / "geraete_tco.json"
    _lauf(pfad, [_o2(TAG1)], TAG1)
    historie = TcoDB(pfad).historie_path
    muell = "{kein json\n"
    historie.write_text(muell, encoding="utf-8")

    _lauf(pfad, [_o2(TAG2)], TAG2)   # darf nicht werfen
    assert historie.read_text(encoding="utf-8") == muell, \
        "eine unlesbare Historie wird still ersatzlos ueberschrieben"
    # Der Stand ist trotzdem von heute - ein Historiesschaden kostet
    # keinen Messtag der Gegenwart.
    assert json.loads(pfad.read_text(encoding="utf-8"))["updated"] == TAG2
