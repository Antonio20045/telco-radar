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
Ein Lauf ueber drei vorhandene Mitschnitte, Werte unveraendert:
1. `o2_vertiefung_iphone18pro.json.gz` - sieben Tarife, keiner mit "Plus";
   daraus entsteht die Referenz.
2. `o2_tarifdurchlauf_xiaomi17.json.gz` - Xiaomi 17 512 GB, Start im Tarif
   "O2 Mobile S" mit 36 Raten (der Referenz bekannt). Der Mitschnitt haelt
   je Tarif und Laufzeit eine Antwort, aber keine Adressen; jeder Link
   einer Xiaomi-Seite antwortet hier mit der Xiaomi-Seite genau dieses
   Tarifs und dieser Laufzeit, die Startadresse ist der Link "O2 Mobile S"
   einer 36-Raten-Seite. "Unlimited L Plus" fehlt im Mitschnitt: dieser
   Link bleibt unbeantwortet.
3. `o2_vertiefung_iphone17pro.json.gz` - zwoelf Tarife, Start in
   "Unlimited M Plus"; die Links seiner Startseite liegen im Mitschnitt.
Abgeleitete Antworten sind Kopien echter Antworten oder Felder: fuer die
Probe mit abweichender Rate antwortet der Xiaomi-Link "O2 Mobile L Plus mit
150 GB+" mit der echten 17-Pro-Antwort desselben Tarifs; fuer die
geraeteeigene Aktion traegt jede Xiaomi-Seite die echte Zeile
"einmaliger Anschlusspreis 0,00 EUR" ihrer Seite "Unlimited L" mit 36 Raten.
"""

import copy
import gzip
import json
import re
from pathlib import Path

import pytest

from telco_radar.collect.geraete import GeraeteAbrufFehler, o2

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_L_PLUS = "O2 Mobile Unlimited L Plus mit 300 MBit/s"
_L_PLUS_SLUG = "o2-mobile-unlimited-l-plus"
_L_PLUS_150 = "O2 Mobile L Plus mit 150 GB+"
_L_PLUS_150_SLUG = "o2-mobile-l-plus"
_XIAOMI_START = (36, "O2 Mobile S mit 15 GB+")
_ANSCHLUSS = "einmaliger Anschlusspreis"
_SEITEN_17PRO = 4
_SEITEN_XIAOMI = 2
_TAG = re.compile(r"<[^>]+>")
_RATEN = re.compile(r"-(\d+)x\w+$")


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
def xiaomi():
    return _lade("o2_tarifdurchlauf_xiaomi17.json.gz")["seiten"]


def _anzeige(option):
    return " ".join(_TAG.sub("", option.get("displayValue") or "").split())


def _uri(option):
    return ((option.get("selectCall") or {}).get("link") or {}).get("uri") or ""


def _schluessel(pv):
    raten = int(_RATEN.search(pv["hardware"]["offerName"]).group(1))
    gewaehlt = [o for o in pv["tariff"]["tariffOptions"] if o.get("selected")]
    assert len(gewaehlt) == 1
    return raten, _anzeige(gewaehlt[0])


def _links(pv, anzeige):
    treffer = [_uri(o) for o in pv["tariff"]["tariffOptions"] if _anzeige(o) == anzeige]
    assert len(treffer) == 1 and treffer[0]
    return treffer[0]


def _xiaomi(seiten):
    nach = {_schluessel(pv): pv for pv in seiten}
    assert len(nach) == len(seiten)
    antworten = {}
    for pv in seiten:
        raten, eigen = _schluessel(pv)
        for o in pv["tariff"]["tariffOptions"]:
            ziel = nach.get((raten, _anzeige(o)))
            if ziel is not None and _uri(o):
                antworten[_uri(o)] = json.dumps(ziel)
        for o in pv["hardware"]["paymentOptions"]:
            ziel = nach.get((int(re.search(r"\d+", o["displayValue"])[0]), eigen))
            if ziel is not None and _uri(o):
                antworten[_uri(o)] = json.dumps(ziel)
    start = _links(nach[(36, "O2 Mobile Unlimited L mit 300 MBit/s")], _XIAOMI_START[1])
    assert json.loads(antworten[start]) == nach[_XIAOMI_START]
    basis = {"url": start, "quelle": "o2_buendel", "strukturierter_name": "Xiaomi 17"}
    return antworten, basis


def _mit_aktion(seiten):
    """Jede Xiaomi-Seite traegt die echte Anschlusszeile mit 0,00 EUR."""
    vorbild = {_schluessel(pv): pv for pv in seiten}[
        (36, "O2 Mobile Unlimited L mit 300 MBit/s")
    ]
    null = [
        e
        for e in vorbild["priceSummary"]["nonRecurringChargesListEntries"]
        if e["description"] == _ANSCHLUSS
    ]
    assert len(null) == 1 and null[0]["amount"].startswith("0,00")
    out = copy.deepcopy(seiten)
    for pv in out:
        eintraege = pv["priceSummary"]["nonRecurringChargesListEntries"]
        for i, e in enumerate(eintraege):
            if e["description"] == _ANSCHLUSS:
                eintraege[i] = copy.deepcopy(null[0])
    return out


def _katalog(m):
    return o2.lies_buendel(json.dumps(m["katalog"]))


def _start_17pro(m17):
    return o2.lies_konfiguration(m17["antworten"][_katalog(m17)[0]["url"]])


def _drei_geraete(m18, m17, xiaomi_seiten):
    xa, xbasis = _xiaomi(xiaomi_seiten)
    antworten = {**m18["antworten"], **xa, **m17["antworten"]}
    assert len(antworten) == len(m18["antworten"]) + len(xa) + len(m17["antworten"])
    return antworten, _katalog(m18) + [xbasis] + _katalog(m17)


def _lauf(antworten, rohsaetze, weiter=None, status=404):
    protokoll, z = [], {}

    def hole(url):
        protokoll.append(url)
        if url not in antworten:
            raise GeraeteAbrufFehler("nicht im Mitschnitt", status=status)
        return antworten[url]

    return o2.vertiefe_buendel(hole, rohsaetze, weiter, z), protokoll, z


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


def _l_plus_256_24(pro17):
    return [
        (s["geraet_monatsrate"], s["tarif_monatlich"])
        for s in pro17
        if (s["speicher_gb"], s["laufzeit_monate"], s["tarif_slug"])
        == (256, 24, _L_PLUS_SLUG)
    ]


def test_zweites_geraet_bekommt_den_tarif_nach_einer_probe(m18, m17, xiaomi):
    antworten, rohsaetze = _drei_geraete(m18, m17, xiaomi)
    saetze, protokoll, z = _lauf(antworten, rohsaetze)
    allein17, _, _ = _lauf(m17["antworten"], _katalog(m17))
    allein18, _, _ = _lauf(m18["antworten"], _katalog(m18))

    pro17 = _modell(saetze, "Apple iPhone 17 Pro")
    assert sorted(map(_kennung, pro17)) == sorted(map(_kennung, allein17))
    assert len(pro17) == 48
    assert _l_plus_256_24(pro17) == [(54.5, 29.99)]
    assert round(sum(_l_plus_256_24(pro17)[0]), 2) == 84.49
    pro18 = _modell(saetze, "Apple iPhone 18 Pro")
    assert sorted(map(_kennung, pro18)) == sorted(map(_kennung, allein18))

    l_plus_17 = _links(_start_17pro(m17), _L_PLUS)
    assert protokoll.count(l_plus_17) == 1
    assert z["referenz_tarife"] == 7
    assert z["probe_unlesbar"] == 1
    assert z["ohne_referenz"] == _SEITEN_XIAOMI
    pro_x = _modell(saetze, "Xiaomi 17")
    assert len(pro_x) == _SEITEN_XIAOMI * 11
    assert _L_PLUS_SLUG not in {s["tarif_slug"] for s in pro_x}


def test_probe_mit_abweichender_rate_bleibt_ohne_referenz(m18, m17, xiaomi):
    antworten, rohsaetze = _drei_geraete(m18, m17, xiaomi)
    start17 = _start_17pro(m17)
    link17 = _links(start17, _L_PLUS_150)
    nach = {_schluessel(pv): pv for pv in xiaomi}
    link_x = _links(nach[_XIAOMI_START], _L_PLUS_150)
    antworten[link_x] = m17["antworten"][link17]
    fremd = o2.saetze_aus_konfiguration(
        o2.lies_konfiguration(antworten[link_x]), {}, None, "u"
    )[0]
    eigen = o2.saetze_aus_konfiguration(nach[_XIAOMI_START], {}, None, "u")[0]
    assert fremd["tarif_slug"] == _L_PLUS_150_SLUG
    assert fremd["laufzeit_monate"] == eigen["laufzeit_monate"] == 36
    assert fremd["geraet_monatsrate"] != eigen["geraet_monatsrate"]

    saetze, protokoll, z = _lauf(antworten, rohsaetze)
    pro17 = _modell(saetze, "Apple iPhone 17 Pro")
    assert protokoll.count(link_x) == 1
    assert link17 not in protokoll
    assert not [s for s in pro17 if s["tarif_slug"] == _L_PLUS_150_SLUG]
    assert _l_plus_256_24(pro17) == [(54.5, 29.99)]
    assert len(pro17) == _SEITEN_17PRO * 11
    assert z["probe_verworfen"] == 1
    assert z["ohne_referenz"] == 2 * _SEITEN_XIAOMI + _SEITEN_17PRO


def test_ohne_zeit_keine_probe(m18, m17, xiaomi):
    antworten, rohsaetze = _drei_geraete(m18, m17, xiaomi)
    protokoll, z = [], {}

    def weiter():
        return sum(u in m17["antworten"] for u in protokoll) < _SEITEN_17PRO

    def hole(url):
        protokoll.append(url)
        if url not in antworten:
            raise GeraeteAbrufFehler("nicht im Mitschnitt", status=404)
        return antworten[url]

    saetze = o2.vertiefe_buendel(hole, rohsaetze, weiter, z)
    assert _links(_start_17pro(m17), _L_PLUS) not in protokoll
    assert sum(u in m17["antworten"] for u in protokoll) == _SEITEN_17PRO
    assert z["probe_frist"] == _SEITEN_17PRO
    pro17 = _modell(saetze, "Apple iPhone 17 Pro")
    assert _l_plus_256_24(pro17) == []
    assert len(pro17) == _SEITEN_17PRO * 11


def _falsch_gegen_die_seite(saetze, m17):
    """17 Pro 256 GB / 36 Raten: jeder Satz gegen die echte Seite seines Tarifs."""
    echt = {}
    for text in m17["antworten"].values():
        pv = o2.lies_konfiguration(text)
        s = o2.saetze_aus_konfiguration(pv, {}, None, "u")[0]
        if (s["speicher_gb"], s["laufzeit_monate"]) == (256, 36):
            echt[s["tarif_slug"]] = s
    assert len(echt) == 12
    return [
        (s["tarif_slug"], s["anschlusspreis"], echt[s["tarif_slug"]]["anschlusspreis"])
        for s in _modell(saetze, "Apple iPhone 17 Pro")
        if (s["speicher_gb"], s["laufzeit_monate"]) == (256, 36)
        and _kennung(s)[2:] != _kennung(echt[s["tarif_slug"]])[2:]
    ]


def test_aktion_beim_xiaomi_schreibt_nichts_fuer_andere_geraete(m18, m17, xiaomi):
    antworten, rohsaetze = _drei_geraete(m18, m17, _mit_aktion(xiaomi))
    saetze, protokoll, z = _lauf(antworten, rohsaetze)
    assert _falsch_gegen_die_seite(saetze, m17) == []
    pro_x = _modell(saetze, "Xiaomi 17")
    assert pro_x and all("herleitung" not in s for s in pro_x)
    assert {s["anschlusspreis"] for s in pro_x} == {0.0}
    assert z["referenz_widerspricht"] >= 1
    assert "referenz_probe" not in z

    gegen, _, _ = _lauf(*_drei_geraete(m18, m17, xiaomi))
    assert _falsch_gegen_die_seite(gegen, m17) == []
    assert len(_modell(gegen, "Apple iPhone 17 Pro")) == 48


def test_unlesbare_probe_sperrt_den_tarif_nicht(m18, m17, xiaomi):
    antworten, rohsaetze = _drei_geraete(m18, m17, xiaomi)
    saetze, protokoll, z = _lauf(antworten, rohsaetze, status=503)
    assert (z["unlesbar"], z["probe_unlesbar"]) == (1, 1)
    assert _l_plus_256_24(_modell(saetze, "Apple iPhone 17 Pro")) == [(54.5, 29.99)]

    ohne = dict(antworten)
    del ohne[_links(_start_17pro(m17), _L_PLUS)]
    saetze, protokoll, z = _lauf(ohne, rohsaetze, status=503)
    assert z["probe_unlesbar"] == _proben_je_anzeige() == 2
    assert z["unlesbar"] == 2
    assert _l_plus_256_24(_modell(saetze, "Apple iPhone 17 Pro")) == []
    assert z["ohne_referenz"] == _SEITEN_XIAOMI + _SEITEN_17PRO


def _proben_je_anzeige():
    from telco_radar.collect.geraete.o2_referenz import PROBEN_JE_ANZEIGE

    return PROBEN_JE_ANZEIGE
