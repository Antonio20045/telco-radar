"""o2: die Vertiefung ruft den Knopf "Einmalzahlung Gerät" nicht ab.

BEFUND 20.11.2026 (Geräte-Lauf, Rohlog): o2 führt je Speicher neben "36 Monate"
und "24 Monate" einen dritten Zahlungsknopf "Einmalzahlung Gerät"
(`rateplanOption: false`). Die Vertiefung folgte jedem nicht gewählten Knopf,
also auch diesem: 62 der 254 o2-Abrufe, jeder im Mittel 19,7 s statt 3 s
(drei davon liefen in den Lese-Timeout), zusammen rund 1.450 der 2.094
Sekunden. Keiner ergab einen Satz (`ohne_probe` 62): eine Einmalzahlung hat
keine Ratenzahl, `_gemessen` verwirft sie. Die Vertiefung endete an der Frist
nach 63 von 70 Katalog-Geräten.

Die Fixture ist der gespeicherte Abruf des iPhone 17 Pro
(`o2_vertiefung_iphone17pro.json.gz`, 29.09.2026); ihr wird der dritte Knopf so
eingesetzt, wie die Konfigurationsantwort vom 20.11.2026 ihn trägt
(`displayValue`, `rateplanOption`, `deviceMonthlyPrice`, `deviceUpfrontPayment`).
"""

import copy
import gzip
import json
from pathlib import Path

from telco_radar.collect.geraete import GeraeteAbrufFehler, o2

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_EINMAL = "https://www.o2online.de/e-shop/rest/configuration/einmalzahlung-{}"


def _mitschnitt_mit_einmalzahlung() -> dict:
    with gzip.open(_FIX / "o2_vertiefung_iphone17pro.json.gz", "rt") as fh:
        m = json.load(fh)
    m = copy.deepcopy(m)
    for i, (url, text) in enumerate(list(m["antworten"].items())):
        pv = o2.lies_konfiguration(text)
        optionen = (pv.get("hardware") or {}).get("paymentOptions")
        if not optionen:
            continue
        optionen.append(
            {
                "@type": "pdp:PaymentOptionValue",
                "displayValue": "Einmalzahlung Gerät",
                "selected": False,
                "selectCall": {"link": {"uri": _EINMAL.format(i)}},
                "rateplanOption": False,
                "deviceMonthlyPrice": "39,99\xa0€",
                "deviceUpfrontPayment": "1.199,00\xa0€",
            }
        )
        m["antworten"][url] = json.dumps(pv)
    return m


def _lauf(m: dict):
    protokoll: list[str] = []

    def hole(url):
        protokoll.append(url)
        if url not in m["antworten"]:
            raise GeraeteAbrufFehler("nicht im Mitschnitt", status=404)
        return m["antworten"][url]

    zaehler: dict = {}
    saetze = o2.vertiefe_buendel(
        hole, o2.lies_buendel(json.dumps(m["katalog"])), None, zaehler
    )
    return saetze, protokoll, zaehler


def test_der_einmalzahlungsknopf_wird_nicht_abgerufen():
    saetze, protokoll, zaehler = _lauf(_mitschnitt_mit_einmalzahlung())
    assert not [u for u in protokoll if "einmalzahlung" in u]
    assert len(protokoll) == 15
    assert zaehler["abrufe"] == 15
    assert "unlesbar" not in zaehler


def test_ohne_den_knopf_bleiben_alle_ratenbuendel():
    saetze, _, _ = _lauf(_mitschnitt_mit_einmalzahlung())
    kombis = {(s["speicher_gb"], s["laufzeit_monate"], s["tarif_slug"]) for s in saetze}
    assert len(saetze) == len(kombis) == 48
    assert {s["laufzeit_monate"] for s in saetze} == {24, 36}


def test_ein_ratenknopf_ohne_merker_wird_weiter_abgerufen():
    """Die gespeicherten Abrufe vom 29.09.2026 tragen `rateplanOption` noch
    nicht; entscheidend ist die Ratenzahl im Knopf, wie in `_gemessen`."""
    assert o2.ratenzahl_im_knopf({"displayValue": "24 Monate"}) == 24
    assert o2.ratenzahl_im_knopf({"displayValue": "Einmalzahlung Gerät"}) is None
    assert o2.ratenzahl_im_knopf({"displayValue": "0 Monate"}) is None
    assert (
        o2.ratenzahl_im_knopf({"displayValue": "36 Monate", "rateplanOption": False})
        is None
    )
