"""Telekom-Tarifkacheln: der durchgestrichene Preis, nicht der Ø-Kombipreis.

DIE FIXTURE IST EIN GESPEICHERTER ECHTER ABRUF
----------------------------------------------
`tests/fixtures/tarife/telekom_shop_tarife_handyvertrag.html.gz` ist die
rohe, ungekuerzte Antwort von
https://www.telekom.de/shop/tarife/handyvertrag vom 05.09.2026 (HTTP 200,
2.267.192 Bytes, Absender `TelcoRadar/1.0`). Herkunft und sha256 stehen in
`tests/fixtures/tarife/_herkunft.json`.
"""
import gzip
from pathlib import Path

from telco_radar.collect import tarif_telekom_kacheln
from telco_radar.tarif_model import PREISTYP_LIVE_SHOP

_FIX = Path(__file__).parent / "fixtures" / "tarife"
_DATEI = "telekom_shop_tarife_handyvertrag.html.gz"
_URL = "https://www.telekom.de/shop/tarife/handyvertrag"


def _seite() -> str:
    with gzip.open(_FIX / _DATEI, "rt", encoding="utf-8") as fh:
        return fh.read()


def _tarife(html=None):
    return tarif_telekom_kacheln.tarife_aus_html(
        html if html is not None else _seite(), anbieter="Telekom",
        seiten_url=_URL, abgerufen_am="2026-09-05")


# --------------------------------------------------------------------------
# Die gemessene Seite
# --------------------------------------------------------------------------

def test_die_fuenf_kacheln_der_seite():
    """Fuenf Tarife mit dem DURCHGESTRICHENEN Preis - so gemessen am 05.09.2026.

    Nicht die gross gezeigte "Ø"-Zahl (34,95 / 39,95 / 49,95 / 74,95 /
    24,95 EUR): sie ist ein bedingter Kombipreis, siehe Modul-Docstring von
    `tarif_telekom_kacheln.py`.
    """
    tarife = [t for t, _ in _tarife()]
    assert [(t.name, t.grundgebuehr) for t in tarife] == [
        ("MagentaMobil XL", 84.95),
        ("MagentaMobil L", 59.95),
        ("MagentaMobil M", 49.95),
        ("MagentaMobil S", 39.95),
        ("MagentaMobil XS", 29.95),
    ]


def test_der_durchgestrichene_preis_trifft_das_produktinformationsblatt():
    """Die Gegenprobe: vier der fuenf Betraege stehen bereits im PIB-Bestand.

    `data/state/tarife.jsonl` fuehrt (Stand 04.09.2026, vor diesem Adapter)
    MagentaMobil S/M/L/XL zu genau 39,95/49,95/59,95/84,95 EUR - exakt die
    durchgestrichenen Betraege dieser Kacheln, nicht die Ø-Betraege.
    """
    by_name = {t.name: t.grundgebuehr for t, _ in _tarife()}
    assert by_name["MagentaMobil S"] == 39.95
    assert by_name["MagentaMobil M"] == 49.95
    assert by_name["MagentaMobil L"] == 59.95
    assert by_name["MagentaMobil XL"] == 84.95


def test_jeder_satz_traegt_seinen_beleg():
    """`pruefe_belege` ist die Zusage: jede Zahl steht woertlich im Rohtext."""
    for tarif, _ in _tarife():
        tarif.pruefe_belege()
        assert tarif.preistyp == PREISTYP_LIVE_SHOP
        assert tarif.abgerufen_am == "2026-09-05"


def test_jeder_beleglink_ist_die_tiefenadresse_dieses_tarifs():
    """Der Link ist `?tariffId=...`, nicht die Uebersichtsseite fuer alle fuenf."""
    urls = [t.dokument_url for t, _ in _tarife()]
    assert len(urls) == len(set(urls))
    for url in urls:
        assert "tariffid=" in url.lower()
        assert url.startswith("https://www.telekom.de/")


def test_xl_ist_unbegrenzt_die_anderen_tragen_ein_gb_volumen():
    by_name = {t.name: t.datenvolumen_gb for t, _ in _tarife()}
    assert by_name["MagentaMobil XL"] == float("inf")
    assert by_name["MagentaMobil L"] == 100
    assert by_name["MagentaMobil M"] == 50
    assert by_name["MagentaMobil S"] == 30
    assert by_name["MagentaMobil XS"] == 20


# --------------------------------------------------------------------------
# Gestellte Faelle
# --------------------------------------------------------------------------

def _kachel(name="MagentaMobil M", oben='<span class="Price__value">39,95 €</span>',
            strike='<span class="strike-price-value">49,95 €</span>',
            link='<a class="Button" href="https://www.telekom.de/shop/tarife/'
                 'smartphone-tarife?tariffId=MF_17791#js-tileSectionRef">'
                 'Tarif auswählen</a>') -> str:
    return (
        '<div class="Tile TariffTileModified_TariffTileModified__3XAAl">'
        f'<div class="TariffTile__name-wrapper"><strong>{name}</strong></div>'
        f'<div class="price-wrapper">{oben}</div>'
        f'<p class="strike-price">{strike}</p>'
        f'{link}</div>')


def test_ohne_durchgestrichenen_preis_wird_die_kachel_verworfen():
    """Der Ø-Preis allein ist kein Beleg fuer einen Standalone-Betrag."""
    html = _kachel(strike="")
    assert _tarife(html) == []


def test_ohne_namen_wird_die_kachel_verworfen():
    html = _kachel(name="")
    assert _tarife(html) == []


def test_eine_leere_seite_liefert_nichts():
    assert _tarife("") == []


def test_dieselbe_kachel_zweimal_ergibt_einen_tarif():
    """Der Fingerabdruck haengt an der Kachel - eine echte Dublette faellt heraus."""
    html = _kachel() + _kachel()
    assert len(_tarife(html)) == 1
