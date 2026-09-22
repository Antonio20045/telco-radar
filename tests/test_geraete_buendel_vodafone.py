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
        ("Frost", 256), ("Frost", 512), ("Hibiscus", 256)}
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
    sub = [s for s in _saetze() if s["tarif_slug"] in
           {_HASH_SUB, "8C1657624D227310534A73B7774CD7F3DFB49911C77BF8A498103C01F8E8CBE5",
            "9DCB892187186C326C9A82CDF8A8D47C8881E194247D538442982814A29D7A56"}]
    assert len(sub) == 3          # je Variante einer
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
    assert len(rate) == 9         # 3 Varianten x 3 Ratenfaelle (12/24/36)
    for s in rate:
        k = je_hash[s["tarif_slug"]]
        gesamt = k["totalMonthlyRatePrice"]["withoutDiscounts"][0]["gross"]
        assert s["geraet_monatsrate"] + s["tarif_monatlich"] == \
            pytest.approx(gesamt, abs=0.005)
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
        {**atom["prices"]["composition"][0], "offerCoreHash": ""}]
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
    return {"recurrenceUnit": "month", "recurrenceStart": start,
            "recurrenceEnd": ende, "gross": gross, "net": 58.82}


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
    saetze = lies_buendel(_sub_mit_phasen([_sub_phase(1, 24),
                                           _sub_phase(25, None)]))
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
                continue                  # der "sub"-Fall, siehe unten
            ende = (k["priceByComponent"]["hardware"]["priceByType"]["rate"]
                    ["month"]["withoutDiscounts"]["recurrenceEnd"])
            assert ende == dauer, (k["offerCoreHash"], dauer, ende)
            gemessen += 1
    assert gemessen == 9                   # 3 Varianten x 3 Ratenfaelle


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
    assert [p["recurrenceEnd"]
            for p in rate12["totalMonthlyRatePrice"]["withoutDiscounts"]] \
        == [12, 24]
    rate12["financingDuration"] = None
    atom["prices"]["composition"] = [rate12]

    saetze = lies_buendel(json.dumps(roh))
    assert len(saetze) == 1
    assert saetze[0]["laufzeit_monate"] == 12
    assert saetze[0]["geraet_zuzahlung"] + \
        saetze[0]["laufzeit_monate"] * saetze[0]["geraet_monatsrate"] == \
        pytest.approx(belegt, abs=0.005)


def test_gar_keine_bestimmbare_laufzeit_steht_im_protokoll(caplog):
    """Nur offene Phasen: nichts ist bestimmbar - und der Verlust wird
    BENANNT, nicht verschluckt (keine 0, keine geratene Laufzeit)."""
    with caplog.at_level("INFO", logger="telco_radar.collect.geraete.vodafone"):
        saetze = lies_buendel(_sub_mit_phasen([_sub_phase(1, None),
                                               _sub_phase(25, None)]))
    assert saetze == []
    meldungen = [r.getMessage() for r in caplog.records]
    assert any("ohne bestimmbare Ratenlaufzeit" in m for m in meldungen), \
        meldungen
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
    assert len(rate) == 9                  # 3 Varianten x 3 Ratenfaelle
    for s in rate:
        k = je_hash[s["tarif_slug"]]
        hardware_gesamt = k["priceByComponent"]["hardware"]["priceByType"] \
            ["total"]["onetime"]["withoutDiscounts"]["gross"]
        # `totalMonthlyRatePrice` traegt bei 12 und 36 Monaten ZWEI Phasen
        # (Modulkopf) - die Gegenprobe laeuft trotzdem auf.
        assert len(k["totalMonthlyRatePrice"]["withoutDiscounts"]) == \
            (1 if s["laufzeit_monate"] == 24 else 2)
        assert s["geraet_zuzahlung"] + \
            s["laufzeit_monate"] * s["geraet_monatsrate"] == \
            pytest.approx(hardware_gesamt, abs=0.005)

    # Die scharfe Gegenprobe (siehe Docstring): Phase 0 ohne Ende, Phase 1
    # mit Ende 24. Wer nur Phase 0 liest, verliert das ganze Buendel.
    scharf = lies_buendel(_sub_mit_phasen([_sub_phase(1, None),
                                           _sub_phase(2, 24)]))
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
    zweite_phase = {**erste_phase, "recurrenceStart": 25,
                    "recurrenceEnd": 30, "gross": erste_phase["gross"]}
    sub["totalMonthlyRatePrice"]["withoutDiscounts"] = [erste_phase,
                                                        zweite_phase]
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


def test_loese_tarifnamen_fuellt_bekannte_hashes_und_laesst_rest_leer():
    rohbuendel = [s for s in _saetze() if s["sku"] == "58060"]
    assert len(rohbuendel) == 4
    aufrufe = []

    def hole(url, kopfzeilen=None):
        aufrufe.append((url, kopfzeilen))
        assert "hardwareId=58060" in url
        assert kopfzeilen == {"x-api-key": "geheim"}
        return 200, _fixture("vodafone_tarif_hardware.json")

    aufgeloest = loese_tarifnamen(hole, {"x-api-key": "geheim"}, rohbuendel)
    assert aufgeloest == 2
    assert len(aufrufe) == 1                     # EIN GET je hardwareId
    je_hash = {s["tarif_slug"]: s["tarif_name"] for s in rohbuendel}
    assert je_hash[_HASH_RATE_12] == "Mobil S"
    assert je_hash[_HASH_RATE_24] == "Mobil M"
    assert je_hash[_HASH_SUB] == ""               # bleibt unaufgeloest
    assert je_hash[_HASH_RATE_36] == ""


def test_loese_tarifnamen_macht_nur_einen_get_je_hardwareid():
    """Zwoelf Rohsaetze, drei eindeutige `hardwareId` - nicht zwoelf GETs."""
    rohbuendel = _saetze()
    aufrufe = []

    def hole(url, kopfzeilen=None):
        aufrufe.append(url)
        return 200, _fixture("vodafone_tarif_hardware.json")

    loese_tarifnamen(hole, {}, rohbuendel)
    assert len(aufrufe) == 3
    assert len({u.split("hardwareId=")[1].split("&")[0] for u in aufrufe}) == 3


def test_loese_tarifnamen_uebersteht_einen_scheiternden_abruf():
    rohbuendel = [s for s in _saetze() if s["sku"] == "58060"]

    def hole(url, kopfzeilen=None):
        raise ConnectionError("kein Netz")

    assert loese_tarifnamen(hole, {}, rohbuendel) == 0
    assert all(s["tarif_name"] == "" for s in rohbuendel)


def test_loese_tarifnamen_uebersteht_einen_fehlerstatus():
    rohbuendel = [s for s in _saetze() if s["sku"] == "58060"]

    def hole(url, kopfzeilen=None):
        return 404, "nicht gefunden"

    assert loese_tarifnamen(hole, {}, rohbuendel) == 0


# ==========================================================================
# Vom aufgeloesten Rohsatz zum echten Buendel
# ==========================================================================

def _bestand_mit_mobil_s():
    """Der Tarifbestand, wie ihn der Tarif-Sammler aus einem Vodafone-PIB
    schreibt - Namen tragen dort das Markenpraefix, die Tarifantwort
    (`_hash_namen_aus_tarifantwort`) nicht. `ueber_namen()` gleicht das
    ueber `_ohne_marke` auf BEIDEN Seiten aus (siehe `tarif_bezug.py`)."""
    return Tarifbestand([
        {"tarif_id": "vodafone:vodafone-mobil-s", "anbieter": "Vodafone",
         "name": "Vodafone Mobil S", "grundgebuehr": 39.95},
    ])


def test_ein_aufgeloester_tarifname_ergibt_ein_echtes_buendel():
    """Der Weg zu Ende gegangen: Hash -> Klarname (Tarifschnittstelle) ->
    `tarif_id` (Tarifbestand, ueber den Namen ohne Markenpraefix)."""
    rohbuendel = [s for s in _saetze() if s["tarif_slug"] == _HASH_RATE_12]
    assert len(rohbuendel) == 1

    def hole(url, kopfzeilen=None):
        return 200, _fixture("vodafone_tarif_hardware.json")

    loese_tarifnamen(hole, {}, rohbuendel)
    assert rohbuendel[0]["tarif_name"] == "Mobil S"

    satz = {**rohbuendel[0], "anbieter": "Vodafone", "sku_id": "google-pixel-11-256gb-frost",
            "quelle_url": rohbuendel[0]["url"]}
    bilanz = aus_rohsaetzen([satz], _bestand_mit_mobil_s(), "2026-09-05")
    assert len(bilanz.buendel) == 1
    buendel = bilanz.buendel[0]
    assert buendel.tarif_id == "vodafone:vodafone-mobil-s"
    assert buendel.tarif_id_guete == HOCH
    assert buendel.geraet_zuzahlung == 1.0
    assert buendel.anschlusspreis == 0.0


def test_ohne_aufgeloesten_tarifnamen_wird_verworfen_und_gezaehlt():
    """Kein Blocker fuer den Merge (siehe Auftrag) - aber auch kein
    stilles Ablegen einer Zahl ohne nachschlagbaren Tarif: dieselbe Regel
    wie bei o2 (`TcoDB.upsert_buendel` wuerde sonst werfen)."""
    satz = {**_saetze()[0], "anbieter": "Vodafone",
            "sku_id": "google-pixel-11-256gb-frost",
            "quelle_url": _saetze()[0]["url"]}
    assert satz["tarif_name"] == ""
    bilanz = aus_rohsaetzen([satz], _bestand_mit_mobil_s(), "2026-09-05")
    assert bilanz.buendel == []
    assert bilanz.ohne_tarif == 1


# ==========================================================================
# Die Verdrahtung: sammle_anbieter() ruft lies_buendel() auf derselben Seite
# ==========================================================================

_ROBOTS_FREI = (404, "")   # api.vodafone.de hat keine robots.txt


def _vodafone_anbieter():
    return Anbieter(
        name="Vodafone", typ="netzbetreiber", methode="vodafone_api",
        basis_url="https://www.vodafone.de", rate_limit_sekunden=0,
        kopfzeilen={"x-api-key": "geheim"},
        einstiege=[Einstieg(
            url="https://api.vodafone.de/glados/v2/hardware/v2"
               "?businessTransaction=newContract&salesChannel=Online.Consumer",
            label="Geraeteliste", kind="static")])


def test_sammle_anbieter_liest_buendel_von_derselben_seite(katalog, farben):
    """Der Verdrahtungspunkt aus dem Auftrag: EIN Abruf der Detailseite
    liefert sowohl die Listung (`lies`) als auch die Buendelsaetze
    (`lies_buendel`) - kein zweiter `kind: buendel`-Einstieg noetig."""
    seiten = {
        "https://api.vodafone.de/glados/v2/hardware/v2"
        "?businessTransaction=newContract&salesChannel=Online.Consumer":
            _fixture("vodafone_hardware_liste.json"),
        "https://api.vodafone.de/glados/v2/hardware/v2/virtualItem/287"
        "?businessTransaction=newContract&salesChannel=Online.Consumer":
            _fixture("vodafone_virtualitem.json"),
    }

    def hole(url, kopfzeilen=None):
        if url.endswith("/robots.txt"):
            return _ROBOTS_FREI
        return 200, seiten.get(url, "")

    waechter = RobotsWaechter(hole=hole)
    bilanz = sammle_anbieter(_vodafone_anbieter(), katalog, farben, hole,
                             "2026-09-05", waechter)
    assert bilanz.status == "ok"
    assert len(bilanz.listungen) == 3          # unveraendert: eine je Atom
    assert len(bilanz.buendel) == 12
    b = bilanz.buendel[0]
    assert b["anbieter"] == "Vodafone"
    assert b["sku_id"]                          # ueber den Katalog gebildet
    assert b["geraet_zuzahlung"] == 1.0


def test_adapter_registry_traegt_vodafones_buendelhaken():
    adapter = ADAPTER["vodafone_api"]
    assert adapter.lies_buendel is not None
    assert adapter.loese_tarifnamen is not None
    assert adapter.direkt is False
