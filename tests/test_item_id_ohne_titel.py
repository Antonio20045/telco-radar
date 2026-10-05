"""Abnahme T2: ein Item ohne URL und ohne ID bekommt keine ID aus dem Titel."""

from __future__ import annotations

import hashlib
import json

import pytest
from bestand_pfad import BERICHTE

from telco_radar.models import Item

AUSGABE = "2026-10-02.json"
ADSLZONE_NORMAL = (
    "https://adslzone.net/noticias/operadores/"
    "diferencia-velocidad-fibra-1gbps-movistar-orange-digi"
)
GESPEICHERTE_ID = "4ff7e2502a8ec8db"


def _meldungen() -> list[dict]:
    """Die Höhepunkte der Ausgabe 2026-10-02 mit Titel und URL."""
    bericht = json.loads((BERICHTE / AUSGABE).read_text(encoding="utf-8"))
    return [
        meldung
        for region in bericht["regions"].values()
        for meldung in region.get("highlights", [])
        if meldung.get("title") and meldung.get("url")
    ]


def _erste() -> dict:
    meldungen = _meldungen()
    assert meldungen, "die Ausgabe 2026-10-02 hat keine Höhepunkte mit Titel und URL"
    return meldungen[0]


def _hash(basis: str) -> str:
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def test_item_ohne_url_und_id_scheitert_statt_id_aus_dem_titel() -> None:
    meldung = _erste()
    try:
        item = Item(title=meldung["title"], url="", source_name=meldung["source"])
    except ValueError:
        return
    pytest.fail(
        f"Item ohne URL und ohne ID bekam die ID aus dem Titel ({item.id}) "
        "statt eines ValueError"
    )


def test_from_dict_ohne_url_und_id_gibt_den_fehler_weiter() -> None:
    meldung = _erste()
    try:
        item = Item.from_dict({"title": meldung["title"], "source_name": "ADSLZone"})
    except ValueError:
        return
    pytest.fail(
        "Item.from_dict ohne URL und ohne ID bildete die ID aus dem Titel "
        f"({item.id}) statt eines ValueError"
    )


def test_url_ergibt_dieselbe_id_wie_vorher() -> None:
    meldung = _erste()
    erwartet = _hash(ADSLZONE_NORMAL)
    item = Item(title=meldung["title"], url=meldung["url"], source_name="ADSLZone")
    assert item.id == erwartet
    mit_tracking = Item(
        title="anderer Titel",
        url=meldung["url"] + "?utm_source=feed",
        source_name="ADSLZone",
    )
    assert mit_tracking.id == erwartet
    assert len(item.id) == 16


def test_alle_meldungen_haben_die_id_ihrer_url() -> None:
    for meldung in _meldungen():
        item = Item(title=meldung["title"], url=meldung["url"], source_name="x")
        gegenprobe = Item(title="", url=meldung["url"], source_name="y")
        assert item.id == gegenprobe.id
        assert item.id != _hash(" ".join(meldung["title"].split()).lower())


def test_from_dict_behaelt_gespeicherte_id_auch_ohne_url() -> None:
    meldung = _erste()
    item = Item.from_dict({"title": meldung["title"], "url": "", "id": GESPEICHERTE_ID})
    assert item.id == GESPEICHERTE_ID
    mit_url = Item.from_dict(
        {"title": meldung["title"], "url": meldung["url"], "id": GESPEICHERTE_ID}
    )
    assert mit_url.id == GESPEICHERTE_ID


def test_gleicher_titel_verschiedene_urls_ergibt_zwei_ids() -> None:
    meldungen = _meldungen()
    assert len(meldungen) >= 2
    titel = meldungen[0]["title"]
    erste = Item(title=titel, url=meldungen[0]["url"], source_name="a")
    zweite = Item(title=titel, url=meldungen[1]["url"], source_name="b")
    assert erste.id != zweite.id
