"""o2: ein zweiter Referenzdurchlauf, wenn kein Geraet mehr proben darf.

DER BEFUND (17.11.2026, gemessen am Original)
---------------------------------------------
o2 teilt seinen Buendelkatalog in zwei Haelften, und seit dem Abend des
13.11.2026 fallen sie genau mit der Referenz zusammen:

* 8 von 70 Katalogsaetzen stehen in einem Tarif OHNE "Plus" ("O2 Mobile on
  Demand M mit 50 GB+"); ihre Produktseite bietet SIEBEN Tarife. Gemessen
  am 17.11.2026: Samsung Galaxy A27 5G, Xiaomi Redmi Note 17 5G, Apple
  iPhone 18 Pro Max - jeweils sieben Optionen.
* die anderen 62 stehen in einem "Plus"-Tarif und bieten ZWOELF.

Die Referenz entsteht am ersten Geraet (`nach_prioritaet` stellt die
Pflichtmodelle vorn, das iPhone 18 Pro Max also an den Anfang) und hat
damit sieben Tarife. `ergaenze` darf nur an einer Antwort proben, deren
eigener Tarif schon in der Referenz steht - das sind genau die Geraete mit
sieben Optionen, die nichts Neues kennen. Die 62 Geraete, die die fuenf
fehlenden Tarife kennen, widersprechen der Referenz und sind damit vom
Proben ausgeschlossen. Lauf 44066902790 (17.11.2026): `referenz_tarife` 7,
`referenz_widerspricht` 153 von 185 gemessenen Antworten, 192 abgeleitete
Saetze - am 13.11.2026 morgens waren es mit `referenz_tarife` 12 noch 1864.

DIE ANTWORT
-----------
Ein ZWEITER vollstaendiger Tarifdurchlauf am ersten widersprechenden
Geraet, und er ergaenzt nur, wenn er in ALLEN gemeinsamen Anzeigen Slug und
Anschlusspreis der Referenz bestaetigt. Damit bleibt der Schutz des
Befundes vom 07.10.2026 bestehen: ein Geraet mit eigener Aktion schreibt
nichts fuer andere Geraete fest - seine abweichenden Anschlusspreise
widersprechen der Referenz und der ganze Durchlauf faellt weg.

Die Mitschnitte sind dieselben echten Abrufe wie in
`test_geraete_o2_referenzprobe.py` (29.09.2026, TelcoRadar/1.0): das
iPhone 18 Pro mit sieben Tarifen als Referenz, das iPhone 17 Pro mit
zwoelf als das widersprechende Geraet. Nur diese zwei Geraete laufen hier -
ohne das Xiaomi, dessen eigener Tarif der Referenz bekannt ist und das
deshalb proben darf. Genau diese Lage hat der Katalog seit dem 13.11.2026.
"""

import gzip
import json
import re
from pathlib import Path

import pytest

from telco_radar.collect.geraete import GeraeteAbrufFehler, o2
from telco_radar.collect.geraete.o2_referenz import (
    DURCHLAEUFE_JE_LAUF,
    DURCHLAUF_ABRUF,
    DURCHLAUF_ERGAENZT,
    DURCHLAUF_VERWORFEN,
)

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_ANSCHLUSS = "einmaliger Anschlusspreis"
_TAG = re.compile(r"<[^>]+>")
_SEITEN_17PRO = 4
_TARIFE_18PRO = 7
_TARIFE_17PRO = 12
_L_PLUS_SLUG = "o2-mobile-unlimited-l-plus"


def _lade(name):
    with gzip.open(_FIX / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def m18():
    return _lade("o2_vertiefung_iphone18pro.json.gz")


@pytest.fixture(scope="module")
def m17():
    return _lade("o2_vertiefung_iphone17pro.json.gz")


def _anzeige(option):
    return " ".join(_TAG.sub("", option.get("displayValue") or "").split())


def _katalog(m):
    return o2.lies_buendel(json.dumps(m["katalog"]))


def _lauf(antworten, rohsaetze):
    protokoll, z = [], {}

    def hole(url):
        protokoll.append(url)
        if url not in antworten:
            raise GeraeteAbrufFehler("nicht im Mitschnitt", status=404)
        return antworten[url]

    return o2.vertiefe_buendel(hole, rohsaetze, None, z), protokoll, z


def _zwei_geraete(m18, m17):
    antworten = {**m18["antworten"], **m17["antworten"]}
    assert len(antworten) == len(m18["antworten"]) + len(m17["antworten"])
    return antworten, _katalog(m18) + _katalog(m17)


def _modell(saetze, name):
    return [s for s in saetze if s["strukturierter_name"] == name]


def _mit_aktion(antworten, m17):
    """Jede Seite des 17 Pro traegt 0,00 EUR Anschlusspreis - eine Aktion,
    die nur fuer dieses Geraet gilt. Die Zeile ist die echte Zeile einer
    Seite desselben Mitschnitts, nur ihr Betrag wird uebernommen."""
    out = dict(antworten)
    for url, text in m17["antworten"].items():
        pv = o2.lies_konfiguration(text)
        geaendert = 0
        for e in pv["priceSummary"]["nonRecurringChargesListEntries"]:
            if e["description"] == _ANSCHLUSS:
                e["amount"] = "0,00 EUR"
                geaendert += 1
        assert geaendert == 1
        out[url] = json.dumps(pv)
    return out


def test_referenz_am_ersten_geraet_kennt_nur_sieben_tarife(m18, m17):
    """Die Lage: sieben Tarife am Referenzgeraet, zwoelf am zweiten."""
    start18 = o2.lies_konfiguration(m18["antworten"][_katalog(m18)[0]["url"]])
    start17 = o2.lies_konfiguration(m17["antworten"][_katalog(m17)[0]["url"]])
    assert len(start18["tariff"]["tariffOptions"]) == _TARIFE_18PRO
    assert len(start17["tariff"]["tariffOptions"]) == _TARIFE_17PRO
    eigen17 = [o for o in start17["tariff"]["tariffOptions"] if o.get("selected")]
    assert len(eigen17) == 1
    assert _anzeige(eigen17[0]) not in {
        _anzeige(o) for o in start18["tariff"]["tariffOptions"]
    }


def test_widersprechendes_geraet_bekommt_alle_tarife(m18, m17):
    antworten, rohsaetze = _zwei_geraete(m18, m17)
    saetze, _, z = _lauf(antworten, rohsaetze)

    pro17 = _modell(saetze, "Apple iPhone 17 Pro")
    assert len(pro17) == _SEITEN_17PRO * _TARIFE_17PRO
    assert _L_PLUS_SLUG in {s["tarif_slug"] for s in pro17}
    assert z["referenz_tarife"] == _TARIFE_17PRO
    assert z[DURCHLAUF_ABRUF] == 1
    assert z[DURCHLAUF_ERGAENZT] == _TARIFE_17PRO - _TARIFE_18PRO
    assert DURCHLAUF_VERWORFEN not in z

    allein18 = _modell(saetze, "Apple iPhone 18 Pro")
    gegen, _, _ = _lauf(m18["antworten"], _katalog(m18))
    assert len(allein18) == len(gegen) == 8 * _TARIFE_18PRO


def test_eigene_aktion_verwirft_den_ganzen_durchlauf(m18, m17):
    antworten, rohsaetze = _zwei_geraete(m18, m17)
    saetze, _, z = _lauf(_mit_aktion(antworten, m17), rohsaetze)

    pro17 = _modell(saetze, "Apple iPhone 17 Pro")
    assert {s["anschlusspreis"] for s in pro17} == {0.0}
    assert all("herleitung" not in s for s in pro17)
    assert len(pro17) == _SEITEN_17PRO
    assert z["referenz_tarife"] == _TARIFE_18PRO
    assert z[DURCHLAUF_VERWORFEN] == 1
    assert DURCHLAUF_ERGAENZT not in z


def test_hoechstens_zwei_durchlaeufe_je_lauf(m18, m17):
    """Der Deckel ist eine benannte Konstante, keine Zahl im Code."""
    assert DURCHLAEUFE_JE_LAUF == 2
    antworten, rohsaetze = _zwei_geraete(m18, m17)
    _, _, z = _lauf(_mit_aktion(antworten, m17), rohsaetze)
    assert z[DURCHLAUF_ABRUF] <= DURCHLAEUFE_JE_LAUF - 1
