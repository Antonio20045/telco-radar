"""Der Abdeckungswaechter (Phase P1, Paket C2): faellt ein Anbieter aus,
wird es laut.

WARUM ES DIESE DATEI GIBT
-------------------------
50 Laeufe von `geraete.yml` waren `success` - auch die sechs Tage, an denen
die Telekom keine einzige Zeile geliefert hat. Ein gruener Lauf ohne Daten
ist genau die Fehlerklasse, die CLAUDE.md Regel 9 verbietet: "Faellt eine
Stufe aus, zeigt die Seite das sichtbar an, statt 'nichts gefunden'
vorzutaeuschen."

DIE VIER REGELN, DIE HIER FESTGENAGELT SIND
-------------------------------------------
1. Wer gestern lieferte und heute nichts liefert, loest Alarm aus - nach
   EINEM Tag, nicht nach sieben.
2. Wer mehr als 30 % seiner Zeilen verliert, ebenso. 30 % genau nicht: die
   Schwelle ist echt groesser.
3. "Nicht gelesen" ist kein Ausfall. Ein Anbieter ausserhalb seiner
   Besuchszeit (robots.txt) faellt aus dem Vergleich heraus - er gilt aber
   auch nicht als in Ordnung.
4. Ein Anbieter ohne Vortagsdaten loest nichts aus. Unbekannt ist nicht
   "geliefert" und nicht "ausgefallen".

MODULEBENE ABSICHTLICH OHNE DIE NEUEN NAMEN
-------------------------------------------
Die Importe hier oben gibt es auch im Stand VOR diesem Auftrag. Das ist
Absicht: der Beweis, dass ein Test rot wird, ist nur dann einer, wenn er
mit einer ASSERTION faellt und nicht mit einem ImportError beim Einsammeln.
Die neuen Namen holen sich die Tests dort, wo sie sie brauchen.
"""
import logging

from telco_radar.analyze.geraete_store import GeraeteDB
from telco_radar.geraete_pipeline import run_geraete_stage
from telco_radar.report import geraete_view
from telco_radar.report.html import _env
# Die Fixtures des Pipeline-Tests sind der kuerzeste Weg zu einem Lauf mit
# echtem Store - Uebung dieses Repos (siehe test_geraete_stille_tage.py).
from test_geraete_pipeline import _SEITEN, _hole, _jetzt, _root

_LOGGER = "telco_radar.geraete_pipeline"


def _db(tmp_path):
    return GeraeteDB(tmp_path / "geraete_db.json")


def _tag(n: int) -> str:
    """Fixtures setzen ihr Datum selbst (CLAUDE.md Regel 11) - kein
    `date.today()`, nirgends."""
    return f"2026-09-{n:02d}"


# --------------------------------------------------------------------------
# Regel 1: ein Tag reicht
# --------------------------------------------------------------------------

def test_wer_gestern_lieferte_und_heute_nichts_liefert_alarmiert(tmp_path):
    from telco_radar.analyze.geraete_store import ALARM_AUSFALL

    db = _db(tmp_path)
    db.protokolliere_lauf("o2", _tag(1), funde=84, vollstaendig=True)
    db.protokolliere_lauf("o2", _tag(2), funde=0, vollstaendig=True)
    alarme = db.ausfall_alarme(heute=_tag(2))
    assert [a.anbieter for a in alarme] == ["o2"]
    assert alarme[0].art == ALARM_AUSFALL
    assert alarme[0].zeilen == 0 and alarme[0].zeilen_vortag == 84
    assert alarme[0].vortag == _tag(1)
    assert alarme[0].kurz == "heute nicht erfasst"
    assert "84" in alarme[0].satz and "01.09.2026" in alarme[0].satz


def test_ein_unveraenderter_tag_alarmiert_nicht(tmp_path):
    """Die Gegenprobe zum Test darueber: derselbe Aufbau, nur mit Zeilen -
    ohne sie wuerde ein Waechter, der immer meldet, hier gruen aussehen."""
    db = _db(tmp_path)
    db.protokolliere_lauf("o2", _tag(1), funde=84, vollstaendig=True)
    db.protokolliere_lauf("o2", _tag(2), funde=84, vollstaendig=True)
    assert db.ausfall_alarme(heute=_tag(2)) == []


# --------------------------------------------------------------------------
# Regel 2: die Schwelle
# --------------------------------------------------------------------------

def test_die_schwelle_steht_auf_dreissig_prozent():
    from telco_radar.analyze.geraete_store import ABDECKUNG_RUECKGANG

    assert ABDECKUNG_RUECKGANG == 0.30


def _rueckgang(tmp_path, gestern: int, heute: int):
    db = _db(tmp_path)
    db.protokolliere_lauf("congstar", _tag(1), funde=gestern, vollstaendig=True)
    db.protokolliere_lauf("congstar", _tag(2), funde=heute, vollstaendig=True)
    return db.ausfall_alarme(heute=_tag(2))


def test_mehr_als_dreissig_prozent_rueckgang_alarmiert(tmp_path):
    from telco_radar.analyze.geraete_store import ALARM_RUECKGANG

    alarme = _rueckgang(tmp_path, 100, 69)
    assert [a.anbieter for a in alarme] == ["congstar"]
    assert alarme[0].art == ALARM_RUECKGANG
    assert alarme[0].prozent == 31
    assert alarme[0].kurz == "heute unvollständig erfasst"


def test_genau_dreissig_prozent_alarmieren_nicht(tmp_path):
    """Die Grenze ist ECHT groesser. Steht sie auf 0, faellt dieser Test -
    das ist die Mutationsprobe dieser Schwelle."""
    assert _rueckgang(tmp_path, 100, 70) == []


def test_ein_kleiner_rueckgang_alarmiert_nicht(tmp_path):
    """20 % Rueckgang sind Sortimentsrauschen. Auch dieser Test faellt,
    sobald die Schwelle auf 0 sinkt."""
    assert _rueckgang(tmp_path, 100, 80) == []


def test_ein_zuwachs_alarmiert_nicht(tmp_path):
    assert _rueckgang(tmp_path, 100, 140) == []


# --------------------------------------------------------------------------
# Regel 3: "nicht gelesen" ist kein Ausfall
# --------------------------------------------------------------------------

def test_wer_nicht_gelesen_wurde_ist_kein_ausfall(tmp_path):
    """Medimax und ep.de duerfen laut robots.txt nur zwischen 02:00 und
    08:00 UTC abgerufen werden. Ein Lauf danach fasst sie nicht an - das
    ist eine Luecke, kein Quellentod."""
    from telco_radar.analyze.geraete_store import NICHT_GELESEN

    db = _db(tmp_path)
    db.protokolliere_lauf("Medimax", _tag(1), funde=20, vollstaendig=True)
    db.protokolliere_lauf("Medimax", _tag(2), funde=0, vollstaendig=False,
                          zustand=NICHT_GELESEN)
    assert db.ausfall_alarme(heute=_tag(2)) == []


def test_ein_lesefehler_ist_sehr_wohl_ein_ausfall(tmp_path):
    """Die Gegenprobe zum Test darueber, und der Kern dieser Phase: ein
    gescheiterter Abruf ist genau das, was gemeldet werden muss."""
    from telco_radar.analyze.geraete_store import LESEFEHLER

    db = _db(tmp_path)
    db.protokolliere_lauf("Medimax", _tag(1), funde=20, vollstaendig=True)
    db.protokolliere_lauf("Medimax", _tag(2), funde=0, vollstaendig=False,
                          zustand=LESEFEHLER)
    alarme = db.ausfall_alarme(heute=_tag(2))
    assert [a.anbieter for a in alarme] == ["Medimax"]
    assert alarme[0].zustand == "lesefehler"


def test_ein_nicht_gelesener_tag_zaehlt_auch_nicht_als_vortag(tmp_path):
    """Unbekannt faellt aus dem Vergleich - auf BEIDEN Seiten. Der Vortag
    ist deshalb der 01., nicht der uebersprungene 02."""
    from telco_radar.analyze.geraete_store import NICHT_GELESEN

    db = _db(tmp_path)
    db.protokolliere_lauf("Medimax", _tag(1), funde=20, vollstaendig=True)
    db.protokolliere_lauf("Medimax", _tag(2), funde=0, vollstaendig=False,
                          zustand=NICHT_GELESEN)
    db.protokolliere_lauf("Medimax", _tag(3), funde=0, vollstaendig=True)
    alarme = db.ausfall_alarme(heute=_tag(3))
    assert [(a.anbieter, a.vortag, a.zeilen_vortag) for a in alarme] == \
        [("Medimax", _tag(1), 20)]


# --------------------------------------------------------------------------
# Regel 4: ohne Vortag kein Alarm - und trotzdem kein "in Ordnung"
# --------------------------------------------------------------------------

def test_ohne_vortagsdaten_kein_alarm(tmp_path):
    db = _db(tmp_path)
    db.protokolliere_lauf("1&1", _tag(1), funde=0, vollstaendig=True)
    assert db.ausfall_alarme(heute=_tag(1)) == []


def test_ein_tag_ohne_messung_ist_kein_alarm(tmp_path):
    """Der Bezugstag selbst fehlt im Journal: der Anbieter war heute nicht
    an der Reihe. Keine Aussage, kein Alarm - und auch keine Entwarnung."""
    db = _db(tmp_path)
    db.protokolliere_lauf("1&1", _tag(1), funde=30, vollstaendig=True)
    assert db.ausfall_alarme(heute=_tag(2)) == []


def test_anhaltende_stille_wiederholt_sich_nicht_taeglich(tmp_path):
    """Tag 2 ist der Alarm. Tag 3 und 4 sind dieselbe, laengst gemeldete
    Stille - ein Waechter, der sie jeden Morgen erneut mailt, schaltet
    sich selbst stumm. Die anhaltende Stille traegt `stille_tage` und die
    Quellenseite."""
    db = _db(tmp_path)
    db.protokolliere_lauf("o2", _tag(1), funde=84, vollstaendig=True)
    for tag in (2, 3, 4):
        db.protokolliere_lauf("o2", _tag(tag), funde=0, vollstaendig=True)
    assert [a.anbieter for a in db.ausfall_alarme(heute=_tag(2))] == ["o2"]
    assert db.ausfall_alarme(heute=_tag(3)) == []
    assert db.ausfall_alarme(heute=_tag(4)) == []
    assert db.stille_tage("o2") == 3


# --------------------------------------------------------------------------
# Buendel sind Zeilen - der Telekom-Fall
# --------------------------------------------------------------------------

def test_buendel_zaehlen_als_zeilen(tmp_path):
    """Die Telekom liefert ausschliesslich Buendel und keine einzige
    Listung. An `funde` allein gemessen waere sie jeden Tag still - und
    ihr Ausfall an fuenf von 21 Tagen war der Anlass dieser Phase."""
    db = _db(tmp_path)
    db.protokolliere_lauf("Telekom", _tag(1), funde=0, vollstaendig=True,
                          buendel=9)
    assert db.ausfall_alarme(heute=_tag(1)) == []
    db.protokolliere_lauf("Telekom", _tag(2), funde=0, vollstaendig=True,
                          buendel=9)
    assert db.ausfall_alarme(heute=_tag(2)) == []
    db.protokolliere_lauf("Telekom", _tag(3), funde=0, vollstaendig=True,
                          buendel=0)
    alarme = db.ausfall_alarme(heute=_tag(3))
    assert [(a.anbieter, a.zeilen_vortag) for a in alarme] == [("Telekom", 9)]


# --------------------------------------------------------------------------
# Was der Alarm NICHT tut
# --------------------------------------------------------------------------

def test_der_alarm_loest_nichts_aus(tmp_path):
    """Gegenprobe zur Zusicherung: der Alarm veraendert die Listungen
    nicht. Ein aktiver Bestand bleibt aktiv, egal wie still die Quelle
    ist - Altern steht allein auf `mark_stale`/`vollstaendig`."""
    from test_geraete_store import _listung

    db = _db(tmp_path)
    db.upsert([_listung(anbieter="o2")], _tag(1))
    db.protokolliere_lauf("o2", _tag(1), funde=1, vollstaendig=True)
    db.protokolliere_lauf("o2", _tag(2), funde=0, vollstaendig=True)
    assert [a.anbieter for a in db.ausfall_alarme(heute=_tag(2))] == ["o2"]
    eintraege = db.eintraege()
    assert len(eintraege) == 1 and eintraege[0]["status"] == "aktiv"
    assert eintraege[0]["last_verified"] == _tag(1)


def test_nur_begrenzt_auf_den_lauf(tmp_path):
    """Ein nicht mehr konfigurierter Anbieter wird nicht mehr beobachtet."""
    db = _db(tmp_path)
    db.protokolliere_lauf("o2", _tag(1), funde=84, vollstaendig=True)
    db.protokolliere_lauf("o2", _tag(2), funde=0, vollstaendig=True)
    assert db.ausfall_alarme(nur={"Vodafone"}, heute=_tag(2)) == []
    assert [a.anbieter for a in
            db.ausfall_alarme(nur={"o2"}, heute=_tag(2))] == ["o2"]


def test_der_altbestand_gilt_als_gelesen(tmp_path):
    """Eintraege der Form `[tag, funde]` stammen aus der Zeit vor diesem
    Auftrag. Sie entstanden AUSSCHLIESSLICH fuer vollstaendige Laeufe oder
    Laeufe mit Funden - "gelesen" ist dort eine Ableitung aus der
    damaligen Schreibregel, keine Annahme."""
    import json

    pfad = tmp_path / "geraete_db.json"
    pfad.write_text(json.dumps({
        "updated": _tag(2), "anbieter": {"o2": {
            "laeufe": 2, "funde_gesamt": 84, "letzter_fund": _tag(1),
            "termine": [_tag(1), _tag(2)],
            "funde_nach_tag": [[_tag(1), 84], [_tag(2), 0]]}},
        "listungen": []}, ensure_ascii=False), encoding="utf-8")
    db = GeraeteDB(pfad)
    assert [a.anbieter for a in db.ausfall_alarme(heute=_tag(2))] == ["o2"]
    assert db.letzter_messtag() == _tag(2)


# --------------------------------------------------------------------------
# Ende zu Ende: der abgeschaltete Collector
# --------------------------------------------------------------------------

def test_ein_abgeschalteter_collector_loest_den_alarm_aus(tmp_path, caplog):
    """DAS TOR DIESER PHASE. Tag 1 liefert zwei Listungen, an Tag 2
    antwortet keine einzige Seite mehr - genau der Zustand, in dem 50
    Laeufe gruen blieben. Der Alarm steht im Protokoll, in der Bilanz des
    Laufs, und er hat nichts gealtert."""
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        bilanz = run_geraete_stage(root, {}, "2026-08-12", jetzt=_jetzt(),
                                   hole=_hole({}))
    assert ("Geraeteradar-Abdeckung: Medimax: heute nicht erfasst – 0 Zeilen, "
            "am 11.08.2026 waren es 2 (Zustand lesefehler). "
            "(Quelle pruefen: geraete-quellen.html)") in caplog.text
    assert [a["anbieter"] for a in bilanz["abdeckung_alarme"]] == ["Medimax"]
    assert bilanz["abdeckung_alarme"][0]["kurz"] == "heute nicht erfasst"
    # Der Alarm ist Meldung, kein Griff: nichts ist gealtert.
    assert bilanz["gealtert"] == 0


def test_eine_leer_gelesene_seite_loest_den_alarm_ebenfalls_aus(tmp_path,
                                                                caplog):
    """Der zweite Weg in denselben Befund: die Kategorieseite antwortet
    mit 200 und ist leer. Der Lauf ist "vollstaendig", der Anbieter
    liefert trotzdem nichts."""
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    leer = dict(_SEITEN)
    leer["https://www.medimax.de/c/116/smartphones"] = "<html><body></body></html>"
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        bilanz = run_geraete_stage(root, {}, "2026-08-12", jetzt=_jetzt(),
                                   hole=_hole(leer))
    assert "Medimax: heute nicht erfasst" in caplog.text
    assert bilanz["abdeckung_alarme"][0]["zustand"] == "gelesen"


def test_ausserhalb_der_besuchszeit_bleibt_der_waechter_still(tmp_path,
                                                              caplog):
    """Ende zu Ende fuer Regel 3: dieselbe Lage wie oben, nur dass die
    robots.txt den Abruf zu dieser Stunde verbietet. Kein Alarm - und
    zwar gemessen am Bilanz-Flag, nicht an einem Grundtext."""
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(3), hole=_hole())

    def hole(url):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nVisit-time: 0200-0800\n")
        return (200, _SEITEN[url]) if url in _SEITEN else (404, "")

    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        bilanz = run_geraete_stage(root, {}, "2026-08-12", jetzt=_jetzt(8),
                                   hole=hole)
    medimax = [a for a in bilanz["anbieter"] if a["anbieter"] == "Medimax"][0]
    assert medimax["listungen"] == 0        # nichts geholt
    assert bilanz["abdeckung_alarme"] == []
    assert "Geraeteradar-Abdeckung" not in caplog.text


def test_ein_uebersprungener_anbieter_alarmiert_nie(tmp_path):
    """Amazon ist `methode: deaktiviert` - der Lauf fasst ihn nie an. Er
    darf weder alarmieren noch als "in Ordnung" durchgehen."""
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    run_geraete_stage(root, {}, "2026-08-12", jetzt=_jetzt(), hole=_hole())
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert [m.zustand for m in db.messtage("Amazon")] == \
        ["nicht gelesen", "nicht gelesen"]
    assert db.ausfall_alarme(heute="2026-08-12") == []


# --------------------------------------------------------------------------
# Der Alarm auf der Seite
# --------------------------------------------------------------------------

def _seitenzeile(tmp_path):
    """Ein echter Lauf, ein echter Ausfall - und daraus die Zeile der
    Quellenseite."""
    from telco_radar.geraete_config import lade_katalog, lade_quellen

    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    run_geraete_stage(root, {}, "2026-08-12", jetzt=_jetzt(), hole=_hole({}))
    daten = geraete_view.aufbereiten(root / "data" / "state",
                                     lade_quellen(root), lade_katalog(root),
                                     heute="2026-08-12")
    zeilen = {z["name"]: z for z in daten["quellenlage"]["zeilen"]}
    return zeilen


def test_der_alarm_steht_auf_der_quellenseite(tmp_path):
    zeilen = _seitenzeile(tmp_path)
    assert zeilen["Medimax"]["abdeckung"]["kurz"] == "heute nicht erfasst"
    assert "11.08.2026" in zeilen["Medimax"]["abdeckung"]["satz"]
    # Gegenprobe: der uebersprungene Anbieter traegt KEINE leere Huelle.
    assert zeilen["Amazon"]["abdeckung"] is None


def test_die_vorlage_zeigt_heute_nicht_erfasst(tmp_path):
    """Gemessen am echten Makro, nicht am Datensatz: die Zeile der
    Quellenseite traegt den Satz und den roten Punkt."""
    zeilen = _seitenzeile(tmp_path)
    # Die Vorlage erbt von `base.html.j2` und braucht darum ihren Rahmen -
    # gemessen wird trotzdem das ECHTE Makro, nicht eine Kopie davon.
    modul = _env().get_template("geraete_quellen.html.j2").make_module(
        {"geraete": {"quellenlage": {"zeilen": [], "ohne_hardware": [],
                                     "aufgefuehrt": 0, "liefernd": 0,
                                     "seiten": 0},
                     "stand": "", "pruefung": {}},
         "prefix": ""})
    html = modul.zeile(zeilen["Medimax"])
    assert "heute nicht erfasst" in html
    assert "sdot fail" in html
    # Gegenprobe: ohne Alarm steht der Dauerzustand da, nicht der Satz.
    ohne = modul.zeile(zeilen["Amazon"])
    assert "heute nicht erfasst" not in ohne


# --------------------------------------------------------------------------
# Die Mail
# --------------------------------------------------------------------------

def test_die_mail_traegt_jeden_alarm_und_keine_zugangsdaten(tmp_path):
    from telco_radar.geraete_pipeline import baue_alarm_mail

    db = _db(tmp_path)
    db.protokolliere_lauf("Telekom", _tag(1), funde=0, vollstaendig=True,
                          buendel=9)
    db.protokolliere_lauf("Telekom", _tag(2), funde=0, vollstaendig=True)
    db.protokolliere_lauf("o2", _tag(1), funde=100, vollstaendig=True)
    db.protokolliere_lauf("o2", _tag(2), funde=50, vollstaendig=True)
    alarme = db.ausfall_alarme(heute=_tag(2))
    betreff, text, html = baue_alarm_mail(alarme, _tag(2))
    assert "02.09.2026" in betreff and "2 Anbieter" in betreff
    for alarm in alarme:
        assert alarm.satz in text
        assert alarm.anbieter in html
    assert "geraete-quellen.html" in text and "geraete-quellen.html" in html
    # Der Betreff sortiert den groessten Einbruch nach vorn.
    assert text.index("Telekom") < text.index("o2")


def test_ohne_alarm_geht_keine_mail_hinaus(tmp_path, monkeypatch):
    from telco_radar import versand
    from telco_radar.geraete_pipeline import sende_alarm_mail

    gesendet = []
    monkeypatch.setattr(versand, "sende_mail",
                        lambda *a, **k: gesendet.append(a) or "gesendet")
    assert "keine" in sende_alarm_mail([], _tag(2))
    assert gesendet == []


def test_mit_alarm_geht_genau_eine_mail_hinaus(tmp_path, monkeypatch):
    from telco_radar import versand
    from telco_radar.geraete_pipeline import sende_alarm_mail

    gesendet = []

    def _fake(betreff, text, html, *, trocken=False):
        gesendet.append((betreff, text, html))
        return "an 1 Empfänger"

    monkeypatch.setattr(versand, "sende_mail", _fake)
    db = _db(tmp_path)
    db.protokolliere_lauf("o2", _tag(1), funde=84, vollstaendig=True)
    db.protokolliere_lauf("o2", _tag(2), funde=0, vollstaendig=True)
    ergebnis = sende_alarm_mail(db.ausfall_alarme(heute=_tag(2)), _tag(2))
    assert ergebnis == "an 1 Empfänger"
    assert len(gesendet) == 1
    assert "heute nicht erfasst" in gesendet[0][1]


def test_ein_zustellfehler_wird_nicht_geschluckt(tmp_path, monkeypatch):
    """Scheitern ist kein leeres Ergebnis (Clean Code 5): der Fehler geht
    an den Aufrufer weiter, der Workflow-Schritt faellt rot aus."""
    import pytest

    from telco_radar import versand
    from telco_radar.geraete_pipeline import sende_alarm_mail

    def _wirft(*a, **k):
        raise versand.VersandFehler("SMTP_HOST fehlt")

    monkeypatch.setattr(versand, "sende_mail", _wirft)
    db = _db(tmp_path)
    db.protokolliere_lauf("o2", _tag(1), funde=84, vollstaendig=True)
    db.protokolliere_lauf("o2", _tag(2), funde=0, vollstaendig=True)
    with pytest.raises(versand.VersandFehler):
        sende_alarm_mail(db.ausfall_alarme(heute=_tag(2)), _tag(2))


# --------------------------------------------------------------------------
# Regel 5: "teilweise gelesen" ist weder "nicht angefasst" noch "gelesen"
#
# Der Befund (S2-1): ein EINZIGER am Fenster abgewiesener Abruf setzte
# `bilanz.ausserhalb_besuchszeit`, und daraus wurde fuer den GANZEN
# Anbieter NICHT_GELESEN - auch wenn er vier Produktseiten gelesen und
# drei Listungen geliefert hatte. Der Waechter war damit fuer medimax und
# ep.de im Regelfall blind, denn genau diese zwei haengen an ihrem
# Fenster. "Gar nicht angefasst" und "teilweise gelesen, Tuer ging zu"
# sind zwei Auskuenfte, und nur die erste ist keine Aussage.
# --------------------------------------------------------------------------

def _bilanz(**kw):
    from telco_radar.collect.geraete import Anbieterbilanz

    b = Anbieterbilanz(name=kw.pop("name", "Medimax"))
    for feld, wert in kw.items():
        setattr(b, feld, wert)
    return b


def test_ein_teillauf_am_fenster_ist_nicht_nicht_gelesen():
    """Die Kernumkehrung: etwas gelesen ist nicht nichts gelesen."""
    from telco_radar.geraete_pipeline import _abdeckungszustand

    bilanz = _bilanz(status="frist", ausserhalb_besuchszeit=True,
                     gelesene_einstiege={"https://www.medimax.de/c/116"},
                     listungen=[1, 2, 3])
    assert _abdeckungszustand(bilanz) == "teilweise gelesen"


def test_wer_wirklich_nichts_gelesen_hat_bleibt_nicht_gelesen():
    """Die Gegenprobe: ohne einen einzigen gelesenen Einstieg, ohne
    Listung und ohne Buendel bleibt es bei der Luecke."""
    from telco_radar.geraete_pipeline import _abdeckungszustand

    bilanz = _bilanz(status="frist", ausserhalb_besuchszeit=True)
    assert _abdeckungszustand(bilanz) == "nicht gelesen"


def test_auch_buendel_allein_sind_ein_lebenszeichen():
    """Die Telekom liefert ausschliesslich Buendel - an Listungen gemessen
    waere sie auch hier "nicht angefasst"."""
    from telco_radar.geraete_pipeline import _abdeckungszustand

    bilanz = _bilanz(status="frist", ausserhalb_besuchszeit=True,
                     buendel=[{"sku": "x"}])
    assert _abdeckungszustand(bilanz) == "teilweise gelesen"


def test_der_teiltag_faellt_nicht_aus_dem_vergleich(tmp_path):
    """Ein Teiltag ohne eine einzige Zeile ist ein Ausfall und wird
    gemeldet - anders als der Tag, an dem gar nicht gelesen wurde."""
    from telco_radar.analyze.geraete_store import ALARM_AUSFALL

    db = _db(tmp_path)
    db.protokolliere_lauf("Medimax", _tag(1), funde=20, vollstaendig=True)
    db.protokolliere_lauf("Medimax", _tag(2), funde=0, vollstaendig=False,
                          zustand="teilweise gelesen")
    alarme = db.ausfall_alarme(heute=_tag(2))
    assert [(a.anbieter, a.art) for a in alarme] == [("Medimax", ALARM_AUSFALL)]


def test_ein_teiltag_senkt_die_vergleichsbasis_nicht(tmp_path):
    """DIE ZWEITE HAELFTE DER REGEL. Der Teiltag selbst ist keine Aussage
    ueber die Abdeckung: seine drei Zeilen sind das, was bis zum
    Fensterende durchkam, nicht das Sortiment. Als Vergleichsbasis
    genommen senkte er die Messlatte auf sich selbst - der echte
    Totalausfall am Folgetag faende dann keinen Vergleich mehr, gegen den
    er auffallen koennte (3 statt 100 Zeilen im Alarm, oder bei 0 Zeilen
    am Teiltag gar kein Alarm)."""
    db = _db(tmp_path)
    db.protokolliere_lauf("Medimax", _tag(1), funde=100, vollstaendig=True)
    db.protokolliere_lauf("Medimax", _tag(2), funde=3, vollstaendig=False,
                          zustand="teilweise gelesen")
    db.protokolliere_lauf("Medimax", _tag(3), funde=0, vollstaendig=True)
    alarme = db.ausfall_alarme(heute=_tag(3))
    assert [(a.anbieter, a.vortag, a.zeilen_vortag) for a in alarme] == \
        [("Medimax", _tag(1), 100)]


def test_der_zustand_heisst_genau_so():
    """Die Wortform steht in der Mail, im Protokoll und auf der Seite -
    sie ist Vertrag, kein Zufall."""
    from telco_radar.analyze.geraete_store import TEILGELESEN

    assert TEILGELESEN == "teilweise gelesen"


# --------------------------------------------------------------------------
# Der dritte Seitenzustand: "heute nicht gelesen" (S2-2)
#
# `liefert` kommt aus dem BESTAND. Ein Anbieter, den der Lauf heute gar
# nicht erreicht hat, bekam damit einen gruenen Punkt und das Wort
# "liefert" - eine Entwarnung, die niemand gemessen hat. Der dritte
# Zustand kommt aus DERSELBEN Definition wie der Waechter: dem
# Lesezustand des Bezugstags.
# --------------------------------------------------------------------------

def _quellenlage_ausserhalb(tmp_path):
    """Tag 1 liefert, an Tag 2 verbietet die robots.txt den Abruf."""
    from telco_radar.geraete_config import lade_katalog, lade_quellen

    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(3), hole=_hole())

    def hole(url):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nVisit-time: 0200-0800\n")
        return (200, _SEITEN[url]) if url in _SEITEN else (404, "")

    run_geraete_stage(root, {}, "2026-08-12", jetzt=_jetzt(8), hole=hole)
    daten = geraete_view.aufbereiten(root / "data" / "state",
                                     lade_quellen(root), lade_katalog(root),
                                     heute="2026-08-12")
    return daten["quellenlage"]


def _quellenzeilen_ausserhalb(tmp_path):
    return {z["name"]: z for z in _quellenlage_ausserhalb(tmp_path)["zeilen"]}


def _quellenmakro():
    """Das ECHTE Makro der Quellenseite, mit dem Rahmen, den es von
    `base.html.j2` erbt - keine Kopie davon."""
    return _env().get_template("geraete_quellen.html.j2").make_module(
        {"geraete": {"quellenlage": {"zeilen": [], "ohne_hardware": [],
                                     "aufgefuehrt": 0, "liefernd": 0,
                                     "seiten": 0},
                     "stand": "", "pruefung": {}},
         "prefix": ""})


def test_die_kennzahl_zaehlt_nur_wer_heute_gelesen_wurde(tmp_path):
    """Die groesste Zahl des Bereichs, gegen den Lesezustand gehalten
    (CLAUDE.md Regel 10). "10 liefern Geräte" stand ueber genau den
    Zeilen, die "heute nicht gelesen" tragen: die Entwarnung, die der
    Punkt nicht mehr gibt, gab die Kennzahl. Gemessen an den wirklich
    gerenderten Zeilen, nicht am Datensatz."""
    quellenlage = _quellenlage_ausserhalb(tmp_path)
    zeilen = {z["name"]: z for z in quellenlage["zeilen"]}
    # Die Lage: der Bestand SAGT "liefert", gelesen hat heute niemand.
    assert zeilen["Medimax"]["liefert"] is True
    assert zeilen["Medimax"]["heute_luecke"] is True
    makro = _quellenmakro()
    gruen = sum(1 for z in quellenlage["zeilen"]
                if "sdot ok" in makro.zeile(z))
    assert quellenlage["liefernd"] == gruen
    assert quellenlage["liefernd"] == 0


def test_die_kennzahl_zaehlt_wer_heute_gelesen_wurde(tmp_path):
    """Die Gegenprobe: derselbe Aufbau innerhalb der Besuchszeit. Ohne
    sie waere eine Kennzahl, die immer 0 meldet, gruen."""
    from telco_radar.geraete_config import lade_katalog, lade_quellen

    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    run_geraete_stage(root, {}, "2026-08-12", jetzt=_jetzt(), hole=_hole())
    quellenlage = geraete_view.aufbereiten(
        root / "data" / "state", lade_quellen(root), lade_katalog(root),
        heute="2026-08-12")["quellenlage"]
    makro = _quellenmakro()
    gruen = sum(1 for z in quellenlage["zeilen"]
                if "sdot ok" in makro.zeile(z))
    assert quellenlage["liefernd"] == gruen
    assert quellenlage["liefernd"] == 1


def test_wer_heute_nicht_gelesen_wurde_bekommt_keinen_gruenen_punkt(tmp_path):
    zeilen = _quellenzeilen_ausserhalb(tmp_path)
    modul = _env().get_template("geraete_quellen.html.j2").make_module(
        {"geraete": {"quellenlage": {"zeilen": [], "ohne_hardware": [],
                                     "aufgefuehrt": 0, "liefernd": 0,
                                     "seiten": 0},
                     "stand": "", "pruefung": {}},
         "prefix": ""})
    html = modul.zeile(zeilen["Medimax"])
    # Gegenprobe: der Bestand SAGT weiter "liefert" - genau daher kam der
    # gruene Punkt.
    assert zeilen["Medimax"]["liefert"] is True
    assert zeilen["Medimax"]["abdeckung"] is None
    assert "sdot ok" not in html
    assert "heute nicht gelesen" in html


def test_wer_heute_gelesen_wurde_behaelt_seinen_gruenen_punkt(tmp_path):
    """Die Gegenprobe: derselbe Aufbau, nur innerhalb der Besuchszeit."""
    zeilen = _seitenzeile_gelesen(tmp_path)
    modul = _env().get_template("geraete_quellen.html.j2").make_module(
        {"geraete": {"quellenlage": {"zeilen": [], "ohne_hardware": [],
                                     "aufgefuehrt": 0, "liefernd": 0,
                                     "seiten": 0},
                     "stand": "", "pruefung": {}},
         "prefix": ""})
    html = modul.zeile(zeilen["Medimax"])
    assert "sdot ok" in html and "liefert" in html
    assert "heute nicht gelesen" not in html


def _seitenzeile_gelesen(tmp_path):
    from telco_radar.geraete_config import lade_katalog, lade_quellen

    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    run_geraete_stage(root, {}, "2026-08-12", jetzt=_jetzt(), hole=_hole())
    daten = geraete_view.aufbereiten(root / "data" / "state",
                                     lade_quellen(root), lade_katalog(root),
                                     heute="2026-08-12")
    return {z["name"]: z for z in daten["quellenlage"]["zeilen"]}


# --------------------------------------------------------------------------
# Das Journal liest, was dasteht - und erfindet nichts
# --------------------------------------------------------------------------

def test_ein_unlesbarer_messtag_wird_nicht_erfunden(tmp_path, caplog):
    """Ein String im Journal ist kein Messtag. Er wurde bis hierher
    ZEICHENWEISE gelesen ("2026-09-01"[0] -> Tag "2", [1] -> Funde 0) und
    ergab einen erfundenen Eintrag, der sich in jeden Vergleich mischt.
    Laut scheitern statt still Muell erzeugen (Clean Code 5)."""
    import json

    pfad = tmp_path / "geraete_db.json"
    pfad.write_text(json.dumps({
        "updated": _tag(2), "anbieter": {"o2": {
            "laeufe": 1, "funde_gesamt": 5,
            "funde_nach_tag": ["2026-09-01", [_tag(2), 5, "gelesen", 0],
                               {"tag": _tag(3)}]}},
        "listungen": []}, ensure_ascii=False), encoding="utf-8")
    db = GeraeteDB(pfad)
    with caplog.at_level(logging.WARNING,
                         logger="telco_radar.analyze.geraete_store"):
        journal = db.messtage("o2")
    assert [(m.tag, m.funde) for m in journal] == [(_tag(2), 5)]
    assert caplog.text.count("unlesbarer Messtag") == 2


def test_heute_nicht_gelesen_sagt_auch_seit_wann(tmp_path):
    """Ein Befund in der Stand-Spalte, zu dem die Warum-Spalte schweigt,
    ist ein halber Befund. Die Zeile nennt den letzten VOLLSTAENDIGEN
    Lauf - genau die Zahl, mit der dieser Waechter angefangen hat."""
    zeilen = _quellenzeilen_ausserhalb(tmp_path)
    modul = _env().get_template("geraete_quellen.html.j2").make_module(
        {"geraete": {"quellenlage": {"zeilen": [], "ohne_hardware": [],
                                     "aufgefuehrt": 0, "liefernd": 0,
                                     "seiten": 0},
                     "stand": "", "pruefung": {}},
         "prefix": ""})
    html = modul.zeile(zeilen["Medimax"])
    assert zeilen["Medimax"]["heute_satz"] == \
        "zuletzt vollständig gelesen am 11.08.2026"
    assert "zuletzt vollständig gelesen am 11.08.2026" in html


# --------------------------------------------------------------------------
# Regel 6: der Waechter wird weder zum Postfachfilter noch stumm (S2-B)
#
# Gemessen ueber 45 simulierte Tage: ein vollstaendiger Tag, danach nur
# noch Teiltage. Bis hierher meldete der Waechter denselben Befund an 29
# Tagen hintereinander - jeder mit eigener Mail -, und ab Teiltag 31 fiel
# der letzte vollstaendige Tag aus dem 30-Tage-Journal: keine
# Vergleichsbasis, kein Alarm, dauerhaft. Ein echter Totalausfall an Tag
# 45 loeste damit nichts mehr aus. Erst laut bis zur Unbrauchbarkeit,
# dann stumm - genau die Fehlerklasse, gegen die dieser Waechter gebaut
# ist.
# --------------------------------------------------------------------------

def _datum(n: int) -> str:
    """Tag n einer Simulation ab dem 01.09.2026 - auch ueber den
    Monatswechsel hinaus. Fest verankert, kein `date.today()`
    (CLAUDE.md Regel 11)."""
    from datetime import date, timedelta

    return (date(2026, 9, 1) + timedelta(days=n - 1)).isoformat()


def _fuenfundvierzig_tage(tmp_path):
    """Tag 1 vollstaendig mit 100 Zeilen, danach nur noch Teiltage mit drei
    Zeilen - die Lage von medimax.de und ep.de an ihrem Besuchsfenster -,
    und an Tag 45 der echte Totalausfall.

    Gespielt wird Tag fuer Tag, so wie `geraete.yml` schreibt und der
    Versandschritt fragt. Das ist nicht kosmetisch: das Journal ist auf
    `_FUND_HISTORIE_TAGE` gedeckelt, ein spaeter Rueckblick saehe einen
    anderen Ausschnitt als der Tag selbst.

    Zurueck kommt `{Tag: [Alarm, ...]}` - genau die Tage, an denen eine
    Mail hinausgegangen waere.
    """
    from telco_radar.analyze.geraete_store import LESEFEHLER, TEILGELESEN

    db = _db(tmp_path)
    gemeldet = {}
    for n in range(1, 46):
        if n == 1:
            db.protokolliere_lauf("Medimax", _datum(n), funde=100,
                                  vollstaendig=True)
        elif n < 45:
            db.protokolliere_lauf("Medimax", _datum(n), funde=3,
                                  vollstaendig=False, zustand=TEILGELESEN)
        else:
            db.protokolliere_lauf("Medimax", _datum(n), funde=0,
                                  vollstaendig=False, zustand=LESEFEHLER)
        alarme = db.ausfall_alarme(heute=_datum(n))
        if alarme:
            gemeldet[n] = alarme
    return db, gemeldet


def test_dieselbe_lage_wird_nicht_neunundzwanzig_mal_gemeldet(tmp_path):
    """Jeder dieser Tage IST ein Befund - gemeldet wird er beim
    Zustandswechsel und danach in festem Abstand wieder, nicht taeglich.
    Ein Kanal, der 29 Mails mit demselben Satz schickt, ist nach der
    dritten ein Postfachfilter."""
    _, gemeldet = _fuenfundvierzig_tage(tmp_path)
    # Der Wechsel an Tag 2, danach ein Wiederholungstag je Woche.
    assert [n for n in gemeldet if n <= 30] == [2, 6, 13, 20, 27]
    # Und ueber alle 45 Tage: nie zwei Meldungen derselben Lage dicht
    # hintereinander - ausser beim echten Wechsel an Tag 45.
    assert len(gemeldet) <= 8


def test_der_waechter_verstummt_nicht_wenn_die_basis_aus_dem_journal_faellt(
        tmp_path):
    """DIE ZWEITE HAELFTE. Ab Teiltag 31 kennt das Journal keinen
    vollstaendig gelesenen Tag mehr. Ein dauerhaft fehlender Vergleich ist
    selbst eine meldepflichtige Lage und kein Schweigegrund - sonst geht
    der echte Totalausfall an Tag 45 (0 Zeilen, Lesefehler) still
    durch."""
    from telco_radar.analyze.geraete_store import LESEFEHLER

    db, gemeldet = _fuenfundvierzig_tage(tmp_path)
    # Die Gegenprobe zur Lage: es GIBT keine Vergleichsbasis mehr.
    assert [m.tag for m in db.messtage("Medimax") if m.vergleichsbasis] == []
    # Nach dem Wegfall der Basis bleibt der Kanal laut - regelmaessig,
    # nicht taeglich: nie laenger als eine Woche am Stueck still.
    spaete = sorted(n for n in gemeldet if n > 30)
    assert spaete
    assert max(b - a for a, b in zip([30] + spaete, spaete + [45])) <= 7
    spaet = gemeldet[spaete[0]][0]
    # Den neuen Namen erst hier holen - ein ImportError beim Einsammeln
    # waere kein roter Test (siehe Kopf dieser Datei).
    from telco_radar.analyze.geraete_store import ALARM_OHNE_BASIS

    assert spaet.art == ALARM_OHNE_BASIS
    assert spaet.vortag is None and spaet.zeilen_vortag is None
    # UND der Totalausfall an Tag 45 ist ein eigener, sofortiger Befund -
    # ein Zustandswechsel wartet auf keine Sperre.
    assert 45 in gemeldet
    assert gemeldet[45][0].zeilen == 0
    assert gemeldet[45][0].zustand == LESEFEHLER


# --------------------------------------------------------------------------
# Ein Lesefehler MIT Zeilen ist eine Beobachtung (S2-C)
#
# `Messtag.beobachtet` liest `zustand == GELESEN or zeilen > 0`. Der zweite
# Zweig war ungeprueft: gestrichen blieben alle 231 Geraete-Tests gruen,
# obwohl ein abgebrochener Tag mit 100 gelesenen Zeilen still seine Rolle
# als Vergleichsbasis verliert und der Vergleich auf einen aelteren Tag
# springt.
# --------------------------------------------------------------------------

def test_ein_lesefehler_mit_zeilen_bleibt_die_vergleichsbasis(tmp_path):
    from telco_radar.analyze.geraete_store import LESEFEHLER

    db = _db(tmp_path)
    db.protokolliere_lauf("o2", _tag(1), funde=50, vollstaendig=True)
    db.protokolliere_lauf("o2", _tag(2), funde=100, vollstaendig=False,
                          zustand=LESEFEHLER)
    messtag = [m for m in db.messtage("o2") if m.tag == _tag(2)][0]
    assert messtag.beobachtet is True and messtag.vergleichsbasis is True
    db.protokolliere_lauf("o2", _tag(3), funde=0, vollstaendig=True)
    alarme = db.ausfall_alarme(heute=_tag(3))
    # Verglichen wird mit dem 02. (100 Zeilen), nicht mit dem 01. (50).
    assert [(a.vortag, a.zeilen_vortag) for a in alarme] == [(_tag(2), 100)]
