"""Die zweite Lesart der Vodafone-Detailantwort: Geraet PLUS Tarif (B1).

WAS HIER GEPRUEFT WIRD, UND WARUM ES EINE EIGENE DATEI IST
-----------------------------------------------------------
Bis zum 05.09.2026 gab es Geraet-x-Tarif-Buendel nur fuer o2 (63 Stueck);
Vodafone stand mit `zuzahlung` in 0 von 595 Listungen belegt in der
Bestandsaufnahme. Dieselbe Disziplin wie bei o2 (`test_geraete_buendel_
o2.py`), andere Antwortform: Vodafones Detailnutzlast (dieselbe, die
`lies()` schon in Listungen zerlegt) traegt unter
`atomics[].prices.composition` 2-4 Angebote je Variante, ohne Klarnamen -
nur einen `offerCoreHash`.

DIE FIXTURES SIND GESPEICHERTE ECHTE ABRUFE
--------------------------------------------
`vodafone_virtualitem.json` ist die schon vorhandene Fixture des
Preis-ohne-Vertrag-Adapters (28.08.2026) - sie traegt die Buendeldaten
bereits mit, nur wurden sie bisher nicht gelesen.
`vodafone_tarif_hardware.json` ist NEU: die Antwort auf
`/glados/v2/tariff/v2/hardware?hardwareId=58060&businessTransaction=
newContract&salesChannel=Online.Consumer` (05.09.2026, HTTP 200, reiner
HTTP-GET, `TelcoRadar/1.0`, derselbe `x-api-key` wie beim Hauptendpunkt) -
der Endpunkt, der die offene Tarifnamen-Frage des Auftrags beantwortet.

DIE RECHENPROBE ENTSCHEIDET, NICHT `financingType`
----------------------------------------------------
Siehe `collect/geraete/vodafone.py` Modulkopf: bei `financingType: "rate"`
geht `tarif.month + hardware.month == totalMonthlyRatePrice[0]` auf, bei
`"sub"` geht `tarif.month` ALLEIN auf (das Geraet steckt im Tarifpreis).
Beide Faelle liefern einen gueltigen Buendel-Rohsatz, nur der eine ohne
`geraet_monatsrate`.
"""

import json
from pathlib import Path

import pytest

from telco_radar.analyze.tco_buendel import aus_rohsaetzen
from telco_radar.collect.geraete import ADAPTER, GeraeteAbrufFehler, sammle_anbieter
from telco_radar.collect.geraete import vodafone as vodafone_modul
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.collect.geraete.vodafone import (
    _hash_namen_aus_tarifantwort,
    lies_buendel,
    loese_tarifnamen,
)
from telco_radar.geraete_config import Anbieter, Einstieg, lade_farben, lade_katalog
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarif_model import HOCH

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_WURZEL = Path(__file__).parent.parent

_HASH_SUB = "05CFDB77B68E33D50A854615C1AE94C471BDBF9988C4DFFAE4B8757E091903C3"
_HASH_RATE_12 = "046C1DBAAB9D954498427AC5A9E609D949BFE9E682114BB64813A0BD5890E3AD"
_HASH_RATE_24 = "8185E00DA9A03779278563702E06E3A5037825C6830CED3157CC0110BA556A8F"
_HASH_RATE_36 = "AFC74ADAE1BC4C496886CC4B085D7F3BA822C281CEB6A7EA818901675B460FE8"


def _fixture(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(_WURZEL)


@pytest.fixture(scope="module")
def farben():
    return lade_farben(_WURZEL)


def _saetze():
    return lies_buendel(_fixture("vodafone_virtualitem.json"))


# ==========================================================================
# lies_buendel()
# ==========================================================================


def test_zwoelf_buendel_aus_drei_varianten_und_vier_kompositionen():
    """3 Atomics (Frost 256/512 GB, Hibiscus 256 GB) x 4 Kompositionen."""
    saetze = _saetze()
    assert len(saetze) == 12
    assert {(s["farbe"], s["speicher_gb"]) for s in saetze} == {
        ("Frost", 256),
        ("Frost", 512),
        ("Hibiscus", 256),
    }
    assert {s["sku"] for s in saetze} == {"58060", "58061", "58063"}


def test_jeder_satz_traegt_zuzahlung_und_anschlusspreis():
    """Die Kernluecke aus der Bestandsaufnahme: 0 von 595 Listungen mit
    belegtem `zuzahlung`. Hier sind es zwoelf von zwoelf Rohsaetzen."""
    for s in _saetze():
        assert s["geraet_zuzahlung"] == 1.0
        assert s["anschlusspreis"] == 0.0
        assert s["tarif_monatlich"] is not None
        assert s["laufzeit_monate"] > 0


def test_der_subventions_fall_hat_keine_separate_geraeterate():
    """Das PM-Sample: Zuzahlung 1,00 EUR, Tarifrate 69,99 EUR, Gesamtrate
    69,99 EUR. `financingType: "sub"` steckt vollstaendig im Tarifpreis -
    `hardware.month` (30 EUR in der Rohantwort) ist dort ein Vergleichswert,
    keine zusaetzlich berechnete Rate (siehe Modulkopf)."""
    sub = [
        s
        for s in _saetze()
        if s["tarif_slug"]
        in {
            _HASH_SUB,
            "8C1657624D227310534A73B7774CD7F3DFB49911C77BF8A498103C01F8E8CBE5",
            "9DCB892187186C326C9A82CDF8A8D47C8881E194247D538442982814A29D7A56",
        }
    ]
    assert len(sub) == 3  # je Variante einer
    for s in sub:
        assert s["tarif_monatlich"] == 69.99
        assert s["geraet_zuzahlung"] == 1.0
        assert s["geraet_monatsrate"] is None
        assert s["laufzeit_monate"] == 24
        assert s["tarif_name"] == ""


def test_die_ratenfaelle_gehen_gegen_die_gesamtrate_auf():
    """`financingType: "rate"`: Tarifrate + Geraeterate == Gesamtrate der
    ersten Phase, fuer alle drei Laufzeiten (12/24/36 Monate)."""
    roh = json.loads(_fixture("vodafone_virtualitem.json"))
    je_hash = {}
    for atom in roh["data"]["atomics"]:
        for k in atom["prices"]["composition"]:
            je_hash[k["offerCoreHash"]] = k

    rate = [s for s in _saetze() if s["geraet_monatsrate"] is not None]
    assert len(rate) == 9  # 3 Varianten x 3 Ratenfaelle (12/24/36)
    for s in rate:
        k = je_hash[s["tarif_slug"]]
        gesamt = k["totalMonthlyRatePrice"]["withoutDiscounts"][0]["gross"]
        assert s["geraet_monatsrate"] + s["tarif_monatlich"] == pytest.approx(
            gesamt, abs=0.005
        )
        assert s["laufzeit_monate"] == k["financingDuration"]


def test_alle_saetze_tragen_leeren_tarifnamen_und_den_hash_als_slug():
    """Die offene Frage aus dem Auftrag: kein Klarname in dieser Antwort -
    nicht raten, `tarif_slug` traegt den Hash, damit `loese_tarifnamen()`
    (oder eine spaetere Instanz) ihn nachliefern kann."""
    for s in _saetze():
        assert s["tarif_name"] == ""
        assert len(s["tarif_slug"]) >= 32


def test_kaputte_nutzlast_wirft():
    with pytest.raises(GeraeteAbrufFehler):
        lies_buendel("kein json")


def test_ohne_modellnamen_liefert_leer_statt_zu_werfen():
    """`lies()` hat auf derselben Seite schon geworfen, wenn der Modellname
    fehlt - diese Funktion meldet denselben Fehler nicht ein zweites Mal."""
    assert lies_buendel(json.dumps({"data": {"atomics": []}})) == []


def _nur_erstes_atom(roh: dict) -> dict:
    """Die uebrigen zwei Atomics kappen, damit ein manipuliertes Beispiel
    nicht zwischen echten Saetzen der anderen Varianten verschwindet."""
    roh["data"]["atomics"] = roh["data"]["atomics"][:1]
    return roh


def test_ohne_hash_wird_die_komposition_uebergangen():
    roh = _nur_erstes_atom(json.loads(_fixture("vodafone_virtualitem.json")))
    atom = roh["data"]["atomics"][0]
    atom["prices"]["composition"] = [
        {**atom["prices"]["composition"][0], "offerCoreHash": ""}
    ]
    assert lies_buendel(json.dumps(roh)) == []


def test_eine_summe_die_nicht_aufgeht_faellt():
    """Weder MIT noch OHNE Geraeterate stimmt die Summe - verworfen, nicht
    geraten (dieselbe Disziplin wie bei o2)."""
    roh = _nur_erstes_atom(json.loads(_fixture("vodafone_virtualitem.json")))
    atom = roh["data"]["atomics"][0]
    kaputt = json.loads(json.dumps(atom["prices"]["composition"][1]))  # "rate"
    kaputt["totalMonthlyRatePrice"]["withoutDiscounts"][0]["gross"] = 9999.0
    atom["prices"]["composition"] = [kaputt]
    assert lies_buendel(json.dumps(roh)) == []


def _sub_mit_phasen(phasen: list[dict]) -> str:
    """Die `sub`-Komposition (ohne `financingDuration`) der echten Fixture
    mit ausgetauschten Phasen - die Phasen sind synthetisch und sagen das,
    alles andere an der Komposition ist der gespeicherte echte Abruf."""
    roh = _nur_erstes_atom(json.loads(_fixture("vodafone_virtualitem.json")))
    atom = roh["data"]["atomics"][0]
    sub = json.loads(json.dumps(atom["prices"]["composition"][0]))
    assert sub["financingType"] == "sub"
    assert sub.get("financingDuration") is None
    sub["totalMonthlyRatePrice"]["withoutDiscounts"] = phasen
    atom["prices"]["composition"] = [sub]
    return json.dumps(roh)


def _sub_phase(start: int, ende, gross: float = 69.99) -> dict:
    return {
        "recurrenceUnit": "month",
        "recurrenceStart": start,
        "recurrenceEnd": ende,
        "gross": gross,
        "net": 58.82,
    }


def test_ohne_ratenlaufzeit_und_ohne_periode_faellt():
    roh = _nur_erstes_atom(json.loads(_fixture("vodafone_virtualitem.json")))
    atom = roh["data"]["atomics"][0]
    kaputt = json.loads(json.dumps(atom["prices"]["composition"][0]))  # "sub"
    kaputt["totalMonthlyRatePrice"]["withoutDiscounts"][0]["recurrenceEnd"] = None
    atom["prices"]["composition"] = [kaputt]
    assert lies_buendel(json.dumps(roh)) == []


def test_eine_offene_anschlussphase_verliert_das_buendel_nicht():
    """FIX3-Befund: eine Phase OHNE Ende ist eine offene Anschlussphase
    ("ab Monat 25", `recurrenceEnd: null`) und keine Laufzeit.

    Der Rueckfall auf `perioden[-1]["recurrenceEnd"]` machte daraus
    `int(None)`, die Laufzeit blieb None und das GANZE Buendel fiel ohne
    Protokoll heraus. Gemessen am HEAD-Stand c6bd8a5: 0 Saetze statt 1.
    Die Vertragsmindestlaufzeit - die spaeteste GENANNTE Endgrenze -
    bleibt der Rueckfall.
    """
    saetze = lies_buendel(_sub_mit_phasen([_sub_phase(1, 24), _sub_phase(25, None)]))
    assert len(saetze) == 1
    assert saetze[0]["laufzeit_monate"] == 24
    # Der `sub`-Fall hat keine separate Geraeterate (Modulkopf) - die
    # Gegenprobe, dass hier wirklich der Subventionsfall gemessen wurde.
    assert saetze[0]["geraet_monatsrate"] is None


def test_die_geraeterate_nennt_ihr_eigenes_ende_und_es_ist_die_laufzeit():
    """Die Gegenprobe zur zweiten Quelle in `_laufzeit()`: in JEDER
    Ratenkomposition der Fixture ist
    `priceByComponent.hardware...rate.month.withoutDiscounts.recurrenceEnd`
    exakt `financingDuration`. Nur deshalb darf sie der Rueckfall sein."""
    roh = json.loads(_fixture("vodafone_virtualitem.json"))
    gemessen = 0
    for atom in roh["data"]["atomics"]:
        for k in atom["prices"]["composition"]:
            dauer = k.get("financingDuration")
            if dauer is None:
                continue  # der "sub"-Fall, siehe unten
            ende = k["priceByComponent"]["hardware"]["priceByType"]["rate"]["month"][
                "withoutDiscounts"
            ]["recurrenceEnd"]
            assert ende == dauer, (k["offerCoreHash"], dauer, ende)
            gemessen += 1
    assert gemessen == 9  # 3 Varianten x 3 Ratenfaelle


def test_ohne_financingduration_gilt_das_ende_der_geraeterate_nicht_der_phasen():
    """FIX3-Befund des Pruefers: die Phasen von `totalMonthlyRatePrice`
    beschreiben den GANZEN Vertrag und laufen laenger als die
    Geraetefinanzierung.

    Genommen wird an der ECHTEN 12-Monats-Komposition, der nur die
    `financingDuration` entfernt wird: mit dem Phasen-Rueckfall ergaben
    64,50 EUR ueber 24 statt 12 Monate 1549,00 EUR statt der in derselben
    Nutzlast belegten 775,00 EUR - die Geraetekosten waeren verdoppelt in
    den Bestand gegangen.
    """
    roh = _nur_erstes_atom(json.loads(_fixture("vodafone_virtualitem.json")))
    atom = roh["data"]["atomics"][0]
    rate12 = json.loads(json.dumps(atom["prices"]["composition"][1]))
    assert rate12["financingType"] == "rate"
    assert rate12["financingDuration"] == 12
    hardware = rate12["priceByComponent"]["hardware"]["priceByType"]
    belegt = hardware["total"]["onetime"]["withoutDiscounts"]["gross"]
    assert belegt == 775.0
    # Die Phasen des Vertrags enden bei 24 - die Finanzierung nicht.
    assert [
        p["recurrenceEnd"] for p in rate12["totalMonthlyRatePrice"]["withoutDiscounts"]
    ] == [12, 24]
    rate12["financingDuration"] = None
    atom["prices"]["composition"] = [rate12]

    saetze = lies_buendel(json.dumps(roh))
    assert len(saetze) == 1
    assert saetze[0]["laufzeit_monate"] == 12
    assert saetze[0]["geraet_zuzahlung"] + saetze[0]["laufzeit_monate"] * saetze[0][
        "geraet_monatsrate"
    ] == pytest.approx(belegt, abs=0.005)


def test_gar_keine_bestimmbare_laufzeit_steht_im_protokoll(caplog):
    """Nur offene Phasen: nichts ist bestimmbar - und der Verlust wird
    BENANNT, nicht verschluckt (keine 0, keine geratene Laufzeit)."""
    with caplog.at_level("INFO", logger="telco_radar.collect.geraete.vodafone"):
        saetze = lies_buendel(
            _sub_mit_phasen([_sub_phase(1, None), _sub_phase(25, None)])
        )
    assert saetze == []
    meldungen = [r.getMessage() for r in caplog.records]
    assert any("ohne bestimmbare Ratenlaufzeit" in m for m in meldungen), meldungen
    assert any(_HASH_SUB in m for m in meldungen), meldungen


def test_alle_phasen_ergeben_den_richtigen_geraete_gesamtpreis():
    """P0-B2a: keine Phase geht verloren. `geraet_monatsrate` kommt flach
    aus `priceByComponent.hardware.month` (deckt die GANZE Ratenlaufzeit
    ab, nicht nur Phase 0 von `totalMonthlyRatePrice`) - nachgerechnet
    gegen den unabhaengigen Gesamtpreis derselben Komponente
    (`...total.onetime.withoutDiscounts.gross`), fuer alle drei
    Ratenfaelle (12/24/36 Monate) der Fixture.

    FIX3: der erste Teil dieses Tests war gegen den Stand VOR P0-B2a
    (fde7f63) gruen - er beschrieb eine Eigenschaft, die schon vorher
    stimmte, und pruefte damit kein neues Verhalten. Der zweite Teil
    unten ist die scharfe Gegenprobe auf "keine Phase geht verloren":
    sie laeuft ueber eine Komposition, deren ERSTE Phase kein Ende nennt
    und deren zweite eines hat. Der alte Stand las ausschliesslich Phase
    0, bekam `int(None)` und verwarf das Buendel (0 Saetze).
    """
    roh = json.loads(_fixture("vodafone_virtualitem.json"))
    je_hash = {}
    for atom in roh["data"]["atomics"]:
        for k in atom["prices"]["composition"]:
            je_hash[k["offerCoreHash"]] = k

    rate = [s for s in _saetze() if s["geraet_monatsrate"] is not None]
    assert len(rate) == 9  # 3 Varianten x 3 Ratenfaelle
    for s in rate:
        k = je_hash[s["tarif_slug"]]
        hardware_gesamt = k["priceByComponent"]["hardware"]["priceByType"]["total"][
            "onetime"
        ]["withoutDiscounts"]["gross"]
        # `totalMonthlyRatePrice` traegt bei 12 und 36 Monaten ZWEI Phasen
        # (Modulkopf) - die Gegenprobe laeuft trotzdem auf.
        assert len(k["totalMonthlyRatePrice"]["withoutDiscounts"]) == (
            1 if s["laufzeit_monate"] == 24 else 2
        )
        assert s["geraet_zuzahlung"] + s["laufzeit_monate"] * s[
            "geraet_monatsrate"
        ] == pytest.approx(hardware_gesamt, abs=0.005)

    # Die scharfe Gegenprobe (siehe Docstring): Phase 0 ohne Ende, Phase 1
    # mit Ende 24. Wer nur Phase 0 liest, verliert das ganze Buendel.
    scharf = lies_buendel(_sub_mit_phasen([_sub_phase(1, None), _sub_phase(2, 24)]))
    assert [s["laufzeit_monate"] for s in scharf] == [24]


def test_sub_ohne_financingduration_nimmt_das_ende_der_letzten_phase():
    """P0-B2a: der Laufzeit-Fallback fuer den `sub`-Fall (keine eigene
    `financingDuration`) liest nicht nur Phase 0, sondern die spaeteste
    GENANNTE Endgrenze - eine zweite, spaeter endende Phase (hier
    synthetisch ergaenzt, kein Beleg zeigt das fuer den `sub`-Fall) darf
    die Laufzeit nicht verkuerzen."""
    roh = _nur_erstes_atom(json.loads(_fixture("vodafone_virtualitem.json")))
    atom = roh["data"]["atomics"][0]
    sub = json.loads(json.dumps(atom["prices"]["composition"][0]))  # "sub"
    erste_phase = sub["totalMonthlyRatePrice"]["withoutDiscounts"][0]
    assert erste_phase["recurrenceEnd"] == 24
    zweite_phase = {
        **erste_phase,
        "recurrenceStart": 25,
        "recurrenceEnd": 30,
        "gross": erste_phase["gross"],
    }
    sub["totalMonthlyRatePrice"]["withoutDiscounts"] = [erste_phase, zweite_phase]
    atom["prices"]["composition"] = [sub]
    saetze = lies_buendel(json.dumps(roh))
    assert len(saetze) == 1
    assert saetze[0]["laufzeit_monate"] == 30


# ==========================================================================
# Die Tarifnamen-Aufloesung - die offene Frage des Auftrags
# ==========================================================================


def test_die_tarifantwort_liefert_hash_name_paare():
    namen = _hash_namen_aus_tarifantwort(_fixture("vodafone_tarif_hardware.json"))
    assert namen[_HASH_RATE_12] == "Mobil S"
    assert namen[_HASH_RATE_24] == "Mobil M"
    # Nicht jeder Hash steht in dieser Antwort - siehe Modulkopf.
    assert _HASH_SUB not in namen
    assert _HASH_RATE_36 not in namen


def test_unlesbare_tarifantwort_liefert_leeres_woerterbuch():
    assert _hash_namen_aus_tarifantwort("kein json") == {}
    assert _hash_namen_aus_tarifantwort(json.dumps({"data": []})) == {}


def test_rueckfall_loest_vorschau_ohne_eigenen_eintrag_ueber_den_hash():
    """Die Fixture vom 05.09.2026 traegt nur 58060. Diese Variante wird
    vollstaendig ersetzt; 58061 und 58063 behalten ihre Vorschau und
    bekommen ihren Namen nur, wo der Hash zufaellig in der Antwort steht."""
    rohbuendel = _saetze()
    aufrufe = []

    def hole(url, kopfzeilen=None):
        aufrufe.append((url, kopfzeilen))
        assert kopfzeilen == {"x-api-key": "geheim"}
        return 200, _fixture("vodafone_tarif_hardware.json")

    loese_tarifnamen(hole, {"x-api-key": "geheim"}, rohbuendel)
    assert len(aufrufe) == 1  # EIN GET je Geraet
    assert "hardwareId=58060,58061,58063&" in aufrufe[0][0]
    je_sku = {}
    for s in rohbuendel:
        je_sku.setdefault(s["sku"], []).append(s)
    assert len(je_sku["58060"]) == 19  # 5 x 3 Mobil + 4 FamilyCard
    assert all(s["tarif_name"] for s in je_sku["58060"])
    assert len(je_sku["58061"]) == 4  # Vorschau bleibt
    assert len(je_sku["58063"]) == 4


def test_loese_tarifnamen_macht_einen_get_je_geraet_nicht_je_variante():
    rohbuendel = _saetze()
    aufrufe = []

    def hole(url, kopfzeilen=None):
        aufrufe.append(url)
        return 200, _fixture("vodafone_tarif_hardware.json")

    loese_tarifnamen(hole, {}, rohbuendel)
    assert len(aufrufe) == 1


def test_ein_deckel_teilt_die_ids_in_mehrere_abrufe(monkeypatch):
    monkeypatch.setattr(vodafone_modul, "_IDS_JE_ABRUF", 2)
    monkeypatch.setattr(vodafone_modul, "_TARIF_RATE_LIMIT", 0.0)
    aufrufe = []

    def hole(url, kopfzeilen=None):
        aufrufe.append(url.split("hardwareId=")[1].split("&")[0])
        return 200, _fixture("vodafone_tarif_hardware.json")

    loese_tarifnamen(hole, {}, _saetze())
    assert aufrufe == ["58060,58061", "58063"]


def test_loese_tarifnamen_uebersteht_einen_scheiternden_abruf():
    rohbuendel = [s for s in _saetze() if s["sku"] == "58060"]
    vorher = [dict(s) for s in rohbuendel]

    def hole(url, kopfzeilen=None):
        raise ConnectionError("kein Netz")

    assert loese_tarifnamen(hole, {}, rohbuendel) == 0
    assert rohbuendel == vorher  # nicht gelesen ist nicht leer


def test_loese_tarifnamen_uebersteht_einen_fehlerstatus():
    rohbuendel = [s for s in _saetze() if s["sku"] == "58060"]

    def hole(url, kopfzeilen=None):
        return 404, "nicht gefunden"

    assert loese_tarifnamen(hole, {}, rohbuendel) == 0
    assert len(rohbuendel) == 4


# ==========================================================================
# Alle Tarife x alle Laufzeiten (Befund 29.09.2026)
# ==========================================================================

_MOBIL = ("Mobil XS", "Mobil S", "Mobil M", "Mobil L", "Mobil XL")


def _vorschau_2909():
    """Die Detailantwort vom 29.09.2026 (Pixel 11, sechs Varianten), wie
    der Sammler sie anreichert - `sku_id` je Variante eindeutig."""
    return [
        {
            **s,
            "anbieter": "Vodafone",
            "sku_id": f"pixel-11-{s['sku']}",
            "zustand": "neu",
            "quelle_url": s["url"],
        }
        for s in lies_buendel(_fixture("vodafone_virtualitem_2026-09-29.json"))
    ]


def _vollstaendig_2909():
    rohbuendel = _vorschau_2909()
    aufrufe = []

    def hole(url, kopfzeilen=None):
        aufrufe.append(url)
        return 200, _fixture("vodafone_tarif_hardware_geraet_2026-09-29.json")

    gesetzt = loese_tarifnamen(hole, {}, rohbuendel)
    return rohbuendel, aufrufe, gesetzt


def test_die_vorschau_koppelt_jede_tarifstufe_an_eine_laufzeit():
    """Die Ursache der Luecke, an der echten Antwort festgehalten: vier
    Angebote je Variante, Tarifbetrag 41,95 (Mobil S) nur mit 12, 51,95
    (Mobil M) nur mit 24, 31,95 (Mobil XS) nur mit 36 Monaten."""
    saetze = _vorschau_2909()
    assert len(saetze) == 24
    paare = {(s["tarif_monatlich"], s["laufzeit_monate"]) for s in saetze}
    assert paare == {(69.99, 24), (41.95, 12), (51.95, 24), (31.95, 36)}


def test_nur_ein_teil_der_vorschau_hashes_steht_in_der_tarifantwort():
    namen = _hash_namen_aus_tarifantwort(
        _fixture("vodafone_tarif_hardware_geraet_2026-09-29.json")
    )
    treffer = [s for s in _vorschau_2909() if s["tarif_slug"] in namen]
    assert len(treffer) == 9


def test_jede_variante_bekommt_alle_tarife_und_alle_laufzeiten():
    rohbuendel, aufrufe, gesetzt = _vollstaendig_2909()
    assert len(aufrufe) == 1
    assert "hardwareId=58060,58061,58063,58065,58066,58068&" in aufrufe[0]
    assert len(rohbuendel) == 6 * 19
    assert gesetzt == 6 * 19
    for sku in ("58060", "58061", "58063", "58065", "58066", "58068"):
        paare = {
            (s["tarif_name"], s["laufzeit_monate"])
            for s in rohbuendel
            if s["sku"] == sku
        }
        for tarif in _MOBIL:
            for laufzeit in (12, 24, 36):
                assert (tarif, laufzeit) in paare, (sku, tarif, laufzeit)
    # Gegenprobe: ein Paar, das die Antwort nicht nennt, entsteht nicht.
    assert not any(
        s["tarif_name"] == "Mobil XL" and s["laufzeit_monate"] == 6 for s in rohbuendel
    )


def test_die_anreicherung_des_sammlers_bleibt_je_variante_erhalten():
    rohbuendel, _, _ = _vollstaendig_2909()
    for s in rohbuendel:
        assert s["sku_id"] == f"pixel-11-{s['sku']}"
        assert s["anbieter"] == "Vodafone"
        assert s["zustand"] == "neu"
        assert s["quelle_url"].startswith("https://www.vodafone.de/")
        assert s["quelle"] == "vodafone_buendel"


def test_betraege_kommen_unveraendert_aus_der_tarifantwort():
    """Mobil L, 24 Monate, 58060 - gegen die rohe Antwort gelesen."""
    roh = json.loads(_fixture("vodafone_tarif_hardware_geraet_2026-09-29.json"))
    eintrag = next(e for e in roh["data"] if e["hardware"]["hardwareId"] == "58060")
    tarif = next(t for t in eintrag["tariffs"] if t["tariffName"] == "Mobil L")
    komp = next(
        k
        for a in tarif["atomics"]
        for k in a["prices"]["composition"]
        if k["financingDuration"] == 24
    )
    teile = komp["priceByComponent"]
    erwartet_tarif = teile["tariff"]["priceByType"]["rate"]["month"][
        "withoutDiscounts"
    ]["gross"]
    erwartet_rate = teile["hardware"]["priceByType"]["rate"]["month"][
        "withoutDiscounts"
    ]["gross"]
    erwartet_zuzahlung = teile["hardware"]["priceByType"]["rate"]["onetime"][
        "withoutDiscounts"
    ]["gross"]

    rohbuendel, _, _ = _vollstaendig_2909()
    satz = next(
        s
        for s in rohbuendel
        if s["sku"] == "58060"
        and s["tarif_name"] == "Mobil L"
        and s["laufzeit_monate"] == 24
    )
    assert satz["tarif_monatlich"] == erwartet_tarif == 61.95
    assert satz["geraet_monatsrate"] == erwartet_rate == 39.75
    assert satz["geraet_zuzahlung"] == erwartet_zuzahlung == 1.0
    assert satz["anschlusspreis"] == 0.0
    assert satz["tarif_slug"] == komp["offerCoreHash"]


def test_eine_fehlende_variante_behaelt_ihre_vorschau():
    """Nur 58060 steht in der (gekuerzten echten) Antwort: die anderen
    fuenf Varianten verlieren nichts."""
    roh = json.loads(_fixture("vodafone_tarif_hardware_geraet_2026-09-29.json"))
    roh["data"] = [e for e in roh["data"] if e["hardware"]["hardwareId"] == "58060"]
    rohbuendel = _vorschau_2909()

    def hole(url, kopfzeilen=None):
        return 200, json.dumps(roh)

    loese_tarifnamen(hole, {}, rohbuendel)
    je_sku = {}
    for s in rohbuendel:
        je_sku.setdefault(s["sku"], []).append(s)
    assert len(je_sku["58060"]) == 19
    for sku in ("58061", "58063", "58065", "58066", "58068"):
        assert len(je_sku[sku]) == 4


def test_unlesbare_kombinationen_lassen_die_vorschau_stehen():
    """Clean Code 6: steht eine Variante in der Antwort, besteht aber keine
    ihrer Kombinationen die Probe (hier: `priceByComponent` fehlt, wie bei
    einem geaenderten Format), bleibt ihre Vorschau stehen - einmal, ohne
    Doppel - statt dass die Variante still leer wird."""
    roh = json.loads(_fixture("vodafone_tarif_hardware_geraet_2026-09-29.json"))
    for e in roh["data"]:
        if e["hardware"]["hardwareId"] == "58060":
            for t in e["tariffs"]:
                for a in t["atomics"]:
                    for k in a["prices"]["composition"]:
                        k.pop("priceByComponent", None)
    rohbuendel = _vorschau_2909()
    vorher = [s for s in rohbuendel if s["sku"] == "58060"]

    def hole(url, kopfzeilen=None):
        return 200, json.dumps(roh)

    loese_tarifnamen(hole, {}, rohbuendel)
    nachher = [s for s in rohbuendel if s["sku"] == "58060"]
    assert len(nachher) == len(vorher) == 4
    assert len({id(s) for s in nachher}) == 4
    # Gegenprobe: die uebrigen Varianten sind voll ersetzt.
    assert len([s for s in rohbuendel if s["sku"] == "58061"]) == 19


def _bestand_vodafone_mobil():
    """Die zehn Blaetter, die der Tarif-Sammler fuer Vodafone schreibt
    (Tarif und "mit Smartphone"), Grundpreise wie in tarife.jsonl."""
    saetze = []
    for stufe, preis in (
        ("XS", 29.95),
        ("S", 39.95),
        ("M", 49.95),
        ("L", 59.95),
        ("XL", 79.95),
    ):
        slug = stufe.lower()
        saetze.append(
            {
                "tarif_id": f"vodafone:vodafone-mobil-{slug}",
                "anbieter": "Vodafone",
                "name": f"Vodafone Mobil {stufe}",
                "grundgebuehr": preis,
            }
        )
        saetze.append(
            {
                "tarif_id": f"vodafone:vodafone-mobil-{slug}-mit-smartphone",
                "anbieter": "Vodafone",
                "name": f"Vodafone Mobil {stufe} mit Smartphone",
                "grundgebuehr": preis,
            }
        )
    return Tarifbestand(saetze)


def test_alle_mobil_tarife_werden_buendel_familycard_bleibt_draussen():
    rohbuendel, _, _ = _vollstaendig_2909()
    bilanz = aus_rohsaetzen(rohbuendel, _bestand_vodafone_mobil(), "2026-09-29")
    assert len(bilanz.buendel) == 6 * 15
    assert {b.tarif_id for b in bilanz.buendel} == {
        f"vodafone:vodafone-mobil-{s}-mit-smartphone"
        for s in ("xs", "s", "m", "l", "xl")
    }
    assert {b.laufzeit_monate for b in bilanz.buendel} == {12, 24, 36}
    # Die Buendel-ID traegt Tarif und Laufzeit: keine zwei gleich.
    assert len({b.id for b in bilanz.buendel}) == 6 * 15
    # FamilyCard ist eine Zusatzkarte ohne eigenes Blatt im Bestand.
    assert bilanz.ohne_tarif == 6 * 4
    assert set(bilanz.offene_tarife) == {
        "FamilyCard S",
        "FamilyCard M",
        "FamilyCard L",
        "FamilyCard XL",
    }


# ==========================================================================
# Vom aufgeloesten Rohsatz zum echten Buendel
# ==========================================================================


def _bestand_mit_mobil_s():
    """Der Tarifbestand, wie ihn der Tarif-Sammler aus einem Vodafone-PIB
    schreibt - Namen tragen dort das Markenpraefix, die Tarifantwort
    (`tariffName`) nicht. `ueber_namen()` gleicht das ueber `_ohne_marke`
    auf BEIDEN Seiten aus (siehe `tarif_bezug.py`)."""
    return Tarifbestand(
        [
            {
                "tarif_id": "vodafone:vodafone-mobil-s",
                "anbieter": "Vodafone",
                "name": "Vodafone Mobil S",
                "grundgebuehr": 39.95,
            },
        ]
    )


def _mobil_s_12():
    rohbuendel, _, _ = _vollstaendig_2909()
    return next(
        s
        for s in rohbuendel
        if s["sku"] == "58060"
        and s["tarif_name"] == "Mobil S"
        and s["laufzeit_monate"] == 12
    )


def test_ein_aufgeloester_tarifname_ergibt_ein_echtes_buendel():
    """Der Weg zu Ende gegangen: `tariffName` (Tarifschnittstelle) ->
    `tarif_id` (Tarifbestand, ueber den Namen ohne Markenpraefix)."""
    satz = _mobil_s_12()
    bilanz = aus_rohsaetzen([satz], _bestand_mit_mobil_s(), "2026-09-29")
    assert len(bilanz.buendel) == 1
    buendel = bilanz.buendel[0]
    assert buendel.tarif_id == "vodafone:vodafone-mobil-s"
    assert buendel.tarif_id_guete == HOCH
    assert buendel.geraet_zuzahlung == 1.0
    assert buendel.anschlusspreis == 0.0


def test_ein_buendel_haengt_am_geraeteblatt_und_behaelt_seine_id():
    """P3 (28.09.2026): steht neben "Vodafone Mobil S" das Geraeteblatt
    "Vodafone Mobil S mit Smartphone" zum selben Preis im Bestand, haengt
    das Buendel daran (Datenvolumen und Stufe stehen dort). Die Buendel-ID
    kommt aus dem Tarifnamen der Seite und bleibt - sonst zerfiele der
    Verlauf. Gegenprobe: ohne Geraeteblatt bleibt das Tarifblatt."""
    satz = _mobil_s_12()
    beide = Tarifbestand(
        [
            {
                "tarif_id": "vodafone:vodafone-mobil-s",
                "anbieter": "Vodafone",
                "name": "Vodafone Mobil S",
                "grundgebuehr": 39.95,
            },
            {
                "tarif_id": "vodafone:vodafone-mobil-s-mit-smartphone",
                "anbieter": "Vodafone",
                "name": "Vodafone Mobil S mit Smartphone",
                "grundgebuehr": 39.95,
            },
        ]
    )
    mit = aus_rohsaetzen([satz], beide, "2026-09-05").buendel[0]
    ohne = aus_rohsaetzen([satz], _bestand_mit_mobil_s(), "2026-09-05").buendel[0]
    assert mit.tarif_id == "vodafone:vodafone-mobil-s-mit-smartphone"
    assert ohne.tarif_id == "vodafone:vodafone-mobil-s"
    assert mit.id == ohne.id


def test_ohne_aufgeloesten_tarifnamen_wird_verworfen_und_gezaehlt():
    """Kein Blocker fuer den Merge (siehe Auftrag) - aber auch kein
    stilles Ablegen einer Zahl ohne nachschlagbaren Tarif: dieselbe Regel
    wie bei o2 (`TcoDB.upsert_buendel` wuerde sonst werfen)."""
    satz = {
        **_saetze()[0],
        "anbieter": "Vodafone",
        "sku_id": "google-pixel-11-256gb-frost",
        "quelle_url": _saetze()[0]["url"],
    }
    assert satz["tarif_name"] == ""
    bilanz = aus_rohsaetzen([satz], _bestand_mit_mobil_s(), "2026-09-05")
    assert bilanz.buendel == []
    assert bilanz.ohne_tarif == 1


# ==========================================================================
# Die Verdrahtung: sammle_anbieter() ruft lies_buendel() auf derselben Seite
# ==========================================================================

_ROBOTS_FREI = (404, "")  # api.vodafone.de hat keine robots.txt


def _vodafone_anbieter():
    return Anbieter(
        name="Vodafone",
        typ="netzbetreiber",
        methode="vodafone_api",
        basis_url="https://www.vodafone.de",
        rate_limit_sekunden=0,
        kopfzeilen={"x-api-key": "geheim"},
        einstiege=[
            Einstieg(
                url="https://api.vodafone.de/glados/v2/hardware/v2"
                "?businessTransaction=newContract&salesChannel=Online.Consumer",
                label="Geraeteliste",
                kind="static",
            )
        ],
    )


def test_sammle_anbieter_liest_buendel_von_derselben_seite(katalog, farben):
    """Der Verdrahtungspunkt aus dem Auftrag: EIN Abruf der Detailseite
    liefert sowohl die Listung (`lies`) als auch die Buendelsaetze
    (`lies_buendel`) - kein zweiter `kind: buendel`-Einstieg noetig."""
    seiten = {
        "https://api.vodafone.de/glados/v2/hardware/v2"
        "?businessTransaction=newContract&salesChannel=Online.Consumer": _fixture(
            "vodafone_hardware_liste.json"
        ),
        "https://api.vodafone.de/glados/v2/hardware/v2/virtualItem/287"
        "?businessTransaction=newContract&salesChannel=Online.Consumer": _fixture(
            "vodafone_virtualitem.json"
        ),
    }

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        return 200, seiten.get(url, "")

    waechter = RobotsWaechter(hole=hole)
    bilanz = sammle_anbieter(
        _vodafone_anbieter(), katalog, farben, hole, "2026-09-05", waechter
    )
    assert bilanz.status == "ok"
    assert len(bilanz.listungen) == 3  # unveraendert: eine je Atom
    assert len(bilanz.buendel) == 12
    b = bilanz.buendel[0]
    assert b["anbieter"] == "Vodafone"
    assert b["sku_id"]  # ueber den Katalog gebildet
    assert b["geraet_zuzahlung"] == 1.0


def test_adapter_registry_traegt_vodafones_buendelhaken():
    adapter = ADAPTER["vodafone_api"]
    assert adapter.lies_buendel is not None
    assert adapter.loese_tarifnamen is not None
    assert adapter.direkt is False
