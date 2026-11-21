"""Vodafone: was die Produktseite nicht anbietet, wird kein Bündel (21.11.2026).

Befund (Beleg ``docs/belege/vodafone-tarife-ml-2111/``): Die Tarifschnittstelle
``glados/v2/tariff/v2/hardware`` nennt je Gerät Mobil XS, S, M, L und XL. Die
Produktseite fragt dieselbe Schnittstelle aber nur mit ``virtualItemId=267,268,271``
(XS, S, XL) ab, denn ihr eigener Skriptblock ``additionalPageOptions.
bntPromoHiddenSubscriptions.consumer`` blendet ``269`` (Mobil M) und ``270``
(Mobil L) für Neuverträge aus. Die Schnittstelle selbst trägt kein Merkmal dafür
(gleiche Felder, ``salesChannel`` Online.Consumer bei allen). Gefiltert wird darum
über die Tarif-ID der Seite, nie über den Namen.

Fixtures: echte Abrufe vom 21.11.2026, Samsung Galaxy A17 5G (``hardwareId``
57459): Tarifantwort ohne FamilyCard S/M/L, Detailantwort, Produktseite gekürzt
auf die zwei Skriptblöcke.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from telco_radar.collect.geraete import vodafone as vodafone_modul
from telco_radar.collect.geraete.vodafone import lies_buendel, loese_tarifnamen
from telco_radar.collect.geraete.vodafone_sicht import (
    UEBERSICHT,
    UNGEPRUEFT,
    ausgeblendete_tarife,
    nicht_geprueft,
)

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_SEITE = "https://www.vodafone.de/privat/handys/samsung-galaxy-a17-5g.html"
_MOBIL = {"Mobil XS", "Mobil S", "Mobil M", "Mobil L", "Mobil XL"}


def _text(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


def _seite() -> str:
    return _text("vodafone_produktseite_a17_20261121.html")


def _tarifantwort() -> str:
    return _text("vodafone_tarif_hardware_a17_20261121.json")


def _seite_ohne_ausblendung() -> str:
    """Gegenprobe: dieselbe Seite ohne den Ausblende-Block (so sah sie vor der
    Aktion aus; der Block heißt ``bntPromo…``, ist also befristet)."""
    seite = _seite()
    anfang = seite.index('"bntPromoHiddenSubscriptions"')
    ende = seite.index("},", anfang) + 2
    return seite[:anfang] + seite[ende:]


def _vorschau() -> list[dict]:
    return [
        {
            **s,
            "anbieter": "Vodafone",
            "sku_id": f"a17-{s['sku']}",
            "zustand": "neu",
            "quelle_url": s["url"],
        }
        for s in lies_buendel(_text("vodafone_virtualitem_a17_20261121.json"))
    ]


def _hole(seite: str | None, tarifantwort: str):
    aufrufe: list[str] = []

    def hole(url, kopfzeilen=None, **_):
        aufrufe.append(url)
        if url.startswith("https://api.vodafone.de/"):
            return 200, tarifantwort
        if seite is None:
            return 404, "nicht gefunden"
        return 200, seite

    return hole, aufrufe


def _paare(rohbuendel: list[dict]) -> set[tuple[str, int]]:
    return {(s["tarif_name"], s["laufzeit_monate"]) for s in rohbuendel}


@pytest.fixture(autouse=True)
def _ohne_wartezeit(monkeypatch):
    monkeypatch.setattr(vodafone_modul, "_TARIF_RATE_LIMIT", 0.0)


def test_die_seite_blendet_mobil_m_und_l_aus():
    assert ausgeblendete_tarife(_seite()) == frozenset({"269", "270"})


def test_young_und_soho_zaehlen_nicht_fuer_den_onlinekanal():
    """``young: ['140','141']`` und ``soho: ['270']`` stehen im selben Block; der
    Adapter fragt ``salesChannel=Online.Consumer``, also gilt nur ``consumer``."""
    assert "140" not in ausgeblendete_tarife(_seite())


def test_seite_ohne_ausblendung_blendet_nichts_aus():
    assert ausgeblendete_tarife(_seite_ohne_ausblendung()) == frozenset()


def test_die_tarifuebersicht_schreibt_tariff_ids():
    """Die Übersicht hat nur einen Kanal: ``tariffIds: ['269','270']``."""
    uebersicht = _text("vodafone_tarifuebersicht_20261121.html")
    assert ausgeblendete_tarife(uebersicht) == frozenset({"269", "270"})


def test_unverstandene_seite_ist_unbekannt_nicht_leer():
    assert ausgeblendete_tarife(_tarifantwort()) is None
    assert ausgeblendete_tarife("") is None


def test_ausgeblendete_tarife_werden_keine_buendel():
    rohbuendel = _vorschau()
    hole, aufrufe = _hole(_seite(), _tarifantwort())
    loese_tarifnamen(hole, {}, rohbuendel)
    namen = {s["tarif_name"] for s in rohbuendel}
    assert namen & _MOBIL == {"Mobil XS", "Mobil S", "Mobil XL"}
    assert {"Mobil M", "Mobil L"}.isdisjoint(namen)
    for tarif in ("Mobil XS", "Mobil S", "Mobil XL"):
        for laufzeit in (12, 24, 36):
            assert (tarif, laufzeit) in _paare(rohbuendel)
    assert [a for a in aufrufe if not a.startswith("https://api.")] == [UEBERSICHT]


def test_gegenprobe_ohne_ausblendung_bleiben_alle_fuenf_stufen():
    rohbuendel = _vorschau()
    hole, _ = _hole(_seite_ohne_ausblendung(), _tarifantwort())
    loese_tarifnamen(hole, {}, rohbuendel)
    assert {s["tarif_name"] for s in rohbuendel} & _MOBIL == _MOBIL


def test_der_betrag_eines_sichtbaren_tarifs_bleibt_unveraendert():
    """Mobil XL, 36 Monate, gegen die rohe Antwort: der Filter nimmt weg, er
    rechnet nicht um (Hash und Gerätrate wörtlich aus der Komposition)."""
    roh = json.loads(_tarifantwort())
    xl = next(t for t in roh["data"][0]["tariffs"] if t["virtualItemId"] == "271")
    komposition = next(
        k
        for a in xl["atomics"]
        for k in a["prices"]["composition"]
        if k.get("financingDuration") == 36
    )
    rohbuendel = _vorschau()
    hole, _ = _hole(_seite(), _tarifantwort())
    loese_tarifnamen(hole, {}, rohbuendel)
    satz = next(
        s
        for s in rohbuendel
        if s["tarif_name"] == "Mobil XL" and s["laufzeit_monate"] == 36
    )
    assert satz["tarif_slug"] == komposition["offerCoreHash"]
    assert satz["geraet_monatsrate"] == 5.5
    assert (
        komposition["priceByComponent"]["hardware"]["priceByType"]["rate"]["month"][
            "withoutDiscounts"
        ]["gross"]
        == 5.5
    )


def test_vorschau_mit_ausgeblendetem_tarif_faellt_auch_im_hash_rueckfall():
    """Fehlt die Variante in der Tarifantwort, bleibt ihre Vorschau und bekommt
    den Namen über den Hash. Die Vorschau trägt Mobil M mit 24 Monaten; dieser
    Satz darf über den Rückfall nicht wieder hereinkommen."""
    fremd = _tarifantwort().replace('"hardwareId": "57459"', '"hardwareId": "99999"')
    assert fremd != _tarifantwort()
    ohne = _vorschau()
    hole, _ = _hole(_seite_ohne_ausblendung(), fremd)
    loese_tarifnamen(hole, {}, ohne)
    assert "Mobil M" in {s["tarif_name"] for s in ohne}

    mit = _vorschau()
    hole, _ = _hole(_seite(), fremd)
    loese_tarifnamen(hole, {}, mit)
    assert "Mobil M" not in {s["tarif_name"] for s in mit}
    assert {"Mobil XS", "Mobil S"} <= {s["tarif_name"] for s in mit}


def _zwei_geraete():
    zweite = "https://www.vodafone.de/privat/handys/zweites-geraet.html"
    rohbuendel = _vorschau() + [
        {**s, "sku": "57460", "sku_id": "zweites-57460", "url": zweite}
        for s in _vorschau()
    ]
    return rohbuendel, _tarifantwort().replace(
        '"hardwareId": "57459"', '"hardwareId": "57460"'
    )


def _hole_zwei(andere_antwort: str, seiten: dict):
    seitenabrufe: list[str] = []

    def hole(url, kopfzeilen=None, **_):
        if url.startswith("https://api.vodafone.de/"):
            return 200, andere_antwort if "57460" in url else _tarifantwort()
        seitenabrufe.append(url)
        return seiten.get(url, (404, ""))

    return hole, seitenabrufe


def test_die_ausblendung_wird_einmal_je_lauf_gelesen():
    """Zwei Geräte, ein Seitenabruf: die Tarifübersicht. Sie gilt für beide."""
    rohbuendel, andere = _zwei_geraete()
    uebersicht = (200, _text("vodafone_tarifuebersicht_20261121.html"))
    hole, seitenabrufe = _hole_zwei(andere, {UEBERSICHT: uebersicht})
    loese_tarifnamen(hole, {}, rohbuendel)
    assert seitenabrufe == [UEBERSICHT]
    for sku in ("57459", "57460"):
        namen = {s["tarif_name"] for s in rohbuendel if s["sku"] == sku}
        assert namen & _MOBIL == {"Mobil XS", "Mobil S", "Mobil XL"}, sku
    assert nicht_geprueft(rohbuendel) == []


def test_scheitert_die_uebersicht_gilt_die_erste_produktseite():
    rohbuendel, andere = _zwei_geraete()
    hole, seitenabrufe = _hole_zwei(
        andere, {UEBERSICHT: (503, ""), _SEITE: (200, _seite())}
    )
    loese_tarifnamen(hole, {}, rohbuendel)
    assert len(seitenabrufe) == 2 and seitenabrufe[0] == UEBERSICHT
    assert _SEITE in seitenabrufe
    zweites = {s["tarif_name"] for s in rohbuendel if s["sku"] == "57460"}
    assert zweites & _MOBIL == {"Mobil XS", "Mobil S", "Mobil XL"}


def test_ohne_jede_gelesene_seite_bleibt_alles_und_das_protokoll_sagt_es(caplog):
    """Keine Seite lesbar: welche Tarife die Seite zeigt, ist unbekannt. Dann
    bleibt der alte Stand (alle Tarife der Schnittstelle) - ein Ausfall von
    www.vodafone.de darf nicht die ganze eigene Referenz kosten -, aber nicht
    still."""
    rohbuendel = _vorschau()
    hole, _ = _hole(None, _tarifantwort())
    with caplog.at_level(logging.WARNING, logger=vodafone_modul.log.name):
        loese_tarifnamen(hole, {}, rohbuendel)
    assert {s["tarif_name"] for s in rohbuendel} & _MOBIL == _MOBIL
    assert "Sichtbarkeit unbekannt" in caplog.text
    assert all(s[UNGEPRUEFT] for s in rohbuendel)
    assert nicht_geprueft(rohbuendel) == ["Vodafone"]


def test_gegenprobe_gelesene_seite_kennzeichnet_nichts():
    rohbuendel = _vorschau()
    hole, _ = _hole(_seite(), _tarifantwort())
    loese_tarifnamen(hole, {}, rohbuendel)
    assert not any(UNGEPRUEFT in s for s in rohbuendel)
