"""Shop-Preise statt alter Blätter (Preisprüfung 26.10.2026).

Die Fixtures sind Ausschnitte echter Abrufe vom 26.10.2026 mit dem Absender
TelcoRadar/1.0: die fünf Tarifkacheln von telekom.de/shop/tarife/handyvertrag (im
Browser gerendert) und Titel, Überschriften und Laufzeitauswahl von
congstar.de/handytarife/allnet-flat-tarife/allnet-flat-l/. congstars Blatt 545 nennt
für die Allnet Flat L 29,00 €, die Seite 30,00 €; die Telekom-Kachel trägt seit Oktober
keinen durchgestrichenen Preis mehr.
"""

from pathlib import Path

from telco_radar.collect import (
    tarif_congstar_seite,
    tarif_crawler,
    tarif_telekom_kacheln,
)
from telco_radar.tarif_model import PREISTYP_LIVE_SHOP

_FIX = Path(__file__).parent / "fixtures" / "tarife"


def _lies(modul, datei: str, anbieter: str) -> dict:
    html = (_FIX / datei).read_text(encoding="utf-8")
    return {
        t.name: t
        for t, _ in modul.tarife_aus_html(
            html, anbieter=anbieter, seiten_url="u", abgerufen_am="2026-10-26"
        )
    }


def test_congstar_l_kostet_im_shop_30_euro_mit_und_ohne_laufzeit():
    tarife = _lies(
        tarif_congstar_seite, "congstar_allnet_flat_l_2026-10-26.html", "congstar"
    )
    assert sorted(tarife) == ["Allnet Flat L", "Allnet Flat L Flex"]
    assert {t.grundgebuehr for t in tarife.values()} == {30.0}
    assert tarife["Allnet Flat L"].laufzeit_monate == 24
    assert tarife["Allnet Flat L Flex"].laufzeit_monate is None
    assert tarife["Allnet Flat L"].datenvolumen_gb == 200.0
    assert all(t.preistyp == PREISTYP_LIVE_SHOP for t in tarife.values())
    assert all(not t.fehlende_belege() for t in tarife.values())


def test_congstar_seite_ohne_laufzeitauswahl_liefert_nichts():
    html = "<html><title>x</title><h1>Allnet Flat L</h1></html>"
    assert (
        tarif_congstar_seite.tarife_aus_html(
            html, anbieter="congstar", seiten_url="u", abgerufen_am="2026-10-26"
        )
        == []
    )


def test_telekom_kachel_ohne_streichpreis_nimmt_den_monatspreis_nicht_den_schnitt():
    tarife = _lies(tarif_telekom_kacheln, "telekom_kacheln_2026-10-26.html", "Telekom")
    preise = {n: t.grundgebuehr for n, t in tarife.items()}
    assert preise == {
        "MagentaMobil XS": 29.95,
        "MagentaMobil S": 39.95,
        "MagentaMobil M": 49.95,
        "MagentaMobil L": 59.95,
        "MagentaMobil XL": 84.95,
    }
    assert preise["MagentaMobil M"] != 39.95, "Gegenprobe: Ø mit Cashback ist 39,95 €"


def test_telekom_kacheln_laufen_im_browser_congstar_ohne():
    quellen = tarif_crawler.lade_quellen(Path(__file__).parents[1])
    methoden = {(q.anbieter, q.methode): q.browser for q in quellen}
    assert methoden[("Telekom", tarif_crawler.METHODE_TELEKOM_KACHELN)] is True
    assert methoden[("congstar", tarif_congstar_seite.METHODE)] is False
