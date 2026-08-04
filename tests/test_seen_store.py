"""Seen-Store im kompakten Format (Auftrag Skalierung 3.3).

Der Store ist die einzige Instanz, die verhindert, dass sich der Bericht
wiederholt - ein Fehler hier ist teurer als jede fehlende Quelle. Die Tests
sichern deshalb nicht nur das Format, sondern die Garantie: was einmal
gesehen wurde, gilt als gesehen, und der Verfall darf daran nichts aendern.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from telco_radar.dedupe import EPOCHE, SeenStore, _tagesnummer, filter_fresh
from telco_radar.models import Item


def _item(url: str, tage_alt: float | None = 1.0) -> Item:
    veroeffentlicht = None
    if tage_alt is not None:
        veroeffentlicht = datetime.now(timezone.utc) - timedelta(days=tage_alt)
    return Item(title=f"Meldung {url}", url=url, source_name="test",
                published=veroeffentlicht)


def test_format_ist_kompakt(tmp_path):
    pfad = tmp_path / "seen.tsv"
    store = SeenStore(pfad)
    store.add([_item(f"https://x.example/{i}") for i in range(200)])

    inhalt = pfad.read_text(encoding="utf-8")
    datenzeilen = [z for z in inhalt.splitlines()
                   if z and not z.startswith("#")]
    assert len(datenzeilen) == 200
    # Der ganze Sinn der Uebung: ~22 statt ~300 Byte je Eintrag.
    assert len(inhalt) / 200 < 30

    ident, tag = datenzeilen[0].split("\t")
    assert len(ident) == 16
    assert int(tag) == _tagesnummer()


def test_roundtrip_ueber_die_datei(tmp_path):
    pfad = tmp_path / "seen.tsv"
    a, b = _item("https://x.example/a"), _item("https://x.example/b")

    store = SeenStore(pfad)
    assert store.filter_new([a, b]) == [a, b]
    store.add([a])

    neu = SeenStore(pfad)
    assert neu.filter_new([a, b]) == [b]
    assert len(neu) == 1


def test_anhaengen_schreibt_die_datei_nicht_neu(tmp_path):
    """Sonst waechst das Git-Repo bei jedem Lauf um die ganze Datei."""
    pfad = tmp_path / "seen.tsv"
    store = SeenStore(pfad)
    store.add([_item("https://x.example/a")])
    vorher = pfad.read_text(encoding="utf-8")

    store2 = SeenStore(pfad)
    store2.add([_item("https://x.example/b")])
    nachher = pfad.read_text(encoding="utf-8")

    assert nachher.startswith(vorher)
    assert len(nachher.splitlines()) == len(vorher.splitlines()) + 1


def test_bekannte_meldung_wird_nicht_doppelt_geschrieben(tmp_path):
    pfad = tmp_path / "seen.tsv"
    a = _item("https://x.example/a")
    store = SeenStore(pfad)
    store.add([a, a])
    store.add([a])

    assert len([z for z in pfad.read_text().splitlines()
                if z and not z.startswith("#")]) == 1


# ------------------------------------------------------------- Verfall

def _alte_zeile(ident: str, tage_alt: int) -> str:
    return f"{ident}\t{_tagesnummer() - tage_alt}\n"


def test_datierte_eintraege_verfallen(tmp_path):
    pfad = tmp_path / "seen.tsv"
    pfad.write_text(_alte_zeile("a" * 16, 800) + _alte_zeile("b" * 16, 10))

    store = SeenStore(pfad, max_age_days=548)

    assert len(store) == 1
    assert store.verfallen == 1
    assert "b" * 16 in store._seen


def test_undatierte_eintraege_verfallen_nie(tmp_path):
    """Die Kerngarantie: was der Frischefilter nicht abfangen kann, bleibt.

    Eine Meldung ohne erkanntes Datum kaeme nach einem Verfall als "neu"
    zurueck und wuerde ein zweites Mal berichtet - filter_fresh laesst
    undatierte Meldungen ja bewusst durch.
    """
    pfad = tmp_path / "seen.tsv"
    pfad.write_text(f"{'a' * 16}\tu\n" + _alte_zeile("b" * 16, 9999))

    store = SeenStore(pfad, max_age_days=30)

    assert "a" * 16 in store._seen
    assert len(store) == 1 and store.verfallen == 1


def test_undatierte_meldung_wird_als_unverfallbar_gespeichert(tmp_path):
    pfad = tmp_path / "seen.tsv"
    store = SeenStore(pfad)
    store.add([_item("https://x.example/ohne-datum", tage_alt=None)])

    zeile = [z for z in pfad.read_text().splitlines()
             if z and not z.startswith("#")][0]
    assert zeile.endswith("\tu")
    assert SeenStore(pfad, max_age_days=1).verfallen == 0


def test_verfallene_meldung_faellt_dem_frischefilter_zum_opfer():
    """Warum der Verfall die Garantie nicht bricht - an einem Stueck.

    Verfaellt ein datierter Eintrag und listet die Quelle die Meldung
    Jahre spaeter noch, gilt sie als neu; der Frischefilter wirft sie
    wegen ihres Datums trotzdem weg.
    """
    alt = _item("https://x.example/alt", tage_alt=600)
    assert filter_fresh([alt], lookback_days=8) == []


def test_kompaktierung_bei_vielen_verfallenen(tmp_path):
    pfad = tmp_path / "seen.tsv"
    pfad.write_text("".join(_alte_zeile(f"{i:016x}", 900) for i in range(2500))
                    + _alte_zeile("f" * 16, 1))

    store = SeenStore(pfad, max_age_days=548)
    assert store.verfallen == 2500
    store.add([_item("https://x.example/neu")])

    zeilen = [z for z in pfad.read_text().splitlines()
              if z and not z.startswith("#")]
    assert len(zeilen) == 2          # nur der junge Altbestand und die neue
    assert store.verfallen == 0


def test_wenige_verfallene_loesen_keine_kompaktierung_aus(tmp_path):
    pfad = tmp_path / "seen.tsv"
    pfad.write_text(_alte_zeile("a" * 16, 900) + _alte_zeile("b" * 16, 1))

    store = SeenStore(pfad, max_age_days=548)
    store.add([_item("https://x.example/neu")])

    zeilen = [z for z in pfad.read_text().splitlines()
              if z and not z.startswith("#")]
    assert len(zeilen) == 3          # nur angehaengt, nichts neu geschrieben


def test_ohne_verfall_bleibt_alles_stehen(tmp_path):
    pfad = tmp_path / "seen.tsv"
    pfad.write_text(_alte_zeile("a" * 16, 5000))

    store = SeenStore(pfad, max_age_days=None)
    assert len(store) == 1 and store.verfallen == 0


# ------------------------------------------------------------ Migration

def _legacy(pfad, eintraege):
    pfad.write_text("".join(
        json.dumps({"id": i, "url": f"https://x.example/{i}", "title": "T",
                    "source": "test", "first_seen": ts}) + "\n"
        for i, ts in eintraege), encoding="utf-8")


def test_altbestand_wird_uebernommen(tmp_path):
    alt = tmp_path / "seen.jsonl"
    jetzt = datetime.now(timezone.utc).isoformat()
    _legacy(alt, [("a" * 16, jetzt), ("b" * 16, jetzt)])

    store = SeenStore(tmp_path / "seen.tsv", legacy_path=alt)

    assert len(store) == 2
    # und wird beim ersten Schreiben ins neue Format ueberfuehrt
    store.add([_item("https://x.example/c")])
    zeilen = [z for z in (tmp_path / "seen.tsv").read_text().splitlines()
              if z and not z.startswith("#")]
    assert len(zeilen) == 3
    assert all("\t" in z and not z.startswith("{") for z in zeilen)


def test_altbestand_behaelt_sein_erstsichtungsdatum(tmp_path):
    alt = tmp_path / "seen.jsonl"
    frueher = datetime.now(timezone.utc) - timedelta(days=700)
    _legacy(alt, [("a" * 16, frueher.isoformat())])

    store = SeenStore(tmp_path / "seen.tsv", max_age_days=548, legacy_path=alt)

    assert len(store) == 0 and store.verfallen == 1


def test_alte_datei_direkt_als_pfad_wird_erkannt(tmp_path):
    """Zeigt jemand mit dem neuen Store auf die alte Datei, darf das
    Gedaechtnis nicht still verloren gehen."""
    alt = tmp_path / "seen.jsonl"
    _legacy(alt, [("a" * 16, datetime.now(timezone.utc).isoformat())])

    store = SeenStore(alt)

    assert len(store) == 1


def test_kaputte_zeilen_werden_uebersprungen(tmp_path):
    pfad = tmp_path / "seen.tsv"
    pfad.write_text("# Kommentar\n\nxyz\n" + f"{'a' * 16}\tkeinezahl\n"
                    + _alte_zeile("b" * 16, 1))

    store = SeenStore(pfad, max_age_days=548)

    assert len(store) == 2          # "xyz" zu kurz, Rest uebernommen
    assert store._seen["a" * 16] is None   # unlesbares Datum -> unverfallbar


def test_epoche_ist_stabil():
    """Die Tagesnummer ist nur so gut wie ihr Bezugspunkt."""
    assert EPOCHE.isoformat() == "2020-01-01"
    assert _tagesnummer(datetime(2020, 1, 2, tzinfo=timezone.utc)) == 1
