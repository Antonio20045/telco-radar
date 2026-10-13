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


def _w(datum: str, hs: list[dict]) -> dict:
    for h in hs:
        h.setdefault("date", datum)
    return {"date": datum, "highlights": hs}


def test_zeitung_kappt_je_rubrik_die_aeltesten():
    """Antonio, 13.10.2026: Hoechstzahl je Rubrik, Aeltestes ins Archiv."""
    grenze = meldungen_seite.HOECHSTZAHL["netz"]
    alt = [_h(i, 3) for i in range(grenze + 5)]
    for i, h in enumerate(alt):
        h["date"] = f"2026-10-{1 + i % 9:02d}"
    neu = [_h(100, 2), _h(101, 2)]
    sichtbar, archiv = meldungen_seite.zeitung(
        [_w("2026-10-12", neu), _w("2026-10-09", alt)]
    )
    assert len(sichtbar) == grenze
    assert sichtbar[:2] == [dict(h, lauf="2026-10-12") for h in neu]
    assert len(archiv) == 7
    juengstes_archiv = max(h["date"] for h in archiv)
    aeltestes_sichtbar = min(h["date"] for h in sichtbar[2:])
    assert juengstes_archiv <= aeltestes_sichtbar


def test_neue_meldungen_des_letzten_laufs_bleiben_alle():
    """Bringt ein Lauf mehr Neues als die Hoechstzahl, geht nichts verloren."""
    grenze = meldungen_seite.HOECHSTZAHL["tarife"]
    neu = [_h(i, 3, "tarife") for i in range(grenze + 12)]
    alt = [_h(500, 5, "tarife"), _h(501, 5, "geld")]
    sichtbar, archiv = meldungen_seite.zeitung(
        [_w("2026-10-12", neu), _w("2026-10-09", alt)]
    )
    assert len(sichtbar) == grenze + 13
    assert [h["url"] for h in archiv] == ["https://example.com/500"]


def test_seltene_rubrik_behaelt_alte_meldungen_bis_zur_altersgrenze():
    tage = meldungen_seite.HOECHSTALTER_TAGE
    from datetime import date, timedelta

    stichtag = date(2026, 10, 12)
    knapp = (stichtag - timedelta(days=tage)).isoformat()
    zu_alt = (stichtag - timedelta(days=tage + 1)).isoformat()
    sichtbar, archiv = meldungen_seite.zeitung(
        [
            _w(stichtag.isoformat(), [_h(1, 3)]),
            _w(knapp, [_h(2, 3, "regulierung")]),
            _w(zu_alt, [_h(3, 3, "regulierung")]),
        ]
    )
    assert [h["url"] for h in sichtbar] == [
        "https://example.com/1",
        "https://example.com/2",
    ]
    assert [h["url"] for h in archiv] == ["https://example.com/3"]


def test_dieselbe_adresse_steht_einmal_und_die_neueste_gilt():
    neu = _h(1, 4)
    neu["url"] = "https://www.example.com/1/?utm_source=x"
    alt = _h(1, 2)
    sichtbar, archiv = meldungen_seite.zeitung(
        [_w("2026-10-12", [neu]), _w("2026-10-09", [alt])]
    )
    assert len(sichtbar) == 1 and archiv == []
    assert sichtbar[0]["relevance"] == 4 and sichtbar[0]["lauf"] == "2026-10-12"


def test_kopf_kommt_aus_dem_letzten_lauf():
    alt = [_h(i, 5, image_w=MIND_BREITE_GROSS) for i in range(5)]
    neu = [_h(9, 2, image_w=MIND_BREITE_GROSS)]
    a = meldungen_seite.ausgabe(
        {"highlights": neu}, None, [_w("2026-10-12", neu), _w("2026-10-09", alt)]
    )
    assert a["aufmacher"]["url"] == "https://example.com/9"
    assert len(_alle(a)) == 6


def test_meldungsseite_zeigt_meldungen_frueherer_laeufe(tmp_path):
    """Gegenprobe zum alten Stand: dort stand nur die letzte Ausgabe."""
    import json

    from orakel.test_seiten_inhalt import PORTAL, lies_seite, render

    from telco_radar.report.html import render_site

    render(tmp_path, highlights=PORTAL[:6])
    reports = tmp_path / "data" / "reports"
    frueher = json.loads((reports / "2026-08-05.json").read_text(encoding="utf-8"))
    frueher["date"] = "2026-08-01"
    frueher["regions"]["Europa"]["highlights"] = [
        dict(h, url=f"https://example.com/frueher/{i}", title=f"Früher {i}")
        for i, h in enumerate(PORTAL[6:10])
    ]
    (reports / "2026-08-01.json").write_text(json.dumps(frueher), encoding="utf-8")
    site = tmp_path / "site2"
    render_site(site, reports)
    soup = BeautifulSoup(lies_seite(site, "meldungen.html"), "html.parser")
    links = {a["href"] for a in soup.select("article.meldung a.mg-link")}
    assert "https://example.com/frueher/0" in links
    assert len(soup.select("article.meldung")) == 10


def test_jede_meldung_nennt_ihr_datum(tmp_path):
    """Aeltere Meldungen bleiben stehen, also muss man ihr Alter sehen."""
    from orakel.test_seiten_inhalt import PORTAL, lies_seite, render

    html = lies_seite(render(tmp_path, highlights=PORTAL[:6]), "meldungen.html")
    soup = BeautifulSoup(html, "html.parser")
    wer = soup.select("article.meldung .mg-wer")
    assert wer and all("5. August 2026" in w.get_text() for w in wer)
