"""o2: ein Tarif, den der Referenzdurchlauf des ersten Geraets nicht kannte.

DER BEFUND (07.10.2026)
-----------------------
o2 bietet das iPhone 17 Pro 256 GB mit 24 Raten im Tarif "O2 Mobile
Unlimited L Plus mit 300 MBit/s" fuer 84,49 EUR im Monat an (54,50 Geraet
plus 29,99 Tarif). In `data/state/geraete_tco.json` fehlte dieser Tarif bei
allen 94 o2-Geraeten. `vertiefe_buendel` baute die Referenz nur einmal aus
dem Tarifdurchlauf des ersten Geraets und verwarf jede Option, die dort
nicht vorkam, als `ohne_referenz`.

DIE FIXTURES SIND GESPEICHERTE ECHTE ABRUFE (29.09.2026, TelcoRadar/1.0)
-------------------------------------------------------------------------
Der Lauf hier besteht aus zwei vorhandenen Mitschnitten, unveraendert
nebeneinandergelegt: zuerst `o2_vertiefung_iphone18pro.json.gz` (sieben
Tarife, keiner mit "Plus"), dann `o2_vertiefung_iphone17pro.json.gz`
(zwoelf Tarife, gemessen in "Unlimited M Plus"). Die Links der fuenf
Plus-Tarife der 17-Pro-Startseite fuehren auf Antworten, die im 17-Pro-
Mitschnitt liegen. Fuer die Probe mit abweichender Rate antwortet der
Link "O2 Mobile L Plus mit 150 GB+" mit einer Kopie der echten Antwort
Xiaomi 17 512 GB mit 36 Raten in genau diesem Tarif
(`o2_tarifdurchlauf_xiaomi17.json.gz`): Anzeige gleich, Geraeterate eines
anderen Geraets.
"""

import gzip
import json
from pathlib import Path

import pytest

from telco_radar.collect.geraete import GeraeteAbrufFehler, o2

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_L_PLUS = "O2 Mobile Unlimited L Plus mit 300 MBit/s"
_L_PLUS_SLUG = "o2-mobile-unlimited-l-plus"
_L_PLUS_150 = "O2 Mobile L Plus mit 150 GB+"
_L_PLUS_150_SLUG = "o2-mobile-l-plus"
_PLUS_UNBEKANNT = (
    _L_PLUS,
    "O2 Mobile Unlimited S Special Plus mit 15 MBit/s",
    _L_PLUS_150,
    "O2 Mobile on Demand M Plus mit 50 GB+",
)
_SEITEN_17PRO = 4


def _lade(name):
    with gzip.open(_FIX / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def m18():
    return _lade("o2_vertiefung_iphone18pro.json.gz")


@pytest.fixture(scope="module")
def m17():
    return _lade("o2_vertiefung_iphone17pro.json.gz")


@pytest.fixture(scope="module")
def xiaomi_l_plus_150():
    seiten = _lade("o2_tarifdurchlauf_xiaomi17.json.gz")["seiten"]
    treffer = [
        pv
        for pv in seiten
        if pv["hardware"]["offerName"].endswith("-36xhigh")
        and o2.saetze_aus_konfiguration(pv, {}, None, "u")[0]["tarif_slug"]
        == _L_PLUS_150_SLUG
    ]
    assert len(treffer) == 1
    return treffer[0]


def _katalog(m):
    return o2.lies_buendel(json.dumps(m["katalog"]))


def _start_17pro(m17):
    return o2.lies_konfiguration(m17["antworten"][_katalog(m17)[0]["url"]])


def _links(start, anzeigen):
    out = {}
    for option in start["tariff"]["tariffOptions"]:
        anzeige = " ".join(
            option["displayValue"].replace("<sub>", "").replace("</sub>", "").split()
        )
        if anzeige in anzeigen:
            out[anzeige] = option["selectCall"]["link"]["uri"]
    assert set(out) == set(anzeigen)
    return out


def _lauf(antworten, rohsaetze, weiter=None):
    protokoll, z = [], {}

    def hole(url):
        protokoll.append(url)
        if url not in antworten:
            raise GeraeteAbrufFehler("nicht im Mitschnitt", status=404)
        return antworten[url]

    return o2.vertiefe_buendel(hole, rohsaetze, weiter, z), protokoll, z


def _zwei_geraete(m18, m17):
    antworten = {**m18["antworten"], **m17["antworten"]}
    assert len(antworten) == len(m18["antworten"]) + len(m17["antworten"])
    return antworten, _katalog(m18) + _katalog(m17)


def _modell(saetze, name):
    return [s for s in saetze if s["strukturierter_name"] == name]


def _kennung(s):
    return (
        s["speicher_gb"],
        s["laufzeit_monate"],
        s["tarif_slug"],
        s["tarif_name"],
        s["tarif_monatlich"],
        s["geraet_monatsrate"],
        s["geraet_zuzahlung"],
        s["anschlusspreis"],
    )


def test_zweites_geraet_bekommt_den_tarif_nach_einer_probe(m18, m17):
    antworten, rohsaetze = _zwei_geraete(m18, m17)
    saetze, protokoll, z = _lauf(antworten, rohsaetze)
    allein17, _, _ = _lauf(m17["antworten"], _katalog(m17))
    allein18, _, _ = _lauf(m18["antworten"], _katalog(m18))

    pro17 = _modell(saetze, "Apple iPhone 17 Pro")
    assert sorted(map(_kennung, pro17)) == sorted(map(_kennung, allein17))
    assert len(pro17) == 48
    l_plus = [
        s
        for s in pro17
        if (s["speicher_gb"], s["laufzeit_monate"], s["tarif_slug"])
        == (256, 24, _L_PLUS_SLUG)
    ]
    assert len(l_plus) == 1
    assert (l_plus[0]["geraet_monatsrate"], l_plus[0]["tarif_monatlich"]) == (
        54.5,
        29.99,
    )
    assert round(l_plus[0]["geraet_monatsrate"] + l_plus[0]["tarif_monatlich"], 2) == (
        84.49
    )

    pro18 = _modell(saetze, "Apple iPhone 18 Pro")
    assert sorted(map(_kennung, pro18)) == sorted(map(_kennung, allein18))

    proben = _links(_start_17pro(m17), _PLUS_UNBEKANNT)
    assert all(protokoll.count(u) == 1 for u in proben.values())
    assert len(protokoll) == len(m18["antworten"]) + _SEITEN_17PRO + len(proben)
    assert set(protokoll) <= set(antworten)
    assert (z["referenz_tarife"], z["referenz_probe"], z["referenz_ergaenzt"]) == (
        7,
        4,
        5,
    )
    assert "ohne_referenz" not in z


def test_probe_mit_abweichender_rate_bleibt_ohne_referenz(m18, m17, xiaomi_l_plus_150):
    antworten, rohsaetze = _zwei_geraete(m18, m17)
    link = _links(_start_17pro(m17), (_L_PLUS_150,))[_L_PLUS_150]
    antworten[link] = json.dumps(xiaomi_l_plus_150)

    fremd = o2.saetze_aus_konfiguration(xiaomi_l_plus_150, {}, None, "u")[0]
    eigen = o2.saetze_aus_konfiguration(_start_17pro(m17), {}, None, "u")[0]
    assert fremd["tarif_name"].startswith(_L_PLUS_150)
    assert (fremd["laufzeit_monate"], eigen["laufzeit_monate"]) == (36, 36)
    assert fremd["geraet_monatsrate"] != eigen["geraet_monatsrate"]

    saetze, protokoll, z = _lauf(antworten, rohsaetze)
    pro17 = _modell(saetze, "Apple iPhone 17 Pro")
    assert protokoll.count(link) == 1
    assert not [s for s in pro17 if s["tarif_slug"] == _L_PLUS_150_SLUG]
    assert len([s for s in pro17 if s["tarif_slug"] == _L_PLUS_SLUG]) == 4
    assert len(pro17) == _SEITEN_17PRO * 11
    assert z["probe_verworfen"] == 1
    assert z["ohne_referenz"] == _SEITEN_17PRO
    assert z["referenz_ergaenzt"] == 4


def test_ohne_zeit_keine_probe(m18, m17):
    antworten, rohsaetze = _zwei_geraete(m18, m17)
    protokoll = []

    def weiter():
        return sum(u in m17["antworten"] for u in protokoll) < _SEITEN_17PRO

    z = {}

    def hole(url):
        protokoll.append(url)
        return antworten[url]

    saetze = o2.vertiefe_buendel(hole, rohsaetze, weiter, z)
    proben = _links(_start_17pro(m17), _PLUS_UNBEKANNT)
    assert not set(proben.values()) & set(protokoll)
    assert sum(u in m17["antworten"] for u in protokoll) == _SEITEN_17PRO
    assert z["probe_frist"] == _SEITEN_17PRO
    assert "referenz_probe" not in z
    pro17 = _modell(saetze, "Apple iPhone 17 Pro")
    assert len(pro17) == _SEITEN_17PRO
    assert all("herleitung" not in s for s in pro17)
    assert len(_modell(saetze, "Apple iPhone 18 Pro")) == 56
