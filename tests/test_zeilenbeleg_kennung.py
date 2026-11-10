"""Zeilenbeleg über die Kennung der Messung im Bildnamen (Live-Abnahme 10.11.2026).

Das Manifest trug 318 Bilder vom 10.11., die Seite 0 Zeilen mit Bild: das neueste Bild
hatte keinen Satz vom selben Tag im Bestand (der Klick-Lauf war später als der
Geräte-Lauf), und bei gleich teuren Positionen riet die Seite nicht. Die Kennung im
Namen (erste 16 Zeichen der ``beleg_id``, ein Hash von Screenshot und Mitschnitt)
nennt die Position genau; ein älteres Bild gilt nur, wenn seine eigene Messung im
Bestand liegt, nie als Ersatz für eine andere.
"""

from __future__ import annotations

import test_beleg_position as basis
from bestand_pfad import lese_wurzel

from telco_radar.beleg_regeln import KENNUNG_LAENGE, folge_dateiname
from telco_radar.geraete_config import lade_katalog
from telco_radar.report import geraete_zeilenbelege as zeilen

MODELL = basis.MODELL
ORANGE = "apple-iphone-17-pro-256gb-orange"


def _bild(anbieter_id: str, beleg_id: str, tag=basis.TAG) -> dict:
    name = folge_dateiname(MODELL, anbieter_id, tag, "preis", beleg_id)
    return {
        "datum": tag.isoformat(),
        "gross": False,
        "url": f"https://example.de/belege-{tag.isoformat()}/{name}",
        "bildfolge": [],
    }


def _index(saetze, bilder):
    return zeilen.baue_index(saetze, bilder, lade_katalog(lese_wurzel()))


def _telekom(beleg_id, tag=basis.HEUTE, **extra):
    satz = basis._satz("Telekom", "MagentaMobil S", "tk:klein", 24, 12.0, beleg_id)
    return {**satz, "abgerufen_am": tag, **extra}


def test_gleich_teure_positionen_werden_ueber_die_kennung_eindeutig():
    """Zwei gleich teure Telekom-Sätze: früher kein Bild (Gleichstand), jetzt genau
    der Satz, dessen Kennung im Bildnamen steht, und nur er."""
    saetze = [
        _telekom(basis.ID_TK_1),
        _telekom(basis.ID_TK_2, sku_id=ORANGE),
    ]
    schluessel = (MODELL, "telekom")
    index, gruende = _index(saetze, {schluessel: [_bild("telekom", basis.ID_TK_2)]})
    assert list(index) == [basis.ID_TK_2]
    assert index[basis.ID_TK_2].sku_id == ORANGE
    assert gruende == {}


def test_aelteres_bild_gilt_nur_zur_eigenen_messung():
    """Das neueste Bild (Klick-Lauf nach dem Geräte-Lauf) hat noch keinen Satz im
    Bestand: die Zeile zeigt das Bild von gestern, zu dem ihre Messung gehört."""
    saetze = [_telekom(basis.ID_TK_1, tag=basis.GESTERN.isoformat())]
    neu = _bild("telekom", "9" * 64)
    alt = _bild("telekom", basis.ID_TK_1, tag=basis.GESTERN)
    index, gruende = _index(saetze, {(MODELL, "telekom"): [neu, alt]})
    assert list(index) == [basis.ID_TK_1]
    assert index[basis.ID_TK_1].datum == basis.GESTERN.isoformat()
    assert gruende == {}


def test_unbekannte_kennung_und_fremdes_paar_geben_kein_bild():
    """Gegenprobe: eine Kennung ohne Satz im Paar bleibt ohne Zeilenbild, auch wenn
    sie in einem anderen Paar vorkommt; der Grund wird genannt."""
    saetze = [
        _telekom(basis.ID_TK_1),
        basis._satz("o2", "O2 Mobile Klein", "o2:klein", 24, 18.0, basis.ID_O2),
    ]
    bilder = {
        (MODELL, "telekom"): [_bild("telekom", basis.ID_O2)],
        (MODELL, "o2"): [_bild("o2", "8" * 64)],
    }
    index, gruende = _index(saetze, bilder)
    assert index == {}
    assert set(gruende.values()) == {zeilen.GRUND_KENNUNG_FEHLT}
    assert len(gruende) == 2
    assert KENNUNG_LAENGE == 16
