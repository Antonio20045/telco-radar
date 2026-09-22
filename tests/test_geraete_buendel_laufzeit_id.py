"""P0-B1 (21.09.2026): die Ratenlaufzeit gehoert in den Buendelschluessel.

Der Befund: `tco_model.buendel_id` bildete vier Segmente
(`buendel--<anbieter>--<sku>--<tarif>`). Die Anbieter bieten zum SELBEN
Tarif aber mehrere Ratenlaeufe an - Telekom 6/12/24/36, o2 24/36,
congstar 24/36, Vodafone 12/24/36. Ohne die Laufzeit im Schluessel
ueberschreiben sich diese Varianten gegenseitig, und der Bestand zeigt
willkuerlich eine von ihnen (deshalb liefert der congstar-Adapter bis
heute nur die 36er-Zahlweise, siehe dessen Modulkopf).

Diese Datei pinnt die ZWEITE Haelfte der Aenderung: dass die Historie
dabei nicht reisst. `data/state/geraete_tco.json` und
`geraete_tco_historie.jsonl` tragen IDs von VOR B1. Sie werden nicht
umgeschrieben (CLAUDE.md, harte Regeln 2 und 3), sondern beim Lesen
zugeordnet - aus `laufzeit_monate`, das jede dieser Zeilen ohnehin
traegt (`tco_store.id_aus_satz`).

Drei Fragen, drei Abschnitte:
  1. Stand:    ein Alt-Eintrag wird derselbe Eintrag, nicht ein zweiter.
  2. Zeitreihe: eine alte und eine neue Zeile landen in DERSELBEN Reihe.
  3. Gegenprobe am ECHTEN Bestand: kein Messtag geht verloren. Ein Test,
     dessen Lookup ins Leere laeuft, ist gruen und prueft nichts
     (CLAUDE.md, harte Regel 10) - deshalb misst Abschnitt 3 die Zahl
     der zugeordneten Zeilen mit und faellt durch, wenn sie einbricht.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from telco_radar.analyze.tco_store import TcoDB, basis_aus_satz, id_aus_satz
from telco_radar.report import geraete_zeitreihe
from telco_radar.tco_model import Buendel, buendel_id

_WURZEL = pathlib.Path(__file__).resolve().parent.parent
_STATE = _WURZEL / "data" / "state"

SKU = "apple-iphone-17-256gb-schwarz"
TARIF = "O2 Mobile Klein"
TARIF_ID = "o2:klein"

# Die ID, wie sie VOR B1 entstand - vier Segmente, ohne Laufzeit. Sie steht
# hier als Zeichenkette und nicht als Aufruf von `buendel_id`: der Punkt
# dieser Tests ist genau, dass die alte FORM noch zugeordnet wird.
ALT_ID = f"buendel--o2--{SKU}--o2-mobile-klein"


def _buendel(rate: float, laufzeit: int) -> Buendel:
    return Buendel(sku_id=SKU, anbieter="o2", tarif_name=TARIF,
                   tarif_id=TARIF_ID, tarif_id_guete="hoch",
                   tarif_monatlich=20.0, tarif_bindung_monate=24,
                   geraet_zuzahlung=1.0, geraet_monatsrate=rate,
                   laufzeit_monate=laufzeit, anschlusspreis=0.0,
                   zustand="neu", quelle_url="https://example.de/o2/17",
                   abgerufen_am="2026-09-20")


# --------------------------------------------------------------------------
# 1. Der Stand: derselbe Eintrag, nicht ein zweiter
# --------------------------------------------------------------------------

def _alter_stand(tmp_path: pathlib.Path, laufzeit: int = 36) -> pathlib.Path:
    """`geraete_tco.json` im Zustand von vor B1: ID ohne Laufzeitsegment."""
    pfad = tmp_path / "geraete_tco.json"
    pfad.write_text(json.dumps({
        "updated": "2026-09-20",
        "buendel": [{
            "id": ALT_ID, "sku_id": SKU, "anbieter": "o2",
            "tarif_name": TARIF, "tarif_id": TARIF_ID,
            "tarif_id_guete": "hoch", "tarif_monatlich": 20.0,
            "tarif_bindung_monate": 24, "buendel_monatlich": None,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": 18.0,
            "laufzeit_monate": laufzeit, "anschlusspreis": 0.0,
            "zustand": "neu", "rabatte": [],
            "quelle_url": "https://example.de/o2/17",
            "abgerufen_am": "2026-09-19", "first_seen": "2026-09-12",
            "last_verified": "2026-09-19"}],
        "sim_only": []}, ensure_ascii=False), encoding="utf-8")
    return pfad


def test_der_altbestand_wird_beim_lesen_auf_die_laufzeit_id_gehoben(tmp_path):
    db = TcoDB(_alter_stand(tmp_path, laufzeit=36))
    heute = buendel_id(SKU, "o2", TARIF, 36)

    assert db.nach_id(heute) is not None, \
        "der Alt-Eintrag ist unter seiner heutigen ID nicht zu finden"
    assert db.nach_id(ALT_ID) is None, \
        "die alte ID darf nicht DANEBEN weiterleben - das waere der Riss"
    assert [e["id"] for e in db.buendel()] == [heute]


def test_ein_lauf_legt_den_altbestand_nicht_ein_zweites_mal_an(tmp_path):
    """Der Schaden, gegen den die Lesemigration gebaut ist: ohne sie gilt
    der Altbestand als ausgelistet und entsteht daneben neu (der Docstring
    von `buendel_id` nennt genau das)."""
    db = TcoDB(_alter_stand(tmp_path, laufzeit=36))
    neu, gesehen = db.upsert_buendel([_buendel(18.0, 36)], "2026-09-21")

    assert neu == 0, "der Altbestand wurde als neues Buendel gezaehlt"
    assert len(db.buendel()) == 1
    eintrag = db.buendel()[0]
    assert eintrag["first_seen"] == "2026-09-12", \
        "die Lesemigration hat das Beobachtungsdatum verloren"
    assert gesehen == {buendel_id(SKU, "o2", TARIF, 36)}


def test_zwei_laufzeiten_stehen_als_zwei_eintraege_im_bestand(tmp_path):
    """Der eigentliche Zweck von B1 - vorher ueberschrieb der zweite Satz
    den ersten und der Bestand zeigte willkuerlich einen von beiden."""
    db = TcoDB(tmp_path / "geraete_tco.json")
    neu, gesehen = db.upsert_buendel(
        [_buendel(33.50, 36), _buendel(50.25, 24)], "2026-09-21")

    assert neu == 2 and len(gesehen) == 2
    raten = sorted(e["geraet_monatsrate"] for e in db.buendel())
    assert raten == [33.50, 50.25], \
        "eine der beiden Zahlweisen ist beim Ablegen verschwunden"


def test_eine_unbekannte_id_form_wird_benannt_und_nicht_verworfen(tmp_path,
                                                                  caplog):
    """"Scheitern ist kein leeres Ergebnis": eine ID, die weder die alte
    noch die heutige Form hat, bleibt im Bestand und steht im Protokoll."""
    pfad = tmp_path / "geraete_tco.json"
    pfad.write_text(json.dumps({
        "updated": "2026-09-20",
        "buendel": [{"id": "o2--irgendwas", "sku_id": SKU, "anbieter": "o2",
                     "tarif_name": TARIF, "laufzeit_monate": 24}],
        "sim_only": []}, ensure_ascii=False), encoding="utf-8")

    with caplog.at_level("WARNING"):
        db = TcoDB(pfad)
    assert db.nach_id("o2--irgendwas") is not None
    assert any("Lesemigration" in eintrag.getMessage()
               and "o2--irgendwas" in eintrag.getMessage()
               for eintrag in caplog.records)


# --------------------------------------------------------------------------
# 2. Die Zeitreihe: alte und neue Zeile in DERSELBEN Reihe
# --------------------------------------------------------------------------

_TCO_SICHT = {"modelle": [{"id": "apple-iphone-17-256",
                           "karten": [{"sku_id": SKU}]}],
              "band_je_tarif": {TARIF_ID: "klein"}}


def _historie_zeile(bid: str, datum: str, rate: float,
                    laufzeit: int = 36) -> dict:
    return {"id": bid, "datum": datum, "tarif_id": TARIF_ID,
            "tarif_id_guete": "hoch", "tarif_monatlich": 20.0,
            "tarif_bindung_monate": 24, "buendel_monatlich": None,
            "geraet_zuzahlung": 1.0, "geraet_monatsrate": rate,
            "laufzeit_monate": laufzeit, "anschlusspreis": 0.0,
            "quelle_url": "https://example.de/o2/17", "abgerufen_am": datum,
            "zustand": "neu", "gesamt": 1000.0}


def _reihe(tmp_path: pathlib.Path, zeilen: list[dict],
           stand_laufzeit: int = 36) -> dict:
    """Die Messungen je Tag fuer (Modell, Band, o2) aus diesen Zeilen."""
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    # Der Stand tragt die HEUTIGE ID - so schreibt ihn `TcoDB.save` seit B1.
    (state / "geraete_tco.json").write_text(json.dumps({
        "updated": "2026-09-21",
        "buendel": [{"id": buendel_id(SKU, "o2", TARIF, stand_laufzeit),
                     "sku_id": SKU, "anbieter": "o2", "tarif_name": TARIF,
                     "tarif_id": TARIF_ID, "laufzeit_monate": stand_laufzeit}],
        "sim_only": []}, ensure_ascii=False), encoding="utf-8")
    (state / "geraete_tco_historie.jsonl").write_text(
        "".join(json.dumps(z, ensure_ascii=False) + "\n" for z in zeilen),
        encoding="utf-8")
    messungen = geraete_zeitreihe._messungen(state, _TCO_SICHT, {})
    return (messungen.get(("apple-iphone-17-256", "klein")) or {}).get("o2") \
        or {}


def test_alte_und_neue_historienzeile_landen_in_derselben_reihe(tmp_path):
    """(b) des Auftrags: die Zeile von vor B1 (vier Segmente) und die von
    heute (fuenf) gehoeren demselben Buendel - die Reihe hat ZWEI Tage.

    Gegen den alten Stand ist das rot: dort traf die Alt-ID den
    Stand-Eintrag der heutigen Form nicht mehr, und der 19.09. fiel still
    aus dem Graphen."""
    tage = _reihe(tmp_path, [
        _historie_zeile(ALT_ID, "2026-09-19", 18.0),
        _historie_zeile(buendel_id(SKU, "o2", TARIF, 36), "2026-09-20", 17.0),
    ])
    assert sorted(tage) == ["2026-09-19", "2026-09-20"]


def test_die_laufzeit_der_zeile_entscheidet_nicht_die_vorgabe(tmp_path):
    """Eine Alt-Zeile ueber 12 Monate gehoert zum 12-Monats-Buendel, nicht
    zum 24er der Vorgabe: `laufzeit_monate` der ZEILE traegt die
    Zuordnung."""
    assert id_aus_satz(_historie_zeile(ALT_ID, "2026-09-19", 52.5,
                                       laufzeit=12)) == \
        buendel_id(SKU, "o2", TARIF, 12)
    # und der laufzeitfreie Teil ist der gemeinsame Nenner beider Varianten
    assert basis_aus_satz({"id": ALT_ID, "laufzeit_monate": 12}) == \
        basis_aus_satz({"id": buendel_id(SKU, "o2", TARIF, 36),
                        "laufzeit_monate": 36})


def test_eine_gemessene_laufzeit_ausserhalb_des_standes_kappt_keinen_tag(
        tmp_path):
    """Nichts kappen: wechselt ein Anbieter die Ratenlaufzeit, steht die
    gemessene Variante im heutigen Stand nicht mehr. Anbieter, SKU und
    Tarif haengen nicht an der Laufzeit - der Messtag bleibt."""
    tage = _reihe(tmp_path, [
        _historie_zeile(buendel_id(SKU, "o2", TARIF, 24), "2026-09-19", 25.0,
                        laufzeit=24),
        _historie_zeile(buendel_id(SKU, "o2", TARIF, 36), "2026-09-20", 17.0),
    ], stand_laufzeit=36)
    assert sorted(tage) == ["2026-09-19", "2026-09-20"]


def test_eine_zeile_ohne_zuordenbares_buendel_bleibt_ohne_punkt(tmp_path):
    """Die Gegenprobe zum Test darueber: ein FREMDES Geraet bekommt keinen
    Punkt - die Notzuordnung greift ueber die Laufzeit, nicht quer durch
    den Bestand."""
    fremd = buendel_id("apple-iphone-99-1tb-gold", "o2", TARIF, 36)
    tage = _reihe(tmp_path, [_historie_zeile(fremd, "2026-09-19", 18.0)])
    assert tage == {}


# --------------------------------------------------------------------------
# 3. Gegenprobe am ECHTEN Bestand
# --------------------------------------------------------------------------

@pytest.mark.skipif(not (_STATE / "geraete_tco_historie.jsonl").exists(),
                    reason="ohne Bestand keine Gegenprobe")
def test_am_echten_bestand_verliert_die_migration_keine_messung():
    """(c) des Auftrags, gemessen am 21.09.2026: 3854 Historienzeilen,
    720 Buendel, 9 Messtage, und JEDE Zeile findet ihr Buendel im Stand.

    Die Zahlen stehen als UNTERGRENZEN da (die Historie waechst jede
    Nacht) - aber die Quote steht hart: keine einzige Zeile darf ihre
    Zuordnung verlieren. Ohne die untere Grenze waere dieser Test gruen,
    auch wenn der Lookup ins Leere liefe.
    """
    stand = json.loads((_STATE / "geraete_tco.json").read_text(
        encoding="utf-8"))
    je_id, je_basis = {}, {}
    for b in stand.get("buendel") or []:
        bid = id_aus_satz(b)
        assert bid is not None, f"Stand-Eintrag ohne zuordenbare ID: {b!r}"
        je_id[bid] = b
        je_basis.setdefault(basis_aus_satz(b), b)

    zeilen = zugeordnet = 0
    buendel, tage = set(), set()
    for zeile in (_STATE / "geraete_tco_historie.jsonl").read_text(
            encoding="utf-8").splitlines():
        if not zeile.strip():
            continue
        satz = json.loads(zeile)
        zeilen += 1
        bid = id_aus_satz(satz)
        assert bid is not None, f"Historienzeile ohne ID-Form: {satz!r}"
        buendel.add(bid)
        tage.add(satz["datum"])
        if bid in je_id or basis_aus_satz(satz) in je_basis:
            zugeordnet += 1

    assert zeilen >= 3854 and len(buendel) >= 720 and len(tage) >= 9
    assert zugeordnet == zeilen, \
        (f"{zeilen - zugeordnet} von {zeilen} Historienzeilen finden nach "
         f"der Lesemigration kein Buendel mehr")
