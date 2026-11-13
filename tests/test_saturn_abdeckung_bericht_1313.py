"""Baupaket P6 (analyse-abdeckung-1313.md): die neuen MODELL_SLUGS- und
belegte_luecken-Einträge müssen echte, konsistente Verbesserungen sein, nicht
erfundene Daten.

* jedes `device_id` in den neuen `belegte_luecken`-Einträgen und in
  `MODELL_SLUGS` muss zu einem echten Katalogeintrag gehören,
* die drei Saturn/MediaMarkt-Zeilen müssen nach den neuen Einträgen WENIGER
  "ohne Datensatz und ohne Beleg" sein als vorher (Kennzahl aus
  `scripts/saturn_abdeckung_bericht.py`),
* die acht "nicht lieferbar"-Modelle (Baupaket P6) stehen NICHT in
  `MODELL_SLUGS` (ein täglicher Leerlauf-Abruf ohne Nutzen) und NICHT mit
  `art: nicht_im_portfolio` (die Quelle sagt "nicht lieferbar", nicht "nicht
  im Sortiment" - siehe docs/belege/tarifwelt-nicht-lieferbar-1311/README.md
  für dieselbe Unterscheidung bei den drei älteren Modellen).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts import saturn_abdeckung_bericht as bericht
from telco_radar.collect.geraete.tarifwelt_lauf import MODELL_SLUGS
from telco_radar.geraete_model import device_id

WURZEL = Path(__file__).resolve().parent.parent

NICHT_LIEFERBAR_NEU = {
    "motorola-edge-70",
    "samsung-galaxy-z-flip-7",
    "samsung-galaxy-a17",
    "samsung-galaxy-a26",
    "honor-magic-v6",
    "google-pixel-10-pro",
    "xiaomi-redmi-note-15",
    "xiaomi-redmi-note-15-pro",
}


def _katalog_device_ids() -> set[str]:
    """Nur der handgepflegte Katalog (`config/geraete_katalog.yaml`); die
    Auto-Zusätze im Bestand liest diese Testdatei bewusst nicht (Hermetik-
    Regel, siehe tests/conftest.py). Für MODELL_SLUGS/belegte_luecken reicht
    das, weil keines der dort genannten Modelle nur im Bestand steht
    (geprüft über `scripts.saturn_abdeckung_bericht._AUTO_HERSTELLER`)."""
    katalog = yaml.safe_load(
        (WURZEL / "config" / "geraete_katalog.yaml").read_text("utf-8")
    )
    ids = {
        device_id(g["hersteller"], g["modell"]) for g in katalog.get("geraete") or []
    }
    ids |= {device_id(h, m) for m, h in bericht._AUTO_HERSTELLER.items()}
    return ids


def test_alle_modell_slugs_sind_echte_katalogeintraege():
    katalog_ids = _katalog_device_ids()
    unbekannt = set(MODELL_SLUGS) - katalog_ids
    assert not unbekannt, (
        f"MODELL_SLUGS kennt device_id(s), die der Katalog nicht hat: {unbekannt}"
    )


def test_alle_belegten_saturn_modelle_sind_echte_katalogeintraege():
    katalog_ids = _katalog_device_ids()
    daten = yaml.safe_load(
        (WURZEL / "config" / "geraete_abdeckung.yaml").read_text("utf-8")
    )
    unbekannt: set[str] = set()
    for eintrag in daten.get("belegte_luecken") or []:
        if not str(eintrag.get("anbieter") or "").startswith("Saturn/MediaMarkt"):
            continue
        for modell in eintrag.get("modelle") or []:
            if modell not in katalog_ids:
                unbekannt.add(modell)
    assert not unbekannt, (
        f"belegte_luecken nennt device_id(s) ohne Katalogeintrag: {unbekannt}"
    )


def test_nicht_lieferbare_neue_modelle_bleiben_aus_modell_slugs_draussen():
    assert not (NICHT_LIEFERBAR_NEU & set(MODELL_SLUGS))


def test_nicht_lieferbare_neue_modelle_tragen_keine_sortimentsaussage():
    """ "Nicht lieferbar" (Bestandsaussage) ist keine Sortimentsaussage -
    deshalb ohne `art: nicht_im_portfolio`, wie beim Präzedenzfall vom
    13.11.2026 (Galaxy S26+, A57, Pixel 10a)."""
    daten = yaml.safe_load(
        (WURZEL / "config" / "geraete_abdeckung.yaml").read_text("utf-8")
    )
    getroffen: set[str] = set()
    for eintrag in daten.get("belegte_luecken") or []:
        if not str(eintrag.get("anbieter") or "").startswith("Saturn/MediaMarkt"):
            continue
        modelle = set(eintrag.get("modelle") or [])
        if modelle & NICHT_LIEFERBAR_NEU:
            assert not eintrag.get("art"), eintrag
            getroffen |= modelle & NICHT_LIEFERBAR_NEU
    assert getroffen == NICHT_LIEFERBAR_NEU


def test_sitemap_abwesende_modelle_tragen_nicht_im_portfolio_mit_beleg():
    daten = yaml.safe_load(
        (WURZEL / "config" / "geraete_abdeckung.yaml").read_text("utf-8")
    )
    gefunden = False
    for eintrag in daten.get("belegte_luecken") or []:
        if not str(eintrag.get("anbieter") or "").startswith("Saturn/MediaMarkt"):
            continue
        if "apple-iphone-15" in (eintrag.get("modelle") or []):
            gefunden = True
            assert eintrag.get("art") == "nicht_im_portfolio"
            assert str(eintrag.get("beleg") or "").strip()
    assert gefunden


_EXPORT_SPALTEN = ["Modell", "Speicher GB", "Anbieter", "Zustand"]


def _synthetischer_export(pfad: Path, zeilen: list[dict]) -> None:
    """Testweise erfundene Export-Zeilen, nur mit den Spalten, die das
    Skript tatsächlich liest (kein echter Bestand - die Hermetik-Regel der
    Testsuite verbietet Tests das Lesen von `site/`/`data/`)."""
    import csv

    with open(pfad, "w", encoding="utf-8", newline="") as fh:
        schreiber = csv.DictWriter(fh, fieldnames=_EXPORT_SPALTEN, delimiter=";")
        schreiber.writeheader()
        schreiber.writerows(zeilen)


def test_kennzahl_ohne_datensatz_und_ohne_beleg_sinkt_mit_einer_neuen_beleg_zeile(
    tmp_path,
):
    """Reine Logikprüfung: zwei Einheiten, eine mit Export-Zeile, eine ganz
    ohne. Eine `belegte_luecken`-Zeile für die zweite Einheit muss die
    Kennzahl exakt um 1 senken, nie mehr und nie weniger."""
    export_pfad = tmp_path / "export.csv"
    _synthetischer_export(
        export_pfad,
        [
            {
                "Modell": "iPhone 17",
                "Speicher GB": "256",
                "Anbieter": "Saturn/MediaMarkt · Vodafone-Netz",
                "Zustand": "neu",
            },
            {
                "Modell": "Galaxy Z Fold8",
                "Speicher GB": "256",
                "Anbieter": "Vodafone",
                "Zustand": "neu",
            },
        ],
    )
    hersteller_je_modell = {"iPhone 17": "Apple", "Galaxy Z Fold8": "Samsung"}

    ohne_beleg = """
belegte_luecken: []
"""
    mit_beleg = """
belegte_luecken:
  - anbieter: "Saturn/MediaMarkt · Vodafone-Netz"
    modelle:
      - samsung-galaxy-z-fold8
    grund: Testzeile
    geprueft: "2026-11-13"
    bis: "2026-11-20"
"""
    vorher = bericht._ohne_datensatz_und_ohne_beleg(
        ohne_beleg, hersteller_je_modell, export_pfad=export_pfad
    )
    nachher = bericht._ohne_datensatz_und_ohne_beleg(
        mit_beleg, hersteller_je_modell, export_pfad=export_pfad
    )
    assert vorher["Saturn/MediaMarkt · Vodafone-Netz"] == 1
    assert nachher["Saturn/MediaMarkt · Vodafone-Netz"] == 0
    for zeile in ("Saturn/MediaMarkt · Telekom-Netz", "Saturn/MediaMarkt · o2-Netz"):
        assert vorher[zeile] == nachher[zeile] == 2
