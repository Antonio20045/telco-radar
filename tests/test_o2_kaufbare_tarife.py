"""o2: nur Tarife, die ein Kunde selbst wählen und kaufen kann, werden ein Bündel.

DER BEFUND (21.11.2026)
-----------------------
Die Produktseite des Galaxy S26 256 GB nennt in `pageValue` zwölf Tarife; die Seite
zeigt fünf Kacheln, die „Plus“-Tarife (Browser). „O2 Mobile Unlimited L“ ohne „Plus“
ist über die Tarifübersicht („Handy hinzufügen“, `/e-shop?tarif=o2-mobile-unlimited-l`)
mit Gerät buchbar. Entscheidung Antonio: Bündel nur für kaufbare Tarife.

DIE FIXTURES (echte Abrufe 21.11.2026)
--------------------------------------
``o2_tarifuebersicht_20261121.html.gz``: die Tarifübersicht ohne Browser, vollständig.
``o2_s26_tarifkacheln_browser_20261121.html``: die fünf Kacheln aus dem gerenderten DOM
derselben S26-Seite wie ``o2_galaxy_s26_tarifoptionen_20261121.json.gz``.
``o2_vertiefung_iphone17pro.json.gz`` (29.09.2026): zwölf Antworten mit je eigenem
Tarif und Slug, die Paare Name ↔ Slug.
"""

from __future__ import annotations

import gzip
import html as html_text
import json
import logging
import re
from pathlib import Path

import pytest

from telco_radar.analyze.geraete_pruefstatus import GERAETETARIF_MERKMAL
from telco_radar.collect.geraete import o2
from telco_radar.collect.geraete import o2_kaufbar as kb
from telco_radar.collect.geraete.basis import GeraeteAbrufFehler
from telco_radar.geraete_abruf import Abruf

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_URL = (
    "https://www.o2online.de/e-shop/samsung/samsung-galaxy-s26-256gb-cobalt-violet"
    "-details?ohne-tarif=nein&zielgruppe=privatkunden&ratenzahlung=36"
    "&vertragsart=ratenzahlung&tarif=o2-mobile-on-demand-m-plus"
)
_LABEL = re.compile(r'<label for="choice-panel-input-\d+" aria-label="([^"]+)"')
_UEBERSICHT_SLUGS = {
    "o2-mobile-on-demand-m-plus",
    "o2-mobile-m-flex",
    "o2-mobile-on-demand-l-plus",
    "o2-mobile-on-demand-l-flex",
    "o2-mobile-unlimited-s-special-plus",
    "o2-mobile-unlimited-s-special-flex",
    "o2-mobile-unlimited-m-flex",
    "o2-mobile-unlimited-m-plus",
    "o2-mobile-unlimited-l",
    "o2-mobile-unlimited-l-flex",
}
_PLUS_SLUGS = {
    "o2-mobile-unlimited-l-plus",
    "o2-mobile-unlimited-m-plus",
    "o2-mobile-unlimited-s-special-plus",
    "o2-mobile-l-plus",
    "o2-mobile-on-demand-m-plus",
}


def _gz(name: str) -> str:
    with gzip.open(_FIX / name, "rt", encoding="utf-8") as fh:
        return fh.read()


def _seitenwerte(knoten, out: list) -> list:
    if isinstance(knoten, dict):
        if knoten.get("@type") == "pdp:PageValue":
            out.append(knoten)
            return out
        for wert in knoten.values():
            _seitenwerte(wert, out)
    elif isinstance(knoten, list):
        for wert in knoten:
            _seitenwerte(wert, out)
    elif isinstance(knoten, str) and "pdp:PageValue" in knoten:
        _seitenwerte(o2.lies_konfiguration(knoten), out)
    return out


@pytest.fixture(scope="module")
def paare() -> dict:
    """Name des gewählten Tarifs -> Slug (`dimension59`), je echter Antwort."""
    out: dict = {}
    for pv in _seitenwerte(json.loads(_gz("o2_vertiefung_iphone17pro.json.gz")), []):
        gewaehlt = [o for o in pv["tariff"]["tariffOptions"] if o.get("selected")]
        slug = pv["ecommerceProductValue"]["attributes"]["dimension59"]
        out[o2._ohne_markup(gewaehlt[0]["displayValue"])] = slug
    return out


@pytest.fixture(scope="module")
def s26() -> dict:
    return o2.lies_konfiguration(_gz("o2_galaxy_s26_tarifoptionen_20261121.json.gz"))


@pytest.fixture(scope="module")
def uebersicht() -> frozenset:
    slugs = kb.slugs_der_uebersicht(_gz("o2_tarifuebersicht_20261121.html.gz"))
    assert slugs is not None
    return slugs


def _saetze(pv: dict, paare: dict, url: str = _URL) -> list[dict]:
    referenz = {
        o2._ohne_markup(o["displayValue"]): {
            "slug": paare[o2._ohne_markup(o["displayValue"])],
            "anschluss": 0.0,
        }
        for o in pv["tariff"]["tariffOptions"]
    }
    basis = {"strukturierter_name": "Gerät", "sku": "x", "url": url}
    roh = o2.saetze_aus_konfiguration(pv, basis, referenz, url, {})
    return [{**s, "anbieter": "o2"} for s in roh]


def _slugs(saetze: list) -> set:
    return {s["tarif_slug"] for s in saetze}


def test_uebersicht_verlinkt_zehn_tarife_mit_handy(uebersicht):
    assert set(uebersicht) == _UEBERSICHT_SLUGS
    assert "o2-mobile-l-plus" not in uebersicht


def test_uebersicht_ohne_handy_link_ist_nicht_gelesen():
    fremd = '<a href="https://www.o2online.de/e-shop/sony?tarif=o2-mobile-l-plus">x</a>'
    falscher_pfad = '<a href="/hilfe?tarif=o2-mobile-l">Handy hinzufügen</a>'
    assert kb.slugs_der_uebersicht("<html><body>Wartung</body></html>") is None
    assert kb.slugs_der_uebersicht(fremd + falscher_pfad) is None
    assert kb.slugs_der_uebersicht("") is None


def test_plus_im_namen_heisst_plus_slug(paare):
    """Annahme 1, zweiter Teil: zwölf echte Paare Name ↔ Slug."""
    assert len(paare) == 12
    merkmal = GERAETETARIF_MERKMAL["o2"]
    for name, slug in paare.items():
        assert (merkmal in name.split()) == kb.ist_kachel(slug), (name, slug)
    assert {s for s in paare.values() if kb.ist_kachel(s)} == _PLUS_SLUGS


def test_kacheln_der_produktseite_sind_die_plus_tarife(s26, paare):
    """Annahme 1, erster Teil: die Kacheln im Browser tragen den Plus-Slug."""
    html = (_FIX / "o2_s26_tarifkacheln_browser_20261121.html").read_text("utf-8")
    kacheln = {" ".join(html_text.unescape(x).split()) for x in _LABEL.findall(html)}
    optionen = [
        o2._ohne_markup(o["displayValue"]) for o in s26["tariff"]["tariffOptions"]
    ]
    assert len(optionen) == 12
    assert len(kacheln) == 5
    assert kacheln == {n for n in optionen if kb.ist_kachel(paare[n])}


def test_unlimited_l_bleibt_wenn_die_uebersicht_es_verlinkt(s26, paare, uebersicht):
    befund = kb.pruefe(_saetze(s26, paare), uebersicht)
    assert _slugs(befund.behalten) == _PLUS_SLUGS | {"o2-mobile-unlimited-l"}
    assert befund.wege == {"vorgewaehlt": 1, "produktseite": 4, "uebersicht": 1}
    assert befund.uebersicht_gelesen


def test_unlimited_l_faellt_weg_ohne_link(s26, paare, uebersicht):
    ohne = frozenset(uebersicht - {"o2-mobile-unlimited-l"})
    befund = kb.pruefe(_saetze(s26, paare), ohne)
    assert _slugs(befund.behalten) == _PLUS_SLUGS
    assert befund.verworfen["O2 Mobile Unlimited L mit 300 MBit/s"] == 1


def test_ausfall_der_uebersicht_laesst_nur_die_produktseite(s26, paare):
    befund = kb.pruefe(_saetze(s26, paare), None)
    assert _slugs(befund.behalten) == _PLUS_SLUGS
    assert len(befund.verworfen) == 7
    assert not befund.uebersicht_gelesen


def test_zaehlung_der_verworfenen_tarife(s26, paare, uebersicht):
    befund = kb.pruefe(_saetze(s26, paare), uebersicht)
    assert befund.zeile == (
        "o2: 6 Tarife nur in der Schnittstelle, nicht kaufbar: "
        "O2 Mobile L mit 150 GB+ (1 Bündel), O2 Mobile S mit 15 GB+ (1 Bündel), "
        "O2 Mobile Special (1 Bündel), "
        "O2 Mobile Unlimited M mit 100 MBit/s (1 Bündel), "
        "O2 Mobile Unlimited S Special mit 15 MBit/s (1 Bündel), "
        "O2 Mobile on Demand M mit 50 GB+ (1 Bündel); 6 Bündel verworfen"
    )


def test_vorgewaehlter_tarif_ohne_plus_bleibt(paare, uebersicht):
    """Redmi 17: sieben Tarife ohne Plus, die Seite zeigt den gewählten als Kachel."""
    pv = o2.lies_konfiguration(_gz("o2_redmi17_tarifoptionen_20261121.json.gz"))
    url = _URL.replace("o2-mobile-on-demand-m-plus", "o2-mobile-on-demand-m")
    saetze = _saetze(pv, paare, url)
    befund = kb.pruefe(saetze, uebersicht)
    gemessen = [s for s in saetze if kb.ist_vorgewaehlt(s)]
    assert [s["tarif_slug"] for s in gemessen] == ["o2-mobile-on-demand-m"]
    assert _slugs(befund.behalten) == {"o2-mobile-on-demand-m", "o2-mobile-unlimited-l"}
    assert len(befund.verworfen) == 5


class _Hole:
    def __init__(self, antwort):
        self.antwort, self.aufrufe = antwort, []

    def __call__(self, url, **kwargs):
        self.aufrufe.append((url, kwargs))
        if isinstance(self.antwort, Exception):
            raise self.antwort
        return self.antwort


def test_haken_liest_die_uebersicht_einmal_als_html(s26, paare):
    hole = _Hole(Abruf(200, _gz("o2_tarifuebersicht_20261121.html.gz")))
    saetze = _saetze(s26, paare)
    assert kb.nur_kaufbare(hole, {"Accept": "application/x"}, saetze) == 0
    assert _slugs(saetze) == _PLUS_SLUGS | {"o2-mobile-unlimited-l"}
    erwartet = {"kopfzeilen": {"Accept": "text/html"}, "einmalig": True}
    assert hole.aufrufe == [(kb.UEBERSICHT, erwartet)]


def test_haken_ohne_abgeleitete_saetze_ruft_nicht_ab():
    hole = _Hole(Abruf(200, ""))
    saetze = [{"anbieter": "o2", "tarif_slug": "o2-mobile-s", "tarif_name": "x"}]
    assert kb.nur_kaufbare(hole, {}, saetze) == 0
    assert hole.aufrufe == []
    assert len(saetze) == 1


@pytest.mark.parametrize(
    "antwort",
    [
        GeraeteAbrufFehler("robots.txt verbietet"),
        Abruf(403, "Zugriff verweigert", schutz=True),
        Abruf(503, ""),
        Abruf(200, "<html>Wartung</html>"),
    ],
)
def test_ausfall_wird_benannt_und_nur_die_produktseite_bleibt(
    s26, paare, caplog, antwort
):
    saetze = _saetze(s26, paare)
    with caplog.at_level(logging.INFO, logger=kb.__name__):
        kb.nur_kaufbare(_Hole(antwort), {}, saetze)
    assert _slugs(saetze) == _PLUS_SLUGS
    assert kb.AUSFALL in caplog.text
    assert "o2: 7 Tarife nur in der Schnittstelle, nicht kaufbar" in caplog.text


def test_verlorenes_plus_muster_wird_benannt(s26, paare, uebersicht, caplog):
    umbenannt = [
        {**s, "tarif_slug": s["tarif_slug"].replace("-plus", "-max")}
        for s in _saetze(s26, paare)
    ]
    befund = kb.pruefe(umbenannt, uebersicht)
    with caplog.at_level(logging.WARNING, logger=kb.__name__):
        kb.protokolliere(befund)
    assert not befund.muster_gesehen
    assert kb.MUSTER_FEHLT in caplog.text
    assert kb.pruefe(_saetze(s26, paare), uebersicht).muster_gesehen
