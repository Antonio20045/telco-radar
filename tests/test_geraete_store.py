"""Speicher und Historie des Geraeteradars.

Zwei Zusicherungen tragen dieses Modul, und beide sind teuer erkauft:

1. **Ein Fehltreffer listet nichts aus.** Dieselbe Zwei-Stufen-Logik wie in
   `analyze/promo_store.mark_stale` - ein einzelner Timeout beim Haendler
   darf niemals als "Geraet ausgelistet" in die Lifecycle-Statistik eingehen.
2. **Ein fehlender Wert ist kein geaenderter Wert.** Findet der Extraktor
   diesmal keinen Preis, ist das ein Ausfall und keine Preissenkung. Genau
   dieser Fehler steht in CLAUDE.md §6 fuer den Tarif-Radar
   ("80 GB -> nicht angegeben waere die haeufigste Falschmeldung").
"""
import json
from pathlib import Path

import pytest

from telco_radar.analyze.geraete_store import (
    GeraeteDB,
    Preishistorie,
    STATUS_AKTIV,
    STATUS_AUSGELISTET,
    STATUS_VERMUTLICH,
)
from telco_radar.geraete_model import Listung


def _listung(anbieter="expert", preis=1449.0, sku="apple-iphone-17-pro-max-256gb-titan-natur",
             tag="2026-08-10", verfuegbarkeit="lieferbar", einstieg="https://e.de/handys",
             device=None, **kw):
    # Das Geraet wird aus der SKU abgeleitet, sonst traegt jede Testlistung
    # dieselbe device_id - und der Verwandtenabgleich (`_finde_verwandten`)
    # legte zwei absichtlich verschiedene Artikel zusammen.
    return Listung(sku_id=sku, device_id=device or sku.split("-256gb")[0],
                   anbieter=anbieter, anbieter_typ="handel",
                   quelle_url=f"https://e.de/p/{sku}", abgerufen_am=tag,
                   preis_ohne_vertrag=preis, verfuegbarkeit=verfuegbarkeit,
                   einstieg_url=einstieg, **{"speicher_gb": 256, **kw})


# --------------------------------------------------------------------------
# Aufnahme
# --------------------------------------------------------------------------

def test_neue_listung_wird_aufgenommen(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    neu, gesehen = db.upsert([_listung()], "2026-08-10")
    assert neu == 1 and len(gesehen) == 1
    e = db.nach_id(next(iter(gesehen)))
    assert e["status"] == STATUS_AKTIV
    assert e["first_seen"] == "2026-08-10" and e["last_verified"] == "2026-08-10"
    assert e["erstpreis"] == 1449.0 and e["erstpreis_am"] == "2026-08-10"


def test_dieselbe_listung_zweimal_ist_kein_neuzugang(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung()], "2026-08-10")
    neu, _ = db.upsert([_listung(preis=1399.0, tag="2026-08-17")], "2026-08-17")
    assert neu == 0
    e = db.eintraege()[0]
    assert e["preis_ohne_vertrag"] == 1399.0
    assert e["first_seen"] == "2026-08-10" and e["last_verified"] == "2026-08-17"
    assert e["erstpreis"] == 1449.0        # der Einfuehrungspreis bleibt stehen


def test_listung_ohne_quelle_kommt_gar_nicht_in_den_store(tmp_path):
    """Akzeptanzkriterium aus Teil E - doppelt gesichert: das Modell laesst
    sie nicht bauen, der Store nimmt sie auch als rohes dict nicht an."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    with pytest.raises(ValueError, match="quelle_url"):
        db.upsert([{"sku_id": "x", "device_id": "x", "anbieter": "expert",
                    "anbieter_typ": "handel", "abgerufen_am": "2026-08-10"}],
                  "2026-08-10")


def test_speichern_und_wieder_laden(tmp_path):
    pfad = tmp_path / "geraete_db.json"
    db = GeraeteDB(pfad)
    db.upsert([_listung()], "2026-08-10")
    db.save("2026-08-10")
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    assert roh["updated"] == "2026-08-10" and len(roh["listungen"]) == 1
    assert GeraeteDB(pfad).eintraege()[0]["anbieter"] == "expert"


def test_kaputte_datei_startet_leer_statt_zu_werfen(tmp_path):
    pfad = tmp_path / "geraete_db.json"
    pfad.write_text("{kaputt", encoding="utf-8")
    assert GeraeteDB(pfad).eintraege() == []


# --------------------------------------------------------------------------
# Zwei-Stufen-Auslistung
# --------------------------------------------------------------------------

def test_ein_fehltreffer_listet_nicht_aus(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    _, gesehen = db.upsert([_listung()], "2026-08-10")
    db.mark_stale("expert", set(), "2026-08-17", {"https://e.de/handys"})
    e = db.eintraege()[0]
    assert e["status"] == STATUS_VERMUTLICH
    assert e["stale_since"] == "2026-08-17" and e["missed_checks"] == 1


def test_zwei_fehltreffer_in_folge_listen_aus(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung()], "2026-08-10")
    db.mark_stale("expert", set(), "2026-08-17", {"https://e.de/handys"})
    db.mark_stale("expert", set(), "2026-08-24", {"https://e.de/handys"})
    e = db.eintraege()[0]
    assert e["status"] == STATUS_AUSGELISTET and e["ended_since"] == "2026-08-24"


def test_wiederbestaetigung_setzt_zurueck(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung()], "2026-08-10")
    db.mark_stale("expert", set(), "2026-08-17", {"https://e.de/handys"})
    _, gesehen = db.upsert([_listung(tag="2026-08-24")], "2026-08-24")
    db.mark_stale("expert", gesehen, "2026-08-24", {"https://e.de/handys"})
    e = db.eintraege()[0]
    assert e["status"] == STATUS_AKTIV and e["missed_checks"] == 0
    assert "stale_since" not in e


def test_ein_ausgelistetes_geraet_altert_nicht_weiter(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung()], "2026-08-10")
    for tag in ("2026-08-17", "2026-08-24", "2026-08-31"):
        db.mark_stale("expert", set(), tag, {"https://e.de/handys"})
    e = db.eintraege()[0]
    assert e["ended_since"] == "2026-08-24"   # nicht 08-31
    assert e["missed_checks"] == 2


def test_ungelesene_einstiegsseite_altert_ihre_geraete_nicht(tmp_path):
    """Die Falle, die im Promo-Zweig die halbe Marke geloescht haette: ein
    Anbieter mit fuenf Einstiegsseiten hat pro Lauf typischerweise EINE
    gescheiterte. Ohne diese Einschraenkung rueckten deren Geraete jedes Mal
    Richtung 'ausgelistet' - und das Protokoll saehe normal aus."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([
        _listung(sku="a-1-256gb-schwarz", einstieg="https://e.de/handys"),
        _listung(sku="a-2-256gb-schwarz", einstieg="https://e.de/tarife"),
    ], "2026-08-10")
    # Nur /handys wurde diesmal gelesen; /tarife ist ausgefallen.
    db.mark_stale("expert", set(), "2026-08-17", {"https://e.de/handys"})
    nach_einstieg = {e["einstiege"][0]: e["status"] for e in db.eintraege()}
    assert len(nach_einstieg) == 2      # sonst prueft der Vergleich nichts
    assert nach_einstieg["https://e.de/handys"] == STATUS_VERMUTLICH
    assert nach_einstieg["https://e.de/tarife"] == STATUS_AKTIV


def test_ohne_angabe_gelesener_einstiege_altert_alles(tmp_path):
    # Der Aufrufer sagt damit ausdruecklich "ich habe diesen Anbieter
    # vollstaendig gelesen".
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung(sku="a-1-256gb-schwarz"),
               _listung(sku="a-2-256gb-schwarz", einstieg="https://e.de/tarife")],
              "2026-08-10")
    db.mark_stale("expert", set(), "2026-08-17", None)
    assert {e["status"] for e in db.eintraege()} == {STATUS_VERMUTLICH}


def test_fremder_anbieter_bleibt_unberuehrt(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung(anbieter="expert"), _listung(anbieter="Euronics")],
              "2026-08-10")
    db.mark_stale("expert", set(), "2026-08-17", None)
    nach_anbieter = {e["anbieter"]: e["status"] for e in db.eintraege()}
    assert len(nach_anbieter) == 2
    assert nach_anbieter["Euronics"] == STATUS_AKTIV


# --------------------------------------------------------------------------
# Preishistorie
# --------------------------------------------------------------------------

def test_erste_messung_schreibt_eine_zeile(tmp_path):
    h = Preishistorie(tmp_path / "geraete_preise.jsonl")
    assert h.schreibe(_listung(), "2026-08-10") is True
    h.save()
    zeilen = [json.loads(z) for z in
              (tmp_path / "geraete_preise.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(zeilen) == 1
    assert zeilen[0]["preis_ohne_vertrag"] == 1449.0 and zeilen[0]["datum"] == "2026-08-10"


def test_unveraenderter_preis_schreibt_keine_neue_zeile(tmp_path):
    """Sonst waechst die Datei sinnlos und der Preisverlauf ist nicht mehr
    lesbar - eine Kurve aus 52 identischen Punkten je Jahr und Geraet."""
    h = Preishistorie(tmp_path / "geraete_preise.jsonl")
    h.schreibe(_listung(tag="2026-08-10"), "2026-08-10")
    assert h.schreibe(_listung(tag="2026-08-17"), "2026-08-17") is False
    h.save()
    assert len((tmp_path / "geraete_preise.jsonl").read_text().strip().splitlines()) == 1


def test_geaenderter_preis_schreibt_eine_neue_zeile(tmp_path):
    h = Preishistorie(tmp_path / "geraete_preise.jsonl")
    h.schreibe(_listung(preis=1449.0), "2026-08-10")
    assert h.schreibe(_listung(preis=1399.0, tag="2026-08-17"), "2026-08-17") is True
    assert [p["preis_ohne_vertrag"] for p in h.reihe(_listung().listung_id)] == [1449.0, 1399.0]


def test_fehlender_preis_ist_keine_preisaenderung(tmp_path):
    """Die wichtigste Zeile dieser Datei. Ein Extraktor, der den Preis diesmal
    nicht fand, meldet sonst eine Senkung auf 'nicht angegeben' - und die
    Verfallskurve knickt auf null."""
    h = Preishistorie(tmp_path / "geraete_preise.jsonl")
    h.schreibe(_listung(preis=1449.0), "2026-08-10")
    ohne = Listung(sku_id=_listung().sku_id, device_id="apple-iphone-17-pro-max",
                   anbieter="expert", anbieter_typ="handel",
                   quelle_url="https://e.de/p", abgerufen_am="2026-08-17",
                   preis_ohne_vertrag=None, verfuegbarkeit="lieferbar")
    assert h.schreibe(ohne, "2026-08-17") is False
    assert [p["preis_ohne_vertrag"] for p in h.reihe(_listung().listung_id)] == [1449.0]


def test_verfuegbarkeitswechsel_wird_festgehalten(tmp_path):
    h = Preishistorie(tmp_path / "geraete_preise.jsonl")
    h.schreibe(_listung(verfuegbarkeit="lieferbar"), "2026-08-10")
    assert h.schreibe(_listung(verfuegbarkeit="ausverkauft", tag="2026-08-17"),
                      "2026-08-17") is True


def test_historie_wird_angehaengt_nicht_neu_geschrieben(tmp_path):
    pfad = tmp_path / "geraete_preise.jsonl"
    h1 = Preishistorie(pfad)
    h1.schreibe(_listung(preis=1449.0), "2026-08-10")
    h1.save()
    h2 = Preishistorie(pfad)
    h2.schreibe(_listung(preis=1399.0, tag="2026-08-17"), "2026-08-17")
    h2.save()
    assert len(pfad.read_text(encoding="utf-8").strip().splitlines()) == 2
    assert len(Preishistorie(pfad).reihe(_listung().listung_id)) == 2


def test_kaputte_zeile_in_der_historie_kippt_den_lauf_nicht(tmp_path):
    pfad = tmp_path / "geraete_preise.jsonl"
    pfad.write_text('{"listung_id": "a", "datum": "2026-08-01", "preis_ohne_vertrag": 9}\n'
                    'das ist kein json\n', encoding="utf-8")
    h = Preishistorie(pfad)
    assert len(h.reihe("a")) == 1


def test_buendelpreis_und_ladenpreis_stehen_getrennt_in_der_historie(tmp_path):
    """Teil C4: die zwei Preisarten duerfen nie in derselben Zahl landen."""
    h = Preishistorie(tmp_path / "geraete_preise.jsonl")
    buendel = Listung(sku_id="s", device_id="d", anbieter="Telekom",
                      anbieter_typ="netzbetreiber", quelle_url="https://t.de/p",
                      abgerufen_am="2026-08-10", zuzahlung=49.95,
                      tarif_referenz="MagentaMobil M")
    h.schreibe(buendel, "2026-08-10")
    zeile = h.reihe(buendel.listung_id)[0]
    assert zeile["zuzahlung"] == 49.95
    assert zeile["preis_ohne_vertrag"] is None
    assert zeile["tarif_referenz"] == "MagentaMobil M"


# --------------------------------------------------------------------------
# Hardware-Vermarktung: ein abgeleiteter Befund, kein gepflegtes Feld
# --------------------------------------------------------------------------

def test_anbieter_ohne_funde_gilt_erst_nach_mehreren_laeufen_als_sim_only(tmp_path):
    """Viele Zweitmarken vermarkten ausschliesslich SIM-only. Das ist selbst
    ein Befund - aber erst, wenn er mehrfach gemessen wurde. Nach EINEM
    leeren Lauf ist es eine kaputte Quelle."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    for tag in ("2026-08-03", "2026-08-10"):
        db.protokolliere_lauf("SIMon mobile", tag, funde=0)
    assert db.hardware_vermarktung("SIMon mobile") == "unbekannt"
    db.protokolliere_lauf("SIMon mobile", "2026-08-17", funde=0)
    assert db.hardware_vermarktung("SIMon mobile") == "nein"


def test_ein_einziger_fund_genuegt_fuer_ja(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    for tag in ("2026-08-03", "2026-08-10", "2026-08-17"):
        db.protokolliere_lauf("congstar", tag, funde=0)
    db.protokolliere_lauf("congstar", "2026-08-24", funde=3)
    assert db.hardware_vermarktung("congstar") == "ja"


def test_nie_gelaufener_anbieter_ist_unbekannt(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    assert db.hardware_vermarktung("Norma Connect") == "unbekannt"


def test_laufbilanz_ueberlebt_das_speichern(tmp_path):
    pfad = tmp_path / "geraete_db.json"
    db = GeraeteDB(pfad)
    db.protokolliere_lauf("congstar", "2026-08-10", funde=2)
    db.save("2026-08-10")
    assert GeraeteDB(pfad).hardware_vermarktung("congstar") == "ja"


# --------------------------------------------------------------------------
# Die Befunde des Reviews vom 10.08.2026
# --------------------------------------------------------------------------

def test_fehlendes_farbfeld_spaltet_die_identitaet_nicht(tmp_path):
    """Befund 2, der teuerste am Store: Lauf 1 liest `color` aus dem ld+json,
    Lauf 2 nicht. Die Farbe steckt in der sku_id, also entstand eine NEUE ID -
    der Bericht meldete "1 neues Geraet, 1 vermutlich ausgelistet" statt einer
    Preissenkung, und die Historie zerfiel in zwei Reihen."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    mit = _listung(sku="apple-iphone-17-pro-max-256gb-titan-natur", preis=1449.0,
                   farbe_roh="Titannatur", farbe_normalisiert="titan-natur",
                   speicher_gb=256)
    db.upsert([mit], "2026-08-10")
    ohne = _listung(sku="apple-iphone-17-pro-max-256gb-ohne-farbe", preis=1399.0,
                    tag="2026-08-17", speicher_gb=256)
    neu, gesehen = db.upsert([ohne], "2026-08-17")
    assert neu == 0, "der Ausfall des Farbfeldes hat ein Phantomgeraet erzeugt"
    assert len(db.eintraege()) == 1
    e = db.eintraege()[0]
    assert e["id"] == mit.listung_id      # die ID von der ersten Sichtung
    assert e["preis_ohne_vertrag"] == 1399.0
    assert e["farbe_normalisiert"] == "titan-natur"   # nicht geloescht
    db.mark_stale("expert", gesehen, "2026-08-17", {"https://e.de/handys"})
    assert db.eintraege()[0]["status"] == STATUS_AKTIV


def test_nachgeliefertes_farbfeld_fuellt_die_luecke_ohne_die_id_zu_aendern(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    ohne = _listung(sku="apple-iphone-17-pro-max-256gb-ohne-farbe", speicher_gb=256)
    db.upsert([ohne], "2026-08-10")
    mit = _listung(sku="apple-iphone-17-pro-max-256gb-titan-natur", tag="2026-08-17",
                   farbe_roh="Titannatur", farbe_normalisiert="titan-natur",
                   speicher_gb=256)
    neu, _ = db.upsert([mit], "2026-08-17")
    assert neu == 0 and len(db.eintraege()) == 1
    e = db.eintraege()[0]
    assert e["id"] == ohne.listung_id     # die ID bleibt, sie ist ein Schluessel
    assert e["farbe_normalisiert"] == "titan-natur"


def test_zwei_belegte_farben_bleiben_zwei_skus(tmp_path):
    """Gegenprobe: der Verwandtenabgleich darf nicht zusammenlegen, was
    unterscheidbar ist."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([
        _listung(sku="apple-iphone-17-pro-max-256gb-titan-natur",
                 farbe_normalisiert="titan-natur", speicher_gb=256),
        _listung(sku="apple-iphone-17-pro-max-256gb-schwarz",
                 farbe_normalisiert="schwarz", speicher_gb=256),
    ], "2026-08-10")
    assert len(db.eintraege()) == 2


def test_bei_zwei_kandidaten_wird_nichts_geraten(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([
        _listung(sku="apple-iphone-17-pro-max-256gb-titan-natur",
                 farbe_normalisiert="titan-natur", speicher_gb=256),
        _listung(sku="apple-iphone-17-pro-max-256gb-schwarz",
                 farbe_normalisiert="schwarz", speicher_gb=256),
    ], "2026-08-10")
    neu, _ = db.upsert([_listung(sku="apple-iphone-17-pro-max-256gb-ohne-farbe",
                                 tag="2026-08-17", speicher_gb=256)], "2026-08-17")
    # Zwei Kandidaten - die Zuordnung ist nicht belegbar, also ein eigener
    # Eintrag statt einer geratenen Verschmelzung.
    assert neu == 1 and len(db.eintraege()) == 3


def test_zwei_ununterscheidbare_saetze_desselben_laufs_kollidieren_nicht(tmp_path):
    """Ohne diese Sperre schriebe die Historie in JEDEM Lauf zwei
    Aenderungspunkte hin und zurueck - eine Saegezahnkurve, die aussieht wie
    ein Preiskampf."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    neu, gesehen = db.upsert([
        _listung(sku="apple-iphone-17-pro-max-256gb-ohne-farbe", preis=1449.0,
                 speicher_gb=256),
        _listung(sku="apple-iphone-17-pro-max-256gb-ohne-farbe", preis=1099.0,
                 speicher_gb=256),
    ], "2026-08-10")
    assert neu == 1 and len(gesehen) == 1
    assert db.eintraege()[0]["preis_ohne_vertrag"] == 1449.0
    assert len(db.kollisionen) == 1


def test_unbekannte_verfuegbarkeit_ist_ein_ausfall_keine_aenderung(tmp_path):
    """Befund 5: `verfuegbarkeit` ist nie None, also griff die Ausfallregel
    dort nie. Ein Lauf, der sie nicht parsen konnte, schrieb fuer JEDE Listung
    eine Historienzeile - aus "lieferbar -> unbekannt -> lieferbar" wurde ein
    Lieferereignis, das es nie gab."""
    h = Preishistorie(tmp_path / "geraete_preise.jsonl")
    assert h.schreibe(_listung(verfuegbarkeit="lieferbar"), "2026-08-10") is True
    assert h.schreibe(_listung(verfuegbarkeit="unbekannt", tag="2026-08-17"),
                      "2026-08-17") is False
    assert h.schreibe(_listung(verfuegbarkeit="lieferbar", tag="2026-08-24"),
                      "2026-08-24") is False
    assert len(h.reihe(_listung().listung_id)) == 1


def test_unbekannte_verfuegbarkeit_ueberschreibt_den_bekannten_wert_nicht(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung(verfuegbarkeit="lieferbar")], "2026-08-10")
    db.upsert([_listung(verfuegbarkeit="unbekannt", tag="2026-08-17")], "2026-08-17")
    assert db.eintraege()[0]["verfuegbarkeit"] == "lieferbar"


def test_ein_echter_verfuegbarkeitswechsel_wird_weiterhin_geschrieben(tmp_path):
    # Gegenprobe zum Test darueber.
    h = Preishistorie(tmp_path / "geraete_preise.jsonl")
    h.schreibe(_listung(verfuegbarkeit="lieferbar"), "2026-08-10")
    assert h.schreibe(_listung(verfuegbarkeit="ausverkauft", tag="2026-08-17"),
                      "2026-08-17") is True


def test_eintrag_ohne_einstiegsangabe_haengt_an_der_leitseite(tmp_path):
    """Befund 9: ein Bestandseintrag ohne `einstieg_url` alterte NIE und
    stuende auf ewig als "aktiv" auf der Seite. Dieselbe Konvention wie
    promo_store: er haengt an der Leitseite."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung(einstieg="")], "2026-08-10")
    assert db.eintraege()[0].get("einstiege") in (None, [])
    db.mark_stale("expert", set(), "2026-08-17", {"https://e.de/handys"},
                  leitseite="https://e.de/handys")
    assert db.eintraege()[0]["status"] == STATUS_VERMUTLICH


def test_geraet_auf_zwei_einstiegsseiten_altert_nur_wenn_beide_gelesen_sind(tmp_path):
    """Befund 10: der Eintrag merkte sich nur die ZULETZT gesehene Seite."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung(einstieg="https://e.de/A")], "2026-08-10")
    db.upsert([_listung(einstieg="https://e.de/B", tag="2026-08-10")], "2026-08-10")
    assert db.eintraege()[0]["einstiege"] == ["https://e.de/A", "https://e.de/B"]
    db.mark_stale("expert", set(), "2026-08-17", {"https://e.de/A"})
    assert db.eintraege()[0]["status"] == STATUS_AKTIV
    db.mark_stale("expert", set(), "2026-08-24",
                  {"https://e.de/A", "https://e.de/B"})
    assert db.eintraege()[0]["status"] == STATUS_VERMUTLICH


def test_zwei_aufrufe_am_selben_tag_altern_nur_einen_schritt(tmp_path):
    """Befund 17: "zwei Fehltreffer IN FOLGE" ist eine Aussage ueber zwei
    LAEUFE. Zwei Aufrufe am selben Datum haetten einen Eintrag in einem
    einzigen Lauf ausgelistet."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung()], "2026-08-10")
    db.mark_stale("expert", set(), "2026-08-17", None)
    db.mark_stale("expert", set(), "2026-08-17", None)
    assert db.eintraege()[0]["status"] == STATUS_VERMUTLICH


def test_erstpreis_traegt_seine_preisart(tmp_path):
    """Befund 11: ein Einfuehrungspreis von 1449 Euro ohne Vertrag und eine
    spaetere Zuzahlung von 49,95 Euro ergaeben 96,6 Prozent "Preisverfall" -
    die zwei Preisarten in einer Rechnung."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung(preis=1449.0)], "2026-08-10")
    e = db.eintraege()[0]
    assert e["erstpreis"] == 1449.0 and e["erstpreis_art"] == "ohne_vertrag"


def test_erster_messpunkt_auch_bei_reinem_vertragspreis(tmp_path):
    """Befund 12: eine Listung, deren einziger Preis ein Vertragspreis ist,
    bekam NIE einen Historienpunkt - DB und Historie liefen auseinander."""
    h = Preishistorie(tmp_path / "geraete_preise.jsonl")
    l = Listung(sku_id="s", device_id="d", anbieter="o2",
                anbieter_typ="netzbetreiber", quelle_url="https://o2.de/p",
                abgerufen_am="2026-08-10", preis_mit_vertrag_ab=1.00,
                tarif_referenz="o2 Mobile M")
    assert h.schreibe(l, "2026-08-10") is True
    assert h.reihe(l.listung_id)[0]["preis_mit_vertrag_ab"] == 1.0


# --------------------------------------------------------------------------
# Messtermine: die Diagnose G0 vom 28.08.2026
# --------------------------------------------------------------------------
# Die Seite meldete nach 17 Tagen und vier echten Pruefterminen "bisher
# 1 Messtermin", und die Lifecycle-Auswertung sperrte 84 von 85 Listungen aus.
# Zwei Ursachen, beide hier festgenagelt: die Laufbilanz verbuchte nur
# VOLLSTAENDIGE Laeufe (mobilcom-debitel wurde am Zeitbudget nie fertig und
# fehlte komplett), und die Messtermin-Zaehlung hing an der Preishistorie,
# die bei unveraendertem Preis schweigt.


def test_teillauf_mit_funden_zaehlt_als_messtermin_aber_nicht_als_lauf(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.protokolliere_lauf("mobilcom-debitel", "2026-08-21", funde=68,
                          vollstaendig=False)
    b = db.laufbilanz("mobilcom-debitel")
    assert b.get("laeufe", 0) == 0, "ein Teillauf ist kein vollstaendiger Lauf"
    assert "2026-08-21" in db.messtermine("mobilcom-debitel")
    # Funde aus einem Teillauf sind echte Funde - die Marke vermarktet Hardware.
    assert db.hardware_vermarktung("mobilcom-debitel") == "ja"


def test_teillauf_ohne_funde_schiebt_nicht_richtung_sim_only(tmp_path):
    """Drei abgebrochene Laeufe ohne Fund duerfen keine Marke zum
    SIM-only-Anbieter erklaeren - ein Abbruch ist kein Messergebnis."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    for tag in ("2026-08-20", "2026-08-21", "2026-08-22"):
        db.protokolliere_lauf("ALDI TALK", tag, funde=0, vollstaendig=False)
    assert db.hardware_vermarktung("ALDI TALK") == "unbekannt"
    assert db.messtermine("ALDI TALK") == []


def test_messtermine_lesen_den_altbestand_aus_den_listungsdaten(tmp_path):
    """Die Termine-Buchfuehrung gibt es erst seit dem 28.08.2026. Der
    Altbestand traegt seine Beobachtungszeitpunkte aber in den Listungen
    selbst (first_seen, last_verified, letzter_check) - genau daraus muss
    die Zaehlung die vier echten Prueftermine des Bestands rekonstruieren."""
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung(anbieter="mobilcom-debitel")], "2026-08-10")
    db.upsert([_listung(anbieter="mobilcom-debitel", tag="2026-08-14")],
              "2026-08-14")
    # Die Bilanz absichtlich loeschen - so sieht der Altbestand aus, dessen
    # Laeufe vor der Termine-Buchfuehrung lagen.
    db._anbieter.clear()
    assert db.messtermine("mobilcom-debitel") == ["2026-08-10", "2026-08-14"]


def test_messtermine_mischen_keine_anbieter(tmp_path):
    db = GeraeteDB(tmp_path / "geraete_db.json")
    db.upsert([_listung(anbieter="mobilcom-debitel")], "2026-08-10")
    db.protokolliere_lauf("ALDI TALK", "2026-08-14", funde=1)
    assert "2026-08-14" not in db.messtermine("mobilcom-debitel")
    assert "2026-08-10" not in db.messtermine("ALDI TALK")


def test_termine_ueberleben_das_speichern_und_doppeln_nicht(tmp_path):
    pfad = tmp_path / "geraete_db.json"
    db = GeraeteDB(pfad)
    db.protokolliere_lauf("congstar", "2026-08-10", funde=2)
    db.protokolliere_lauf("congstar", "2026-08-10", funde=2)
    db.save("2026-08-10")
    wieder = GeraeteDB(pfad)
    assert wieder.laufbilanz("congstar").get("termine") == ["2026-08-10"]
