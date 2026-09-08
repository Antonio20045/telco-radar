"""RAD-1 (BRIEF_RAD1_R2, 08.09.2026): der Wettbewerbs-Radar gegen
AUFTRAG_GERAETESEITE.md §§2b/3/8.

Die Pruefkriterien des Briefs, je eine eigene Funktion:
- %-Formel mit Vorzeichen (Wettbewerber guenstiger -> negativ, teurer ->
  positiv), §2b: "Leitzahl ist die Abweichung zu Vodafone in Prozent,
  mit Vorzeichen"
- Sortierung: negativste Abweichung zuerst (§2b: "die groesste Abweichung
  zuungunsten von Vodafone zuerst")
- TCO ausschliesslich tco_24() - im gerenderten Artefakt steht kein
  "TCO-36" (§3: "Immer 24 Monate")
- Haendler vergleichen reinen GERAETEPREIS, nie Tarif oder TCO (§3:
  "Zahlen, nie vermischt"; §8: "Haendler zaehlen als Wettkbewerb")
- kein_buendel-Zeilen: alle drei Netzbetreiber IMMER genannt
- Band-Mismatch: die guenstigste echte Karte als Belegzeile (§2b/§7)
- nicht erhobene Wettbewerber namentlich, nie weggelassen (§8: Amazon,
  MediaMarkt, expert, Euronics)

Drei Lagen, dieselbe Bauform wie die Nachbardateien:
- Konstruierte Faelle laufen den ECHTEN Weg über `karten.modelle()` -
  die Karten sind also echt gerechnete `tco_24()`-Ergebnisse mit echter
  Band-Zuordnung, keine handgebauten Dicts im Karten-Format (Lektion aus
  dem Adapter-Befund vom 11.08.: eine erfundene Fixture beweist nichts).
- Das gerenderte Artefakt entsteht in tmp_path wie in
  `test_geraete_tco_zustand._baue` (eigene Konfiguration MIT den vier
  nicht erhebbaren Haendlern des §8).
- Der echte Bestand prueft INVARIANTEN (nie Tageszaehlungen - der Store
  waechst jede Nacht, eine gemessene Anzahl waere eine Datums-Zeitbombe
  ohne Datum).
"""
from __future__ import annotations

import json
import pathlib

import yaml
import pytest
from bs4 import BeautifulSoup

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_tco_band as band
from telco_radar.report import geraete_tco_karten as karten
from telco_radar.report import geraete_view
from telco_radar.report import wettbewerbsradar as wr
from telco_radar.report.html import render_site
from telco_radar.tco_model import Buendel, SimOnlyReferenz

WURZEL = pathlib.Path(__file__).resolve().parents[1]
ZUSTAND = WURZEL / "data" / "state"
HEUTE = "2026-09-08"

SKU_M1 = "apple-iphone-15-128gb-schwarz"       # o2 im Band Klein, guenstiger
SKU_M2 = "apple-iphone-15-256gb-schwarz"       # o2 im Band Klein, teurer
SKU_M3 = "apple-iphone-16-pro-max-256gb-schwarz"  # o2 nur im Band Gross
SKU_M4 = "apple-iphone-15-512gb-schwarz"       # ohne Vodafone-Basis


# --------------------------------------------------------------------------
# Konstruierte Faelle: echter Weg ueber karten.modelle()
# --------------------------------------------------------------------------

def _tarife() -> list[dict]:
    """Vier Tarife, deren Baender feststehen (§7): vf:xs klein (18 GB),
    o2:k klein (10 GB), o2:m mittel (40 GB), o2:g gross (100 GB)."""
    def satz(anbieter, name, tid, gb, grundgebuehr):
        return {"anbieter": anbieter, "name": name, "tarif_id": tid,
                "art": "mobilfunk", "grundgebuehr": grundgebuehr,
                "laufzeit_monate": 24,
                "datenvolumen_gb": gb, "preisphasen": [],
                "dokument_url": f"https://example.de/pib/{tid}",
                "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}
    # vf:xs mit abgedeckten Phasen (die Naehrung rechnet phasengewichtet)
    xs = satz("Vodafone", "Vodafone Mobil XS", "vf:xs", 18, 29.95)
    xs["preisphasen"] = [{"von_monat": 1, "bis_monat": 24, "betrag": 29.95},
                         {"von_monat": 25, "bis_monat": None, "betrag": 29.95}]
    return [xs,
            satz("o2", "O2 Mobile S", "o2:k", 10, 9.99),
            satz("o2", "O2 Mobile M", "o2:m", 40, 19.99),
            satz("o2", "O2 Mobile L", "o2:g", 100, 39.99),
            satz("o2", "O2 Mobile L Plus", "o2:g2", 80, 44.99)]


def _listung(anbieter, sku, preis, zustand="neu") -> dict:
    return {"id": f"{anbieter.lower()}--{sku}", "sku_id": sku,
            "device_id": "-".join(sku.split("-")[:-2]),
            "anbieter": anbieter, "anbieter_typ": "netzbetreiber",
            "speicher_gb": int(sku.split("-")[-2].replace("gb", "")),
            "farbe_roh": "Schwarz", "farbe_normalisiert": "schwarz",
            "zustand": zustand, "first_seen": "2026-08-20",
            "last_verified": HEUTE, "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-20",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{sku}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/l"]}


def _buendel(sku, tarif_id, tarif_name, tarif_monatlich, rate,
             zuzahlung=1.0, laufzeit=24) -> Buendel:
    return Buendel(sku_id=sku, anbieter="o2", tarif_name=tarif_name,
                   tarif_id=tarif_id, tarif_id_guete="hoch",
                   tarif_monatlich=tarif_monatlich, tarif_bindung_monate=24,
                   geraet_zuzahlung=zuzahlung, geraet_monatsrate=rate,
                   laufzeit_monate=laufzeit, anschlusspreis=0.0,
                   zustand="neu",
                   quelle_url=f"https://example.de/o2/{tarif_id}/{sku}",
                   abgerufen_am=HEUTE)


def _bestand():
    """Vier Modelle am echten Katalog - jede Zahl entsteht auf dem Weg,
    den auch die Seite geht (`karten.modelle` -> `tco_24()`)."""
    tarife = {t["tarif_id"]: t for t in _tarife()}
    listungen = [
        _listung("Vodafone", SKU_M1, 709.90),
        _listung("Vodafone", SKU_M2, 1000.00),
        _listung("Vodafone", SKU_M3, 1199.90),
        _listung("o2", SKU_M4, 649.00),
    ]
    buendel = [
        # M1: o2 im selben Band wie die VF-Naeherung (Klein), deutlich
        # guenstiger -> NEGATIVE Abweichung.
        _buendel(SKU_M1, "o2:k", "O2 Mobile S", 9.99, 1.0),
        # M2: o2 im selben Band (Klein), deutlich teurer -> POSITIV.
        _buendel(SKU_M2, "o2:k", "O2 Mobile S", 49.99, 80.0, laufzeit=36),
        # M3: zwei o2-Buendel in ZWEI Tarifen des Bandes GROSS (derselbe
        # Tarifname wuerde im Dedupe-Schluessel kollidieren) - Vodafone
        # fuehrt das Geraet nur im Band Klein -> Band-Mismatch, die
        # GUENSTIGSTE der beiden Karten ist die Belegzeile.
        _buendel(SKU_M3, "o2:g", "O2 Mobile L", 39.99, 5.0, zuzahlung=0.0),
        _buendel(SKU_M3, "o2:g2", "O2 Mobile L Plus", 44.99, 5.0,
                 zuzahlung=50.0),
        # M4: o2-Buendel im Band Mittel, aber KEIN Vodafone-Preis -> keine
        # Basis, keine Abweichung, trotzdem alle drei Zeilen.
        _buendel(SKU_M4, "o2:m", "O2 Mobile M", 19.99, 10.0),
    ]
    referenzen = [SimOnlyReferenz(
        anbieter="Vodafone", tarif_name="Vodafone Mobil XS",
        tarif_id="vf:xs", tarif_sim_only_monatlich=29.95,
        quelle_url="https://example.de/pib/vf-xs", abgerufen_am=HEUTE)]
    ergebnis = karten.modelle(buendel, listungen, referenzen, tarife,
                              lade_katalog(WURZEL))
    return ergebnis["modelle"], band.tarif_baender(tarife)


def _gruppen():
    modelle, band_je_tarif = _bestand()
    return {g["id"]: g for g in
            wr.netzbetreiber_gruppen(modelle, band_je_tarif)}, modelle, band_je_tarif


def test_prozentformel_mit_vorzeichen():
    """(a) §2b: (W - V) / V * 100 - Wettbewerber guenstiger ist NEGATIV
    ('Vodafone 10 % teurer als der Wettbewerber'), teurer POSITIV. Die
    Formel wird gegen die eigenen Felder der Zeile nachgerechnet, nicht
    gegen eine zweite Rechnung."""
    gruppen, _, _ = _gruppen()

    m1 = gruppen["apple-iphone-15-128"]
    assert m1["vodafone"] is not None, "M1 braucht eine VF-Basis"
    o2 = next(z for z in m1["zeilen"] if z["anbieter"] == "o2")
    assert o2["status"] == wr.STATUS_VERGLEICHBAR
    assert o2["prozent"] < 0, "guenstigerer Wettbewerber muss negativ sein"
    erwartet = round((o2["gesamt"] - o2["vf_gesamt"]) / o2["vf_gesamt"] * 100, 1)
    assert o2["prozent"] == erwartet
    assert o2["gesamt"] < o2["vf_gesamt"]

    m2 = gruppen["apple-iphone-15-256"]
    o2_teuer = next(z for z in m2["zeilen"] if z["anbieter"] == "o2")
    assert o2_teuer["status"] == wr.STATUS_VERGLEICHBAR
    assert o2_teuer["prozent"] > 0, "teurerer Wettbewerber muss positiv sein"
    erwartet = round((o2_teuer["gesamt"] - o2_teuer["vf_gesamt"])
                     / o2_teuer["vf_gesamt"] * 100, 1)
    assert o2_teuer["prozent"] == erwartet
    assert o2_teuer["gesamt"] > o2_teuer["vf_gesamt"]


def test_sortierung_negativste_abweichung_zuerst():
    """(b) §2b: 'die groesste Abweichung zuungunsten von Vodafone zuerst' -
    das ist der negativste Wert der Formel (Wettbewerber am guenstigsten
    gegen Vodafone). Gilt fuer die Gruppen UND fuer die Zeilen darin;
    Zeilen ohne Zahl stehen hinter den Zahlen."""
    gruppen, modelle, band_je_tarif = _gruppen()
    alle = wr.netzbetreiber_gruppen(modelle, band_je_tarif)

    raenge = [g["rang"] for g in alle]
    assert raenge == sorted(raenge), "Gruppen muessen aufsteigend nach Rang stehen"
    # Der konstruierte Fall: M1 (negativ) vor M2 (positiv) vor M3/M4 (inf).
    ids = [g["id"] for g in alle if g["rang"] != float("inf")]
    assert ids.index("apple-iphone-15-128") < ids.index("apple-iphone-15-256")

    for g in alle:
        werte = [z["prozent"] for z in g["zeilen"] if z["prozent"] is not None]
        assert werte == sorted(werte), f"Zeilen in {g['id']} unsortiert"
        # Zeilen ohne Zahl stehen HINTER jeder Zeile mit Zahl.
        erste_luecke = next((i for i, z in enumerate(g["zeilen"])
                             if z["prozent"] is None), len(g["zeilen"]))
        assert all(z["prozent"] is None for z in g["zeilen"][erste_luecke:]), \
            f"Zeile ohne Zahl steht vor einer mit Zahl in {g['id']}"


def test_kein_buendel_nennt_alle_drei_wettbewerber():
    """(c) B.2.5: ein weggelassener Anbieter sieht aus wie einer, den es
    nicht gibt. Jede Gruppe traegt EXAKT die drei Zeilen Telekom, 1&1, o2 -
    mit und ohne Zahl, mit und ohne Vodafone-Basis."""
    gruppen, _, _ = _gruppen()
    erwartet = set(wr.NETZ_WETTBEWERBER)
    assert erwartet == {"Telekom", "1&1", "o2"}

    for gid, g in gruppen.items():
        anbieter = {z["anbieter"] for z in g["zeilen"]}
        assert anbieter == erwartet, f"{gid}: {anbieter}"
        assert len(g["zeilen"]) == 3

    # Die zwei konstruierten Lueckenfaelle: ohne o2-Karte ueberhaupt
    # (M1: Telekom und 1&1) und ohne Vodafone-Basis (M4: alle drei ohne
    # Abweichung, weil es nichts gibt, wogegen man rechnen koennte).
    m1 = gruppen["apple-iphone-15-128"]
    telekom = next(z for z in m1["zeilen"] if z["anbieter"] == "Telekom")
    assert telekom["status"] == wr.STATUS_KEIN_BUENDEL
    assert telekom["prozent"] is None
    assert telekom["grund"], "eine Luecke ohne Grund ist keine Auskunft"

    m4 = gruppen["apple-iphone-15-512"]
    assert m4["vodafone"] is None
    assert m4["vodafone_grund"]
    assert {z["status"] for z in m4["zeilen"]} == {wr.STATUS_KEIN_BUENDEL}


def test_band_mismatch_fuehrt_die_guenstigste_echte_karte():
    """(d) §2b/§7: liegt kein gemeinsames Tarifband vor, KEINE erfundene
    Zahl - aber die guenstigste echte Karte des Wettbewerbers als Beleg,
    mit Quelle. M3 hat zwei o2-Karten im Band Gross (5 und 50 Euro Rate);
    die Belegzeile muss die guenstigste sein."""
    gruppen, modelle, _ = _gruppen()
    m3 = gruppen["apple-iphone-16-pro-max-256"]
    o2 = next(z for z in m3["zeilen"] if z["anbieter"] == "o2")
    assert o2["status"] == wr.STATUS_BAND_MISMATCH
    assert o2["prozent"] is None

    modell = next(m for m in modelle if m["id"] == "apple-iphone-16-pro-max-256")
    o2_karten = [k for k in modell["karten"] if k["anbieter"] == "o2"
                 and k.get("belastbar") and not k.get("naeherung")
                 and k.get("gesamt") is not None]
    assert len(o2_karten) == 2, "Fixture prueft nichts: zweite Karte fehlt"
    guenstigste = min(o2_karten, key=lambda k: k["gesamt"])
    assert o2["gesamt"] == guenstigste["gesamt"]
    assert o2["quelle_url"] == guenstigste["quelle_url"]
    assert o2["abgerufen_am"] == guenstigste["abgerufen_am"]
    assert o2["band_label"] == "Groß"
    assert o2["grund"], "Band-Mismatch muss benannt sein"


def test_vergleichbarkeit_nur_im_gemeinsamen_band():
    """(e) Die Vorzeichen-Zeilen von M1/M2 stehen im Band der VF-Basis
    (Klein), weil Vodafone dort keine ECHTE Karte hat - die gemeinsame
    Bandkarte greift nur bei echten VF-Buendeln. Beide Pfade rechnen gegen
    eine Vodafone-Zahl IMSELBEN Band (die Gegenkarte oder die Basis)."""
    gruppen, modelle, band_je_tarif = _gruppen()
    by_id = {m["id"]: m for m in modelle}
    vergleichbare = [(g, z) for g in gruppen.values() for z in g["zeilen"]
                     if z["prozent"] is not None]
    assert vergleichbare, "Fixture prueft nichts: keine vergleichbare Zeile"
    for g, z in vergleichbare:
        modell = by_id[g["id"]]
        je_band = band.karten_je_band(modell, band_je_tarif)
        assert z["vf_gesamt"] is not None
        vf_echt = (je_band.get(z["band"]) or {}).get("Vodafone")
        if vf_echt is not None:
            # Gemeinsames Band: Gegenkarte ist Vodafones Karte in diesem Band.
            assert z["vf_gesamt"] == vf_echt["gesamt"]
        else:
            # Basisspfad: die Zeile ist im Band der Vodafone-Basis.
            assert z["band"] == g["vodafone"]["band"]
            assert z["vf_gesamt"] == g["vodafone"]["gesamt"]


# --------------------------------------------------------------------------
# Haendler und nicht Erhebbare (reine Leseschichten)
# --------------------------------------------------------------------------

def _vergleich_fixture() -> dict:
    return {"zeilen": [{
        "modell": "iPhone 15", "hersteller": "Apple", "speicher": 128,
        "vodafone": {"preis": 709.90, "url": "https://example.de/vf",
                     "abgerufen_am": HEUTE},
        "guenstiger": [
            {"typ": "handel", "laden": "Saturn", "anbieter": "Saturn",
             "preis": 679.90, "url": "https://example.de/saturn",
             "abgerufen_am": HEUTE},
            # Ein Netzbetreiber ist kein Haendler - seine TCO steht in der
            # anderen Sektion, hier hat er nichts verloren (§3: Zahlen,
            # nie vermischt).
            {"typ": "netzbetreiber", "laden": "o2", "anbieter": "o2",
             "preis": 659.90, "url": "https://example.de/o2",
             "abgerufen_am": HEUTE},
        ],
        "teurer": [{"typ": "handel", "laden": "mobilcom-debitel",
                    "anbieter": "mobilcom-debitel", "preis": 749.90,
                    "url": "https://example.de/md",
                    "abgerufen_am": HEUTE}],
    }]}


def test_haendler_vergleichen_nur_geraetepreise():
    """(f) §3/§8: der Haendler-Abschnitt vergleicht GERAETEPREIS gegen
    GERAETEPREIS - kein Tariffeld, keine TCO-Mischung, kein Netzbetreiber.
    Dieselbe %-Formel wie oben, aber gegen Vodafones Barpreis."""
    zeilen = wr.haendler_zeilen(_vergleich_fixture())
    assert [z["anbieter"] for z in zeilen] == ["Saturn", "mobilcom-debitel"]
    for z in zeilen:
        assert "tarif" not in z and "tco" not in {k.lower() for k in z}
        assert z["prozent"] == round(
            (z["preis"] - z["vodafone_preis"]) / z["vodafone_preis"] * 100, 1)
    assert zeilen[0]["prozent"] < 0 < zeilen[1]["prozent"]
    # Aufsteigend: der guenstigste Haendler (die Meldung) zuerst.
    assert [z["prozent"] for z in zeilen] == sorted(z["prozent"] for z in zeilen)


def _quellenlage_fixture() -> dict:
    return {"zeilen": [
        {"name": "Saturn", "typ": "handel", "zustand": "liefert",
         "grund": "", "aktiv": True},
        {"name": "o2", "typ": "netzbetreiber", "zustand": "ohne_daten",
         "grund": "x", "aktiv": True},
        *[{"name": n, "typ": "handel", "zustand": "ohne_daten",
           "grund": grund, "aktiv": False}
          for n, grund in (("Amazon", "kein PA-API-Zugang (§8)"),
                           ("MediaMarkt", "HTTP 403"),
                           ("expert", "Preis erst nach JS-Nachladen, robots sperrt /api/"),
                           ("Euronics", "HTTP 403 - auch die robots.txt"))],
    ]}


def test_nicht_erhobene_wettbewerber_stehen_namentlich_dabei():
    """(g) §8: 'nicht erhobene Wettbewerber werden als solche ausgewiesen,
    nicht weggelassen' - Amazon, MediaMarkt, expert und Euronics mit
    Grund; ein LIEFERNDER Haendler und ein Netzbetreiber stehen NICHT
    darin."""
    fehlt = wr.nicht_erhebbar(_quellenlage_fixture())
    namen = [f["anbieter"] for f in fehlt]
    assert namen == ["Amazon", "Euronics", "MediaMarkt", "expert"]  # sortiert
    for f in fehlt:
        assert f["grund"], f"{f['anbieter']} ohne Grund"
    assert "Saturn" not in namen
    assert "o2" not in namen


# --------------------------------------------------------------------------
# Das gerenderte Artefakt (tmp_path, eigene Konfiguration nach §8)
# --------------------------------------------------------------------------

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 15", "generation": 15,
     "marktstart": "2023-09-22", "speicher": [128, 256], "segment": "premium"},
]}
_FARBEN = {"farben": {"schwarz": ["Schwarz", "Black"]}}
# Die vier nicht erhebbaren Haendler des §8 stehen WOERTLICH in der
# Konfiguration - genau wie im echten config/geraete_quellen.yaml.
_QUELLEN = {"anbieter": [
    {"name": "o2", "typ": "netzbetreiber", "rang": 1, "methode": "json_endpunkt",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/e-shop/",
                    "label": "Katalog", "kind": "static"}]},
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 2, "eigen": True,
     "methode": "json_endpunkt", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://api.vodafone.de/glados/v2/hardware",
                    "label": "Liste", "kind": "static"}]},
    {"name": "Saturn", "typ": "handel", "gruppe": "Ceconomy", "rang": 2,
     "methode": "saturn_brand", "aktiv": True,
     "basis_url": "https://www.saturn.de",
     "einstiege": [{"url": "https://www.saturn.de/handys",
                    "label": "Handys", "kind": "static"}]},
    {"name": "Amazon", "typ": "handel", "gruppe": "Amazon", "rang": 1,
     "methode": "deaktiviert", "aktiv": False,
     "grund": "Kein PA-API-Zugang - Adapter gebaut, bewusst deaktiviert."},
    {"name": "MediaMarkt", "typ": "handel", "gruppe": "Ceconomy", "rang": 2,
     "methode": "json_endpunkt", "aktiv": False,
     "grund": "HTTP 403 auf jede Abrufvariante."},
    {"name": "expert", "typ": "handel", "gruppe": "expert", "rang": 3,
     "methode": "json_endpunkt", "aktiv": False,
     "grund": "Preis steht erst nach JS-Nachladen, robots.txt sperrt /api/."},
    {"name": "Euronics", "typ": "handel", "gruppe": "Euronics", "rang": 3,
     "methode": "deaktiviert", "aktiv": False,
     "grund": "HTTP 403 - auch auf die robots.txt."},
]}


def _seite(tmp_path: pathlib.Path) -> dict[str, str]:
    """Baut die ganze Site in tmp_path und gibt {seitename: html} zurueck."""
    root = tmp_path / "site-bau"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    listungen = [
        _listung("Vodafone", SKU_M1, 709.90),
        _listung("Saturn", SKU_M1, 679.90),
    ]
    # Saturn ist Haendler - derselbe Anbietertyp wie im echten Bestand.
    listungen[1]["anbieter_typ"] = "handel"
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE, "anbieter": {
            "o2": {"laeufe": 4, "funde_gesamt": 1},
            "Vodafone": {"laeufe": 4, "funde_gesamt": 1},
            "Saturn": {"laeufe": 4, "funde_gesamt": 1}},
        "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text(
        "\n".join(json.dumps({"listung_id": e["id"], "datum": HEUTE,
                              "preis_ohne_vertrag": e["preis_ohne_vertrag"],
                              "quelle_url": e["quelle_url"]})
                  for e in listungen) + "\n", encoding="utf-8")
    b = _buendel(SKU_M1, "o2:k", "O2 Mobile S", 9.99, 1.0)
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE,
        "buendel": [{"id": b.id, "sku_id": b.sku_id, "anbieter": b.anbieter,
                     "tarif_name": b.tarif_name, "tarif_id": b.tarif_id,
                     "tarif_id_guete": "hoch",
                     "tarif_monatlich": b.tarif_monatlich,
                     "geraet_zuzahlung": b.geraet_zuzahlung,
                     "geraet_monatsrate": b.geraet_monatsrate,
                     "laufzeit_monate": b.laufzeit_monate,
                     "anschlusspreis": b.anschlusspreis, "rabatte": [],
                     "zustand": b.zustand, "quelle_url": b.quelle_url,
                     "abgerufen_am": b.abgerufen_am,
                     "first_seen": HEUTE, "last_verified": HEUTE}],
        "sim_only": [{"id": "vf--xs", "anbieter": "Vodafone",
                      "tarif_name": "Vodafone Mobil XS", "tarif_id": "vf:xs",
                      "tarif_id_guete": "hoch",
                      "tarif_sim_only_monatlich": 29.95,
                      "anschlusspreis": None, "rabatte": [],
                      "quelle_url": "https://example.de/pib/vf-xs",
                      "abgerufen_am": HEUTE,
                      "first_seen": HEUTE, "last_verified": HEUTE}]}),
        encoding="utf-8")
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in _tarife()) + "\n", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return {name: (site / name).read_text(encoding="utf-8")
            for name in ("wettbewerbsradar.html", "geraete.html",
                         "index.html")}


def test_im_gerenderten_radar_steht_kein_tco36(tmp_path):
    """(h) §3: 'Immer 24 Monate' - im Artefakt steht kein TCO-36 und keine
    36-Monate-Bezeichnung. TCO-24 muss dafuer VORKOMMEN, sonst pruefte die
    Abwesenheit nichts."""
    html = _seite(tmp_path)["wettbewerbsradar.html"]
    assert "TCO-36" not in html
    assert "36 Monate" not in html
    assert "TCO-24" in html or "24 Monate" in html


def test_die_seite_nennt_die_nicht_erhebbaren_haendler(tmp_path):
    """(i) §8 auf der Seite: Amazon, MediaMarkt, expert und Euronics
    stehen mit Grund im eigenen Abschnitt - benannt, nicht weggelassen."""
    suppe = BeautifulSoup(_seite(tmp_path)["wettbewerbsradar.html"],
                          "html.parser")
    text = suppe.get_text(" ", strip=True)
    for name in ("Amazon", "MediaMarkt", "expert", "Euronics"):
        assert name in text, f"{name} fehlt auf der Seite"
    assert "403" in text, "der Grund (HTTP 403) muss genannt sein"
    assert "PA-API" in text


def test_auf_der_seite_fehlt_kein_netzbetreiber(tmp_path):
    """(j) B.2.5 im Artefakt: Telekom und 1&1 stehen als Zeilen ohne Zahl
    in JEDER Gruppe - der Radar lässt keinen der drei Wettbeweber aus."""
    suppe = BeautifulSoup(_seite(tmp_path)["wettbewerbsradar.html"],
                          "html.parser")
    gruppen = suppe.select(".wr-gruppe")
    assert gruppen, "keine Gruppe gerendert - Test prueft nichts"
    for g in gruppen:
        namen = {z.select("td")[0].get_text(strip=True)
                 for z in g.select(".wr-zeile")}
        assert {"Telekom", "1&1", "o2"} <= namen, namen


def test_die_geraeteseite_traegt_den_fusslink(tmp_path):
    """(k) RAD-1 Aufgabe 2: der Radar ist von geraete.html aus verlinkt,
    sobald er vergleichbare Zeilen hat - und in der Navigation derselben
    Seite."""
    seiten = _seite(tmp_path)
    geraete = BeautifulSoup(seiten["geraete.html"], "html.parser")
    fusslinks = [a.get("href") for a in geraete.select("a")
                 if a.get("href") == "wettbewerbsradar.html"]
    assert fusslinks, "geraete.html verlinkt den Radar nicht"
    index = BeautifulSoup(seiten["index.html"], "html.parser")
    navlinks = [a.get("href") for a in index.select("nav a")
                if a.get("href") == "wettbewerbsradar.html"]
    assert navlinks, "die Navigation verlinkt den Radar nicht"


# --------------------------------------------------------------------------
# Der echte Bestand: Invarianten, keine Tageszaehlungen
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def echt():
    """Dieselben drei Eingaben, die `render_site` an `radar()` reicht -
    nicht weniger (CLAUDE.md §6: render_site ohne cfg rendert halbe
    Seiten; hier steht der ganze Stack wie in der Pipeline)."""
    view = geraete_view.aufbereiten(ZUSTAND, lade_quellen(WURZEL),
                                    lade_katalog(WURZEL), heute=HEUTE)
    radar = wr.radar(view["tco"], view["vergleich"]["ohne_vertrag"],
                     view["quellenlage"])
    return {"view": view, "radar": radar,
            "modelle": view["tco"]["modelle"],
            "band_je_tarif": view["tco"]["band_je_tarif"]}


def test_am_echten_bestand_hat_jede_gruppe_alle_drei_zeilen(echt):
    gruppen = echt["radar"]["gruppen"]
    assert gruppen, "kein Modell im Bestand - der Test pruefte nichts"
    for g in gruppen:
        assert len(g["zeilen"]) == 3
        assert {z["anbieter"] for z in g["zeilen"]} == set(wr.NETZ_WETTBEWERBER)


def test_am_echten_bestand_ist_jede_zahl_gegen_die_vf_zahl_im_selben_band(echt):
    """§2b-Zaehnenpruefung am Bestand: jede vergleichbare Zeile traegt eine
    VF-Gegenzahl (vf_gesamt), und ihre Formel stimmt gegen die eigenen
    Felder - zwei Rechnungen fuer dieselbe Zahl waeren zwei Zahlen."""
    vergleichbare = [(g, z) for g in echt["radar"]["gruppen"]
                     for z in g["zeilen"] if z["prozent"] is not None]
    assert vergleichbare, "keine vergleichbare Zeile im Bestand - " \
        "Datenlage geprueft? (Bandlogik oder Bündelerhebung kaputt)"
    by_id = {m["id"]: m for m in echt["modelle"]}
    for g, z in vergleichbare:
        assert z["vf_gesamt"] is not None
        assert z["prozent"] == round(
            (z["gesamt"] - z["vf_gesamt"]) / z["vf_gesamt"] * 100, 1)
        modell = by_id[g["id"]]
        je_band = band.karten_je_band(modell, echt["band_je_tarif"])
        vf_echt = (je_band.get(z["band"]) or {}).get("Vodafone")
        if vf_echt is not None:
            assert z["vf_gesamt"] == vf_echt["gesamt"]
        else:
            assert z["band"] == g["vodafone"]["band"]
            assert z["vf_gesamt"] == g["vodafone"]["gesamt"]


def test_am_echten_bestand_steht_die_benachteiligung_oben(echt):
    raenge = [g["rang"] for g in echt["radar"]["gruppen"]]
    assert raenge == sorted(raenge)
    erste = next((g for g in echt["radar"]["gruppen"]
                  if g["rang"] != float("inf")), None)
    if erste is not None:
        assert erste["rang"] == min(raenge)
        assert erste["rang"] < 0, "die fuehrende Gruppe ist die " \
            "Benachteiligung - ein positiver Wert oben waere die falsche " \
            "Richtung (§2b)"


def test_am_echten_bestand_fuehrt_jeder_mismatch_die_guenstigste_karte(echt):
    by_id = {m["id"]: m for m in echt["modelle"]}
    treffer = 0
    for g in echt["radar"]["gruppen"]:
        for z in g["zeilen"]:
            if z["status"] != wr.STATUS_BAND_MISMATCH:
                continue
            treffer += 1
            modell = by_id[g["id"]]
            karten_davon = [k for k in modell["karten"]
                            if k["anbieter"] == z["anbieter"]
                            and k.get("belastbar") and not k.get("naeherung")
                            and k.get("gesamt") is not None]
            assert karten_davon, \
                f"{g['id']}/{z['anbieter']}: Mismatch ohne jede echte Karte"
            guenstigste = min(karten_davon, key=lambda k: k["gesamt"])
            assert z["gesamt"] == guenstigste["gesamt"], \
                f"{g['id']}/{z['anbieter']}: Beleg ist nicht die guenstigste"
    assert treffer, "kein Band-Mismatch im Bestand - die Invariantenpruefung " \
        "traefe einen leeren Fall (Datenlage ggf. neu ansehen)"


def test_am_echten_bestand_bleiben_haendlerzeilen_geraetepreise(echt):
    haendler = echt["radar"]["haendler"]
    assert haendler, "keine Haendlerzeile im Bestand - §8-Sektion leer?"
    for h in haendler:
        assert "tarif" not in h
        assert h["prozent"] == round(
            (h["preis"] - h["vodafone_preis"]) / h["vodafone_preis"] * 100, 1)
    prozente = [h["prozent"] for h in haendler]
    assert prozente == sorted(prozente)


def test_am_echten_bestand_stehen_die_vier_nicht_erhebbaren(echt):
    """§8, Wortlaut: Amazon (PA-API), MediaMarkt, expert, Euronics (403).
    Dieser Test haelt die Vorgabe gegen die Konfiguration - liefert einer
    von ihnen someday Daten, faellt er und die Erwartung gehoert
    aktualisiert (dann ist der Haendler naemlich im Vergleich, nicht mehr
    eine Luecke)."""
    namen = {f["anbieter"] for f in echt["radar"]["nicht_erhebbar"]}
    assert {"Amazon", "MediaMarkt", "expert", "Euronics"} <= namen, namen
    for f in echt["radar"]["nicht_erhebbar"]:
        assert f["grund"], f"{f['anbieter']} ohne Grund"
