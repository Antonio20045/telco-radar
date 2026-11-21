"""Klickliste aus dem Katalog: nur Neuware liefert eine Seite.

Befund 21.11.2026 (Geräte-Lauf 44858465074): die Auto-Liste nahm für o2 und das Galaxy
S25 Ultra 256 GB die Adresse eines Bündels „…-titanium-silverblue-erneuert-details“
(SKU ``…-refurbished``) und führte die Seite als Neuware. Der Klick-Lauf las dort den
Preis des gebrauchten Geräts (25 € Anzahlung, 36 × 24 €; die Seite heißt „Samsung
Galaxy S25 Ultra (gebraucht)“, „Gesamtpreis Gerät: 889,00 €“) und die Zusammenführung
ersetzte damit die Neuware-Zeilen (sichtbar: 1 € Anzahlung, 36 × 30 €, „Gesamtpreis
Gerät: 1.081,00 €“). Die Seite trägt keinen Zustand; eine Adresse aus einem Bündel,
das nicht neu ist, darf darum keine Seite liefern.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from telco_radar.collect.geraete.klickliste_auto import leite_ab
from telco_radar.geraete_config import lade_katalog

WURZEL = Path(__file__).resolve().parents[1]
BASIS = "https://www.o2online.de/e-shop/samsung/samsung-galaxy-s25-ultra-256gb-"
FRAGE = "?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36&tarif=o2-mobile-l"
ERNEUERT = f"{BASIS}titanium-silverblue-erneuert-details{FRAGE}"
NEU = f"{BASIS}titanium-gray-details{FRAGE}"


@pytest.fixture
def wurzel(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    for name in ("geraete_quellen.yaml", "geraete_katalog.yaml"):
        shutil.copy(WURZEL / "config" / name, tmp_path / "config" / name)
    hand = {"anbieter": [{"schluessel": "o2", "name": "o2", "seiten": []}]}
    (tmp_path / "config" / "klick_tageslauf.yaml").write_text(
        yaml.safe_dump(hand), encoding="utf-8"
    )
    return tmp_path


def _bestand(wurzel: Path, buendel: list[dict]) -> None:
    pfad = wurzel / "data" / "state" / "geraete_tco.json"
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps({"buendel": buendel}), encoding="utf-8")


def _satz(sku: str, url: str, zustand: str) -> dict:
    return {"anbieter": "o2", "sku_id": sku, "quelle_url": url, "zustand": zustand}


def test_erneuertes_buendel_liefert_keine_seite(wurzel):
    _bestand(
        wurzel,
        [
            _satz(
                "samsung-galaxy-s25-ultra-256gb-titan-blau-refurbished",
                ERNEUERT,
                "refurbished",
            ),
            _satz("samsung-galaxy-s25-ultra-256gb-titan-grau", NEU, "neu"),
        ],
    )

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert [s.url for s in seiten if s.geraet == "samsung-galaxy-s25-ultra"] == [NEU]


def test_gegenprobe_nur_erneuert_heisst_keine_seite(wurzel):
    _bestand(
        wurzel,
        [
            _satz(
                "samsung-galaxy-s25-ultra-256gb-titan-blau-refurbished",
                ERNEUERT,
                "refurbished",
            )
        ],
    )

    assert leite_ab(wurzel, lade_katalog(wurzel), set()) == []


def test_gegenprobe_neuware_ohne_zustandsfeld_bleibt(wurzel):
    """Bündel vor dem Zustandsfeld zählen als Neuware (wie ``seite_zustand``)."""
    satz = _satz("samsung-galaxy-s25-ultra-256gb-titan-grau", NEU, "neu")
    del satz["zustand"]
    _bestand(wurzel, [satz])

    seiten = leite_ab(wurzel, lade_katalog(wurzel), set())

    assert [s.url for s in seiten] == [NEU]
