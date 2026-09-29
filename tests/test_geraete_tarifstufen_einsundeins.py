"""1&1-Tarifstufen: aus Tarifuebersicht und Geraeteraster je Tarif die
Bündel aller Tarife x Speichergrößen (29.09.2026).

DIE FIXTURES SIND GESPEICHERTE ECHTE ABRUFE (29.09.2026, HTTP 200, reines
HTTP-GET, Absender TelcoRadar/1.0)
------------------------------------------------------------------------
* `einsundeins_tarifuebersicht_all_net_flat_2026-09-29.html.gz` =
  `/all-net-flat-vergleich` (460 075 B), `..._unlimited_...` =
  `/unbegrenztes-datenvolumen` (466 497 B), beide vollständig.
* `einsundeins_tarifraster_<tarif>_2026-09-29.html.gz` = die sieben
  Geräteraster `/smartphones-all-net-flat-s|m|l`, `/smartphones-unlimited-
  s|m|l|xl` (je ~563 KB), GEKÜRZT auf den zusammenhängenden Ausschnitt ab
  `<div class="hardware-container__items" id="hardware-list">` bis zum
  letzten `</form>` - dort stehen alle 43 Kacheln; nichts darin ist
  verändert.
* `einsundeins_produktseite_iphone_18_pro_2026-09-29.html.gz` (690 880 B)
  und `..._galaxy_s26_ultra_...` (356 623 B), vollständig.

Was diese Tests festhalten: den Tarifaufschlag als Differenz zweier
Rasterpreise DESSELBEN Geräts, seine Übertragung auf alle Speichergrößen
nur bei einheitlichem Aufschlag, die Gegenprobe gegen den angezeigten
Preis der Geräteseite, und dass das Zubehör-Bundle des Rasters (Galaxy
Buds 4 am S26 Ultra) nicht im Bündelpreis landet.
"""
import gzip
from pathlib import Path

import pytest

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete import ADAPTER
from telco_radar.collect.geraete import einsundeins as E
from telco_radar.tarif_bezug import Tarifbestand

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent
_TAG = "2026-09-29"

_ANF = "https://mobile.1und1.de/all-net-flat-vergleich"
_UNL = "https://mobile.1und1.de/unbegrenztes-datenvolumen"
_IPHONE = "https://mobile.1und1.de/iphone-18-pro"
_S26U = "https://mobile.1und1.de/samsung-galaxy-s26-ultra"
_RASTER = ("all-net-flat-s", "all-net-flat-m", "all-net-flat-l",
           "unlimited-s", "unlimited-m", "unlimited-l", "unlimited-xl")


def _fixture(name: str) -> str:
    return gzip.open(_FIX / name, "rb").read().decode("utf-8", "replace")


def _netz() -> dict:
    netz = {
        _ANF: f"einsundeins_tarifuebersicht_all_net_flat_{_TAG}.html.gz",
        _UNL: f"einsundeins_tarifuebersicht_unlimited_{_TAG}.html.gz",
    }
    for t in _RASTER:
        netz[f"https://mobile.1und1.de/smartphones-{t}"] = (
            f"einsundeins_tarifraster_{t.replace('-', '_')}_{_TAG}.html.gz")
    return netz


class _Hole:
    """Liefert die gespeicherten Antworten; protokolliert jeden Abruf."""

    def __init__(self, fehlend=()):
        self.netz = _netz()
        self.fehlend = set(fehlend)
        self.abgerufen: list = []

    def __call__(self, url, kopfzeilen=None, **kw):
        self.abgerufen.append(url)
        if url in self.fehlend or url not in self.netz:
            return (404, "")
        return (200, _fixture(self.netz[url]))


def _basis():
    """Die Default-Tarif-Sätze zweier echter Geräteseiten, wie sie nach
    `_mit_sku` aussehen (sku_id aus dem Titel - hier nur ein Schlüssel)."""
    out = []
    for url, name in ((_IPHONE, "iphone_18_pro"),
                      (_S26U, "galaxy_s26_ultra")):
        for satz in E.lies_buendel(
                _fixture(f"einsundeins_produktseite_{name}_{_TAG}.html.gz"),
                url=url):
            out.append({**satz, "anbieter": "1&1", "sku_id": satz["titel"],
                        "quelle_url": url})
    return out


def _satz(saetze, titel_teil, tarif):
    treffer = [s for s in saetze
               if titel_teil in s["titel"] and s["tarif_name"] == tarif]
    assert len(treffer) == 1, (titel_teil, tarif, len(treffer))
    return treffer[0]


# ==========================================================================
# Die Lesarten
# ==========================================================================

def test_die_uebersichten_verlinken_sieben_geraeteraster():
    adressen = set()
    for url in (_ANF, _UNL):
        adressen.update(E.tarifraster_adressen(_fixture(_netz()[url]), url))
    assert adressen == {f"https://mobile.1und1.de/smartphones-{t}"
                        for t in _RASTER}
    # Die Warenkorb-Parameter reisen nicht mit.
    assert not any("?" in a for a in adressen)


def test_tarifdetails_je_tarif_aus_der_uebersicht():
    details = E.tarifdetails_je_tarif(_fixture(_netz()[_UNL]), _UNL)
    assert details["1&1 All-Net-Flat M"][1] == "tariff-anf-m-mvl"
    assert details["1&1 Unlimited on demand L"][1] == \
        "tariff-anf-xxl-unlimited-l-mvl"
    assert details["1&1 Unlimited XL"][1] == "tariff-anf-xxl-unlimited-xl-ovl"
    assert details["1&1 All-Net-Flat M"][0].startswith(
        "https://mobile.1und1.de/details-all-net-flat-preisliste?")


def test_das_raster_nennt_tarif_laufzeit_und_je_geraet_einen_preis():
    raster = E.lies_tarifraster(_fixture(_netz()[
        "https://mobile.1und1.de/smartphones-all-net-flat-m"]))
    assert raster["tarif_name"] == "1&1 All-Net-Flat M"
    assert len(raster["preise"]) == 43
    assert raster["preise"]["hw-apple-iphone-18-pro"] == (5499, 36)
    assert raster["preise"]["hw-samsung-galaxy-s26-ultra"] == (4999, 36)


def test_ein_raster_ohne_kachel_wirft():
    with pytest.raises(E.GeraeteAbrufFehler):
        E.lies_tarifraster("<html><body>umgebaut</body></html>")


def test_tarifname_ohne_volumenklammer():
    assert E.tarifname_bereinigt("1&amp;1 All-Net-Flat M (50 GB)") == \
        "1&1 All-Net-Flat M"
    assert E.tarifname_bereinigt("1&1 Unlimited XL (unlimited)") == \
        "1&1 Unlimited XL"
    assert E.tarifname_bereinigt("1&1 All-Net-Flat S") == "1&1 All-Net-Flat S"


def test_die_geraeteseite_nennt_vorauswahl_und_angezeigten_preis():
    saetze = _basis()
    iphone = [s for s in saetze if s["hw_id"] == "hw-apple-iphone-18-pro"]
    vor = [s for s in iphone if s["vorausgewaehlt"]]
    assert [s["speicher_gb"] for s in vor] == [256]
    assert vor[0]["angezeigt_monatlich"] == 49.99
    assert all(s["angezeigt_monatlich"] is None
               for s in iphone if not s["vorausgewaehlt"])
    # S26 Ultra: die Seite ZEIGT 44,99 (mit vorab angehakten Galaxy Buds 4),
    # die Preiskarte nennt 42,99 für das Gerät allein.
    s26 = next(s for s in saetze
               if s["hw_id"] == "hw-samsung-galaxy-s26-ultra"
               and s["vorausgewaehlt"])
    assert s26["angezeigt_monatlich"] == 44.99
    assert s26["buendel_monatlich"] == 42.99


# ==========================================================================
# ergaenze_tarifstufen()
# ==========================================================================

def test_alle_tarife_mal_alle_speichergroessen():
    saetze = _basis()
    hole = _Hole()
    neu = E.ergaenze_tarifstufen(hole, {}, saetze)
    # iPhone 18 Pro 4 Größen, S26 Ultra 3 Größen, sechs einheitliche Tarife
    # ausser dem Default: 7 x 5 = 35; dazu Unlimited XL je Gerät 1 Satz.
    assert neu == 7 * 5 + 2
    # Abrufe: zwei Übersichten, sieben Raster.
    assert len(hole.abgerufen) == 9
    tarife = {s["tarif_name"] for s in saetze}
    assert tarife == {"1&1 All-Net-Flat S", "1&1 All-Net-Flat M",
                      "1&1 All-Net-Flat L", "1&1 Unlimited on demand S",
                      "1&1 Unlimited on demand M", "1&1 Unlimited on demand L",
                      "1&1 Unlimited XL"}


def test_der_aufschlag_kommt_auf_die_preiskarte_der_groesse():
    saetze = _basis()
    E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    # 512 GB im Default-Tarif 56,99 (Preiskarte) + Aufschlag M 5,00.
    m512 = _satz(saetze, "iPhone 18 Pro 512 GB", "1&1 All-Net-Flat M")
    assert m512["buendel_monatlich"] == 61.99
    assert m512["laufzeit_monate"] == 36
    # Die Einmalzahlung steht nur fuer den Default-Tarif auf der Seite.
    assert m512["geraet_zuzahlung"] is None
    assert _satz(saetze, "iPhone 18 Pro 512 GB",
                 "1&1 All-Net-Flat S")["geraet_zuzahlung"] == 510.0
    assert m512["tarif_slug"] == "tariff-anf-m-mvl"
    assert m512["herleitung"] == E.HERLEITUNG_TARIFAUFSCHLAG
    assert m512["quelle_url"] == \
        "https://mobile.1und1.de/smartphones-all-net-flat-m"
    # Die vorausgewählte Größe trifft das Raster selbst (54,99).
    assert _satz(saetze, "iPhone 18 Pro 256 GB",
                 "1&1 All-Net-Flat M")["buendel_monatlich"] == 54.99
    assert _satz(saetze, "iPhone 18 Pro 256 GB",
                 "1&1 Unlimited on demand L")["buendel_monatlich"] == 64.99
    # Gegenprobe: der Default-Satz bleibt unangetastet.
    s512 = _satz(saetze, "iPhone 18 Pro 512 GB", "1&1 All-Net-Flat S")
    assert s512["buendel_monatlich"] == 56.99
    assert "herleitung" not in s512


def test_das_zubehoer_des_rasters_landet_nicht_im_preis():
    """Raster M zeigt für das S26 Ultra 49,99 - mit Galaxy Buds 4. Das
    Bündel ohne Zubehör: 42,99 + 5,00 = 47,99."""
    saetze = _basis()
    E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    satz = _satz(saetze, "Galaxy S26 Ultra 256 GB", "1&1 All-Net-Flat M")
    assert satz["buendel_monatlich"] == 47.99


def test_ein_geraeteabhaengiger_aufschlag_bleibt_bei_der_vorauswahl():
    """Unlimited XL: Apple +25,00, alle anderen +30,00 - der Aufschlag hängt
    am Gerät. Nur die vorausgewählte Größe, und die Einmalzahlungs-Karte
    des Default-Tarifs wird nicht übertragen."""
    saetze = _basis()
    E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    xl = [s for s in saetze if s["tarif_name"] == "1&1 Unlimited XL"]
    assert sorted((s["hw_id"], s["speicher_gb"], s["buendel_monatlich"])
                  for s in xl) == [
        ("hw-apple-iphone-18-pro", 256, 74.99),
        ("hw-samsung-galaxy-s26-ultra", 256, 72.99)]
    assert all(s["geraet_zuzahlung"] is None for s in xl)


def test_ohne_default_raster_wird_nichts_hergeleitet():
    saetze = _basis()
    vorher = len(saetze)
    neu = E.ergaenze_tarifstufen(
        _Hole(fehlend={"https://mobile.1und1.de/smartphones-all-net-flat-s"}),
        {}, saetze)
    assert neu == 0
    assert len(saetze) == vorher


def test_eine_unstimmige_gegenprobe_kostet_nur_dieses_geraet():
    saetze = _basis()
    for s in saetze:
        if s["hw_id"] == "hw-apple-iphone-18-pro" and s["vorausgewaehlt"]:
            s["angezeigt_monatlich"] = 48.99
    E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    assert not [s for s in saetze if s.get("herleitung")
                and s["hw_id"] == "hw-apple-iphone-18-pro"]
    # Gegenprobe: das andere Gerät bekommt seine Tarife.
    assert [s for s in saetze if s.get("herleitung")
            and s["hw_id"] == "hw-samsung-galaxy-s26-ultra"]


def test_ein_zweiter_lauf_verdoppelt_nichts():
    saetze = _basis()
    E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    anzahl = len(saetze)
    assert E.ergaenze_tarifstufen(_Hole(), {}, saetze) == 0
    assert len(saetze) == anzahl


def test_jeder_gelieferte_tarif_loest_im_echten_bestand_auf():
    bestand = Tarifbestand.aus_datei(_WURZEL / "data" / "state" / "tarife.jsonl")
    saetze = _basis()
    E.ergaenze_tarifstufen(_Hole(), {}, saetze)
    bilanz = aus_rohsaetzen(saetze, bestand, "2026-09-29")
    assert bilanz.ohne_tarif == 0, bilanz.offene_tarife
    assert len(bilanz.buendel) == len(saetze) == 7 + 37
    # Gegenprobe: der Name MIT Volumenklammer löst nicht auf - ohne die
    # Bereinigung wären die Sätze verworfen worden.
    assert bestand.loese("1&1", "1&1 All-Net-Flat M (50 GB)",
                         mit_geraet=True) is None


def test_der_haken_setzt_danach_die_gebuehr_auf_alle_tarife(monkeypatch):
    monkeypatch.setattr(E, "_GEBUEHR_ABSTAND", 0.0)
    saetze = _basis()
    hole = _Hole()
    iframe = _fixture("einsundeins_tarifdetails_anf_s.html.gz")

    def hole_mit_iframe(url, kopfzeilen=None, **kw):
        if "/details-" in url:
            hole.abgerufen.append(url)
            return (200, iframe)
        return hole(url, kopfzeilen=kopfzeilen)

    gesetzt = E.ergaenze_buendel(hole_mit_iframe, {}, saetze)
    assert gesetzt == len(saetze) == 44
    assert {s["anschlusspreis"] for s in saetze} == {39.9}
    # Ein Tarifdetails-Abruf je Tarif-Slug: sieben.
    assert len([u for u in hole.abgerufen if "/details-" in u]) == 7


def test_die_registry_traegt_den_kombinierten_haken():
    assert ADAPTER["einsundeins_buendel"].ergaenze_buendel is E.ergaenze_buendel
