"""Die Bündellesart der congstar-Tarifseite: Gerät×Tarif je PlanVariant (B3).

WAS HIER GEPRÜFT WIRD, UND WARUM ES EINE EIGENE DATEI IST
--------------------------------------------------------
Bis zum 08.09.2026 gab es Gerät×Tarif-Bündel für Vodafone (253), Telekom
(45) und o2 (63); congstar stand bei 0 — die Zahlweisen der GERÄTEseite
tragen nur die Hardware (`DevicePrice`-Objekte ohne Tarifpreis), der
Konfigurator mit Tarifwahl ist clientseitig. Die Bündelseiten congstars
sind die TARIFSEITEN unter /handytarife/allnet-flat-tarife/ (vier Stück,
von congstar selbst in der sitemap pages.xml genannt): im selben
Next.js-Flight-Payload stehen unter `prefetchedPlan.variants[]` Tarifpreis,
Bereitstellungspreis und je Gerät die Ratenzahlweisen — je Seite zwei
PlanVarianten (Tarif und Flex).

DIE FIXTURES SIND GESPEICHERTE ECHTE ABRUFE
--------------------------------------------
`congstar_tarifseite_allnet_flat_m.html.gz` (143 KB gzip) ist die Antwort
auf `/handytarife/allnet-flat-tarife/allnet-flat-m/` (08.09.2026, HTTP 200,
980 KB, Absender `TelcoRadar/1.0`, reiner HTTP-GET): PlanVariant 540
„Allnet Flat M" und 548 „Allnet Flat M Flex", je 4 Geräte mit zusammen
9 Speichergrößen — 18 Sätze.
`congstar_tarifseite_allnet_flat_s.html.gz` ist die S-Seite (PlanVariant
560 „Allnet Flat S") — ihr Blattname im Bestand lautet „Allnet Flat S
mit GB+", der Seiten-Titel trägt den Zusatz NICHT. Sie ist deshalb der
Fall, an dem die Namensauflösung scheitert und die PIB-Nummern-Brücke
entscheidet.

DIE EINE REGEL, AN DER DIESES PAKET SCHEITERN KANN
--------------------------------------------------
Im BÜNDEL gilt der Rabatt (`discounted`), im Barpreis gilt `listed` — für
den Preis-ohne-Vertrag-Adapter ist `discounted` die Falle (Differenz bis
252 €), hier ist es genau umgekehrt: Der Nachlass entsteht laut Fußnote
„Bei Abschluss der ANF M (24 Monate Laufzeit) … reduziert sich die
monatliche Rate der Hardware dauerhaft" — er gilt für genau den Abschluss,
den ein Bündel IST. Die Nachrechnung `oneTime.discounted +
n × recurring.discounted == total` ist Bedingung, nicht Protokoll.
"""
import gzip
import json
from pathlib import Path

import pytest

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete import (
    ADAPTER,
    GeraeteAbrufFehler,
    sammle_anbieter,
)
from telco_radar.collect.geraete.congstar import (
    ergaenze_pib_slug,
    lies_buendel,
)
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import Anbieter, Einstieg, lade_farben, lade_katalog
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarif_model import HOCH

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

_M_URL = "https://www.congstar.de/handytarife/allnet-flat-tarife/allnet-flat-m/"
_S_URL = "https://www.congstar.de/handytarife/allnet-flat-tarife/allnet-flat-s/"

_ROBOTS_FREI = (200, "User-agent: *\n")


def _fixture(name: str) -> str:
    pfad = _FIX / name
    if pfad.suffix == ".gz":
        return gzip.open(pfad, "rb").read().decode("utf-8", "replace")
    return pfad.read_text(encoding="utf-8")


def _saetze():
    return lies_buendel(_fixture("congstar_tarifseite_allnet_flat_m.html.gz"),
                        url=_M_URL)


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(_WURZEL)


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


# ==========================================================================
# lies_buendel(): Struktur der Sätze
# ==========================================================================

def test_achtunddreissig_saetze_aus_zwei_planvarianten_neun_speichern_zwei_laufzeiten():
    """Je PlanVariant (M und M Flex) 4 Geräte mit zusammen 9
    Speichergrößen - Farbvarianten sind dedupliziert, wie der Auftrag es
    verlangt: die Zahlweise ist bei jeder Farbe derselben Größe identisch
    (gemessen an beiden Fixtures). Seit P0-B2a kommt jede Speichergröße
    ZWEIMAL vor - einmal je erhobener Laufzeit (24 und 36 Monate)."""
    saetze = _saetze()
    assert len(saetze) == 36
    je_tarif = {}
    for s in saetze:
        je_tarif.setdefault(s["tarif_name"], []).append(s)
    assert set(je_tarif) == {"Allnet Flat M", "Allnet Flat M Flex"}
    assert all(len(v) == 18 for v in je_tarif.values())
    # Keine Dublette je (Tarif, Variante, Laufzeit): 4 Geräte mit zusammen
    # 9 Speichergrößen (256/512/1024 kommen je bei mehreren Geräten vor).
    for v in je_tarif.values():
        assert len({s["sku"] for s in v}) == 9
        assert len({(s["sku"], s["laufzeit_monate"]) for s in v}) == 18


def test_tarifname_slug_und_preise_kommen_aus_der_antwort():
    """M: Tarif 24 €/Monat (Aktion, listed 25), Bereitstellungspreis 0 €
    (listed 15); Flex: derselbe Monatspreis, 0 €. Die Pflichtblattnummer
    (540/548) ist der Slug - siehe Modulkopf von congstar.py."""
    saetze = _saetze()
    m = [s for s in saetze if s["tarif_name"] == "Allnet Flat M"]
    flex = [s for s in saetze if s["tarif_name"] == "Allnet Flat M Flex"]
    for s in m:
        assert s["tarif_slug"] == "540"
        assert s["tarif_monatlich"] == 24.0
        assert s["anschlusspreis"] == 0.0
    for s in flex:
        assert s["tarif_slug"] == "548"
        assert s["tarif_monatlich"] == 24.0
        assert s["anschlusspreis"] == 0.0
    assert {s["laufzeit_monate"] for s in saetze} == {24, 36}
    assert all(s["url"] == _M_URL for s in saetze)


def test_der_iphone_satz_nach_rechnung():
    """Vollständige Nachrechnung an einem konkreten Satz: iPhone 17 Pro
    512 GB, Allnet Flat M - 97 € Zuzahlung + 36 × 33,50 € Rate = 1303 €
    Ratengesamtbetrag (mit Rabatt), dazu 24 €/Monat Tarif."""
    s = next(x for x in _saetze() if "iPhone 17 Pro 512 GB" in x["titel"]
             and x["tarif_name"] == "Allnet Flat M"
             and x["laufzeit_monate"] == 36)
    assert s["geraet_zuzahlung"] == 97.0
    assert s["geraet_monatsrate"] == 33.5
    assert s["geraet_zuzahlung"] + 36 * s["geraet_monatsrate"] == \
        pytest.approx(1303.0, abs=0.005)
    assert s["farbe"] == "Cosmic Orange"
    assert s["speicher_gb"] == 512


def test_im_buendel_gilt_discounted_nicht_listed():
    """DIE eine Regel dieses Pakets. iPhone 17 Pro 512 GB im M-Bündel:
    Rate 33,50 € (discounted), nicht 40,00 € (listed - der Preis ohne die
    Tarifbindung). Umgekehrt zur Geräteseite, wo `listed` richtig ist."""
    s = next(x for x in _saetze() if "iPhone 17 Pro 512 GB" in x["titel"]
             and x["tarif_name"] == "Allnet Flat M"
             and x["laufzeit_monate"] == 36)
    assert s["geraet_monatsrate"] == 33.5
    assert s["geraet_monatsrate"] != 40.0


def test_jede_ratenform_geht_gegen_die_rohantwort_auf():
    """Die Probe ist Bedingung: je Satz muss Zuzahlung + Laufzeit × Rate
    dem `total` DERSELBEN Variante UND DERSELBEN Laufzeit in der
    Rohantwort entsprechen - hier nachgelesen über die Varianten-ID (sku),
    nicht dem gefilterten Satz geglaubt. Dazu die Gegenprobe auf
    discounted: `total` ist der Gesamtbetrag MIT Rabatten."""
    from telco_radar.collect.geraete.congstar import _nutzlast, _planvarianten
    text = _fixture("congstar_tarifseite_allnet_flat_m.html.gz")
    # Der Lookup Schluessel ist (Plan, Variante): dieselbe Variante steht in
    # BEIDEN PlanVarianten einer Seite - mit verschiedenen Zahlweisen (M
    # subventioniert die Rate staerker als M Flex). Nur ueber die Variante
    # zu schluesseln naehme die Zahlweise des LETZTEN Plans.
    roh_je_plan_sku: dict[tuple[str, str], dict] = {}
    for plan in _planvarianten(_nutzlast(text)):
        pid = str(plan.get("id"))
        for geraet in plan.get("devices") or []:
            for variante in geraet.get("variants") or []:
                roh_je_plan_sku[(pid, str(variante.get("id")))] = variante
    assert len(roh_je_plan_sku) >= 58, "Varianten-Lookup leer - Test prüft nichts"

    saetze = _saetze()
    assert len(saetze) == 36                # die Lookup-Zeile
    for s in saetze:
        variante = roh_je_plan_sku[(s["tarif_slug"], s["sku"])]
        zahlweise = next(
            z for z in variante["prices"]["paymentVariants"]
            if z.get("type") == "INSTALLMENT_PLAN"
            and z.get("subtype") == "UNSPECIFIED"
            and z.get("contractDuration") == s["laufzeit_monate"])
        assert s["geraet_zuzahlung"] + \
            s["laufzeit_monate"] * s["geraet_monatsrate"] == \
            pytest.approx(float(zahlweise["total"]), abs=0.005)
        assert s["geraet_monatsrate"] == \
            float(zahlweise["recurring"]["discounted"])


def test_ein_geraet_mit_einem_terabyte_traegt_1024_gb():
    """`size` des 1-TB-Galaxy S26 Ultra ist 1 - nur `referenceGB` trägt die
    Einheit. 1 GB wäre eine SKU, die kein Katalogeintrag trifft."""
    s = next(x for x in _saetze() if "S26 Ultra 1 TB" in x["titel"])
    assert s["speicher_gb"] == 1024
    assert s["geraet_zuzahlung"] == 169.0


def test_der_zustand_reist_als_condition_feld_mit():
    """Alle Varianten der Fixture sind NEW; `zustand_hinweis` trägt das
    rohe Feld weiter - die Einordnung leistet lies_listung (gleiche
    Verdrahtung wie im Listungsweg, QA-Befund B1: der Zustand ist eine
    PREISDIMENSION)."""
    saetze = _saetze()
    assert all(s["zustand_hinweis"] == "NEW" for s in saetze)


# ==========================================================================
# Was verworfen wird - und was wirft
# ==========================================================================

def test_kaputte_nutzlast_wirft():
    with pytest.raises(GeraeteAbrufFehler):
        lies_buendel("gar kein html")


def test_eine_seite_ohne_matrix_und_ohne_plan_wirft():
    """Eine Flight-Nutzlast mit Geraet, aber ohne Tarifmatrix und ohne
    Tarifseitenplan ist keine Buendelantwort - der Fehlerpfad, kein leeres
    Ergebnis. Gebaut aus der echten Produktseite, indem nur die zwei
    Schluessel der Matrix umbenannt werden."""
    roh = _fixture(_IPHONE17_HEUTE)
    kaputt = (roh.replace("prefetchedPlansWithDevicesPrices", "entferntA")
              .replace("prefetchedPlans\\\"", "entferntB\\\""))
    assert "prefetchedPlansWithDevicesPrices" not in kaputt
    with pytest.raises(GeraeteAbrufFehler, match="keine Buendelantwort"):
        lies_buendel(kaputt, url=_IPHONE17_URL)


# ==========================================================================
# Die PRODUKTseite traegt die ganze Tarifmatrix (29.09.2026)
# ==========================================================================
#
# `congstar_produkt_iphone17_20260929.html.gz` und
# `congstar_produkt_pixel11pro_20260929.html.gz` sind gespeicherte echte
# Abrufe vom 29.09.2026 (HTTP 200, TelcoRadar/1.0, reiner GET) von
# /geraete/apple/apple-iphone-17/ und /geraete/google/google-pixel-11-pro/.
# Bis dahin warf `lies_buendel` auf jeder Produktseite und congstar lieferte
# nur die vier Aufmachergeraete der Tarifseiten als Buendel (10 SKUs).

_IPHONE17_HEUTE = "congstar_produkt_iphone17_20260929.html.gz"
_PIXEL11PRO_HEUTE = "congstar_produkt_pixel11pro_20260929.html.gz"
_IPHONE17_URL = "https://www.congstar.de/geraete/apple/apple-iphone-17/"
_ACHT_TARIFE = {"Allnet Flat XS", "Allnet Flat XS Flex", "Allnet Flat S",
                "Allnet Flat S Flex", "Allnet Flat M", "Allnet Flat M Flex",
                "Allnet Flat L", "Allnet Flat L Flex"}


def _sichtbarer_text(html: str) -> str:
    """Der serverseitig gerenderte Text derselben Seite - das, was ein
    Mensch in der Voreinstellung sieht (erste Variante, Allnet Flat M)."""
    import re
    ohne_skripte = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " | ", ohne_skripte)
    text = re.sub(r"(\s*\|\s*)+", " | ", text)
    return re.sub(r"\s+", " ", text)


def test_die_produktseite_liefert_jeden_tarif_jeden_speicher_jede_laufzeit():
    for name, speicher in ((_IPHONE17_HEUTE, {256, 512}),
                           (_PIXEL11PRO_HEUTE, {256, 512})):
        saetze = lies_buendel(_fixture(name), url=_IPHONE17_URL)
        kombis = {(s["tarif_name"], s["speicher_gb"], s["laufzeit_monate"])
                  for s in saetze}
        erwartet = {(t, g, n) for t in _ACHT_TARIFE for g in speicher
                    for n in (24, 36)}
        assert kombis == erwartet, name
        assert len(saetze) == 32, name
        assert all(s["quelle"] == "congstar_produktseite" for s in saetze)
        # Jede PlanVariant verlinkt ihr eigenes Pflichtblatt - die Bruecke
        # zum Tarifbestand (Modulkopf) steht an jedem Satz.
        assert all(s["tarif_slug"] for s in saetze)


def test_congstar_bietet_mit_geraet_keine_xl_an():
    """Gemessen: die Produktseiten nennen in `prefetchedPlans` nur XS/S/M/L
    (+Flex). Taucht XL auf, soll dieser Test auffallen, nicht still fehlen."""
    for name in (_IPHONE17_HEUTE, _PIXEL11PRO_HEUTE):
        namen = {s["tarif_name"] for s in lies_buendel(_fixture(name))}
        assert not [n for n in namen if "XL" in n], name


def test_iphone17_256_gb_allnet_flat_m_24_monate_nach_rechnung():
    """Stichprobe am gespeicherten Abruf, per Hand aus der Nutzlast
    nachgelesen: Zuzahlung 19, Rate 39,75, Tarif 24, Anschluss 0."""
    saetze = lies_buendel(_fixture(_IPHONE17_HEUTE), url=_IPHONE17_URL)
    s = next(x for x in saetze if x["speicher_gb"] == 256
             and x["tarif_name"] == "Allnet Flat M"
             and x["laufzeit_monate"] == 24)
    assert (s["geraet_zuzahlung"], s["geraet_monatsrate"],
            s["tarif_monatlich"], s["anschlusspreis"], s["tarif_slug"]) \
        == (19.0, 39.75, 24.0, 0.0, "540")
    assert s["url"] == _IPHONE17_URL


def test_der_maximale_gesamtpreis_der_seite_ist_zuzahlung_plus_raten():
    """Gegenprobe gegen den SICHTBAREN Text derselben Antwort: die Seite
    zeigt in der Voreinstellung (Allnet Flat M, 36 Raten) den maximalen
    Gesamtpreis - er muss Zuzahlung + 36 x Rate des M-Satzes sein."""
    import re
    html = _fixture(_IPHONE17_HEUTE)
    treffer = re.search(r"wenn du dein Gerät behältst: \| ([\d.]+),(\d\d) €",
                        _sichtbarer_text(html))
    assert treffer, "Fixture ohne sichtbaren Gesamtpreis"
    seite = float(treffer.group(1).replace(".", "")) + int(treffer.group(2)) / 100
    s = next(x for x in lies_buendel(html) if x["speicher_gb"] == 256
             and x["tarif_name"] == "Allnet Flat M"
             and x["laufzeit_monate"] == 36)
    assert s["geraet_zuzahlung"] + 36 * s["geraet_monatsrate"] == seite == 973.0


def test_die_rate_haengt_am_tarif_wie_die_seite_es_sagt():
    """Die Seite nennt je Tarif "Zusätzlich N € Rabatt auf dein Gerät"
    gegenueber der Flex-Variante. Dieselbe Zahl muss aus den Raten folgen:
    36 x (Flex-Rate - Tarif-Rate). Wer die Matrix nicht je PlanVariant
    liest (etwa ueberall die M-Rate), faellt hier durch."""
    import re
    html = _fixture(_IPHONE17_HEUTE)
    text = _sichtbarer_text(html)
    saetze = [s for s in lies_buendel(html)
              if s["speicher_gb"] == 256 and s["laufzeit_monate"] == 36]
    rate = {s["tarif_name"]: s["geraet_monatsrate"] for s in saetze}
    raten = set()
    for stufe in ("XS", "S", "M", "L"):
        treffer = re.search(r"Zusätzlich (\d+) € Rabatt auf dein Gerät \| "
                            r"[\d ]+GB \| ([\d,]+) € \| mtl\. \| Allnet Flat "
                            + stufe + r" \|", text)
        assert treffer, stufe
        rabatt = 36 * (rate[f"Allnet Flat {stufe} Flex"]
                       - rate[f"Allnet Flat {stufe}"])
        assert rabatt == float(treffer.group(1)), stufe
        raten.add(rate[f"Allnet Flat {stufe}"])
    assert len(raten) == 4, "vier Tarife, vier verschiedene Raten"


def test_alle_acht_tarife_der_produktseite_loesen_gegen_den_echten_bestand():
    bestand = Tarifbestand.aus_datei(_WURZEL / "data" / "state" / "tarife.jsonl")
    ergaenze_pib_slug(bestand)
    rohsaetze = [{**s, "anbieter": "congstar",
                  "sku_id": f"sku-{s['speicher_gb']}", "quelle_url": s["url"]}
                 for s in lies_buendel(_fixture(_IPHONE17_HEUTE),
                                       url=_IPHONE17_URL)]
    bilanz = aus_rohsaetzen(rohsaetze, bestand, "2026-09-29")
    assert bilanz.ohne_tarif == 0, bilanz.offene_tarife
    assert len(bilanz.buendel) == 32
    assert {b.tarif_name for b in bilanz.buendel} == _ACHT_TARIFE
    assert all(b.tarif_id.startswith("congstar:") for b in bilanz.buendel)
    assert len({b.id for b in bilanz.buendel}) == 32, "Schluessel kollidieren"


def test_beide_ratenlaufzeiten_werden_erhoben():
    """P0-B2a: Je Variante stehen 24- und 36-Monats-Zahlweisen nebeneinander
    - seit der Bestandsschluessel die Laufzeit traegt (`tco_model.
    buendel_id`, B1), werden BEIDE erhoben, nicht nur die 36er. 18 Saetze
    (Modulkopf: 2 PlanVarianten x 9 Speichergroessen) werden zu 36 - jeder
    doppelt, einmal je Laufzeit."""
    saetze = _saetze()
    assert len(saetze) == 36
    laufzeiten = {s["laufzeit_monate"] for s in saetze}
    assert laufzeiten == {24, 36}
    je_sku_tarif: dict = {}
    for s in saetze:
        je_sku_tarif.setdefault((s["sku"], s["tarif_name"]), set()).add(
            s["laufzeit_monate"])
    assert len(je_sku_tarif) == 18
    assert all(v == {24, 36} for v in je_sku_tarif.values())


def test_die_24_monats_rate_ist_hoeher_als_die_36_monats_rate():
    """congstar finanziert zum Nulltarif: kuerzere Laufzeit heisst hoehere
    Rate, beide zum selben `total` (iPhone 17 Pro 512 GB, Allnet Flat M:
    1 + 97 + 36 x 33,50 = 1303 = 97 + 24 x 50,25)."""
    saetze = [s for s in _saetze() if "iPhone 17 Pro 512 GB" in s["titel"]
              and s["tarif_name"] == "Allnet Flat M"]
    nach_laufzeit = {s["laufzeit_monate"]: s for s in saetze}
    assert set(nach_laufzeit) == {24, 36}
    assert nach_laufzeit[36]["geraet_monatsrate"] == 33.5
    assert nach_laufzeit[24]["geraet_monatsrate"] == 50.25
    assert nach_laufzeit[36]["geraet_zuzahlung"] == \
        nach_laufzeit[24]["geraet_zuzahlung"] == 97.0
    for s in nach_laufzeit.values():
        assert s["geraet_zuzahlung"] + \
            s["laufzeit_monate"] * s["geraet_monatsrate"] == \
            pytest.approx(1303.0, abs=0.005)


def test_wird_eine_laufzeit_aus_der_antwort_entfernt_bleibt_die_andere(caplog):
    """Wird die 36-Monats-Zahlweise auf eine nicht erhobene Laufzeit
    gedreht - hier durch eine Textersetzung am ECHTEN Abruf, sonst kein
    Byte veraendert -, bleibt die 24-Monats-Zahlweise trotzdem ein Satz:
    eine kaputte oder fehlende Laufzeit verwirft nur sich selbst, nicht
    die andere.

    FIX3: und sie verschwindet nicht STILL. `_RATENLAUFZEITEN` ist eine
    Positivliste; eine 48-Monats-Zahlweise fiel bis zum 21.09.2026 ohne
    ein Wort heraus. Jetzt nennt das Protokoll sie samt Liste."""
    roh = _fixture("congstar_tarifseite_allnet_flat_m.html.gz")
    assert '\\"contractDuration\\":36' in roh, \
        "die Fixture muss 36-Monats-Zahlweisen tragen, sonst prüft der Test nichts"
    ohne_36 = roh.replace('\\"contractDuration\\":36',
                          '\\"contractDuration\\":48')
    with caplog.at_level("INFO",
                         logger="telco_radar.collect.geraete.congstar"):
        saetze = lies_buendel(ohne_36, url=_M_URL)
    assert len(saetze) == 18
    assert all(s["laufzeit_monate"] == 24 for s in saetze)
    uebergangen = [m for m in caplog.messages
                   if "48 Monate" in m and "uebergangen" in m]
    assert uebergangen, caplog.messages
    assert "[24, 36]" in uebergangen[0]


def test_eine_laufzeit_als_zeichenkette_ist_dieselbe_laufzeit(caplog):
    """FIX3: die Positivliste gilt fuer LAUFZEITEN, nicht fuer JSON-Typen.

    Kommt `contractDuration` als `"36"` statt als `36` - dieselbe Aussage,
    eine andere Schreibweise -, fiel die Zahlweise vorher stumm aus der
    Positivliste: 18 statt 36 Saetze, ohne Protokoll. Textersetzung am
    ECHTEN Abruf, sonst kein Byte veraendert."""
    roh = _fixture("congstar_tarifseite_allnet_flat_m.html.gz")
    assert '\\"contractDuration\\":36' in roh
    als_text = roh.replace('\\"contractDuration\\":36',
                           '\\"contractDuration\\":\\"36\\"')
    with caplog.at_level("INFO",
                         logger="telco_radar.collect.geraete.congstar"):
        saetze = lies_buendel(als_text, url=_M_URL)
    assert len(saetze) == 36
    assert {s["laufzeit_monate"] for s in saetze} == {24, 36}
    # Und die Laufzeit steht als ZAHL im Satz, nicht als Zeichenkette -
    # `buendel_id` und die Etiketten rechnen mit ihr.
    assert all(isinstance(s["laufzeit_monate"], int) for s in saetze)
    assert not [m for m in caplog.messages if "uebergangen" in m], \
        caplog.messages


def test_trade_in_wird_nicht_als_normaler_kauf_gehoben():
    """Die TRADE_IN-Zahlweise setzt die Einnahme eines Altgeräts voraus
    (ihr `benefit` nennt den Tauschbonus) - ihre niedrigere Rate wäre ein
    Preis, der nur mit einem zweiten Gerät gilt. Werden alle Zahlweisen zu
    TRADE_IN gedreht (Textersetzung am echten Abruf), gibt es keinen
    Satz."""
    roh = _fixture("congstar_tarifseite_allnet_flat_m.html.gz")
    assert '\\"subtype\\":\\"UNSPECIFIED\\"' in roh, \
        "die Fixture muss UNSPECIFIED-Zahlweisen tragen"
    nur_trade = roh.replace('\\"subtype\\":\\"UNSPECIFIED\\"',
                            '\\"subtype\\":\\"TRADE_IN\\"')
    assert lies_buendel(nur_trade, url=_M_URL) == []


# ==========================================================================
# Die PIB-Nummern-Brücke: tarif_slug -> buendel_slug am Bestandssatz
# ==========================================================================

def _bestand_mit_gb_namen():
    """Der Bestand, wie ihn der congstar-PIB-Lauf schreibt: der S-Tarif
    heißt im Blatt 'Allnet Flat S mit GB+' (tarif_id mit Zusatz), die
    Blattnummer steht in der dokument_url."""
    return Tarifbestand([
        {"tarif_id": "congstar:allnet-flat-s-mit-gb", "anbieter": "congstar",
         "name": "Allnet Flat S mit GB+", "grundgebuehr": 20.0,
         "dokument_url": "https://www.congstar.de/fileadmin/produktinformationsblatt/Produktinformationsblatt_560.pdf"},
        {"tarif_id": "congstar:allnet-flat-m", "anbieter": "congstar",
         "name": "Allnet Flat M", "grundgebuehr": 24.0,
         "dokument_url": "https://www.congstar.de/fileadmin/produktinformationsblatt/Produktinformationsblatt_540.pdf"},
    ])


def test_die_bruecke_setzt_buendelslug_aus_der_blattnummer():
    bestand = _bestand_mit_gb_namen()
    assert ergaenze_pib_slug(bestand) == 2
    s = bestand.je_id["congstar:allnet-flat-s-mit-gb"]
    assert s["buendel_slug"] == "560"


def test_der_s_tarif_loest_nur_ueber_die_bruecke():
    """Der Fall, für den die Brücke gebaut ist: Seiten-Titel 'Allnet Flat
    S', Blattname 'Allnet Flat S mit GB+' - über den Namen treffen sich
    die zwei nie. Ohne Brücke fällt der Satz unter 'ohne aufloesbaren
    Tarif', mit ihr löst er mit Güte HOCH."""
    roh = next(s for s in lies_buendel(
        _fixture("congstar_tarifseite_allnet_flat_s.html.gz"), url=_S_URL)
        if s["tarif_name"] == "Allnet Flat S")
    satz = {**roh, "anbieter": "congstar",
            "sku_id": "apple-iphone-17-pro-256gb-cosmic-orange",
            "quelle_url": roh["url"]}

    ohne = aus_rohsaetzen([dict(satz)], _bestand_mit_gb_namen(), "2026-09-08")
    assert ohne.buendel == [] and ohne.ohne_tarif == 1

    bestand = _bestand_mit_gb_namen()
    ergaenze_pib_slug(bestand)
    mit = aus_rohsaetzen([dict(satz)], bestand, "2026-09-08")
    assert len(mit.buendel) == 1
    assert mit.buendel[0].tarif_id == "congstar:allnet-flat-s-mit-gb"
    assert mit.buendel[0].tarif_id_guete == HOCH


def test_eine_doppelte_blattnummer_ist_keine_bruecke():
    """Zwei Blätter mit derselben Nummer wären eine Mehrdeutigkeit -
    derselbe Regel wie `ueber_slug`: zwei Treffer sind keine schwache
    Zuordnung, sondern gar keine."""
    bestand = Tarifbestand([
        {"tarif_id": "congstar:a", "anbieter": "congstar", "name": "A",
         "dokument_url": "https://www.congstar.de/fileadmin/produktinformationsblatt/Produktinformationsblatt_560.pdf"},
        {"tarif_id": "congstar:b", "anbieter": "congstar", "name": "B",
         "dokument_url": "https://www.congstar.de/x/Produktinformationsblatt_560.pdf"},
    ])
    assert ergaenze_pib_slug(bestand) == 0
    assert all(not str(s.get("buendel_slug") or "").strip()
               for s in bestand.je_id.values())


def test_gesetzte_slugs_und_fremde_anbieter_bleiben_unberuehrt():
    """o2-Kachel-Sätze tragen ihren Slug selbst (den anderen Weg); ein
    congstar-Satz MIT slug wird nicht überschrieben."""
    bestand = Tarifbestand([
        {"tarif_id": "o2:x", "anbieter": "o2", "name": "O2 Mobile",
         "dokument_url": "https://www.o2online.de/Produktinformationsblatt_999.pdf"},
        {"tarif_id": "congstar:c", "anbieter": "congstar", "name": "C",
         "buendel_slug": "alt",
         "dokument_url": "https://www.congstar.de/fileadmin/produktinformationsblatt/Produktinformationsblatt_555.pdf"},
    ])
    assert ergaenze_pib_slug(bestand) == 0
    assert bestand.je_id["congstar:c"]["buendel_slug"] == "alt"
    assert "buendel_slug" not in bestand.je_id["o2:x"]


def test_der_ganze_weg_bis_zum_buendel_mit_echtem_bestand():
    """Ende zu Ende gegen den echten tarife.jsonl-Bestand: die 36 Sätze
    der M-Fixture (P0-B2a: 18 × 2 Laufzeiten) lösen nach der Brücke alle
    auf (M und M Flex über den Namen, die Brücke stört das nicht)."""
    bestand = Tarifbestand.aus_datei(_WURZEL / "data" / "state" / "tarife.jsonl")
    ergaenze_pib_slug(bestand)
    rohsaetze = [{**s, "anbieter": "congstar",
                  "sku_id": f"sku-{i}", "quelle_url": s["url"]}
                 for i, s in enumerate(_saetze())]
    bilanz = aus_rohsaetzen(rohsaetze, bestand, "2026-09-08")
    assert len(bilanz.buendel) == 36, (
        f"{bilanz.ohne_tarif} ohne auflösbaren Tarif, "
        f"häufigste: {bilanz.offene_tarife}")
    assert all(b.tarif_id.startswith("congstar:") for b in bilanz.buendel)
    b = next(x for x in bilanz.buendel
             if x.tarif_name == "Allnet Flat M"
             and x.geraet_monatsrate == 33.5)
    assert b.tarif_id == "congstar:allnet-flat-m"
    assert b.tarif_monatlich == 24.0
    assert b.anschlusspreis == 0.0
    assert b.laufzeit_monate == 36


# ==========================================================================
# Die Verdrahtung: sammle_anbieter() am kind:buendel-Einstieg
# ==========================================================================

def _congstar_anbieter():
    return Anbieter(
        name="congstar", typ="discount", netz="Telekom",
        methode="congstar_next", basis_url="https://www.congstar.de",
        rate_limit_sekunden=0,
        einstiege=[Einstieg(url=_M_URL, label="Allnet Flat M (Bündel)",
                            kind="buendel")])


def test_sammle_anbieter_liefert_buendel_und_keine_listungen(katalog, farben):
    """`kind: buendel` heißt: die Sätze gehen an der Listungsstrecke
    vorbei in `bilanz.buendel` - und ihre sku_id ist über den KATALOG
    gebildet, damit die TCO-Tafel den Gerätenamen nachschlagen kann."""
    def hole(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        return 200, _fixture("congstar_tarifseite_allnet_flat_m.html.gz")

    waechter = RobotsWaechter(hole=hole)
    bilanz = sammle_anbieter(_congstar_anbieter(), katalog, farben, hole,
                             "2026-09-08", waechter)
    assert bilanz.status == "ok"
    assert bilanz.listungen == []
    assert len(bilanz.buendel) == 36
    b = bilanz.buendel[0]
    assert b["anbieter"] == "congstar"
    assert b["sku_id"]
    assert b["tarif_name"] in ("Allnet Flat M", "Allnet Flat M Flex")
    assert b["geraet_monatsrate"] is not None


def test_der_zustand_eines_buendels_kommt_aus_dem_condition_feld(katalog, farben):
    """Die _mit_sku-Verdrahtung (B3): congstar nennt den Zustand
    strukturiert (`condition`), nicht im Titel. Wird die Condition der
    Fixture zu REFURBISHED gedreht (nur dieses eine Feld, sonst kein Byte),
    trägt das Bündel 'refurbished' - vorher stand es still als 'neu' da
    (QA-Befund B1: der Zustand ist eine PREISDIMENSION)."""
    roh = _fixture("congstar_tarifseite_allnet_flat_m.html.gz")
    assert '\\"condition\\":\\"NEW\\"' in roh, \
        "die Fixture muss condition=NEW im escapten JSON tragen"
    veraendert = roh.replace('\\"condition\\":\\"NEW\\"',
                             '\\"condition\\":\\"REFURBISHED\\"')

    def hole(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        return 200, veraendert

    bilanz = sammle_anbieter(_congstar_anbieter(), katalog, farben, hole,
                             "2026-09-08", RobotsWaechter(hole=hole))
    assert bilanz.status == "ok" and bilanz.buendel
    assert all(b["zustand"] == "refurbished" for b in bilanz.buendel)


def test_adapter_registry_traegt_congstars_buendelhaken():
    adapter = ADAPTER["congstar_next"]
    assert adapter.lies_buendel is not None
    # Der Tarifname steht in derselben Antwort (prefetchedPlan.variants[].
    # title) - congstar braucht anders als Vodafone keinen Haken für die
    # Namensauflösung nach dem Sammeln, derselbe Grund wie bei der Telekom.
    assert adapter.loese_tarifnamen is None


def _congstar_aus_konfiguration():
    from telco_radar.geraete_config import lade_quellen
    quellen = lade_quellen(_WURZEL)
    return next(a for a in quellen.anbieter if a.name == "congstar")


def _sitemap_hole(abgerufen: list, seite: str):
    sitemap = _fixture("congstar_sitemap_devices_20260929.xml")

    def hole(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        if url.endswith("/sitemap/devices.xml"):
            return 200, sitemap
        abgerufen.append(url)
        return 200, seite
    return hole


def test_auf_den_produktseiten_wird_die_buendelmatrix_gelesen(katalog, farben):
    """Der ausgelieferte congstar-Eintrag gegen die echte Sitemap vom
    29.09.2026: jede Produktseite liefert ihre Buendel (hier ueberall die
    echte iPhone-17-Seite als Antwort). Bis 29.09.2026 stand
    `buendel_auf_produktseite=False`, und von Produktseiten kam kein
    einziges Buendel."""
    abgerufen: list = []
    anbieter = _congstar_aus_konfiguration()
    anbieter.rate_limit_sekunden = 0
    bilanz = sammle_anbieter(anbieter, katalog, farben,
                             _sitemap_hole(abgerufen, _fixture(_IPHONE17_HEUTE)),
                             "2026-09-29", RobotsWaechter(hole=_sitemap_hole(
                                 [], "")))
    assert bilanz.status == "ok"
    assert ADAPTER["congstar_next"].buendel_auf_produktseite is True
    assert {b["url"] for b in bilanz.buendel} == set(abgerufen)
    assert len(bilanz.buendel) == 32 * len(abgerufen)
    assert bilanz.vollstaendig


def test_die_sitemap_holt_keine_uhren_kopfhoerer_oder_tablets(katalog, farben):
    """56 Adressen in der echten Sitemap, 13 davon keine Smartphones
    (Apple Watch x5, AirPods x2, iPad x3, Galaxy Tab, Anio, Xplora) -
    `ohne_pfadmuster` laesst sie aus. Gegenprobe: derselbe Einstieg ohne
    Ausschluss holt alle 56."""
    anbieter = _congstar_aus_konfiguration()
    anbieter.rate_limit_sekunden = 0
    abgerufen: list = []
    sammle_anbieter(anbieter, katalog, farben,
                    _sitemap_hole(abgerufen, _fixture(_IPHONE17_HEUTE)),
                    "2026-09-29", RobotsWaechter(hole=_sitemap_hole([], "")))
    assert len(abgerufen) == 43
    for marke in ("watch", "airpods", "ipad", "galaxy-tab", "/anio/",
                  "/xplora/"):
        assert not [u for u in abgerufen if marke in u], marke
    assert any("apple-iphone-17/" in u for u in abgerufen)
    assert any("samsung-galaxy-xcover-7-ee" in u for u in abgerufen)

    einstieg = anbieter.einstiege[0]
    anbieter.einstiege = [Einstieg(url=einstieg.url, kind=einstieg.kind,
                                   pfadmuster=einstieg.pfadmuster)]
    ohne_ausschluss: list = []
    sammle_anbieter(anbieter, katalog, farben,
                    _sitemap_hole(ohne_ausschluss, _fixture(_IPHONE17_HEUTE)),
                    "2026-09-29", RobotsWaechter(hole=_sitemap_hole([], "")))
    assert len(ohne_ausschluss) == 56


def test_die_konfiguration_liest_buendel_von_den_produktseiten():
    anbieter = _congstar_aus_konfiguration()
    # Die Tarifseiten fuehren nur vier Aufmachergeraete - sie sind durch
    # die Produktseiten vollstaendig abgedeckt und keine Einstiege mehr.
    assert [e for e in anbieter.einstiege if e.kind == "buendel"] == []
    sitemap = [e for e in anbieter.einstiege if e.kind == "sitemap"]
    assert len(sitemap) == 1 and sitemap[0].ohne_pfadmuster
    # Der ehrliche Absender ist per Anbieter überschrieben (B2-Muster) -
    # sonst gingen die Produktseiten mit der globalen Chrome-Kennung hinaus.
    assert anbieter.user_agent.startswith("TelcoRadar/1.0")
