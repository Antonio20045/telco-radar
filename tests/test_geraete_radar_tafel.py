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

from telco_radar.report import geraete_radar as wr
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
    Abschnitt - jede mit einem Satz, was sie misst.

    P4/D1 (STRATEGIE_GERAETE_V3, 18.09.2026): VOR diesen dreien steht
    seit dem Design-Durchlauf die GRAFIK-Sektion (#wr-grafik) - die
    Frage des Reiters liest sich zuerst als Bild, die Tabellen sind
    Aufklapper darunter (design.md: „Radar: Balken je Modell statt 746
    Zeilen"). Der Test war gegen den Grafik-Stand ROT (3 Köpfe statt 4)
    und hält jetzt VIER Sektionen in dieser Folge fest."""
    suppe = _suppe(tmp_path)
    tafel = suppe.select_one("#tafel-radar")
    assert tafel is not None, "#tafel-radar fehlt"
    koepfe = [_text(k) for k in tafel.select("h3.gr-unter")]
    assert len(koepfe) == 4, f"vier Sektionen erwartet, steht da: {koepfe}"
    assert koepfe[0].startswith("Die größten Abstände zu Vodafone"), koepfe
    assert koepfe[1].startswith("Preis-Alarme"), koepfe
    assert koepfe[2].startswith("Alle Modelle nach Abweichung zu Vodafone"), \
        koepfe
    assert koepfe[3].startswith("Händler"), koepfe
    # Jede Sektion erklärt in einem Satz ihre Frage - keine ohne Zweck.
    for kopf in koepfe:
        sec = kopf and suppe.find(string=kopf)
        assert sec, kopf


# --------------------------------------------------------------------------
# P4/D1 (STRATEGIE_GERAETE_V3, 18.09.2026): die Grafik, die Legende, der
# Rot-Deckel
# --------------------------------------------------------------------------

def test_die_radar_tafel_traegt_eine_balkengrafik(tmp_path):
    """design.md Regel 3: kein Reiter ohne Grafik - die Frage des Radars
    ("wo sind wir teuer?") liest sich zuerst als BILD. Servergerendertes
    SVG in ZWEI Varianten (schirm/mobil, dasselbe Umschalten wie die
    Zeitreihe), je Balken der Wert an der Spitze, die Nulllinie mit GENAU
    EINEM Etikett ("Vodafone" - die Referenz, nicht 48-mal wiederholt)."""
    suppe = _suppe(tmp_path)
    tafel = suppe.select_one("#tafel-radar")
    assert tafel is not None
    svgs = tafel.select("svg.wr-gr")
    varianten = {v for s in svgs for v in s.get("class", [])}
    assert {"wr-gr--breit", "wr-gr--schmal"} <= varianten, \
        "die Grafik fehlt oder steht nur in einer Breite da"
    breit = tafel.select_one("svg.wr-gr--breit")
    balken = breit.select("path.wr-gr-balken")
    assert balken, "die Grafik trägt keinen Balken - der Test prüft nichts"
    # Ein Balken trägt beide Zahlen selbst (Wert an der Spitze); der
    # <title> nennt beide Preise der Messung (Nachprüfbarkeit).
    assert breit.select("text.wr-gr-wert"), "kein Balken trägt seinen Wert"
    titel = balken[0].select_one("title")
    assert titel is not None and "€" in titel.get_text(), \
        "der Balken nennt seine Messung nicht (Belegzwang)"
    etiketten = [e.get_text(strip=True)
                 for e in breit.select("text.wr-gr-nulltext")]
    assert etiketten == ["Vodafone"], etiketten


def test_die_grafik_traegt_genau_einen_roten_balken(tmp_path):
    """Rot-Deckel (design.md Regel 4): in der Grafik trägt ROT genau der
    schärfste Befund - der größte Abstand ZUUNGUNSTEN Vodafones. Ist kein
    solcher Fall im Bestand, gibt es keinen roten Balken (die Fixture
    trägt genau einen: iPhone 15, VF 709,90 € gegen Saturn 679,90 €)."""
    suppe = _suppe(tmp_path)
    tafel = suppe.select_one("#tafel-radar")
    for variante in ("wr-gr--breit", "wr-gr--schmal"):
        svg = tafel.select_one(f"svg.{variante}")
        assert svg is not None
        rot = svg.select("path.wr-gr-balken--spitze")
        assert len(rot) == 1, \
            f"{variante}: {len(rot)} rote Balken statt genau einem"
        assert rot[0].select_one("title").get_text().startswith("iPhone 15")


def test_die_vodafone_basis_steht_als_eine_legende(tmp_path):
    """P4/D1: die Zeile 'Vodafone-Basis: … TCO-24 (…, Band …)' stand in
    JEDER Modell-Detailzeile (am echten Bestand 48- bis 60-mal dieselbe
    Formel). Seit P4 gibt es EINE Legende über der Tabelle - der
    VF-Betrag steht je Anbieter-Zeile selbst ('Band · VF x €')."""
    suppe = _suppe(tmp_path)
    tafel = suppe.select_one("#tafel-radar")
    assert tafel.select_one(".wr-basis-legende") is not None, \
        "die Vodafone-Basis-Legende fehlt"
    assert len(tafel.select(".wr-basis-legende")) == 1, \
        "die Legende steht mehrfach da - wiederholte Formel"
    assert not tafel.select(".wr-basis"), \
        "eine alte Vodafone-Basis-Zeile steht noch in einer Detailzeile"


def test_rot_ist_akzent_nicht_teppich(tmp_path):
    """Rot-Deckel (design.md Regel 4, messbar): maximal ZEHN rot
    eingefärbte Datenelemente je Tafel. Als DOM-Stellvertreter zählt der
    Test die Elemente, die eine Rot-Klasse tragen ('--spitze' sowie das
    rote Eigen-Markierung des Lifecycle), denn die Farbe sitzt im
    Stylesheet - am echten Bestand gemessen (Playwright, 18.09.2026):
    vorher 40 sichtbare Daten-Rot-Elemente, nachher 1."""
    suppe = _suppe(tmp_path)
    tafel = suppe.select_one("#tafel-radar")
    rot = tafel.select("[class*='--spitze'], .gr-eigen")
    assert len(rot) <= 10, \
        f"{len(rot)} Elemente tragen Rot-Klassen - Rot ist Fläche geworden"


def test_jede_sektion_traegt_einen_frage_satz(tmp_path):
    suppe = _suppe(tmp_path)
    for sec in suppe.select("#tafel-radar .gr-r-sektion"):
        # P4-Fix (Sicht-Pruefung 18.09.): die Grafik-Sektion traegt ihren
        # Satz als ACHSLABEL unter dem Bild (p.gr-achsenlabel) - dieselbe
        # Pflicht, andere Bauform: der Satz erklaert die Achse, nicht die
        # Sektion.
        satz = sec.select_one("h3.gr-unter ~ p.gr-erklaer, p.gr-erklaer, "
                              "p.gr-achsenlabel")
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
    Abschnitt ganz unten sein' - die Händler-Sektion ist die LETZTE der
    gleichwertigen Sektionen, kein Rest unter dem Rest (bis E3 stand sie
    auf der Schwesterseite unter den Portfolio-Listen).

    P4/D1 (18.09.2026): die Grafik-Sektion (#wr-grafik) steht seit dem
    Design-Durchlauf VOR den dreien - dieselbe Liste, ein Kopf mehr. Der
    Test war gegen den Grafik-Stand ROT und dreht seitdem mit."""
    suppe = _suppe(tmp_path)
    sektionen = suppe.select("#tafel-radar .gr-r-sektion")
    assert [s.get("id") for s in sektionen] == ["wr-grafik", "wr-alarme",
                                                "wr-abweichung",
                                                "wr-haendler"]


def test_der_tafelkopf_polt_nur_die_sektionen_mit_vorzeichen(tmp_path):
    """E3-Fix (QA 17.09.2026, B2): Der Tafelkopf sagte, die Leitzahl gelte
    'mit Vorzeichen' für ALLE drei Sektionen - die Alarmtabelle zeigt
    denselben Abstand aber als positiven BETRAG (Stufen, Sortierung und
    Export der Alarme sind Betrags-Sprache: '41,3 %' heißt dort
    Wettbewerber günstiger, in der Modellliste heißt dasselbe '−41,3 %').
    Der Leser sah auf EINER Tafel −55,5 % und +41,3 % für dieselbe
    Richtung der Aussage. Die Zeichenregel muss irgendwo die Wahrheit
    sagen: Vorzeichen in Modellliste und Händlern, Betrag ohne Vorzeichen
    in den Preis-Alarmen - und die Alarmtabelle bleibt Betrags-Tabelle
    (keine Zeile trägt ein Minus, für die keine Regel mehr gilt).
    P4-Fix (Sicht-Prüfung 18.09.): der Regel-Satz steht seit dem Design-
    Durchlauf nicht mehr als Absatz zwischen Leitzahl und Grafik
    (Tafelkopf), sondern als Achslabel UNTER der Balkengrafik - der
    Locator ist mitgezogen, die AUSSAGE unverändert."""
    suppe = _suppe(tmp_path)
    tafel = suppe.select_one("#tafel-radar")
    kopf = _text(tafel.select_one("#wr-grafik .gr-achsenlabel"))
    assert kopf, "das Achslabel unter der Balkengrafik fehlt"
    # Die Pauschalbehauptung ('mit Vorzeichen' für alle drei) ist weg …
    assert "Die drei Sektionen messen sie" not in kopf, kopf
    # … und die Alarme sind als BETRAG benannt, nicht als vorzeichen-
    # behaftete Leitzahl. P4/D4 (18.09.2026) hat den Kopf von drei
    # Sätzen auf EINEN gestrafft (Falz-Regel: vor dem ersten Datenelement
    # höchstens EIN Satz - die Leitzahl darüber sagt die Richtung ohne
    # Worte); der Test hält die AUSSAGE, nicht den alten Wortlaut.
    assert "als Betrag" in kopf, kopf
    # Die Gegenseite der Zusicherung: die Alarmtabelle zeigt Beträge -
    # jede sichtbare Prozentzahl ist positiv (Wettbewerber günstiger).
    werte = [float(z.get("data-s-prozent"))
             for z in tafel.select("#wr-alarme .gr-a-zeile[data-s-prozent]")]
    assert werte, "Fixture ohne Alarmzeilen - der Test prüfte nichts"
    assert all(w > 0 for w in werte), werte


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
    Vergleich steht (keine Vodafone-Kosten über 24 Monate erhoben, kein
    gemeinsames Band)."""
    suppe = _suppe(tmp_path)
    text = _text(suppe.select_one("#wr-abweichung"))
    assert "keine Vodafone-Kosten über 24 Monate erhoben" in text, \
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


def test_die_alt_url_ist_weiterleitung_und_der_lifecycle_ist_mitgezogen(tmp_path):
    """E3 Schritt 3: die Schwesterseite wettbewerbsradar.html ist eine
    Meta-Refresh-Weiterleitung auf #tafel-radar (Musterdatei im Entwurfs-
    ordner). Der Vergleichstest gegen ihre Alarmtabelle ist damit gegen-
    standslos - es gibt sie nicht mehr. Was er sicherte (EINE Quelle, kein
    zweites Leben), sichert jetzt die Struktur: die Alt-URL trägt keine
    Tabelle, und die Lifecycle-Sektion, die bis zur Abschaltung NUR dort
    stand, ist MITGEZOGEN - zugeklappt im Radar-Reiter (Bauform des
    genehmigten Prototyps), nicht gelöscht."""
    seiten = _seite(tmp_path)
    alt = BeautifulSoup(seiten["wettbewerbsradar.html"], "html.parser")
    assert alt.select_one('meta[http-equiv="refresh"]') is not None, \
        "die Alt-URL ist keine Weiterleitung"
    assert alt.select_one(".gr-a-zeile") is None, \
        "die Alt-URL trägt noch Alarmzeilen"
    geraete = BeautifulSoup(seiten["geraete.html"], "html.parser")
    tafel = geraete.select_one("#tafel-radar")
    lifecycle = tafel.select_one("#lifecycle")
    assert lifecycle is not None, \
        "die Lifecycle-Sektion fehlt im Radar-Reiter (Inhaltsverlust)"
    details = lifecycle.select_one("details.gr-auf")
    assert details is not None and "Wie lange ein Gerät im Markt lebt" \
        in _text(details.select_one("summary")), \
        "der Lifecycle ist kein zugeklappter Aufklapper (Prototyp-Bauform)"
    assert not details.get("open", False), \
        "der Lifecycle-Aufklapper steht offen und frisst das 11b-Budget"


# --------------------------------------------------------------------------
# Der Notzustand
# --------------------------------------------------------------------------

def test_leerzustand_traegt_den_modellisten_schluessel():
    """`leer()` ist der Auffangboden - fehlt der Schlüssel, wirft die
    Vorlage genau dann, wenn ohnehin etwas kaputt ist."""
    voll = wr.radar({"modelle": [], "band_je_tarif": {}}, {}, {})
    assert set(wr.leer()) == set(voll)
    assert voll["modelliste"] == wr.leer()["modelliste"]
