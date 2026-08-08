"""Lieferzeit-Radar (collect/lieferzeit.py + report/lieferzeit_view.py).

Es gibt keine oeffentliche Studie, gegen die jemand diese Zahlen gegenpruefen
koennte. Genau deshalb ist die Frage hier nicht "misst er?", sondern "schweigt
er, wo er nichts weiss?" - eine unbelegte Zahl ist auf dieser Seite schlimmer
als eine Luecke.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from telco_radar.collect import lieferzeit as L
from telco_radar.report import lieferzeit_view as V

JETZT = datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc)
SEITE = L.AnbieterSeite(marke="winSIM", produkt="iphone-topmodell",
                        url="https://x.test/iphone")
PRODUKT = L.Produkt(ref="iphone-topmodell", name="Apple iPhone 17 Pro",
                    variante="256 GB")


def _html(rumpf: str) -> str:
    return f"<html><body>{rumpf}</body></html>"


# ------------------------------------------------------------- Extraktion

@pytest.mark.parametrize("text,lage,lo,hi", [
    ("Sofort lieferbar, Lieferzeit 1-3 Werktage", "sofort", 1, 3),
    ("Lieferzeit ca. 14 Tage", "verzoegert", 14, 14),
    ("Versand in 2 bis 4 Wochen", "verzoegert", 14, 28),
    ("Derzeit nicht lieferbar", "nein", None, None),
    ("Sofort lieferbar", "sofort", 0, 0),
])
def test_lieferzeit_aus_dem_text(text, lage, lo, hi):
    gelesen = L.aus_text(text)
    assert gelesen is not None
    assert (gelesen[1], gelesen[2], gelesen[3]) == (lage, lo, hi)


def test_laufzeit_und_widerruf_sind_keine_lieferzeit():
    """Ohne den Kontexttest liest der Regex "24 Monate Laufzeit" und
    "14 Tage Widerrufsrecht" als Lieferzeit - beide stehen auf jeder
    Produktseite."""
    assert L.aus_text("Vertragslaufzeit 24 Monate, Widerruf 14 Tage") is None


def test_der_punkt_in_ca_zerschneidet_den_satz_nicht():
    """"Nicht auf Lager (Lieferzeit ca. 14 Tage)" zerfiel am "ca." in zwei
    Teile, und der erste las sich als "auf Lager" - also als sofort
    lieferbar, wo das Gegenteil dasteht."""
    gelesen = L.aus_text("Nicht auf Lager (Lieferzeit ca. 14 Tage)")
    assert gelesen[1] == "verzoegert" and gelesen[3] == 14


def test_platzhalter_gilt_nicht_als_messung():
    """otelo traegt seine Zustaende in einem JS-Woerterbuch: "Lieferzeit ca.
    {DELIVERY_TIME} Tage". Das ist keine Zahl, das ist eine Vorlage."""
    b = L.beobachte(_html("Lieferzeit ca. {DELIVERY_TIME} Tage"),
                    SEITE, PRODUKT, "40213", JETZT)
    assert b.quarantaene


# ------------------------------------------------------------------ JSON-LD

def test_jsonld_wird_gelesen_wenn_es_da_ist():
    """Gemessen am 08.08.2026 liefert kein deutscher Telko-Shop das - die
    Stufe bleibt trotzdem, weil sie die richtige ist und nichts kostet."""
    ld = json.dumps({
        "@type": "Product", "name": "x",
        "offers": {"@type": "Offer", "shippingDetails": {
            "@type": "OfferShippingDetails",
            "deliveryTime": {
                "handlingTime": {"minValue": 1, "maxValue": 1},
                "transitTime": {"minValue": 1, "maxValue": 2}}}}})
    b = L.beobachte(
        _html(f'<script type="application/ld+json">{ld}</script>'),
        SEITE, PRODUKT, "40213", JETZT)
    assert b.methode == "jsonld"
    assert b.belastbarkeit == L.HOCH
    assert (b.tage_min, b.tage_max) == (2, 3)
    assert b.verfuegbarkeit == "sofort"


def test_jsonld_ohne_versanddetails_faellt_auf_den_text_zurueck():
    """Genau der gemessene Fall: winSIM liefert ein sauberes Product samt
    Offer, aber ohne OfferShippingDetails."""
    ld = json.dumps({"@type": "Product", "name": "x",
                     "offers": {"@type": "Offer", "price": 1}})
    b = L.beobachte(
        _html(f'<script type="application/ld+json">{ld}</script>'
              "<p>Sofort lieferbar</p>"), SEITE, PRODUKT, "40213", JETZT)
    assert b.methode == "text"
    assert b.belastbarkeit == L.NIEDRIG


# ---------------------------------------------------------------- Quarantaene

def test_ohne_angabe_gibt_es_keine_zahl():
    b = L.beobachte(_html("<p>Tolles Handy</p>"), SEITE, PRODUKT, "40213",
                    JETZT)
    assert b.quarantaene == "keine Lieferzeitangabe gefunden"
    assert b.tage_max is None


def test_unplausibler_wert_geht_in_quarantaene():
    b = L.beobachte(_html("<p>Lieferzeit ca. 200 Tage</p>"), SEITE, PRODUKT,
                    "40213", JETZT)
    assert "unplausibel" in b.quarantaene


def test_quarantaene_erscheint_nicht_auf_der_seite():
    korb = L.Warenkorb(test_plz="40213", produkte=[PRODUKT])
    daten = {"reihen": {"iphone-topmodell|winSIM": [
        {"zeitstempel": "2026-08-08T09:00:00", "tage_max": 200,
         "quarantaene": "200 Tage - unplausibel", "anbieter": "winSIM"}]}}
    view = V.aufbereiten(daten, korb)
    feld = view["zeilen"][0]["felder"][0]
    assert feld["hat_wert"] is False
    assert view["n_quarantaene"] == 1


# ------------------------------------------------------------------ Engpass

def test_der_sprung_ist_die_nachricht_nicht_die_zahl():
    """Manche Anbieter liefern grundsaetzlich in zehn Tagen - das ist keine
    Nachricht. Die Nachricht ist die Veraenderung."""
    vorher = {"tage_max": 3}
    jetzt = L.Beobachtung(produkt_ref="p", produkt_name="P", anbieter="a",
                          url="u", zeitstempel="t", tage_max=21)
    assert L.ist_engpass(vorher, jetzt) is True
    # Dauerhaft langsam ist kein Engpass.
    assert L.ist_engpass({"tage_max": 20}, jetzt) is False
    # Ohne Vorwert auch nicht - der erste Messpunkt ist die Grundlinie.
    assert L.ist_engpass(None, jetzt) is False


def test_engpass_faerbt_die_zelle():
    korb = L.Warenkorb(test_plz="40213", produkte=[PRODUKT])
    reihe = [{"zeitstempel": "2026-08-01T09:00:00", "tage_max": 2,
              "verfuegbarkeit": "sofort", "anbieter": "winSIM"},
             {"zeitstempel": "2026-08-08T09:00:00", "tage_max": 21,
              "verfuegbarkeit": "verzoegert", "anbieter": "winSIM"}]
    view = V.aufbereiten({"reihen": {"iphone-topmodell|winSIM": reihe}}, korb)
    assert view["zeilen"][0]["felder"][0]["engpass"] is True


# ------------------------------------------------------------------ Speicher

def test_die_zeitreihe_waechst_und_hat_ein_ende(tmp_path):
    sp = L.Lieferzeitspeicher(tmp_path / "lieferzeit.json")
    for i in range(L.MAX_HISTORIE + 20):
        sp.anhaengen(L.Beobachtung(
            produkt_ref="p", produkt_name="P", anbieter="a", url="u",
            zeitstempel=(JETZT + timedelta(days=i)).isoformat(), tage_max=i))
    assert len(sp.reihe("p", "a")) == L.MAX_HISTORIE
    # Behalten wird das ENDE, nicht der Anfang.
    assert sp.letzte("p", "a")["tage_max"] == L.MAX_HISTORIE + 19


def test_letzte_ueberspringt_quarantaene(tmp_path):
    sp = L.Lieferzeitspeicher(tmp_path / "lieferzeit.json")
    sp.anhaengen(L.Beobachtung(produkt_ref="p", produkt_name="P",
                               anbieter="a", url="u", zeitstempel="t1",
                               tage_max=3))
    sp.anhaengen(L.Beobachtung(produkt_ref="p", produkt_name="P",
                               anbieter="a", url="u", zeitstempel="t2",
                               tage_max=200, quarantaene="unplausibel"))
    assert sp.letzte("p", "a")["tage_max"] == 3


# ---------------------------------------------------------------- Ende zu Ende

def test_ein_durchlauf_ohne_netz(tmp_path):
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "config" / "lieferzeit_warenkorb.yaml").write_text(
        'test_plz: "40213"\n'
        'produkte:\n  - ref: "p"\n    name: "Testgerät"\n'
        'anbieter:\n  - marke: "winSIM"\n    ident: "Video-Ident"\n'
        '    seiten:\n      - produkt: "p"\n        url: "https://x.test/1"\n',
        encoding="utf-8")
    bilanz = L.sammle(tmp_path, {}, jetzt=JETZT,
                      hole=lambda url: _html("<p>Lieferzeit 1-3 Werktage</p>"))
    assert bilanz["gemessen"] == 1 and bilanz["quarantaene"] == 0
    gespeichert = json.loads(
        (tmp_path / "data" / "state" / "lieferzeit.json").read_text("utf-8"))
    eintrag = gespeichert["reihen"]["p|winSIM"][0]
    assert eintrag["tage_max"] == 3
    # Der Originaltext wird IMMER mitgefuehrt - er ist der Beleg.
    assert "Werktage" in eintrag["lieferzeit_roh"]
    assert eintrag["plz"] == "40213"


def test_fehlende_konfiguration_legt_nichts_lahm(tmp_path):
    assert L.sammle(tmp_path, {}, jetzt=JETZT)["seiten"] == 0


def test_der_ausgelieferte_warenkorb_ist_klein_und_fest():
    korb = L.lade_warenkorb(Path(__file__).resolve().parents[1])
    assert korb.test_plz, "eine feste PLZ, konsistent verwendet"
    assert 2 <= len(korb.produkte) <= 6, "ein fester Warenkorb, kein Sortiment"
    # Jedes Produkt hat EINE festgelegte Variante - sonst vergleicht der
    # Verlauf wechselnde Konfigurationen und damit nichts.
    for p in korb.produkte:
        assert p.typ
    # Ident-Verfahren je Anbieter: die effektive Wartezeit haengt daran.
    assert all(m.get("ident") for m in korb.anbieter_meta.values())


def test_die_seite_nennt_ihre_grenzen():
    korb = L.lade_warenkorb(Path(__file__).resolve().parents[1])
    view = V.aufbereiten({"reihen": {}}, korb)
    assert view["test_plz"] == korb.test_plz
    assert view["aktiv"] is False      # ohne Messung keine Matrix
