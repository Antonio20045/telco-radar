"""Wegeverzeichnis: `erfassung` je Anbieter stimmt mit der Wirklichkeit überein.

Umbauplan „Eine Methode für alle Anbieter“, Schritt 1. Das Feld in
config/geraete_quellen.yaml beschreibt nur; die Wirklichkeit steckt in der
Adapter-Registry (`register.py`, `aktiv`, Einstiege) und in der Klick-Tagesdatei
(config/klick_tageslauf.yaml samt Karte). Wer einen Weg hinzufügt, abschaltet
oder einen Anbieter in einen Weg aufnimmt, ohne das Verzeichnis zu pflegen,
macht diesen Test rot.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

from telco_radar.collect import geraete
from telco_radar.collect.geraete.klickziele import geplante_anbieter
from telco_radar.geraete_config import lade_quellen
from telco_radar.geraete_felder import ERFASSUNG_UNBEKANNT, ERFASSUNGEN
from telco_radar.geraete_model import normalisiere

WURZEL = Path(__file__).resolve().parents[1]


def erwartete_erfassung(adapter_liest: bool, liefert_buendel: bool, klick: bool) -> str:
    """Der Weg, der aus den Tatsachen folgt (die einzige Ableitungsregel)."""
    if adapter_liest and klick:
        return "adapter+klick"
    if klick:
        return "klick"
    if adapter_liest:
        return "adapter" if liefert_buendel else "barpreis"
    return "aus"


def _tatsachen(anbieter, klick_namen: set) -> tuple:
    adapter = geraete.ADAPTER.get(anbieter.methode)
    liest = adapter is not None and anbieter.crawlbar
    buendel = adapter is not None and adapter.lies_buendel is not None
    return liest, buendel, normalisiere(anbieter.name) in klick_namen


@pytest.fixture(scope="module")
def quellen():
    return lade_quellen(WURZEL)


@pytest.fixture(scope="module")
def klick_namen():
    namen = geplante_anbieter(WURZEL)
    assert namen, "config/klick_tageslauf.yaml nennt keinen Anbieter mit Karte"
    return {normalisiere(n) for n in namen}


def test_ableitung_deckt_jeden_weg_ab():
    assert erwartete_erfassung(True, True, True) == "adapter+klick"
    assert erwartete_erfassung(True, True, False) == "adapter"
    assert erwartete_erfassung(True, False, False) == "barpreis"
    assert erwartete_erfassung(False, False, True) == "klick"
    assert erwartete_erfassung(False, True, False) == "aus"
    assert set(ERFASSUNGEN) == {"adapter", "klick", "adapter+klick", "barpreis", "aus"}


def test_jeder_anbieter_hat_einen_gueltigen_weg(quellen):
    ohne = [a.name for a in quellen.anbieter if a.erfassung not in ERFASSUNGEN]
    assert not ohne, f"erfassung fehlt oder ist ungültig bei {ohne}"


def test_wegeverzeichnis_stimmt_mit_registry_und_klick_tagesdatei(quellen, klick_namen):
    abweichungen = []
    for a in quellen.anbieter:
        soll = erwartete_erfassung(*_tatsachen(a, klick_namen))
        if a.erfassung != soll:
            abweichungen.append(
                f"{a.name}: Verzeichnis {a.erfassung!r}, Wirklichkeit {soll!r}"
            )
    assert not abweichungen, "Wegeverzeichnis pflegen: " + "; ".join(abweichungen)


def test_jeder_klick_anbieter_steht_im_verzeichnis(quellen, klick_namen):
    bekannt = {a.schluessel for a in quellen.anbieter}
    fehlt = sorted(klick_namen - bekannt)
    assert not fehlt, (
        f"Klick-Tagesdatei nennt Anbieter ohne Eintrag in geraete_quellen: {fehlt}"
    )


def test_jede_tagesdatei_zeile_hat_einen_klick_weg_im_verzeichnis(quellen):
    roh = yaml.safe_load(
        (WURZEL / "config" / "klick_tageslauf.yaml").read_text("utf-8")
    )
    namen = {normalisiere(str(e["name"])) for e in roh["anbieter"]}
    for a in quellen.anbieter:
        if a.schluessel in namen:
            assert "klick" in a.erfassung, (
                f"{a.name} hat Klick-Jobs, erfassung={a.erfassung!r}"
            )


def test_aktiver_adapter_ist_nicht_aus(quellen):
    for a in quellen.crawlbare:
        if a.methode in geraete.ADAPTER:
            assert a.erfassung != "aus", f"{a.name} wird per Adapter gelesen"


def test_gegenprobe_neuer_weg_ohne_pflege_wird_erkannt(quellen, klick_namen):
    """Ein Anbieter, der „aus“ führt, aber einen Klick-Job bekommt, fällt auf."""
    a = next(x for x in quellen.anbieter if x.erfassung == "aus")
    soll = erwartete_erfassung(*_tatsachen(a, klick_namen | {a.schluessel}))
    assert soll != a.erfassung


def test_loader_fuehrt_fehlende_und_falsche_angabe_als_unbekannt(tmp_path, caplog):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "geraete_quellen.yaml").write_text(
        "anbieter:\n"
        "  - {name: A, erfassung: klick}\n"
        "  - {name: B}\n"
        "  - {name: C, erfassung: magie}\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING):
        a, b, c = lade_quellen(tmp_path).anbieter
    assert (a.erfassung, b.erfassung, c.erfassung) == (
        "klick",
        ERFASSUNG_UNBEKANNT,
        ERFASSUNG_UNBEKANNT,
    )
    assert "magie" in caplog.text
