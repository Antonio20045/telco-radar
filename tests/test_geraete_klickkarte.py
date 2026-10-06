"""Klick-Karte je Anbieter (Datenkonzept Geräteradar, Abschnitt 8, Schritt 4).

Die Karte sagt dem Klick-Crawler, welche Knöpfe Speicher, Tarif und Ratenlaufzeit
wählen, wo die Preiszusammenfassung steht, welche Antwort er mitschneidet und welcher
Kanarienwert gilt. Ändert ein Anbieter seine Seite, ändert sich nur die Karte. Eine
unvollständige Karte darf nicht still als leerer Lauf enden: jedes fehlende
Pflichtfeld wirft ``KlickkartenFehler`` und nennt das Feld.

Die Karte hier ist ein Beispiel, kein echter Anbieter.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

BEISPIEL = {
    "anbieter": "Beispielanbieter",
    "knoepfe": {
        "speicher": {"selektor": "#speicher button", "wert": "data-wert"},
        "tarif": {"selektor": "#tarif button", "wert": "data-wert"},
        "laufzeit": {"selektor": "#laufzeit button"},
        "gewaehlt": {"attribut": "aria-pressed", "wert": "true"},
    },
    "zusammenfassung": {"selektor": "#preis"},
    "antwort": {
        "url_muster": r"/api/preis\?",
        "pfade": {
            "anzahlung": "preis.anzahlung",
            "rate": "preis.rate",
            "ratenzahl": "preis.raten",
            "tarifphasen": {
                "liste": "tarif.phasen",
                "von": "ab",
                "bis": "bis",
                "betrag": "betrag",
            },
            "tarifbindung": "tarif.mindestlaufzeit",
            "anschluss": "tarif.anschluss",
            "volumen_gb": "tarif.volumen_gb",
        },
        "variante": {"speicher": "auswahl.speicher", "laufzeit": "auswahl.laufzeit"},
    },
    "kanarie": {"selektor": "#kanarie", "enthaelt": "Beispielhandy X"},
}

PFLICHTFELDER = (
    "anbieter",
    "knoepfe.speicher.selektor",
    "knoepfe.tarif.selektor",
    "knoepfe.laufzeit.selektor",
    "knoepfe.gewaehlt.attribut",
    "knoepfe.gewaehlt.wert",
    "zusammenfassung.selektor",
    "antwort.url_muster",
    "antwort.pfade",
    "kanarie.selektor",
    "kanarie.enthaelt",
)


def _schreibe(ordner: Path, daten: object) -> Path:
    pfad = ordner / "karte.yaml"
    pfad.write_text(yaml.safe_dump(daten, allow_unicode=True), encoding="utf-8")
    return pfad


def _mit(pfad: str, wert: object) -> dict:
    daten = copy.deepcopy(BEISPIEL)
    *weg, letztes = pfad.split(".")
    knoten = daten
    for teil in weg:
        knoten = knoten[teil]
    if wert is None:
        del knoten[letztes]
    else:
        knoten[letztes] = wert
    return daten


def test_beispielkarte_liest_alle_teile(tmp_path):
    from telco_radar.collect.geraete.klickkarte import Phasenpfad, lade_klickkarte

    karte = lade_klickkarte(_schreibe(tmp_path, BEISPIEL))

    assert karte.anbieter == "Beispielanbieter"
    assert karte.knoepfe["speicher"].selektor == "#speicher button"
    assert karte.knoepfe["speicher"].wert_attribut == "data-wert"
    assert karte.knoepfe["laufzeit"].wert_attribut is None
    assert (karte.gewaehlt.attribut, karte.gewaehlt.wert) == ("aria-pressed", "true")
    assert karte.zusammenfassung == "#preis"
    assert karte.antwort.pfade["rate"] == "preis.rate"
    assert karte.antwort.pfade["tarifphasen"] == Phasenpfad(
        liste="tarif.phasen", von="ab", bis="bis", betrag="betrag"
    )
    assert dict(karte.antwort.variante) == {
        "speicher": "auswahl.speicher",
        "laufzeit": "auswahl.laufzeit",
    }
    assert (karte.kanarie.selektor, karte.kanarie.enthaelt) == (
        "#kanarie",
        "Beispielhandy X",
    )


def test_url_muster_trifft_nur_die_preisantwort(tmp_path):
    from telco_radar.collect.geraete.klickkarte import lade_klickkarte

    karte = lade_klickkarte(_schreibe(tmp_path, BEISPIEL))

    assert karte.antwort.passt("https://beispiel.invalid/api/preis?speicher=128")
    assert not karte.antwort.passt("https://beispiel.invalid/api/preisliste")
    assert not karte.antwort.passt("https://beispiel.invalid/handy/x")


def test_dimensionen_und_wertfelder_sind_benannt():
    from telco_radar.collect.geraete.klickkarte import DIMENSIONEN, WERTFELDER

    assert DIMENSIONEN == ("speicher", "tarif", "laufzeit")
    assert WERTFELDER == (
        "anzahlung",
        "rate",
        "ratenzahl",
        "tarifphasen",
        "tarifbindung",
        "anschluss",
        "volumen_gb",
    )


@pytest.mark.parametrize("feld", PFLICHTFELDER)
def test_fehlendes_pflichtfeld_wirft_benannte_ausnahme(tmp_path, feld):
    from telco_radar.collect.geraete.klickkarte import (
        KlickkartenFehler,
        lade_klickkarte,
    )

    pfad = _schreibe(tmp_path, _mit(feld, None))

    with pytest.raises(KlickkartenFehler) as fehler:
        lade_klickkarte(pfad)

    assert fehler.value.feld == feld
    assert feld in str(fehler.value)
    assert str(pfad) in str(fehler.value)


@pytest.mark.parametrize(
    ("feld", "wert"),
    [
        ("knoepfe.tarif.selektor", "   "),
        ("kanarie.enthaelt", ""),
        ("antwort.pfade", {}),
        ("knoepfe.speicher", "#speicher button"),
    ],
)
def test_leerer_oder_falsch_geformter_wert_zaehlt_als_fehlend(tmp_path, feld, wert):
    from telco_radar.collect.geraete.klickkarte import (
        KlickkartenFehler,
        lade_klickkarte,
    )

    with pytest.raises(KlickkartenFehler) as fehler:
        lade_klickkarte(_schreibe(tmp_path, _mit(feld, wert)))

    assert fehler.value.feld.startswith(feld)


@pytest.mark.parametrize(
    ("feld", "wert", "gemeldet"),
    [
        ("antwort.pfade.rabatt", "preis.rabatt", "antwort.pfade.rabatt"),
        ("antwort.variante.farbe", "auswahl.farbe", "antwort.variante.farbe"),
        ("antwort.url_muster", "/api/(preis", "antwort.url_muster"),
        (
            "antwort.pfade.tarifphasen",
            {"liste": "tarif.phasen", "von": "ab", "bis": "bis"},
            "antwort.pfade.tarifphasen.betrag",
        ),
        ("knoepfe.farbe", {"selektor": "#farbe button"}, "knoepfe.farbe"),
    ],
)
def test_unbekanntes_oder_kaputtes_feld_wirft(tmp_path, feld, wert, gemeldet):
    from telco_radar.collect.geraete.klickkarte import (
        KlickkartenFehler,
        lade_klickkarte,
    )

    with pytest.raises(KlickkartenFehler) as fehler:
        lade_klickkarte(_schreibe(tmp_path, _mit(feld, wert)))

    assert fehler.value.feld == gemeldet


@pytest.mark.parametrize("text", ["- nur\n- eine Liste\n", "anbieter: [offen\n", ""])
def test_karte_ohne_zuordnung_wirft(tmp_path, text):
    from telco_radar.collect.geraete.klickkarte import (
        KlickkartenFehler,
        lade_klickkarte,
    )

    pfad = tmp_path / "karte.yaml"
    pfad.write_text(text, encoding="utf-8")

    with pytest.raises(KlickkartenFehler):
        lade_klickkarte(pfad)


def test_ungequoteter_wahrheitswert_bleibt_attributtext(tmp_path):
    from telco_radar.collect.geraete.klickkarte import lade_klickkarte

    pfad = tmp_path / "karte.yaml"
    text = yaml.safe_dump(BEISPIEL, allow_unicode=True).replace(
        "wert: 'true'", "wert: true"
    )
    assert "wert: true" in text
    pfad.write_text(text, encoding="utf-8")

    assert lade_klickkarte(pfad).gewaehlt.wert == "true"


def test_tarifphasen_als_einfacher_pfad(tmp_path):
    from telco_radar.collect.geraete.klickkarte import lade_klickkarte

    daten = _mit("antwort.pfade.tarifphasen", "tarif.preis")

    karte = lade_klickkarte(_schreibe(tmp_path, daten))

    assert karte.antwort.pfade["tarifphasen"] == "tarif.preis"
