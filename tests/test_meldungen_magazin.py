"""Die Meldungsseite als Magazin (Antonio, 10.10.2026).

`meldungen_seite.ausgabe()` verteilt die Woche auf die Positionen der
Seite. Zugesichert wird, was die Seite verspricht: jede Meldung genau
einmal, der Aufmacher mit grossem Bild, Deutschland nach Watchlist-Land,
keine Zahl der Meldungen im Kopf.
"""

from __future__ import annotations

from types import SimpleNamespace

from bs4 import BeautifulSoup

from telco_radar.report import meldungen_seite
from telco_radar.report.bilder import MIND_BREITE_GROSS


def _h(i: int, relevance: int, ressort: str = "netz", image_w: int = 0, operator=None):
    return {
        "id": f"h{i}",
        "url": f"https://example.com/{i}",
        "schlagzeile": f"Meldung {i}",
        "relevance": relevance,
        "ressort": ressort,
        "ressort_label": ressort.title(),
        "operator": operator or f"Betreiber {i}",
        "image": f"{i}.jpg" if image_w else None,
        "image_w": image_w or None,
    }


def _cfg(*deutsche):
    ops = [
        SimpleNamespace(name=n, aliases=[n.split()[0]], country="DE") for n in deutsche
    ]
    ops.append(SimpleNamespace(name="Orange", aliases=[], country="FR"))
    return SimpleNamespace(operators=ops)


def _alle(a: dict) -> list[dict]:
    teile = ["links", "unter", "rechts", "reihe", "strom", "deutschland"]
    return [a["aufmacher"]] + [h for t in teile for h in a[t]]


def test_jede_meldung_steht_genau_einmal():
    hs = [
        _h(i, 5 - i % 4, ("netz", "tarife", "geld")[i % 3], (0, 500, 1200)[i % 3])
        for i in range(40)
    ]
    hs[7]["operator"] = "Deutsche Telekom"
    a = meldungen_seite.ausgabe({"highlights": hs}, _cfg("Deutsche Telekom"))
    verteilt = _alle(a)
    assert len(verteilt) == len(hs)
    assert {id(h) for h in verteilt} == {id(h) for h in hs}


def test_aufmacher_braucht_ein_grosses_bild():
    hs = [_h(1, 5, image_w=500), _h(2, 5, image_w=MIND_BREITE_GROSS), _h(3, 4)]
    a = meldungen_seite.ausgabe({"highlights": hs}, None)
    assert a["aufmacher"] is hs[1]
    ohne = meldungen_seite.ausgabe({"highlights": [_h(1, 3)]}, None)
    assert ohne["aufmacher"]["id"] == "h1", "ohne grosses Bild fuehrt die erste"


def test_deutschland_folgt_dem_land_der_watchlist():
    hs = [
        _h(1, 5, operator="Deutsche Telekom"),
        _h(2, 4, operator="Deutsche"),
        _h(3, 5, operator="Orange"),
    ]
    a = meldungen_seite.ausgabe({"highlights": hs}, _cfg("Deutsche Telekom"))
    assert a["deutschland"] == hs[:2], "Name und Alias zaehlen"
    assert hs[2] not in a["deutschland"]
    assert meldungen_seite.ausgabe({"highlights": hs}, None)["deutschland"] == []


def test_schwerpunkt_zuerst_das_thema_mit_den_meisten_wichtigen():
    hs = (
        [_h(i, 5, "tarife", 1200) for i in range(4)]
        + [_h(10 + i, 4, "geld") for i in range(3)]
        + [_h(20 + i, 2, "netz") for i in range(5)]
        + [_h(30 + i, 5, "partner") for i in range(2)]
    )
    a = meldungen_seite.ausgabe({"highlights": hs}, None)
    keys = [s["key"] for s in a["schwerpunkte"]]
    assert keys == ["geld", "netz", "tarife"], (
        "Aufmacher-Thema zuletzt, unter drei faellt weg"
    )
    assert all(
        len(s["meldungen"]) <= meldungen_seite.SCHWERPUNKT_TIEFE
        for s in a["schwerpunkte"]
    )


def test_kalenderwoche_aus_dem_ausgabedatum():
    assert meldungen_seite.kalenderwoche("2026-10-09") == 41
    assert meldungen_seite.kalenderwoche("") is None
    a = meldungen_seite.ausgabe(
        {"report": {"date": "2026-08-05"}, "highlights": []}, None
    )
    assert a["kw"] == 32 and a["aufmacher"] is None


def test_meldungsseite_nennt_keine_zahl_der_meldungen(tmp_path):
    """Antonio, 10.10.2026: "131 Meldungen moechte ich nicht sehen"."""
    from orakel.test_seiten_inhalt import PORTAL, lies_seite, render

    html = lies_seite(render(tmp_path, highlights=PORTAL), "meldungen.html")
    soup = BeautifulSoup(html, "html.parser")
    assert f"{len(PORTAL)} Meldungen" not in soup.get_text(" ")
    assert not soup.select(".rubrik-zahl, .chip[data-filter]")
    assert soup.select_one(".mg-kopf .mg-datum")
