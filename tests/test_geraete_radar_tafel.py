"""E3 Schritt 2 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1d/S2/S3): die Radar-Tafel
im Radar-Reiter von geraete.html.

Die Inhalte der bisherigen Schwesterseite wettbewerbsradar.html stehen
seit E3 Schritt 1 als eigener Reiter auf der EINEN Geräteseite - dieser
Test hält die NEUSTRUKTURIERUNG nach S2/S3:

  * DREI klar getrennte, gleichwertige Sektionen (S3): Alarme /
    Abweichung TCO als MODELL-LISTE (S2) / Händler als eigener Abschnitt,
    jede mit einem Satz, was sie misst.
  * Die Abweichungstabelle IST die Modell-Liste (S2): klarer Titel
    "Alle Modelle nach Abweichung zu Vodafone", ALLE Zeilen im DOM
    (kein stiller Deckel - Deckel nur mit Aufklapper "alle N anzeigen"),
    sortierbar nach Rohwert (data-s-*), JE Zeile ein Sprung in den
    Graphen des Vergleichs-Reiters (?modell=…&band=…).
  * Händler = Gerätepreis ohne Finanzierung als GLEICHWERTIGER Abschnitt
    (Antonio: "nicht auf so einem komischen unteren Abschnitt ganz unten").

Gemessen wird am gerenderten Paar (geraete.html derselben Site), gebaut
in tmp_path nach der Bauform von `test_wettbewerbsradar._seite`: die
Karten entstehen auf dem echten Weg über `karten.modelle()` → `tco_24()`,
keine handgebauten Dicts (Adapter-Lektion vom 11.08.).
"""
from __future__ import annotations

import json
import pathlib

import yaml
from bs4 import BeautifulSoup

from telco_radar.report import wettbewerbsradar as wr
from telco_radar.report.html import render_site

HEUTE = "2026-09-17"

# Die festen Faelle (je Zeile: sku, hersteller, modell, speicher).
SKU_IP15 = "apple-iphone-15-128gb-schwarz"       # VF + o2 klein: vergleichbar
SKU_S26 = "samsung-galaxy-s26-256gb-schwarz"     # VF + o2 klein: vergleichbar
SKU_X17 = "xiaomi-17-512gb-schwarz"              # nur o2: kein VF-TCO-24
SKU_P10 = "google-pixel-10-256gb-schwarz"        # VF klein, o2 gross: Mismatch

_FARBEN = {"farben": {"schwarz": ["Schwarz", "Black"]}}


def _tarife() -> list[dict]:
    """vf:xs klein (18 GB), o2:k klein (10 GB), o2:g gross (100 GB) - die
    Band-Zuordnung steht damit fuer jeden Fall der Fixture fest."""
    def satz(anbieter, name, tid, gb, grundgebuehr):
        return {"anbieter": anbieter, "name": name, "tarif_id": tid,
                "art": "mobilfunk", "grundgebuehr": grundgebuehr,
                "laufzeit_monate": 24, "datenvolumen_gb": gb,
                "preisphasen": [], "rabatte": [],
                "dokument_url": f"https://example.de/pib/{tid}",
                "abgerufen_am": HEUTE, "confidence": {}, "fundstellen": {}}
    xs = satz("Vodafone", "Vodafone Mobil XS", "vf:xs", 18, 29.95)
    xs["preisphasen"] = [{"von_monat": 1, "bis_monat": 24, "betrag": 29.95},
                         {"von_monat": 25, "bis_monat": None, "betrag": 29.95}]
    return [xs, satz("o2", "O2 Mobile S", "o2:k", 10, 9.99),
            satz("o2", "O2 Mobile L", "o2:g", 100, 39.99)]


def _listung(anbieter, sku, preis, typ="netzbetreiber") -> dict:
    return {"id": f"{anbieter.lower()}--{sku}", "sku_id": sku,
            "device_id": "-".join(sku.split("-")[:-2]),
            "anbieter": anbieter, "anbieter_typ": typ,
            "speicher_gb": int(sku.split("-")[-2].replace("gb", "")),
            "farbe_roh": "Schwarz", "farbe_normalisiert": "schwarz",
            "zustand": "neu", "first_seen": "2026-08-20",
            "last_verified": HEUTE, "status": "aktiv", "missed_checks": 0,
            "preis_ohne_vertrag": preis, "erstpreis": preis,
            "erstpreis_art": "ohne_vertrag", "erstpreis_am": "2026-08-20",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{sku}",
            "abgerufen_am": HEUTE, "verfuegbarkeit": "lieferbar",
            "confidence": "hoch", "einstiege": ["https://example.de/l"]}


def _buendel(sku, tarif_id, tarif_name, tarif_monatlich, rate,
             anbieter="o2") -> dict:
    """Ein Bündelsatz für geraete_tco.json - dieselben Felder, die der
    nächtliche Lauf schreibt."""
    return {"id": f"buendel--{anbieter.lower()}--{sku}",
            "sku_id": sku, "anbieter": anbieter,
            "tarif_name": tarif_name, "tarif_id": tarif_id,
            "tarif_id_guete": "hoch", "tarif_monatlich": tarif_monatlich,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": rate,
            "laufzeit_monate": 36, "anschlusspreis": 0.0, "rabatte": [],
            "zustand": "neu",
            "quelle_url": f"https://example.de/{anbieter.lower()}/{tarif_id}",
            "abgerufen_am": HEUTE, "first_seen": HEUTE,
            "last_verified": HEUTE}


def _katalog(n_generisch: int) -> dict:
    geraete = [
        {"hersteller": "Apple", "modell": "iPhone 15", "generation": 15,
         "speicher": [128], "segment": "premium"},
        {"hersteller": "Samsung", "modell": "Galaxy S26", "generation": 26,
         "speicher": [256], "segment": "premium"},
        {"hersteller": "Xiaomi", "modell": "Xiaomi 17", "generation": 17,
         "speicher": [512], "segment": "premium"},
        {"hersteller": "Google", "modell": "Pixel 10", "generation": 10,
         "speicher": [256], "segment": "premium"},
    ]
    # Die generischen Geraete reissen den Deckel der Modelliste - ihre Zahl
    # haengt am Modulwert, nicht an einer abgeschriebenen Konstanten (derselbe
    # Grund wie bei SICHTBAR_MAX in test_geraete_reiter_browser).
    for i in range(n_generisch):
        geraete.append({"hersteller": "Testmarke",
                        "modell": f"Testgerät {i + 1:02d}",
                        "generation": 1, "speicher": [128],
                        "segment": "mittel"})
    return {"geraete": geraete}


_QUELLEN = {"anbieter": [
    {"name": "o2", "typ": "netzbetreiber", "rang": 1,
     "methode": "json_endpunkt", "basis_url": "https://www.o2online.de",
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
]}


def _state(n_generisch: int) -> dict:
    """Listungen, Preise und Bündel der Fixture.

    Jedes generische Geraet bekommt VF-Listung + o2-Bündel im Band klein
    (vergleichbar); die vier festen Geraete decken die Sonderfaelle ab.
    """
    listungen = [
        _listung("Vodafone", SKU_IP15, 709.90),
        _listung("Saturn", SKU_IP15, 679.90, "handel"),
        _listung("Vodafone", SKU_S26, 1099.00),
        _listung("o2", SKU_X17, 649.00),
        _listung("Vodafone", SKU_P10, 899.00),
    ]
    buendel = [
        _buendel(SKU_IP15, "o2:k", "O2 Mobile S", 9.99, 20.00),
        _buendel(SKU_S26, "o2:k", "O2 Mobile S", 9.99, 30.00),
        _buendel(SKU_X17, "o2:k", "O2 Mobile S", 9.99, 15.00),
        _buendel(SKU_P10, "o2:g", "O2 Mobile L", 39.99, 25.00),
    ]
    for i in range(n_generisch):
        sku = f"testmarke-testgerat-{i + 1:02d}-128gb-schwarz"
        listungen.append(_listung("Vodafone", sku, 500.0 + i))
        buendel.append(_buendel(sku, "o2:k", "O2 Mobile S", 9.99,
                                10.00 + i))
    return {"listungen": listungen, "buendel": buendel}


def _seite(tmp_path: pathlib.Path) -> str:
    """Baut die Site in tmp_path und gibt das HTML von geraete.html zurück."""
    n_generisch = wr.MODELLISTE_SICHTBAR + 2
    root = tmp_path / "site-bau"
    (root / "config").mkdir(parents=True)
    for name, daten in (("geraete_katalog.yaml", _katalog(n_generisch)),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (root / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    state_daten = _state(n_generisch)
    state = root / "data" / "state"
    state.mkdir(parents=True)
    (state / "geraete_db.json").write_text(json.dumps({
        "updated": HEUTE,
        "anbieter": {n: {"laeufe": 4, "funde_gesamt": 1}
                     for n in ("Vodafone", "o2", "Saturn")},
        "listungen": state_daten["listungen"]}), encoding="utf-8")
    (state / "geraete_preise.jsonl").write_text(
        "".join(json.dumps({"listung_id": e["id"], "datum": HEUTE,
                            "preis_ohne_vertrag": e["preis_ohne_vertrag"],
                            "quelle_url": e["quelle_url"]}) + "\n"
                for e in state_daten["listungen"]), encoding="utf-8")
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": HEUTE, "buendel": state_daten["buendel"],
        "sim_only": [
            {"id": "vf--xs", "anbieter": "Vodafone",
             "tarif_name": "Vodafone Mobil XS", "tarif_id": "vf:xs",
             "tarif_id_guete": "hoch", "tarif_sim_only_monatlich": 29.95,
             "anschlusspreis": None, "rabatte": [],
             "quelle_url": "https://example.de/pib/vf-xs",
             "abgerufen_am": HEUTE, "first_seen": HEUTE,
             "last_verified": HEUTE}]}), encoding="utf-8")
    (state / "tarife.jsonl").write_text(
        "".join(json.dumps(t) + "\n" for t in _tarife()), encoding="utf-8")
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
            for name in ("geraete.html", "wettbewerbsradar.html")}


def _suppe(tmp_path) -> BeautifulSoup:
    return BeautifulSoup(_seite(tmp_path)["geraete.html"], "html.parser")


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


# --------------------------------------------------------------------------
# S3: drei gleichwertige Sektionen, jede mit ihrem Satz
# --------------------------------------------------------------------------

def test_drei_sektionen_in_folge_jede_mit_ihrem_satz(tmp_path):
    """S3: Alarme / Abweichung als Modell-Liste / Händler als gleichwertiger
    Abschnitt - in dieser Folge, jede mit einem Satz, was sie misst."""
    suppe = _suppe(tmp_path)
    tafel = suppe.select_one("#tafel-radar")
    assert tafel is not None, "#tafel-radar fehlt"
    koepfe = [_text(k) for k in tafel.select("h3.gr-unter")]
    assert len(koepfe) == 3, f"drei Sektionen erwartet, steht da: {koepfe}"
    assert koepfe[0].startswith("Preis-Alarme"), koepfe
    assert koepfe[1].startswith("Alle Modelle nach Abweichung zu Vodafone"), \
        koepfe
    assert koepfe[2].startswith("Händler"), koepfe
    # Jede Sektion erklärt in einem Satz ihre Frage - keine ohne Zweck.
    for kopf in koepfe:
        sec = kopf and suppe.find(string=kopf)
        assert sec, kopf


def test_jede_sektion_traegt_einen_frage_satz(tmp_path):
    suppe = _suppe(tmp_path)
    for sec in suppe.select("#tafel-radar .gr-r-sektion"):
        satz = sec.select_one("h3.gr-unter ~ p.gr-erklaer, p.gr-erklaer")
        assert satz is not None and len(_text(satz)) > 30, \
            f"Sektion ohne Frage-Satz: {_text(sec)[:60]}"


def test_die_haendler_sektion_sagt_was_sie_misst(tmp_path):
    """S3: 'Händler = Gerätepreis ohne Finanzierung […] mit einem Satz, was
    er misst (Barpreis ohne Vertrag/Tarif)'."""
    suppe = _suppe(tmp_path)
    sec = suppe.select_one("#wr-haendler")
    assert sec is not None, "die Händler-Sektion fehlt"
    text = _text(sec)
    assert "ohne Finanzierung" in _text(sec.select_one("h3")), text
    assert "Barpreis" in text and "ohne Vertrag" in text, \
        "der Satz nennt nicht das Maß (Barpreis ohne Vertrag/Tarif)"
    # Der Händler steht MIT Namen und Abweichung da - dieselbe %-Logik,
    # nie gegen eine TCO gerechnet.
    assert "Saturn" in text
    assert "%" in text


def test_die_haendler_sektion_steht_nicht_mehr_ganz_unten_als_rest(tmp_path):
    """Antonios Wortlaut: 'das sollte nicht auf so einem komischen unteren
    Abschnitt ganz unten sein' - die Händler-Sektion ist die DRITTE von
    DREI gleichwertigen Sektionen, nicht ein Rest unter dem Rest (bis E3
    stand sie auf der Schwesterseite unter den Portfolio-Listen)."""
    suppe = _suppe(tmp_path)
    sektionen = suppe.select("#tafel-radar .gr-r-sektion")
    assert [s.get("id") for s in sektionen] == ["wr-alarme", "wr-abweichung",
                                                "wr-haendler"]


# --------------------------------------------------------------------------
# S2: die Abweichungstabelle IST die Modell-Liste
# --------------------------------------------------------------------------

def test_die_modelliste_zeigt_alle_modelle_ohne_stillen_deckel(tmp_path):
    """S2: 'alle Zeilen' - jede Modell-Gruppe steht als Zeile im DOM. Der
    Deckel kappt nur die ANSICHT (gr-a-rest), der Rest ist hinter dem
    Aufklapper-Knopf 'alle N anzeigen' erreichbar - nichts wird still
    weggelassen."""
    suppe = _suppe(tmp_path)
    tabelle = suppe.select_one("#wr-abweichung table")
    assert tabelle is not None, "die Modell-Liste fehlt"
    zeilen = tabelle.select("tr.gr-a-zeile")
    n_generisch = wr.MODELLISTE_SICHTBAR + 2
    assert len(zeilen) == 4 + n_generisch, \
        f"{len(zeilen)} Zeilen statt {4 + n_generisch} Modellen"
    ohne_deckel = [z for z in zeilen if "gr-a-rest" not in z.get("class", [])]
    assert len(ohne_deckel) == wr.MODELLISTE_SICHTBAR
    knopf = suppe.select_one("#gr-wmehr")
    assert knopf is not None, "kein 'alle N anzeigen'-Knopf"
    assert f"alle {4 + n_generisch}" in _text(knopf), _text(knopf)


def test_die_modelliste_ist_nach_abweichung_sortiert(tmp_path):
    """Die bewusste Leseentscheidung des Modulkopfs: negativste Abweichung
    (stärkste Benachteiligung Vodafones) zuerst, Zeilen ohne Zahl zuletzt."""
    suppe = _suppe(tmp_path)
    werte = []
    for z in suppe.select("#wr-abweichung tr.gr-a-zeile"):
        roh = z.get("data-s-prozent", "")
        werte.append(float(roh) if roh else None)
    zahlen = [w for w in werte if w is not None]
    assert zahlen == sorted(zahlen), \
        "die Modell-Zeilen stehen nicht nach Abweichung sortiert da"
    assert all(w is None for w in werte[len(zahlen):]), \
        "Zeilen ohne Zahl stehen vor vergleichbaren Zeilen"


def test_die_modellliste_sortiert_nach_robwerten(tmp_path):
    """CLAUDE.md-Regel: Sortierköpfe mit data-sort/data-art, die Rohwerte
    stehen als Zahl an der Zeile (data-s-*), nie im Zelltext - '1.099,90 €'
    ist als Zeichenkette kleiner als '199,00 €'."""
    suppe = _suppe(tmp_path)
    koepfe = {k.get("data-sort"): k.get("data-art")
              for k in suppe.select("#wr-abweichung .gr-sort")}
    assert koepfe.get("prozent") == "zahl", koepfe
    assert koepfe.get("geraet") == "text", koepfe
    assert koepfe.get("gesamt") == "zahl", koepfe
    for z in suppe.select("#wr-abweichung tr.gr-a-zeile"):
        roh = z.get("data-s-prozent", "")
        assert roh == "" or isinstance(float(roh), float)
    # Der Prozent-ROHWERT trägt den Punkt, die ZELLE das deutsche Komma -
    # zwei verschiedene Schreibweisen derselben Zahl sind die Regel, nicht
    # der Zufall (die Zelle formatiert, der Rohwert sortiert).
    erste = suppe.select_one("#wr-abweichung tr.gr-a-zeile td:nth-child(2)")
    assert "," in _text(erste), "die Abweichungs-Zelle ist nicht formatiert"


def test_je_modellzeile_ein_sprung_in_den_graphen(tmp_path):
    """S2: je Zeile ein Sprung in den Graphen des Vergleichs-Reiters, über
    die Deep-Link-Mechanik von E2 (?modell=…&band=…)."""
    suppe = _suppe(tmp_path)
    zeilen = suppe.select("#wr-abweichung tr.gr-a-zeile")
    assert zeilen
    for z in zeilen:
        sprung = z.select_one("a.gr-sprung")
        assert sprung is not None, \
            f"Zeile {_text(z.select_one('td'))} ohne Sprung in den Graphen"
        href = sprung.get("href", "")
        assert "modell=" in href, href
        assert href.startswith("geraete.html") or href.startswith("?"), href
    # Eine vergleichbare Zeile nennt ihr Band (der Graph springt direkt
    # in das Band, in dem das Paar gerechnet wurde).
    vergleichbar = [z for z in zeilen
                    if z.get("data-s-prozent") not in (None, "")]
    assert vergleichbar, "die Fixture trägt keine vergleichbare Zeile"
    with_band = [z.select_one("a.gr-sprung")["href"] for z in vergleichbar
                 if "band=" in z.select_one("a.gr-sprung")["href"]]
    assert with_band, "keine vergleichbare Zeile springt mit Band"


def test_lueckenzeilen_sagen_ihren_grund(tmp_path):
    """Eine Zeile ohne Zahl ist keine leere Zeile: sie sagt, WARUM kein
    Vergleich steht (kein Vodafone-TCO, kein gemeinsames Band)."""
    suppe = _suppe(tmp_path)
    text = _text(suppe.select_one("#wr-abweichung"))
    assert "kein Vodafone-TCO" in text, \
        "der Fall Xiaomi (nur o2) nennt keinen Grund"
    assert "kein gemeinsames Band" in text, \
        "der Fall Pixel (VF klein, o2 gross) nennt keinen Grund"


def test_die_detailzeile_zeigt_alle_anbieter_der_gruppe(tmp_path):
    """B.2.5 gilt weiter: Telekom und 1&1 stehen je Modell als Zeilen ohne
    Zahl da - der Klick auf eine Modell-Zeile zeigt die ganze Gruppe, kein
    Anbieter wird weggelassen."""
    suppe = _suppe(tmp_path)
    tafel = suppe.select_one("#wr-abweichung")
    for z in tafel.select("tr.gr-a-zeile"):
        auf = suppe.select_one("#" + z["data-auf"])
        assert auf is not None, "Modell-Zeile ohne Detailzeile"
        # Nur Zeilen MIT td zaehlen - der html.parser setzt die thead-Zeile
        # der Tabelle-in-Zelle neben den tbody (Browser-Test deckt das DOM).
        namen = {_text(det.select("td")[0]) for det in auf.select("tr")
                 if det.select("td")}
        assert {"Telekom", "1&1", "o2"} <= namen, \
            f"Detailzeile ohne alle Netzbetreiber: {namen}"


def test_die_alarmsektion_steht_im_radar_reiter(tmp_path):
    """Die Alarmtabelle steht im Radar-REITER (S3, erste Sektion) - und
    weiterhin NICHT in der Vergleichsansicht (O2-Regel bleibt)."""
    suppe = _suppe(tmp_path)
    tafel = suppe.select_one("#tafel-radar")
    alarme = tafel.select_one("#wr-alarme")
    assert alarme is not None, "die Alarm-Sektion fehlt im Radar-Reiter"
    assert alarme.select_one(".gr-chips") is not None, "ohne Kacheln"
    assert alarme.select_one("table.gr-alarm") is not None, "ohne Tabelle"
    assert alarme.select("[data-filter='marke']"), "ohne Filter"
    assert alarme.select("tr.gr-a-zeile"), "ohne Alarmzeilen"
    vergleich = suppe.select_one("#tafel-tco")
    assert vergleich.select_one("tr.gr-a-zeile") is None, \
        "Alarmzeilen stehen in der Vergleichsansicht"


def test_die_alarmtabelle_ist_dieselbe_wie_auf_der_schwesterseite(tmp_path):
    """Die Tabelle im Radar-Reiter ist keine zweite Kopie mit eigenem Leben:
    beide Seiten rendern sie aus der geteilten Teilvorlage. Gemessen am
    Zeichenbestand der ersten Zeile (die Fixture hat genau eine)."""
    seiten = _seite(tmp_path)
    import re
    zeilen = []
    for name in ("geraete.html", "wettbewerbsradar.html"):
        fund = re.findall(
            r'<tr class="gr-a-zeile"[^>]*data-auf="auf-1".*?</tr>',
            seiten[name], re.S)
        assert len(fund) == 1, (name, len(fund))
        zeilen.append(fund[0])
    assert zeilen[0].split("data-s-")[0] == zeilen[1].split("data-s-")[0]


# --------------------------------------------------------------------------
# Der Notzustand
# --------------------------------------------------------------------------

def test_leerzustand_traegt_den_modellisten_schluessel():
    """`leer()` ist der Auffangboden - fehlt der Schlüssel, wirft die
    Vorlage genau dann, wenn ohnehin etwas kaputt ist."""
    voll = wr.radar({"modelle": [], "band_je_tarif": {}}, {}, {})
    assert set(wr.leer()) == set(voll)
    assert voll["modelliste"] == wr.leer()["modelliste"]
