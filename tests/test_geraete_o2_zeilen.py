"""O2 (STRATEGIE_GERAETE_OPTIK §3, 11.09.2026): Entrümpelung der
Vergleichsansicht - die Bündel-Karten werden Tabellenzeilen.

Die Abnahmekriterien des O2-Auftrags, hier als statische Messung:
  A2  <details> gesamt im Hauptpfad deutlich unter 100 - Rechenweg-
      Aufklapper je Zeile, "Wie gerechnet?", wenige.
  A6  KEIN DATENVERLUST: jede Information, die vorher auf den Karten stand
      (Rechenweg, Pflichtzeile "nach 24 Monaten gezahlt", Zustand
      "erneuert", Beleglinks, Abrufdatum), steht danach in der Zeile oder
      ihrem Rechenweg-Aufklapper. Der Test zählt die Karten der Aufbereitung
      gegen die Zeilen des gerenderten HTML - vorher (Daten) gegen nachher
      (Seite).

Dazu die Streichungen des Auftrags: keine "Beschaffung läuft"-
Platzhalterkarten (die Legendenzeile aus O1 trägt die Information), keine
Kartenklappe, keine "Alle Bündel als Tabelle" (beide verschmelzen mit der
Zeilen-Tabelle), keine Alarmtabelle und kein "Bei Wettbewerbern gelistet"
auf der Geräteseite (beide stehen auf wettbewerbsradar.html - dort hält
sie `tests/test_wettbewerbsradar_alarme.py` fest).
"""
from __future__ import annotations

import json
import math
import pathlib

import yaml
from bs4 import BeautifulSoup

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view
from telco_radar.report.html import render_site

from test_geraete_tco_zustand import HEUTE, _baue


def _zr_fragment(tmp_path: pathlib.Path) -> list:
    """Die Zeitreihen-Lager des gerenderten Fragments - _baue_ohne_band
    rendert nach <tmp>/ohne_band/site, das Fragment liegt daneben."""
    fragment = (tmp_path / "ohne_band" / "site" / "data"
                / "geraete-zeitreihe.html")
    assert fragment.exists(), "Zeitreihen-Fragment fehlt"
    return BeautifulSoup(fragment.read_text(encoding="utf-8"),
                         "html.parser").select(".gr-zr-lager")

WURZEL = pathlib.Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Eine eigene Fixture für die Ohne-Tarifband-Gruppe: unbegrenzte Tarife,
# Tarife ohne Volumen und ein Händler-Barpreis - die drei Lager, die nach
# dem Entwurf als KOMPAKTE Gruppe unter der Band-Tabelle stehen, nicht als
# Mischkarten im Band.
# --------------------------------------------------------------------------

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro", "generation": 17,
     "marktstart": "2025-09-19", "speicher": [256], "segment": "premium"}]}
_FARBEN = {"farben": {"schwarz": ["Schwarz"]}}
_QUELLEN = {"anbieter": [
    {"name": "o2", "typ": "netzbetreiber", "rang": 2, "methode": "ldjson",
     "basis_url": "https://www.o2online.de",
     "einstiege": [{"url": "https://www.o2online.de/handys"}]},
    {"name": "Vodafone", "typ": "netzbetreiber", "rang": 1, "eigen": True,
     "methode": "ldjson", "basis_url": "https://www.vodafone.de",
     "einstiege": [{"url": "https://www.vodafone.de/handys"}]},
    {"name": "Saturn", "typ": "handel", "gruppe": "Ceconomy", "rang": 2,
     "methode": "saturn_brand", "aktiv": True,
     "basis_url": "https://www.saturn.de",
     "einstiege": [{"url": "https://www.saturn.de/handys"}]},
]}

SKU = "apple-iphone-17-pro-256gb-schwarz"


def _listung(anbieter, preis):
    return {"id": f"{anbieter.lower()}--{SKU}", "sku_id": SKU,
            "device_id": "apple-iphone-17-pro", "anbieter": anbieter,
            "anbieter_typ": ("handel" if anbieter == "Saturn"
                             else "netzbetreiber"),
            "speicher_gb": 256, "farbe_roh": "Schwarz",
            "farbe_normalisiert": "schwarz", "zustand": "neu",
            "first_seen": "2026-08-20", "last_verified": HEUTE,
            "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-20",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{SKU}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/liste"]}


def _buendel(anbieter, tarif_id, tarif_name, gb, *, tarif=24.99, rate=20.0,
             laufzeit=24, zuzahlung=1.0):
    return {"id": f"buendel--{anbieter.lower()}--{tarif_id}",
            "sku_id": SKU, "anbieter": anbieter, "tarif_name": tarif_name,
            "tarif_id": tarif_id, "tarif_id_guete": "hoch",
            "tarif_monatlich": tarif, "geraet_zuzahlung": zuzahlung,
            "geraet_monatsrate": rate, "laufzeit_monate": laufzeit,
            "anschlusspreis": 0.0, "zustand": "neu", "rabatte": [],
            "quelle_url": f"https://example.de/{anbieter.lower()}/{SKU}",
            "abgerufen_am": HEUTE, "first_seen": HEUTE,
            "last_verified": HEUTE}


def _tarif(anbieter, tarif_id, tarif_name, gb):
    return {"anbieter": anbieter, "name": tarif_name, "tarif_id": tarif_id,
            "art": "mobilfunk", "grundgebuehr": 24.99, "laufzeit_monate": 24,
            "datenvolumen_gb": gb,
            "preisphasen": [{"von_monat": 1, "bis_monat": None,
                             "betrag": 24.99}],
            "dokument_url": f"https://example.de/pib/{tarif_id}",
            "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}


def _baue_ohne_band(tmp_path: pathlib.Path) -> BeautifulSoup:
    """Ein Modell in drei Lagern: Band Klein (o2 + Vodafone), unbegrenzt
    (o2, ohne Band), kein Tarifbestand (1&1, ohne Band) - dazu Saturn mit
    und Amazon/Expert ohne Händlerpreis."""
    import math
    root = tmp_path / "ohne_band"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state = root / "data" / "state"
    state.mkdir(parents=True)
    listungen = [_listung("o2", 1099.0), _listung("Vodafone", 1199.90),
                 _listung("Saturn", 1179.0)]
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE, "anbieter": {
            n: {"laeufe": 4, "funde_gesamt": 1}
            for n in ("o2", "Vodafone", "Saturn")},
        "listungen": listungen}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text("", encoding="utf-8")
    buendel = [
        _buendel("o2", "o2:klein", "O2 Mobile Klein", 10),
        _buendel("Vodafone", "vf:klein", "Vodafone Mobil XS", 18, rate=26.0),
        # Unbegrenzt: außerhalb der Bänder (§ 7) - Zeile der eigenen Gruppe.
        _buendel("o2", "o2:unlimited", "O2 Unlimited", math.inf),
        # 1&1 ohne tarif_id (wie im echten Bestand: 1&1-Tarife stehen
        # nicht im Tarifbestand) - kein Datenvolumen, also kein Band.
        {**_buendel("1&1", "", "1&1 All-Net-Flat S", None),
         "tarif_monatlich": None, "geraet_monatsrate": None,
         "buendel_monatlich": 44.99, "geraet_zuzahlung": 1.0,
         "laufzeit_monate": 36},
    ]
    for b in buendel:
        if b["tarif_id"] == "":
            b.pop("tarif_id")
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": buendel, "sim_only": []}),
        encoding="utf-8")
    tarife = [_tarif("o2", "o2:klein", "O2 Mobile Klein", 10),
              _tarif("Vodafone", "vf:klein", "Vodafone Mobil XS", 18),
              _tarif("o2", "o2:unlimited", "O2 Unlimited", math.inf)]
    (state / "tarife.jsonl").write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8")
    reports = root / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / f"{HEUTE}.json").write_text(json.dumps({
        "date": HEUTE, "language": "de",
        "briefing_md": "## Auf einen Blick\n\n- Nichts Besonderes.\n",
        "stats": {}, "regions": []}), encoding="utf-8")
    (reports / f"{HEUTE}.md").write_text("# Bericht\n", encoding="utf-8")
    site = root / "site"
    render_site(site, reports)
    return BeautifulSoup((site / "geraete.html").read_text(encoding="utf-8"),
                         "html.parser")


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


# --------------------------------------------------------------------------
# Die Zeilen-Struktur (Auftrag 1)
# --------------------------------------------------------------------------

def test_je_buendel_eine_zeile_mit_vier_kernangaben_und_aufklapper(tmp_path):
    """Jedes Bündel des Vorgabemodells ist EINE Zeile: Anbieter, Tarif mit
    Volumen, TCO-24, Δ zur Vodafone-Referenz, Gerät ohne Vertrag - und je
    Zeile EIN schmaler Rechenweg-Aufklapper (Entwurf `.bnd`)."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    zeilen = tafel.select("#gr-bndliste .gr-bnd")
    assert len(zeilen) == 3, "o2 neu, o2 erneuert und die Referenz"
    for z in zeilen:
        summary = z.select_one("summary")
        assert summary is not None, "Zeile ohne summary"
        an = summary.select_one(".gr-bnd-an")
        tarif = summary.select_one(".gr-bnd-tarif")
        tco = summary.select_one(".gr-bnd-tco")
        delta = summary.select_one(".gr-bnd-delta")
        bar = summary.select_one(".gr-bnd-bar")
        for zelle, name in ((an, "Anbieter"), (tarif, "Tarif"),
                            (tco, "TCO-24"), (delta, "Δ"), (bar, "Gerät")):
            assert zelle is not None, f"Zeile ohne {name}-Zelle"
        assert "€" in tco.get_text(), "TCO-Zelle ohne Zahl"
        assert "TCO-24" in tco.get_text(), "TCO-Zelle ohne Laufzeit-Etikett"
        assert z.select_one(".gr-bnd-rw") is not None, \
            "Zeile ohne Rechenweg-Aufklapper-Inhalt"


def test_die_zeilen_stehen_nach_gesamtkosten_sortiert(tmp_path):
    """Der Entwurf sortiert die Bandliste aufsteigend nach TCO-24 - die
    günstigste Zeile zuerst (kein Sortier-Control, §4 Entscheidung 3)."""
    s = _baue(tmp_path)
    werte = []
    for z in s.select("#gr-bndliste .gr-bnd"):
        roh = z.get("data-gesamt")
        werte.append(float(roh) if roh else None)
    # Gegenprobe gegen den leeren Lookup: eine leere Liste waere immer
    # sortiert (CLAUDE.md 6 - dieselbe Falle wie der Titel-Lookup).
    assert werte, "keine Zeile in der Bandliste - der Test misst nichts"
    assert werte == sorted(werte), werte


def test_keine_karten_und_keine_kartenklappe_mehr(tmp_path):
    """Auftrag 1: Kartenklappe und "Alle Bündel als Tabelle" verschmelzen
    mit der Zeilen-Tabelle - keins der drei alten Gebilde bleibt."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select_one("details.gr-karten-auf") is None, \
        "die Kartenklappe steht noch"
    assert tafel.select_one(".gr-kkarte") is None, "Karten stehen noch"
    assert tafel.select_one(".gr-ksteuer") is None, \
        "Sortierung/Filter der Klappe stehen noch"
    assert tafel.select_one("#gr-tco-tabelle") is None, \
        "'Alle Bündel als Tabelle' steht noch als eigene Tabelle"
    assert tafel.select_one("table.gr-ttab--leit") is None


# --------------------------------------------------------------------------
# A6 - kein Datenverlust, gezählt vorher (Aufbereitung) gegen nachher (Seite)
# --------------------------------------------------------------------------

def _vorgabe_daten(root: pathlib.Path) -> dict:
    geraete = geraete_view.aufbereiten(
        root / "data" / "state", lade_quellen(root), lade_katalog(root),
        heute=HEUTE)
    tco = geraete["tco"]
    modell = next(m for m in tco["modelle"]
                  if m["id"] == tco["modell_vorgabe"])
    return modell


def test_jede_karte_der_aufbereitung_ist_eine_zeile(tmp_path):
    """A6, der Zähltest: die Karten des Vorgabemodells aus der Aufbereitung
    (vorher) und die Zeilen des gerenderten HTML (nachher) sind dieselbe
    Menge - je (Anbieter, Tarif, Gesamt) genau eine Zeile."""
    s = _baue(tmp_path)
    modell = _vorgabe_daten(tmp_path / "mit")
    karten = [k for k in modell["karten"] if k["belastbar"]]
    assert len(karten) == 3
    zeilen = s.select("#tafel-tco .gr-bnd")
    assert len(zeilen) == len(karten), (
        f"{len(karten)} Karten stehen {len(zeilen)} Zeilen gegenüber")
    gesehen = set()
    for k in karten:
        treffer = [z for z in zeilen
                   if z.get("data-anbieter") == k["anbieter"]
                   and _text(z.select_one(".gr-bnd-tco")).startswith(
                       _euro(k["gesamt"]))]
        assert len(treffer) == 1, (
            f"{k['anbieter']} {k['tarif']}: {len(treffer)} Zeilen")
        gesehen.add(id(treffer[0]))
    assert len(gesehen) == len(karten), "Zeilen wurden doppelt getroffen"


def _euro(betrag: float) -> str:
    """Dieselbe deutsche Euro-Schreibweise wie der `euro`-Filter der Seite."""
    text = f"{betrag:,.2f}".replace(",", "#").replace(".", ",") \
        .replace("#", ".")
    return text


def test_jede_zeile_traegt_rechenweg_pflichtzeile_und_belege(tmp_path):
    """A6: Der Rechenweg-Aufklapper einer Zeile trägt, was die Karte trug -
    die Postenliste, die Pflichtzeile aus A5.2 ("nach 24 Monaten gezahlt"),
    den vollen Delta-Satz mit Referenz-Tarif, Beleglink UND Abrufdatum."""
    s = _baue(tmp_path)
    zeilen = s.select("#tafel-tco .gr-bnd")
    assert zeilen
    for z in zeilen:
        rw = z.select_one(".gr-bnd-rw")
        assert rw is not None
        posten = rw.select(".gr-tposten li")
        assert posten, f"{z.get('data-anbieter')}: Rechenweg ohne Posten"
        assert _text(rw).startswith("nach 24 Monaten gezahlt") or \
            "nach 24 Monaten gezahlt" in _text(rw), (
            f"{z.get('data-anbieter')}: Pflichtzeile fehlt")
        assert rw.select_one("a[href]") is not None, \
            f"{z.get('data-anbieter')}: kein Beleglink im Rechenweg"
        assert "abgerufen" in _text(rw), \
            f"{z.get('data-anbieter')}: kein Abrufdatum im Rechenweg"


def test_der_zustand_steht_auf_der_zeile(tmp_path):
    """A6: 'erneuert' ist eine Preisdimension - das Etikett steht im
    Anbieter-Feld der Zeile (nicht erst im Rechenweg)."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    erneuert = tafel.select_one('.gr-bnd[data-zustand="refurbished"]')
    assert erneuert is not None
    assert _text(erneuert.select_one(".gr-bnd-an")) .endswith("erneuert")
    assert erneuert.select_one(".gr-kk-marke--zustand") is not None
    # Und die Gegenprobe am selben Bestand: die neu-Zeile trägt KEIN
    # Etikett - sonst wäre 'erneuert' kein Etikett, sondern Zierat.
    neu = tafel.select_one('.gr-bnd[data-anbieter="o2"][data-zustand="neu"]')
    assert neu is not None
    assert neu.select_one(".gr-kk-marke--zustand") is None


def test_die_referenz_nennt_ihre_naehrung_im_rechenweg(tmp_path):
    """F1 Stufe 1 bleibt: die Referenzzeile heißt 'Referenzrechnung' und
    sagt im Rechenweg, dass der eigene Bündelpreis nicht erhoben ist."""
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    ref = tafel.select_one('.gr-bnd[data-anbieter="Vodafone"]')
    assert ref is not None
    assert "Referenzrechnung" in _text(ref.select_one(".gr-bnd-an"))
    rw = _text(ref.select_one(".gr-bnd-rw"))
    assert "noch nicht erhoben" in rw
    assert "weist zu diesem Gerät keinen Bündelpreis aus" not in \
        tafel.get_text(" ")


# --------------------------------------------------------------------------
# Auftrag 2 - "Beschaffung läuft" und leere Platzhalter weg
# --------------------------------------------------------------------------

def test_beschaffung_laeuft_steht_nicht_mehr_in_der_leseflaeche(tmp_path):
    """E2 (§3.1 + Antonio 9b.7): die 'Beschaffung läuft'-Legende der
    Balkenform ist gefallen - ein Händler ohne Preis ist kein Bündel-
    Anbieter und steht nicht einzeln da. Die Auskunft lebt auf
    geraete-quellen.html; der Katalog zeigt die Listungen."""
    s = _baue_ohne_band(tmp_path)
    kopie = BeautifulSoup(str(s), "html.parser")
    for k in kopie.select("script"):
        k.decompose()
    text = kopie.get_text(" ")
    assert "Beschaffung läuft" not in text
    for name in ("Amazon", "Expert"):
        assert name not in text, f"{name} steht einzeln in der Lesefläche"


def test_keine_leeren_platzhalterkarten_mehr(tmp_path):
    """Leerkarten ('Für dieses Modell ist bei Telekom noch kein Bündelpreis
    erhoben …') fallen - die Legende nennt dieselben Anbieter je Band."""
    s = _baue_ohne_band(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert not tafel.select(".gr-kkarte--leer")
    assert "noch kein Bündelpreis erhoben" not in tafel.get_text(" ")
    # Die Legende formuliert die Lücke je Band - Namen, kein Satz je
    # Anbieter (das war der O1-Befund: 145 Einzelizeilen).
    legende = _text(tafel.select_one(".gr-lueckenzeile"))
    assert legende.count("Kein Bündel") <= 1
    assert ". ." not in legende


def test_die_lueckensaetze_des_fragments_bleiben_fuer_das_umschalten(
        tmp_path):
    """E2: das Modell-/Band-Umschalten versorgt das lazy Fragment
    `data/geraete-zeitreihe.html` - JEDES (Modell, Band) trägt seinen
    Lückensatz dort (und der Server-Startzustand seinen auf der Seite).
    Dieselbe Regel wie O1, am neuen Ort: EIN Satz je Paar, nicht je
    Anbieter; Alternativ-Bänder mit Betrag in Klammern, gruppiert."""
    s = _baue_ohne_band(tmp_path)
    zustand = _zr_fragment(tmp_path)
    assert zustand, "das Zeitreihen-Fragment trägt keine Paare"
    for lager in zustand:
        satz = _text(lager.select_one(".gr-lueckenzeile"))
        if not satz:
            continue
        assert satz.count("Kein Bündel") <= 1, satz
        assert ", " in satz or "·" in satz, \
            "der Sammelsatz gruppiert, er listet nicht je Anbieter"


# --------------------------------------------------------------------------
# Auftrag 3 - die kompakte Gruppe "Ohne Tarifband"
# --------------------------------------------------------------------------

def test_ohne_tarifband_ist_eigene_gruppe_unter_der_bandliste(tmp_path):
    """Unbegrenzte Tarife und Tarife ohne erhobenes Volumen stehen in
    einer klar getrennten Gruppe UNTER der Band-Tabelle - als Zeilen
    derselben Form, nicht heimlich in einem Band."""
    s = _baue_ohne_band(tmp_path)
    tafel = s.select_one("#tafel-tco")
    gruppe = tafel.select_one("#gr-ohneband")
    assert gruppe is not None, "die Gruppe 'Ohne Tarifband' fehlt"
    ohueberschrift = _text(gruppe.find(["h3", "h4"]))
    assert "Ohne Tarifband" in ohueberschrift
    zeilen = gruppe.select(".gr-bnd")
    assert len(zeilen) == 2, "o2 Unlimited und 1&1 stehen ohne Band"
    tarife = [_text(z.select_one(".gr-bnd-tarif")) for z in zeilen]
    assert any("unbegrenzt" in t for t in tarife), tarife
    # Keine Zeile der Gruppe trägt ein Band-Attribut - sonst klänge sie an
    # die Band-Auswahl mit an.
    assert all(z.get("data-band") is None for z in zeilen)
    # Und die Gruppe steht NACH der Bandliste: select() liefert in
    # Dokumentreihenfolge.
    reihenfolge = [el.get("id") or "gr-bndliste"
                   for el in tafel.select("#gr-bndliste, #gr-ohneband")]
    assert reihenfolge == ["gr-bndliste", "gr-ohneband"], reihenfolge


def test_haendler_barpreise_stehen_kompakt_mit_beleg(tmp_path):
    """Händler ohne Tarifbündel: Saturns Barpreis als kompakte Zeile MIT
    Beleg und Abrufdatum (was die Händlerkarte trug) - Amazon und Expert
    ohne Preis stehen NICHT als leere Karten, die Legende nennt sie."""
    s = _baue_ohne_band(tmp_path)
    gruppe = s.select_one("#gr-ohneband")
    zeilen = gruppe.select(".gr-haendlerzeile")
    assert len(zeilen) == 1, "nur Saturn hat einen Preis"
    saturn = _text(zeilen[0])
    assert "Saturn" in saturn and "1.179,00 €" in saturn
    assert "ohne Vertrag" in saturn
    assert zeilen[0].select_one("a[href]") is not None, "ohne Beleglink"
    assert "abgerufen" in saturn
    # Amazon und Expert: kein Preis, keine Zeile - und seit E2 auch keine
    # Einzelnennung in einer Legende (Antonio 9b.7: nichts heisst nicht
    # einzeln). Der Lückensatz nennt nur den Bündel-Anbieterkreis.
    assert "Amazon" not in _text(gruppe)
    assert "Expert" not in _text(gruppe)
    tafel_text = _text(s.select_one("#tafel-tco"))
    assert "Amazon" not in tafel_text and "Expert" not in tafel_text


def test_die_bandliste_traegt_ihr_band_als_attribut(tmp_path):
    """app.js versteckt Zeilen anderer Bänder - das Band steht als
    data-band AN der Zeile (kein zweiter Gruppierungspfad im DOM)."""
    s = _baue_ohne_band(tmp_path)
    zeilen = s.select("#gr-bndliste .gr-bnd")
    assert zeilen
    for z in zeilen:
        assert z.get("data-band") in ("klein", "mittel", "gross"), \
            z.get("data-band")


# --------------------------------------------------------------------------
# A2 - die Anzahl der Aufklapper
# --------------------------------------------------------------------------

def test_deutlich_weniger_als_hundert_aufklapper(tmp_path):
    """A2: <details> gesamt in der Vergleichsansicht deutlich unter 100 -
    Rechenweg je Zeile, 'Wie gerechnet?', Maßstab, Datenlage. Gemessen an
    der Fixture; der ECHTE Bestand misst derselbe Satz in
    `test_geraete_o2_zeilen_browser` (dort mit Vorgabemodell, 19 Zeilen)."""
    s = _baue_ohne_band(tmp_path)
    tafel = s.select_one("#tafel-tco")
    anzahl = len(tafel.select("details"))
    assert anzahl < 100, f"{anzahl} <details> in der Vergleichsansicht"
    # Und die Mischkarte ist wirklich weg: keine Karte, keine Klappe.
    assert anzahl <= 4 + 3 * 3, (
        f"{anzahl} Aufklapper - mehr als Wie-gerechnet + Maßstab + "
        "Datenlage + Rest + Rechenwege je Zeile")


# --------------------------------------------------------------------------
# Auftrag 4/5 - Alarmtabelle und "Bei Wettbewerbern gelistet" sind WEG
# ( ihr neuer Ort ist wettbewerbsradar.html - dort hält
#   tests/test_wettbewerbsradar_alarme.py beide fest. )
# --------------------------------------------------------------------------

def test_keine_alarmtabelle_mehr_auf_der_geraeteseite(tmp_path):
    s = _baue(tmp_path)
    tafel = s.select_one("#tafel-tco")
    assert tafel.select_one("#gr-alarme") is None
    assert tafel.select_one(".gr-chips") is None
    assert tafel.select_one(".gr-a-zeile") is None, \
        "Alarmzeilen stehen noch in der Vergleichsansicht"
    assert "stehen einem Wettbewerber gegenüber" not in tafel.get_text(" ")


def test_kein_bei_wettbewerbern_gelistet_mehr_auf_der_geraeteseite(tmp_path):
    s = _baue(tmp_path)
    assert s.select_one(".gr-vergleich-luecke") is None
    assert "Bei Wettbewerbern gelistet" not in s.get_text(" ")
