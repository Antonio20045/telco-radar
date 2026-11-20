"""1&1-Gegenprobe nach dem Rasterwechsel auf 48 Geräteraten (20.11.2026).

DER BEFUND (Karte fcd018e3, Geräte-Lauf 44728882384)
----------------------------------------------------
Der Bündelwächter war rot: "1&1: 17 Pflichtmodelle ohne Bündel". Im
Protokoll stand für jeden der sechs Tarife "Aufschlag einheitlich, alle
Speichergrößen, 41 Geräte ohne passende Gegenprobe" - also KEINE einzige
hergeleitete Tarifstufe, obwohl alle Seiten HTTP 200 lieferten.

Ursache: die Geräteraster bewerben seit dem 20.11.2026 die Flex-
Finanzierung mit 48 GERÄTERATEN (`data-hardware-months="48"` auf allen 41
Kacheln, iPhone 17 Pro 37,99 statt 59,99). Die Gegenprobe hat diese Zahl
gegen `laufzeit_monate` des Satzes (24, die Mindestbindung) geprüft und
jedes Gerät verworfen. 48 Raten und 24 Monate Mindestbindung sind aber
zwei verschiedene Größen - die Seite selbst nennt beide.

DIE FIXTURES SIND GESPEICHERTE ECHTE ABRUFE (20.11.2026, HTTP 200,
reines HTTP-GET, Absender TelcoRadar/1.0, robots.txt erlaubt alle drei
Seitentypen; Größen und sha256 je Datei in `fixtures/_herkunft.json`)
------------------------------------------------------------------------
* `einsundeins_tarifuebersicht_all_net_flat_2026-11-20.html.gz` =
  `/all-net-flat-vergleich` (479 784 B), GEKÜRZT auf den zusammen-
  hängenden Ausschnitt, der die `targetpage`-Links der sieben Raster und
  die `Tarifdetails`-Anker trägt.
* `einsundeins_tarifraster_all_net_flat_s|m_2026-11-20.html.gz` =
  `/smartphones-all-net-flat-s|m` (593 603 bzw. 592 888 B), GEKÜRZT auf
  den Ausschnitt ab `<div class="hardware-container__items"
  id="hardware-list">` bis zum letzten `</form>` - dort stehen alle 41
  Kacheln.
* `einsundeins_produktseite_<modell>_2026-11-20.html.gz` = die
  Geräteseiten von sieben der acht Pflichtmodelle, GEKÜRZT auf den
  Ausschnitt vom Seitenanfang bis zum Ende des `const products`-Blocks;
  dahinter stehen nur Fußbereich und Skripte. Die Seite des iPhone 17 Pro
  liegt schon vollständig im Bestand
  (`..._iphone_17_pro_2026-11-20.html.gz`, K1) und wird wiederverwendet.

Nichts in den Ausschnitten ist verändert; `lies_buendel` liest aus jedem
Ausschnitt dieselben Sätze wie aus der vollständigen Antwort (geprüft
beim Anlegen).
"""

import gzip
from pathlib import Path

from telco_radar.collect.geraete import einsundeins as E

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_TAG = "2026-11-20"

_ANF = "https://mobile.1und1.de/all-net-flat-vergleich"
_UNL = "https://mobile.1und1.de/unbegrenztes-datenvolumen"
_RASTER_S = "https://mobile.1und1.de/smartphones-all-net-flat-s"
_RASTER_M = "https://mobile.1und1.de/smartphones-all-net-flat-m"

_PFLICHT = {
    "iphone-17": "hw-apple-iphone-17",
    "iphone-17e": "hw-apple-iphone-17e",
    "iphone-17-pro": "hw-apple-iphone-17-pro",
    "iphone-17-pro-max": "hw-apple-iphone-17-pro-max",
    "iphone-18-pro": "hw-apple-iphone-18-pro",
    "iphone-18-pro-max": "hw-apple-iphone-18-pro-max",
    "iphone-duo": "hw-apple-iphone-duo",
    "samsung-galaxy-s26": "hw-samsung-galaxy-s26",
}

_SEITEN = {
    "iphone-17": "iphone_17",
    "iphone-17e": "iphone_17e",
    "iphone-17-pro": "iphone_17_pro",
    "iphone-17-pro-max": "iphone_17_pro_max",
    "iphone-18-pro": "iphone_18_pro",
    "iphone-18-pro-max": "iphone_18_pro_max",
    "iphone-duo": "iphone_duo",
    "samsung-galaxy-s26": "galaxy_s26",
}


def _fixture(name: str) -> str:
    return gzip.open(_FIX / name, "rb").read().decode("utf-8", "replace")


def _netz() -> dict:
    return {
        _ANF: f"einsundeins_tarifuebersicht_all_net_flat_{_TAG}.html.gz",
        _RASTER_S: f"einsundeins_tarifraster_all_net_flat_s_{_TAG}.html.gz",
        _RASTER_M: f"einsundeins_tarifraster_all_net_flat_m_{_TAG}.html.gz",
    }


class _Hole:
    """Liefert die gespeicherten Antworten; alles andere ist 404.

    Nur die Übersicht `/all-net-flat-vergleich` und zwei ihrer sieben
    Raster liegen als Fixture vor - die übrigen fünf fehlen absichtlich
    (ein toter Abruf darf die Herleitung nicht kosten, geprüft in
    `test_geraete_tarifstufen_einsundeins.py`).
    """

    def __init__(self):
        self.netz = _netz()
        self.abgerufen: list = []

    def __call__(self, url, kopfzeilen=None, **kw):
        self.abgerufen.append(url)
        if url not in self.netz:
            return (404, "")
        return (200, _fixture(self.netz[url]))


def _basis() -> list:
    """Die Default-Tarif-Sätze der acht Pflichtmodell-Seiten."""
    out: list = []
    for slug, name in _SEITEN.items():
        url = f"https://mobile.1und1.de/{slug}"
        for satz in E.lies_buendel(
            _fixture(f"einsundeins_produktseite_{name}_{_TAG}.html.gz"), url=url
        ):
            out.append(
                {**satz, "anbieter": "1&1", "sku_id": satz["titel"], "quelle_url": url}
            )
    return out


def test_das_raster_nennt_jetzt_48_geraeteraten():
    """Der Markupwechsel selbst: alle 41 Kacheln stehen auf 48 Raten."""
    raster = E.lies_tarifraster(_fixture(_netz()[_RASTER_S]))
    assert raster["tarif_name"] == "1&1 All-Net-Flat S"
    assert len(raster["preise"]) == 41
    assert {monate for _, monate in raster["preise"].values()} == {48}
    assert raster["preise"]["hw-apple-iphone-17-pro"] == (3799, 48)


def test_die_geraeteseite_belegt_den_betrag_zur_ratenzahl():
    """Die 37,99 des Rasters stehen auf der Geräteseite in der Stufe "36 +
    12 Monate Flex": 25,00 Geräterate (1200,00 / 25,00 = 48 Raten) plus
    12,99 Tarifrate, flach über genau diese 48 Monate. Die Mindestbindung
    der Seite bleibt daneben 24 Monate."""
    text = _fixture(f"einsundeins_produktseite_iphone_17_pro_{_TAG}.html.gz")
    karte = E._hardwarepreiskarte(text)
    preise = E.geraeteraten_preise(karte["product-COSMIC_ORANGE-256"])
    assert preise == {24: 59.99, 36: 44.99, 48: 37.99}
    assert E._vertragslaufzeit(text) == 24


def test_eine_stufe_mit_springendem_tarifpreis_zaehlt_nicht():
    """Gegenprobe zu `geraeteraten_preise`: eine Stufe, deren Tarifpreis
    VOR dem Ende der Raten springt, ist nicht flach belegt und liefert
    keinen Betrag - lieber ein Preis weniger als ein falscher."""
    eintrag = {
        "36": {
            "flex": {
                "hardwarePricePerMonth": "25.00",
                "hardwareTotalPrice": "1200.00",
                "tariffPricePerMonth": "12.99",
                "tariffMonthlyPrices": [
                    {"amount": 12.99, "begin": 1, "end": 36},
                    {"amount": 14.99, "begin": 37, "end": 0},
                ],
            }
        }
    }
    assert E.geraeteraten_preise(eintrag) == {}


def test_die_pflichtmodelle_bekommen_wieder_buendel():
    """Der Regressionsfall: vor dem Fix verwarf die Gegenprobe alle 41
    Geräte ("41 Geräte ohne passende Gegenprobe"), es entstand kein
    einziger Satz. Jetzt entsteht je Gerät und Speichergröße einer - für
    alle acht Pflichtmodelle."""
    saetze = _basis()
    vorher = len(saetze)
    neu = E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    assert neu == vorher == 23
    hergeleitet = [s for s in saetze if s.get("herleitung")]
    assert {s["tarif_name"] for s in hergeleitet} == {"1&1 All-Net-Flat M"}
    assert {s["hw_id"] for s in hergeleitet} == set(_PFLICHT.values())


def test_der_aufschlag_ist_die_rasterdifferenz_die_bindung_bleibt():
    """S -> M kostet im Raster überall 5,00 mehr (41 Kacheln, einheitlich).
    Der Aufschlag kommt auf den Betrag des Default-Satzes; die Mindest-
    bindung bleibt die der Geräteseite (24) und wird NICHT auf die
    Ratenzahl des Rasters (48) gesetzt."""
    saetze = _basis()
    E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    for hw_id, s_betrag, m_betrag in (
        ("hw-apple-iphone-17-pro", 59.99, 64.99),
        ("hw-samsung-galaxy-s26", 44.99, 49.99),
    ):
        default = next(
            s
            for s in saetze
            if s["hw_id"] == hw_id and s["vorausgewaehlt"] and not s.get("herleitung")
        )
        assert default["buendel_monatlich"] == s_betrag
        stufe = next(
            s
            for s in saetze
            if s["hw_id"] == hw_id
            and s["vorausgewaehlt"]
            and s.get("herleitung") == E.HERLEITUNG_TARIFAUFSCHLAG
        )
        assert stufe["buendel_monatlich"] == m_betrag
        assert stufe["laufzeit_monate"] == default["laufzeit_monate"] == 24
        assert stufe["tarif_slug"] == "tariff-anf-m-mvl"
        assert "raten_preise" not in stufe


def test_ein_rasterpreis_ohne_beleg_auf_der_seite_wird_verworfen():
    """Die Gegenprobe greift weiter: kennt die Geräteseite zur Ratenzahl
    des Rasters keinen Betrag, bleibt das Gerät ohne Tarifstufe - auch
    wenn der Default-Tarif und die Ratenzahl stimmen."""
    saetze = _basis()
    for satz in saetze:
        if satz["hw_id"] == "hw-apple-iphone-duo" and satz["raten_preise"]:
            satz["raten_preise"] = {48: 99.99}
    E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    hergeleitet = {s["hw_id"] for s in saetze if s.get("herleitung")}
    assert "hw-apple-iphone-duo" not in hergeleitet
    assert hergeleitet == set(_PFLICHT.values()) - {"hw-apple-iphone-duo"}
