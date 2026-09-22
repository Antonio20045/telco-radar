"""Provider-Probe je Lauf (Strategie v3, P5-Auftrag 2): die Existenz-Schwelle.

DIE REGEL, DIE DIESE DATEI FESTNAGELT
-------------------------------------
Die drei Proben aus Phase S (metric3+metric2 == monthlyPrice, metric5 ==
oneTimePrice, metric4 == activationFee, damals 66 von 66) sind im o2-Adapter
Bedingung fuer jeden Satz - aber ihr AUSBLEIBEN war bislang unsichtbar:
Eintraege, deren Trackingblock nicht mehr passt, fallen einfach heraus, die
Buendelzeile der Pipeline meldet "0 von 88", und niemand sieht, OB die
Feldstruktur starb oder der Anbieter nur nichts mehr verkauft (premortem.md,
FM 2). Die Probe zaehlt deshalb JE Kandidat die Feldebenen nach - als
Protokollzeile mit Zahl, ohne Mail, ohne Teams, ohne Statistik-Seite.

DIE FIXTURE IST EIN GESPEICHERTER ECHTER ABRUF
----------------------------------------------
`tests/fixtures/geraete/o2_katalog_buendel.json.gz` (Herkunft in
tests/fixtures/geraete/_herkunft.json) - 88 Eintraege, 66 Buendel. Die
"66 von 66" der Phase S sind damit kein nachgebauter, sondern der
gemessene Fall. Auch der TOTALTOD des Referenzfeldes (S2-1 der
P5-Codepruefung) wird an DIESELBE echte Antwort gemessen, nicht an
eine konstruierte.

ZWEI ALARME, ZWEI FÄLLE (S2-1: welcher greift wann)
---------------------------------------------------
- Preisblock tot, Antwort da (monthlyPrice komplett weg): o2 liefert
  seine LISTUNGEN ueber den hwOnly-Pfad weiter, `funde` bleibt > 0 -
  der Abdeckungswaechter (`test_geraete_abdeckung.py`) bleibt dauerhaft
  stumm. DIESE Probe ist der einzige Kanal, der den Fall meldet (Test
  unten: 0 % WARNING mit Ebene "monthlyPrice").
- GAR keine Antwort mehr: auch die Listungen bleiben aus -> Funde 0 ->
  der Vortagsvergleich schlaegt am naechsten Tag an
  (`test_geraete_abdeckung.py::test_wer_gestern_lieferte_und_heute_
  nichts_liefert_alarmiert` deckt genau diesen Weg).
"""
import json
import logging

from telco_radar.collect.geraete.o2 import lies_buendel
from telco_radar.geraete_pipeline import melde_proben, run_geraete_stage
# Repo-Uebung fuer Testfixtures ueber Modulgrenzen (siehe
# test_eine_seite_querlinks.py & Co.).
from test_geraete_buendel_o2 import _antwort, _eintrag, _katalog, _URL
from test_geraete_pipeline import _jetzt


# --------------------------------------------------------------------------
# Die gemessene Antwort
# --------------------------------------------------------------------------

def test_die_gemessene_antwort_besteht_alle_proben():
    """66 Kandidaten, 66 bestanden - die Existenz-Schwelle an der echten,
    unveraenderten Antwort vom 04.09.2026 (Praezedenz Phase S)."""
    proben: dict = {}
    saetze = lies_buendel(_katalog(), _URL, proben=proben)
    assert len(saetze) == 66
    assert proben == {"kandidaten": 66, "bestanden": 66}


def test_die_protokollzeile_hat_ihren_festen_wortlaut(caplog):
    """Die Zeile ist der Alarm - ein driftender Wortlaut waere im
    Actions-Log nicht mehr grepbar."""
    with caplog.at_level(logging.INFO, logger="telco_radar.geraete_pipeline"):
        melde_proben([{"anbieter": "o2",
                       "proben": {"kandidaten": 66, "bestanden": 66}}])
    assert ("Geraeteradar-Probe: o2 liefert 66 von 66 erwarteten Saetzen "
            "noch ihre Felder (100 %)") in caplog.text


# --------------------------------------------------------------------------
# Der Fall, fuer den die Probe gebaut ist
# --------------------------------------------------------------------------

def _antwort_ohne_metric3(n=2):
    eintraege = [_eintrag(beschreibung=f"Geraet {i}") for i in range(n)]
    for e in eintraege:
        del e["ecommerceProductValue"]["attributes"]["metric3"]
    return _antwort(*eintraege)


def test_verschwindende_feldebene_faellt_auf_null_prozent(caplog):
    """o2 loescht metric3 aus der Nutzlast: kein Abruf schlaegt fehl, alle
    Saetze fallen still heraus - die Probe meldet 0 % als WARNUNG und
    nennt die gescheiterte Feldebene mit Zahl."""
    proben: dict = {}
    saetze = lies_buendel(_antwort_ohne_metric3(), _URL, proben=proben)
    assert saetze == []
    assert proben == {"kandidaten": 2, "metric3+metric2": 2}
    with caplog.at_level(logging.WARNING,
                         logger="telco_radar.geraete_pipeline"):
        melde_proben([{"anbieter": "o2", "proben": proben}])
    assert ("Geraeteradar-Probe: o2 liefert 0 von 2 erwarteten Saetzen "
            "noch ihre Felder (0 %) - gescheitert an: 2x metric3+metric2") \
        in caplog.text
    assert caplog.records[-1].levelname == "WARNING"


def test_verschwindender_referenzbetrag_ist_eine_gescheiterte_probe():
    """Nicht nur die Trackingfelder: auch ein wegfallender TYPISIERTER
    Betrag (hier activationFee) ist das Verschwinden einer Feldebene -
    kein ungeeigneter Kandidat. Genau das soll die Probe melden."""
    e = _eintrag()
    del e["price"]["activationFee"]
    proben: dict = {}
    lies_buendel(_antwort(e), _URL, proben=proben)
    assert proben == {"kandidaten": 1, "metric4": 1}


def test_zubehoer_und_tariflose_zaehlen_nicht_als_kandidaten():
    """Ohne Erwartung keine Probe: Zubehoerbuendel und Eintraege ohne
    Tarifnamen fallen aus anderen Gruenden und duerfen die Quote nicht
    verwaessern."""
    zubehoer = _eintrag(beschreibung="Apple iPhone 17 Pro mit Watch Ultra 3")
    tariflos = _eintrag()
    del tariflos["bundle"]["tariffName"]
    proben: dict = {}
    lies_buendel(_antwort(zubehoer, tariflos, _eintrag()), _URL,
                 proben=proben)
    assert proben == {"kandidaten": 1, "bestanden": 1}


def test_ohne_kandidaten_steht_keine_zeile(caplog):
    """Grenzfall der Meldung: 0 Kandidaten heisst, die Probe lief nicht
    (kein Buendelzweig, oder jede Satz fiel VOR der Zaehlung - Zubehoer,
    tariflos). Kein Kandidat, keine Erwartung, keine Quote - dafuer sind
    die Buendel- und Ausfallzeile da. Der TOTALTOD des Referenzfeldes
    zaehlt dagegen als Kandidat mit gescheiterten Proben (Test unten)."""
    with caplog.at_level(logging.INFO, logger="telco_radar.geraete_pipeline"):
        melde_proben([{"anbieter": "o2", "proben": {"kandidaten": 0}}])
        melde_proben([{"anbieter": "Vodafone", "proben": {}}])
    assert "Geraeteradar-Probe" not in caplog.text


# --------------------------------------------------------------------------
# S2-1 der P5-Codepruefung: der Totaltod des Referenzfeldes, an der
# gespeicherten ECHTEN Antwort gemessen (88 Eintraege, 66 Buendel)
# --------------------------------------------------------------------------

def _katalog_ohne_monthlyprice() -> str:
    """Die echte Antwort vom 04.09. mit EINER Operation: `price.monthlyPrice`
    komplett entfernt - der Schnittstellen-Umbau der P5-Codepruefung,
    ausgefuehrt auf der gemessenen Menge statt auf einer konstruierten."""
    roh = json.loads(_katalog())
    for e in roh["hardware"]:
        e.get("price", {}).pop("monthlyPrice", None)
    return json.dumps(roh)


def test_totaltod_des_referenzfeldes_ist_eine_gescheiterte_probe(caplog):
    """Verschwindet monthlyPrice KOMPLETT aus der Antwort (Schnittstellen-
    Umbau), bleiben alle 66 Kandidaten Kandidaten - als GESCHEITERTE Probe
    der Ebene 'monthlyPrice' (0 %), nicht als Stille. Bis zum P5-Fix zaehlte
    der Code nur Kandidaten MIT monthlyPrice: kandidaten == 0, keine
    Probzeile - und Ausfallalarm (zaehlt LISTUNGEN, o2 liefert sie weiter)
    plus Buendelzeile ("0 von 0", Info) sahen dauerhaft normal aus."""
    proben: dict = {}
    saetze = lies_buendel(_katalog_ohne_monthlyprice(), _URL, proben=proben)
    assert saetze == []
    assert proben == {"kandidaten": 66, "monthlyPrice": 66}
    with caplog.at_level(logging.WARNING,
                         logger="telco_radar.geraete_pipeline"):
        melde_proben([{"anbieter": "o2", "proben": proben}])
    assert ("Geraeteradar-Probe: o2 liefert 0 von 66 erwarteten Saetzen "
            "noch ihre Felder (0 %) - gescheitert an: 66x monthlyPrice") \
        in caplog.text
    assert caplog.records[-1].levelname == "WARNING"


def test_ein_einzelfehler_ist_keine_perfektion(caplog):
    """199 von 200: round() wuerde 100 % daraus machen und die Info-Zeile
    waere Perfektion fuer einen gescheiterten Satz (S3 der P5-Codepruefung).
    Die Quote wird abgerundet - nur bestanden == erwartete heisst 100 %."""
    with caplog.at_level(logging.WARNING,
                         logger="telco_radar.geraete_pipeline"):
        melde_proben([{"anbieter": "o2",
                       "proben": {"kandidaten": 200, "bestanden": 199}}])
    assert "(99 %)" in caplog.text
    assert "100 %" not in caplog.text
    assert caplog.records[-1].levelname == "WARNING"


# --------------------------------------------------------------------------
# Ende-zu-Ende: der Collector reicht die Zaehler durch
# --------------------------------------------------------------------------

def test_der_lauf_traegt_die_probe_in_seine_bilanz(tmp_path, caplog):
    """Vom Adapterzaehler bis zur Protokollzeile in EINEM Lauf: der
    Collector reicht `bilanz.proben` nach `lies_buendel`, die Pipeline
    meldet sie. Ein Eintrag in der Antwort -> 1 von 1 (100 %)."""
    from test_geraete_pipeline import _o2_hole, _o2_root
    with caplog.at_level(logging.INFO, logger="telco_radar.geraete_pipeline"):
        bilanz = run_geraete_stage(_o2_root(tmp_path), {}, "2026-09-17",
                                   jetzt=_jetzt(), hole=_o2_hole())
    assert bilanz["anbieter"][0]["proben"] == {"kandidaten": 1,
                                               "bestanden": 1}
    assert ("Geraeteradar-Probe: o2 liefert 1 von 1 erwarteten Saetzen "
            "noch ihre Felder (100 %)") in caplog.text
