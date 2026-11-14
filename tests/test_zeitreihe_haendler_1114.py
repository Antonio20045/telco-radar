"""Issue #125 (Auftrag grafik-haendler-1114): die Händlerreihen in der
Preisverlauf-Grafik der Geräteseite.

Der Satz über dem Preisverlauf nennt z. B. „Saturn/MediaMarkt · Telekom-Netz
am günstigsten“, die Grafik zeichnete aber nur die fünf Netzbetreiber aus
`ANBIETER_FOLGE`. Erwartet: Hat ein Anbieter für das Paar eine Reihe (Serie
mit mindestens einem Punkt), zeichnet `_svg` (breit und schmal) ihn mit
Punkt und Namensetikett, `legende_html` führt ihn, und das Feld `anbieter`
des Paar-Blocks nennt ihn - zuerst die fünf, danach die Händler.

Geprüft wird über den öffentlichen Eingang `geraete_zeitreihe.aufbereiten`
(Testbestand aus `test_geraete_zeitreihe_ansicht.baue`, um eine Händlerreihe
ergänzt) und - wie in `test_geraete_zeitreihe_kurvenregeln.py` und
`test_legende_rest_0911.py` - direkt an `_svg` und `legende_html` mit
synthetischen Serien. Keine Uhr, kein Netz, kein data/ oder site/.

Die Gegenprobe (ohne Händlerreihe bleibt die Ausgabe wie vor dem Umbau) ist
heute grün und hält die Ausgabe über Prüfsummen und lesbare Struktur fest.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import date, timedelta

import pytest
from test_geraete_zeitreihe_ansicht import HEUTE, baue

from telco_radar.geraete_config import lade_katalog, lade_quellen
from telco_radar.report import geraete_view, geraete_zeitreihe
from telco_radar.report import geraete_zeitreihe as gz
from telco_radar.report.geraete_zeitreihe_legende import legende_html

FUENF = ("Telekom", "Vodafone", "o2", "1&1", "congstar")
HAENDLER = (
    "Saturn/MediaMarkt · Telekom-Netz",
    "Saturn/MediaMarkt · Vodafone-Netz",
    "Saturn/MediaMarkt · o2-Netz",
)
MIN_ABSTAND_PX = 12
PAAR = ("apple-iphone-17-pro-256", "xs", 24)


def _tage(start_iso: str, n: int) -> list[str]:
    start = date.fromisoformat(start_iso)
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def _serien(anbieter: tuple[str, ...], basis: float = 1500.0, schritt: float = 40.0):
    tage = _tage("2026-09-12", 3)
    return {
        a: [(t, basis + i * schritt - j * 5.0) for j, t in enumerate(tage)]
        for i, a in enumerate(anbieter)
    }


def _belege(anbieter) -> dict:
    return {
        a: (f"https://example.de/{i}", "2026-09-14") for i, a in enumerate(anbieter)
    }


def _data_anb(svg: str) -> list[str]:
    """Anbieter der Punkte in Zeichenreihenfolge, ohne Doppelte."""
    reihe: list[str] = []
    for roh in re.findall(r"data-anb='([^']*)'", svg):
        name = html.unescape(roh)
        if name not in reihe:
            reihe.append(name)
    return reihe


def _namensetiketten(svg: str) -> list[tuple[str, float]]:
    """(Name, y) je `gr-zr-name`, der Pfeil-tspan zählt nicht zum Namen."""
    etiketten = []
    for m in re.finditer(
        r"<text class='gr-zr-name'[^>]*\by='([-0-9.]+)'[^>]*>(.*?)</text>", svg
    ):
        name = re.sub(r"<tspan[^>]*>.*?</tspan>", "", m.group(2))
        etiketten.append((html.unescape(name).strip(), float(m.group(1))))
    return etiketten


def _svg_hoehe(svg: str) -> float:
    m = re.search(r"viewBox='0 0 ([0-9.]+) ([0-9.]+)'", svg)
    assert m, "SVG ohne viewBox"
    return float(m.group(2))


def _legende_namen(leg: str) -> list[str]:
    namen = []
    for roh in re.findall(r"<span><i style='[^']*'></i>([^<]*)", leg):
        namen.append(html.unescape(roh).strip())
    return namen


def _fehlt(was: str, fehlend, gesehen) -> str:
    return (
        f"Händler fehlt in der Grafik ({was}): {sorted(fehlend)} hat eine Reihe, "
        f"erscheint aber nicht; gesehen: {list(gesehen)}"
    )


@pytest.mark.parametrize("breit", [True, False], ids=["breit", "schmal"])
def test_svg_zeichnet_haendler_mit_punkt_und_namensetikett(breit):
    alle = FUENF + HAENDLER
    svg = gz._svg(_serien(alle), breit, _belege(alle), None, laufzeit=24)
    punkte = _data_anb(svg)
    namen = [n for n, _y in _namensetiketten(svg)]
    fehlend_punkt = [a for a in HAENDLER if a not in punkte]
    fehlend_name = [a for a in HAENDLER if a not in namen]
    assert not fehlend_punkt, _fehlt("Punkt data-anb", fehlend_punkt, punkte)
    assert not fehlend_name, _fehlt("Namensetikett", fehlend_name, namen)


@pytest.mark.parametrize("breit", [True, False], ids=["breit", "schmal"])
def test_svg_haendler_allein_ergibt_ein_bild(breit):
    """Ein Paar, in dem nur ein Händler gemessen ist, bekommt trotzdem ein
    Bild - heute liefert `_svg` dafür den leeren Text."""
    a = HAENDLER[0]
    svg = gz._svg({a: [("2026-09-12", 1400.0)]}, breit, _belege([a]), None)
    assert a in _data_anb(svg), _fehlt("einziger Anbieter", [a], _data_anb(svg))


@pytest.mark.parametrize("breit", [True, False], ids=["breit", "schmal"])
def test_svg_reihenfolge_erst_die_fuenf_dann_die_haendler(breit):
    alle = HAENDLER + FUENF
    svg = gz._svg(_serien(alle), breit, _belege(alle), None)
    punkte = _data_anb(svg)
    fehlend = [a for a in HAENDLER if a not in punkte]
    assert not fehlend, _fehlt("Reihenfolge", fehlend, punkte)
    assert punkte[:5] == list(FUENF), punkte
    assert set(punkte[5:]) == set(HAENDLER), punkte


def test_legende_fuehrt_haendler_nach_den_fuenf():
    alle = FUENF + HAENDLER
    namen = _legende_namen(legende_html(_serien(alle)))
    fehlend = [a for a in HAENDLER if a not in namen]
    assert not fehlend, _fehlt("Legende", fehlend, namen)
    assert namen[:5] == list(FUENF), namen
    assert set(namen[5:]) == set(HAENDLER), namen


def test_legende_ohne_reihe_kein_eintrag():
    """Ein Händler ohne Punkt (leere Serie) erscheint nicht."""
    serien = _serien(("Vodafone",))
    serien[HAENDLER[0]] = []
    assert _legende_namen(legende_html(serien)) == ["Vodafone"]


def _ansicht(root, state) -> dict:
    g = geraete_view.aufbereiten(
        state, lade_quellen(root), lade_katalog(root), heute=HEUTE
    )
    return geraete_zeitreihe.aufbereiten(state, g["tco"])


def _paar_block(ansicht: dict) -> dict:
    modell, band, laufzeit = PAAR
    for p in ansicht["paare"]:
        if (p["modell"], p["band"], p["laufzeit"]) == (modell, band, laufzeit):
            return p
    raise AssertionError(f"Paar {PAAR} fehlt in der Aufbereitung")


def _jsonl(pfad) -> list[dict]:
    return [json.loads(z) for z in pfad.read_text(encoding="utf-8").splitlines() if z]


def _mit_haendler(state, haendler: str) -> None:
    """Ergänzt den Testbestand um ein Händlerbündel (Vodafone-Bündel als
    Vorlage, gleicher Tarif) mit zwei Messtagen in der Historie."""
    tco_pfad = state / "geraete_tco.json"
    tco = json.loads(tco_pfad.read_text(encoding="utf-8"))
    vorlage = next(b for b in tco["buendel"] if b["anbieter"] == "Vodafone")
    neu = {
        **vorlage,
        "anbieter": haendler,
        "id": vorlage["id"].replace("vodafone", "saturn-mediamarkt-tk"),
        "geraet_monatsrate": 24.0,
        "quelle_url": "https://example.de/saturn-mediamarkt",
    }
    tco["buendel"].append(neu)
    tco_pfad.write_text(json.dumps(tco), encoding="utf-8")

    hist_pfad = state / "geraete_tco_historie.jsonl"
    hist = _jsonl(hist_pfad)
    muster = next(z for z in hist if z["id"] == vorlage["id"])
    for tag, rate in (("2026-09-12", 24.0), ("2026-09-13", 23.5)):
        hist.append(
            {
                **muster,
                "id": neu["id"],
                "datum": tag,
                "abgerufen_am": tag,
                "geraet_monatsrate": rate,
                "gesamt": round(1.0 + 24 * 20.0 + 24 * rate, 2),
                "quelle_url": neu["quelle_url"],
            }
        )
    hist_pfad.write_text(
        "\n".join(json.dumps(z) for z in hist) + "\n", encoding="utf-8"
    )

    tarif_pfad = state / "tarife.jsonl"
    tarife = _jsonl(tarif_pfad)
    tarif = next(t for t in tarife if t["tarif_id"] == vorlage["tarif_id"])
    tarife.append({**tarif, "anbieter": haendler})
    tarif_pfad.write_text(
        "\n".join(json.dumps(t) for t in tarife) + "\n", encoding="utf-8"
    )


@pytest.fixture(scope="module")
def paar_mit_haendler(tmp_path_factory):
    root, state = baue(tmp_path_factory.mktemp("zr_haendler"))
    _mit_haendler(state, HAENDLER[0])
    return _paar_block(_ansicht(root, state))


@pytest.fixture(scope="module")
def paar_ohne_haendler(tmp_path_factory):
    root, state = baue(tmp_path_factory.mktemp("zr_ohne"))
    return _paar_block(_ansicht(root, state))


def test_paar_feld_anbieter_nennt_den_haendler(paar_mit_haendler):
    anbieter = paar_mit_haendler["anbieter"]
    assert HAENDLER[0] in anbieter, _fehlt("Feld anbieter", [HAENDLER[0]], anbieter)
    assert anbieter == ["Vodafone", "o2", "1&1", "congstar", HAENDLER[0]], anbieter


def test_paar_bilder_und_legende_zeigen_den_haendler(paar_mit_haendler):
    for feld in ("svg_breit", "svg_schmal"):
        svg = paar_mit_haendler[feld]
        punkte = _data_anb(svg)
        namen = [n for n, _y in _namensetiketten(svg)]
        assert HAENDLER[0] in punkte, _fehlt(feld + " Punkt", [HAENDLER[0]], punkte)
        assert HAENDLER[0] in namen, _fehlt(feld + " Etikett", [HAENDLER[0]], namen)
    namen = _legende_namen(paar_mit_haendler["legende_html"])
    assert HAENDLER[0] in namen, _fehlt("legende_html", [HAENDLER[0]], namen)


@pytest.mark.parametrize("breit", [True, False], ids=["breit", "schmal"])
def test_acht_nahe_reihen_etiketten_ueberlappen_nicht_und_bleiben_im_bild(breit):
    alle = FUENF + HAENDLER
    serien = _serien(alle, basis=1500.0, schritt=1.0)
    svg = gz._svg(serien, breit, _belege(alle), None, laufzeit=24)
    etiketten = _namensetiketten(svg)
    namen = [n for n, _y in etiketten]
    fehlend = [a for a in alle if a not in namen]
    assert not fehlend, _fehlt("Namensetikett bei acht Reihen", fehlend, namen)
    hoehe = _svg_hoehe(svg)
    ys = sorted(y for _n, y in etiketten)
    for oben, unten in zip(ys, ys[1:], strict=False):
        assert unten - oben >= MIN_ABSTAND_PX, (
            f"Namensetiketten näher als {MIN_ABSTAND_PX} px: {etiketten}"
        )
    raus = [(n, y) for n, y in etiketten if not 0 < y <= hoehe]
    assert not raus, f"Etikett ausserhalb der SVG-Höhe {hoehe}: {raus}"


_FUENF_STRUKTUR = {
    True: (
        list(FUENF),
        [
            ("congstar", 81.6),
            ("1&1", 159.9),
            ("o2", 238.3),
            ("Vodafone", 316.7),
            ("Telekom", 395.0),
        ],
    ),
    False: (
        list(FUENF),
        [
            ("congstar", 60.7),
            ("1&1", 122.2),
            ("o2", 183.7),
            ("Vodafone", 245.2),
            ("Telekom", 306.6),
        ],
    ),
}
"""Stand origin/main vor dem Umbau (14.11.2026): Zeichenreihenfolge der
Punkte und (Name, y) der Namensetiketten für `_serien(FUENF)`."""

_FUENF_SHA = {
    "breit": "7cd10fe1ead88a25537c4a5874b9d4c5e494f641c7707c20b5ac3f611f8685c8",
    "schmal": "6de33c266dff7615a36866576b978ed1629290314159b67155c1415cf28a9e9d",
    "legende": "b7e6341ef486fc5476865b487948598a92c918eab0ddbcb20c795619d3736ca4",
}
_PAAR_OHNE_STRUKTUR = {
    "svg_breit": (
        ["Vodafone", "o2", "1&1", "congstar"],
        [("Vodafone", 69.5), ("congstar", 183.1), ("o2", 304.2), ("1&1", 395.0)],
    ),
    "svg_schmal": (
        ["Vodafone", "o2", "1&1", "congstar"],
        [("Vodafone", 51.3), ("congstar", 140.4), ("o2", 235.4), ("1&1", 306.6)],
    ),
}
"""Paar iPhone 17 Pro 256 · xs · 24 des Testbestands ohne Händlerreihe, Stand
origin/main vor dem Umbau (14.11.2026): Punktreihenfolge und Etiketten."""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("breit", [True, False], ids=["breit", "schmal"])
def test_gegenprobe_fuenf_ohne_haendler_struktur_unveraendert(breit):
    svg = gz._svg(_serien(FUENF), breit, _belege(FUENF), None, laufzeit=24)
    punkte_soll, etiketten_soll = _FUENF_STRUKTUR[breit]
    assert _data_anb(svg) == punkte_soll
    assert _namensetiketten(svg) == etiketten_soll


def test_gegenprobe_fuenf_ohne_haendler_ausgabe_byte_gleich():
    serien = _serien(FUENF)
    ist = {
        "breit": _sha(gz._svg(serien, True, _belege(FUENF), None, laufzeit=24)),
        "schmal": _sha(gz._svg(serien, False, _belege(FUENF), None, laufzeit=24)),
        "legende": _sha(legende_html(serien)),
    }
    assert ist == _FUENF_SHA


def test_gegenprobe_paar_ohne_haendler_unveraendert(paar_ohne_haendler):
    p = paar_ohne_haendler
    assert p["anbieter"] == ["Vodafone", "o2", "1&1", "congstar"]
    for feld, (punkte_soll, etiketten_soll) in _PAAR_OHNE_STRUKTUR.items():
        assert _data_anb(p[feld]) == punkte_soll, feld
        assert _namensetiketten(p[feld]) == etiketten_soll, feld
    assert _legende_namen(p["legende_html"]) == ["Vodafone", "o2", "1&1", "congstar"]
