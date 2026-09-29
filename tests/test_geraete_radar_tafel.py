"""E3 Schritt 2 (AUFTRAG_GERAETE_EINE_SEITE_V2 §1d/S2/S3): die Radar-Tafel
im Radar-Reiter von geraete.html.

Der Radar-Reiter ist mit dem Neuentwurf der Geräteseite (29.09.2026,
eine Kosten-Rangliste ohne Reiter) gefallen, mit ihm die Seitentests
dieser Datei. Geblieben sind die Einheiten von `geraete_radar`, die für
den Radar-Export weiter rechnen (Leerzustand, Richtungswort, Vorzeichen
der Balken), und die Fixture `_seite` (gebaut in tmp_path nach der
Bauform von `test_wettbewerbsradar._seite`, Karten auf dem echten Weg
über `karten.modelle()` → `tco_24()`), die
`test_geraete_methodik_umzug.py` nutzt.
"""
from __future__ import annotations

import json
import pathlib

import yaml
from bs4 import BeautifulSoup

from tarifleiter_testbestand import mit_leiter

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
    # P3-E1: die Testleiter XS/M/L (5/36/85 GB) legt die Stufen dorthin,
    # wo die alten Baender lagen - XS 10/18 GB, L 100 GB.
    return mit_leiter([xs, satz("o2", "O2 Mobile S", "o2:k", 10, 9.99),
                       satz("o2", "O2 Mobile L", "o2:g", 100, 39.99)], HEUTE)


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
                        "segment": "m"})
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

    Jedes generische Geraet bekommt VF-Listung + o2-Bündel im Band XS
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


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split())


# --------------------------------------------------------------------------
# Der Notzustand
# --------------------------------------------------------------------------

def test_leerzustand_traegt_den_modellisten_schluessel():
    """`leer()` ist der Auffangboden - fehlt der Schlüssel, wirft die
    Vorlage genau dann, wenn ohnehin etwas kaputt ist."""
    voll = wr.radar({"modelle": [], "band_je_tarif": {}}, {}, {})
    assert set(wr.leer()) == set(voll)
    assert voll["modelliste"] == wr.leer()["modelliste"]


def test_das_richtungswort_liest_den_angezeigten_cent():
    """Das Wort der Leitzahl rundet wie ihre Zahl: -0,004 € steht als
    „+0,00 €" (bzw. „-0,00 €") da und darf nicht „günstiger" heißen."""
    assert wr._richtung(-811.05) == "günstiger als"
    assert wr._richtung(12.0) == "teurer als"
    assert wr._richtung(0.0) == "gleich teuer wie"
    assert wr._richtung(-0.004) == "gleich teuer wie"
    assert wr._richtung(-0.006) == "günstiger als"


def test_die_balken_tragen_das_vorzeichen_der_seite():
    """Die Balken rechnen `delta` = Vodafone − Wettbewerber (Länge und
    Richtung), beschriften aber in der Zeichenregel der Seite: ein
    Wettbewerber, der 280,90 € günstiger ist, steht als „-280,90 €" da -
    wie in Modell-Liste, Händlertabelle und Δ-Spalte „Mit Tarif". Bis
    28.09.2026 stand dort „+280,90 €" (gegen den alten Stand rot)."""
    zeilen = [
        {"device_id": "a", "speicher": 128, "modell": "Guenstig bei W",
         "hersteller": "x", "delta": 280.90, "prozent": 28.7,
         "laden": "Medimax", "vf_preis": 979.90, "gegen_preis": 699.00},
        {"device_id": "b", "speicher": 128, "modell": "Teurer bei W",
         "hersteller": "x", "delta": -20.0, "prozent": -2.0,
         "laden": "Saturn", "vf_preis": 1000.0, "gegen_preis": 1020.0},
    ]
    for breit in (True, False):
        svg = BeautifulSoup(wr._grafik_svg(zeilen, ("a", 128), breit),
                            "html.parser")
        werte = [_text(t) for t in svg.select("text.wr-gr-wert")]
        assert any(w.startswith("-280,90 €") for w in werte), werte
        assert any(w.startswith("+20,00 €") for w in werte), werte
        assert not any(w.startswith("+280,90") for w in werte), werte
        # Richtung und Vorzeichen aus derselben Größe: negative Werte
        # stehen links der Vodafone-Linie (Anker am Ende), positive rechts.
        for t in svg.select("text.wr-gr-wert"):
            links = t.get("text-anchor") == "end"
            assert links == _text(t).startswith("-"), (_text(t), links)


def test_scheiternder_kostenvergleich_steht_sichtbar_auf_der_seite(
        tmp_path, monkeypatch):
    """Clean Code 5: wirft die Aufbereitung, nennt die Seite das Scheitern
    im Kostenbereich, statt still "Keine Gerätepreise." zu zeigen."""
    from telco_radar.report import geraete_kosten

    def kaputt(*_a, **_k):
        raise ValueError("kaputt")

    monkeypatch.setattr(geraete_kosten, "seite", kaputt)
    html = _seite(tmp_path)["geraete.html"]
    kosten = BeautifulSoup(html, "html.parser").select_one("#kosten .kv-nichts")
    assert kosten is not None
    assert _text(kosten) == "Kostenvergleich fehlgeschlagen: ValueError"


def test_heiler_kostenvergleich_nennt_kein_scheitern(tmp_path):
    """Gegenprobe zum Fehlerweg."""
    html = _seite(tmp_path)["geraete.html"]
    assert "Kostenvergleich fehlgeschlagen" not in html
