"""Preisphase über die ganze Ratenlaufzeit, nur wo der Anbieter sie fürs Bündel nennt.

Datenkonzept Geräte 5.3, Regel 8. Ein gemessener Tarifpreis ohne Phase ist nur für die
Bindung belegt. Die Summe über 36 Monate zählt den Tarif ohnehin nur 24 Monate
(Antonio, 10.10.2026); die Phase bleibt der Beleg für den Preis danach. o2 nennt im
Ratenplan-Hinweis den Tarifrabatt „über die
gesamte Laufzeit deines Geräte-Ratenplans“, und der Tarif der Konfiguration trägt die
Ratenzahl („…-hwv-36m-05-00“); congstar führt den Tarifpreis ohne Rabattphase. Dann
trägt das Bündel eine Phase von Monat 1 bis N mit Beleg, nie darüber hinaus.

Fixtures: `o2_ratenplan_galaxy_s26_20261007.json.gz` (Auszug aus der Klick-Erkundung vom
07.10.2026, zwei Konfigurationsantworten mit dem Hinweis), `o2_vertiefung_iphone17pro.
json.gz` (29.09.2026, auf die gelesenen Felder gekürzt, ohne den Hinweis),
`congstar_produkt_iphone17_20260929.html.gz`; Herkunft in `_herkunft.json`.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest
from bestand_pfad import ZUSTAND

from telco_radar.analyze.geraete_pruefstatus import buendel_aus_satz
from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.analyze.tco_store import TcoDB
from telco_radar.collect.geraete import GeraeteAbrufFehler, congstar, o2
from telco_radar.report import geraete_rechenweg, geraete_tco_view
from telco_radar.report.geraete_tco_karten import tarif_anreichern
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tco_kosten import tarifphasen
from telco_radar.tco_model import Buendel, kosten_ueber, tco_24

FIX = Path(__file__).parent / "fixtures" / "geraete"
CONGSTAR_URL = "https://www.congstar.de/geraete/apple/apple-iphone-17/"
CONGSTAR_SKU = "apple-iphone-17-256gb-weiss"
O2_MIT_RATENZAHL = {
    "o2-mobile-unlimited-m-plus",
    "o2-mobile-unlimited-l-plus",
    "o2-mobile-s",
}
CONGSTAR_OHNE_RABATT = {
    "Allnet Flat XS",
    "Allnet Flat XS Flex",
    "Allnet Flat S",
    "Allnet Flat S Flex",
}


def _json_gz(name: str):
    with gzip.open(FIX / name, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _spannen(phasen: list[dict]) -> list[tuple]:
    return [(p["von_monat"], p["bis_monat"], p["betrag"]) for p in phasen]


def _ratenplan_seiten() -> list[dict]:
    return list(
        _json_gz("o2_ratenplan_galaxy_s26_20261007.json.gz")["antworten"].values()
    )


def _raten(pv: dict) -> int:
    return 36 if pv["hardware"]["offerName"].endswith("-36xhigh") else 24


def _o2_phasen(pv: dict, option: dict, angebot: str, raten: int) -> list[dict]:
    from telco_radar.collect.geraete import ratenlaufzeit

    gemessen = {"angebot": angebot, "laufzeit": raten}
    return ratenlaufzeit.o2_phasen(pv, o2._link(option), gemessen, 19.99, {})


def test_o2_der_hinweis_belegt_nur_tarife_mit_derselben_ratenzahl():
    """Galaxy S26 512 GB am 07.10.2026, je eine Antwort mit 36 und mit 24 Raten. Nur
    die Tarife, deren Konfiguration die Ratenzahl nennt, bekommen die Phase 1 bis N;
    S Special Plus, L Plus 150 GB und on Demand M Plus („…-online-hwv“) und der Tarif
    ohne Plus („…-online-promo“) nicht, und keiner eine Phase für die andere Ratenzahl
    oder ein anderes Angebot."""
    seiten = _ratenplan_seiten()
    assert sorted(_raten(pv) for pv in seiten) == [24, 36]
    for pv in seiten:
        angebot, raten = pv["hardware"]["offerName"], _raten(pv)
        optionen = pv["tariff"]["tariffOptions"]
        belegt = {
            o2._ohne_markup(o["displayValue"]): _o2_phasen(pv, o, angebot, raten)
            for o in optionen
        }
        assert {name for name, phasen in belegt.items() if phasen} == {
            "O2 Mobile Unlimited L Plus mit 300 MBit/s",
            "O2 Mobile Unlimited M Plus mit 100 MBit/s",
        }
        for phasen in filter(None, belegt.values()):
            assert _spannen(phasen) == [(1, raten, 19.99)]
            assert (
                "über die gesamte Laufzeit deines Geräte-Ratenplans"
                in phasen[0]["beleg"]
            )
            assert f"-hwv-{raten}m-05-00" in phasen[0]["beleg"]
        andere = 60 - raten
        assert not any(_o2_phasen(pv, o, angebot, andere) for o in optionen)
        fremd = angebot.replace("512gb", "256gb")
        assert not any(_o2_phasen(pv, o, fremd, raten) for o in optionen)


def _hole(mitschnitt: dict, hinweis: dict | None):
    """Die Antworten vom 29.09.; mit `hinweis` trägt jede den Ratenplan-Hinweis der
    Antwort vom 07.10. (die Fixture vom 29.09. ist ohne ihn gekürzt; die Klick-Erkundung
    vom 07.10. zeigt ihn auch beim iPhone 17 Pro)."""

    def hole(url: str) -> str:
        if url not in mitschnitt["antworten"]:
            raise GeraeteAbrufFehler("nicht im Mitschnitt", status=404)
        if hinweis is None:
            return mitschnitt["antworten"][url]
        pv = o2.lies_konfiguration(mitschnitt["antworten"][url])
        pv["hardware"]["contents"] = hinweis
        return json.dumps(pv)

    return hole


def _o2_vertieft(hinweis: dict | None, zaehler: dict | None = None):
    mitschnitt = _json_gz("o2_vertiefung_iphone17pro.json.gz")
    katalog = o2.lies_buendel(json.dumps(mitschnitt["katalog"]))
    tief = o2.vertiefe_buendel(_hole(mitschnitt, hinweis), katalog, None, zaehler)
    return katalog, tief


def test_o2_mit_hinweis_tragen_genau_die_tarife_mit_ratenzahl_die_phase():
    zaehler: dict = {}
    katalog, tief = _o2_vertieft(
        _ratenplan_seiten()[0]["hardware"]["contents"], zaehler
    )
    mit = [s for s in tief if s.get("tarif_phasen")]
    assert {s["tarif_slug"] for s in mit} == O2_MIT_RATENZAHL
    assert len(mit) == zaehler["ratenplan_belegt"] == 12
    for s in mit:
        assert _spannen(s["tarif_phasen"]) == [
            (1, s["laufzeit_monate"], s["tarif_monatlich"])
        ]
    assert {s["laufzeit_monate"] for s in mit} == {24, 36}

    zusammen = o2.fuehre_zusammen(katalog, tief)
    assert len(zusammen) == 48
    assert _spannen(zusammen[0].get("tarif_phasen", [])) == [(1, 36, 19.99)]
    anders = [{**katalog[0], "tarif_monatlich": 24.99}]
    assert "tarif_phasen" not in o2.fuehre_zusammen(anders, tief)[0]


def test_o2_ohne_hinweis_bleibt_jeder_satz_ohne_phase():
    katalog, tief = _o2_vertieft(None)
    assert len(tief) == 48
    assert not any(s.get("tarif_phasen") for s in o2.fuehre_zusammen(katalog, tief))


def _congstar_saetze() -> list[dict]:
    with gzip.open(FIX / "congstar_produkt_iphone17_20260929.html.gz", "rt") as fh:
        return congstar.lies_buendel(fh.read(), CONGSTAR_URL)


def test_congstar_nur_der_tarifpreis_ohne_rabattphase_traegt_die_ratenlaufzeit():
    """XS und S stehen am 29.09.2026 mit `discounts: []` und listed = discounted; M und
    L mit einem dauerhaften Nachlass von 1 €, der hier kein Beleg ist."""
    saetze = _congstar_saetze()
    mit = [s for s in saetze if s.get("tarif_phasen")]
    assert {s["tarif_name"] for s in mit} == CONGSTAR_OHNE_RABATT
    assert (len(mit), len(saetze)) == (16, 32)
    for s in mit:
        assert _spannen(s["tarif_phasen"]) == [
            (1, s["laufzeit_monate"], s["tarif_monatlich"])
        ]
        assert "discounts []" in s["tarif_phasen"][0]["beleg"]


def _bestand() -> Tarifbestand:
    bestand = Tarifbestand.aus_datei(ZUSTAND / "tarife.jsonl")
    congstar.ergaenze_pib_slug(bestand)
    return bestand


def _congstar_roh(tarif: str, raten: int) -> dict:
    [satz] = [
        s
        for s in _congstar_saetze()
        if (s["speicher_gb"], s["tarif_name"], s["laufzeit_monate"])
        == (256, tarif, raten)
    ]
    return {**satz, "sku_id": CONGSTAR_SKU, "anbieter": "congstar"}


def _buendel(roh: dict, bestand: Tarifbestand) -> Buendel:
    """Wie der Tageslauf: Rohsatz zum Bündel, dann die Karte mit dem Tarifblatt."""
    bilanz = aus_rohsaetzen([roh], bestand, "2026-09-29")
    [b] = bilanz.buendel
    tarif_anreichern(b, bestand.je_id_aktuell[b.tarif_id])
    return b


def _ueber_36(b: Buendel) -> tuple:
    """Die Summe über 36 Monate und ob eine belegte Tarifphase Monat 36 nennt."""
    k = kosten_ueber(b, 36)
    return k.gesamt, any(
        p.von_monat <= 36 and (p.bis_monat is None or p.bis_monat >= 36)
        for p in tarifphasen(b)
    )


def test_mit_beleg_traegt_die_phase_monat_36_die_summe_bleibt_bei_24_tarifmonaten():
    """Allnet Flat XS zu 15,00 € mit 36 Raten: das Tarifblatt nennt nur den Grundpreis
    (eine Phase ohne Ende), die Messung die Phase 1 bis 36 - sie bleibt stehen. Die
    Summe über 36 Monate ist mit und ohne Beleg `tco_24`."""
    bestand = _bestand()
    xs = _buendel(_congstar_roh("Allnet Flat XS", 36), bestand)
    assert _ueber_36(xs) == (tco_24(xs).gesamt, True)
    assert [(p.von_monat, p.bis_monat) for p in xs.tarif_phasen] == [(1, 36)]

    m = _buendel(_congstar_roh("Allnet Flat M", 36), bestand)
    assert _ueber_36(m) == (tco_24(m).gesamt, False)
    xs_ohne = _buendel(
        {**_congstar_roh("Allnet Flat XS", 36), "tarif_phasen": []}, bestand
    )
    assert _ueber_36(xs_ohne) == (tco_24(xs).gesamt, False)
    assert tco_24(xs).gesamt == tco_24(xs_ohne).gesamt


def test_ein_24_raten_buendel_bekommt_keine_36er_phase():
    b = _buendel(_congstar_roh("Allnet Flat XS", 24), _bestand())
    assert [(p.von_monat, p.bis_monat) for p in b.tarif_phasen] == [(1, 24)]
    assert _ueber_36(b) == (tco_24(b).gesamt, False)
    assert kosten_ueber(b).gesamt == tco_24(b).gesamt


@pytest.mark.parametrize(
    "phase",
    [
        {"von_monat": 1, "bis_monat": 36, "betrag": 15.0},
        {"von_monat": 1, "bis_monat": 36, "betrag": 15.0, "beleg": "  "},
        {"von_monat": 1, "bis_monat": None, "betrag": 15.0, "beleg": "x"},
        {"von_monat": 0, "bis_monat": 36, "betrag": 15.0, "beleg": "x"},
        {"von_monat": 1, "bis_monat": 36, "betrag": None, "beleg": "x"},
    ],
)
def test_eine_phase_ohne_beleg_oder_monate_belegt_nichts(phase):
    roh = {**_congstar_roh("Allnet Flat XS", 36), "tarif_phasen": [phase]}
    b = _buendel(roh, _bestand())
    assert _ueber_36(b) == (tco_24(b).gesamt, False)


def test_die_phase_geht_durch_speicher_historie_und_ansicht(tmp_path):
    """Gespeichert wird die Phase mit Beleg; Karte, Prüfstelle und Zeitreihe lesen sie
    zurück. Ein Lauf ohne Beleg löscht sie wieder (eine Messung, alle Felder)."""
    bestand = _bestand()
    roh = _congstar_roh("Allnet Flat XS", 36)
    [b] = aus_rohsaetzen([roh], bestand, "2026-09-29").buendel
    blatt = bestand.je_id_aktuell[b.tarif_id]
    db = TcoDB(tmp_path / "geraete_tco.json")
    db.upsert_buendel([b], "2026-09-29")
    db.save("2026-09-29")

    [satz] = TcoDB(tmp_path / "geraete_tco.json").buendel()
    assert _spannen(satz.get("tarif_phasen", [])) == [(1, 36, 15.0)]
    assert satz["tarif_phasen"] == roh["tarif_phasen"]
    zeile = json.loads(
        (tmp_path / "geraete_tco_historie.jsonl").read_text().splitlines()[0]
    )
    assert zeile.get("tarif_phasen") == roh["tarif_phasen"]

    [karte] = geraete_tco_view._aus_speicher(
        [satz], Buendel, geraete_tco_view._BUENDEL_FELDER
    )
    tarif_anreichern(karte, blatt)
    zeitreihe = geraete_rechenweg._buendel_aus_messung(
        {"satz": zeile, "stand": satz}, {b.tarif_id: blatt}
    )
    pruefung = buendel_aus_satz(satz)
    erwartet = _ueber_36(_buendel(roh, bestand))
    assert erwartet[1] is True
    for gelesen in (karte, zeitreihe, pruefung):
        assert _ueber_36(gelesen) == erwartet

    [ohne] = aus_rohsaetzen(
        [{**roh, "tarif_phasen": []}], bestand, "2026-09-30"
    ).buendel
    db.upsert_buendel([ohne], "2026-09-30")
    db.save("2026-09-30")
    [satz] = TcoDB(tmp_path / "geraete_tco.json").buendel()
    assert "tarif_phasen" not in satz
    [karte] = geraete_tco_view._aus_speicher(
        [satz], Buendel, geraete_tco_view._BUENDEL_FELDER
    )
    tarif_anreichern(karte, blatt)
    assert _ueber_36(karte) == (erwartet[0], False)
