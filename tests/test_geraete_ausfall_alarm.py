"""FM-2-Alarm (Strategie v3, P5-Auftrag 2): Quellentod darf nicht still bleiben.

DIE REGEL, DIE DIESE DATEI FESTNAGELT
-------------------------------------
Ein Anbieter, dessen Quelle sich geaendert hat (Felder weg, robots.txt neu),
wird weiterhin "erfolgreich" gelesen - nur ohne Saetze. Ausbleiben ist kein
Fehlerzustand: kein Test wird rot, deploy.yml bleibt gruen, und gesehen wird
es fruehestens beim monatlichen Sichttest (premortem.md, FM 2). Die
Ausfall-Schwelle "Anbieter liefert 7 Tage 0 Saetze" ist der billigste Alarm:
eine Protokollzeile je Lauf, mehr nicht - und genau das ist hier Vertrag.

ZWEI GRENZEN, BEIDE WICHTIG
---------------------------
1. Der Alarm loest NICHTS aus. Kein Altern, kein Loesen, kein Loeschen -
   die Auslistung bleibt allein an `vollstaendig` gebunden. Ein Alarm mit
   Nebenwirkung waere schlimmer als die Blindheit, die er ersetzt.
2. Gezaehlt werden BEOBACHTETE Tage, nicht Kalendertage. Ein uebersprungener
   Anbieter (Besuchszeit, Fehler) ist keine Aussage und zaehlt weder fuer
   noch gegen ihn.
"""
import json
import logging

from telco_radar.analyze.geraete_store import AUSFALL_TAGE, GeraeteDB
# Fuer den Ende-zu-Ende-Fall: die fixtures des Pipeline-Tests sind der
# kuerzeste Weg zu einem Lauf mit echtem Store - repo-Uebung (siehe
# test_eine_seite_querlinks.py & Co.).
from test_geraete_pipeline import _hole, _jetzt, _root

_ALARMZEILE = ("Geraeteradar-Ausfall: o2 liefert 7 Tage 0 Saetze "
               "(Quelle pruefen: geraete-quellen.html)")


def _db(tmp_path):
    return GeraeteDB(tmp_path / "geraete_db.json")


def _nulltage(db, n, start=2, erster="2026-09-01", funde=3):
    """Ein Tag MIT Funden, dann n vollstaendige Tage ohne - der Lauf jedes
    Tages ist beobachtet (vollstaendig=True, funde=0)."""
    db.protokolliere_lauf("o2", erster, funde=funde, vollstaendig=True)
    for tag in range(start, start + n):
        db.protokolliere_lauf("o2", f"2026-09-{tag:02d}", funde=0,
                              vollstaendig=True)


# --------------------------------------------------------------------------
# Die Schwelle
# --------------------------------------------------------------------------

def test_die_schwelle_steht_auf_sieben_tagen():
    """Sieben, nicht drei - drei ist die SIM-only-Schwelle, und die beiden
    sagen Verschiedenes (siehe geraete_store.py)."""
    assert AUSFALL_TAGE == 7


def test_sieben_tage_null_funde_loesen_den_alarm_aus(tmp_path, caplog):
    db = _db(tmp_path)
    _nulltage(db, 7)
    assert db.ausfall_alarme() == [("o2", 7)]
    with caplog.at_level(logging.WARNING,
                         logger="telco_radar.geraete_pipeline"):
        from telco_radar.geraete_pipeline import melde_ausfall
        melde_ausfall(db.ausfall_alarme())
    assert _ALARMZEILE in caplog.text


def test_sechs_tage_null_funde_loesen_den_alarm_nicht_aus(tmp_path, caplog):
    db = _db(tmp_path)
    _nulltage(db, 6)
    assert db.stille_tage("o2") == 6
    assert db.ausfall_alarme() == []
    with caplog.at_level(logging.WARNING,
                         logger="telco_radar.geraete_pipeline"):
        from telco_radar.geraete_pipeline import melde_ausfall
        melde_ausfall(db.ausfall_alarme())
    assert "Geraeteradar-Ausfall" not in caplog.text


def test_ein_fund_dazwischen_setzt_die_zaehlung_zurueck(tmp_path):
    """Sechs Null-Tage, ein Fund, wieder sechs: nur die letzen sechs zaehlen."""
    db = _db(tmp_path)
    _nulltage(db, 6, start=2, erster="2026-09-01")
    db.protokolliere_lauf("o2", "2026-09-08", funde=2, vollstaendig=True)
    for tag in range(9, 15):
        db.protokolliere_lauf("o2", f"2026-09-{tag:02d}", funde=0,
                              vollstaendig=True)
    assert db.stille_tage("o2") == 6
    assert db.ausfall_alarme() == []


def test_der_alarm_zaehlt_weiter_als_die_schwelle(tmp_path):
    """Tag 8 und 9 stehen in der Zeile - die Zahl ist die Messung, nicht
    die Schwelle."""
    db = _db(tmp_path)
    _nulltage(db, 9)
    assert db.ausfall_alarme() == [("o2", 9)]


# --------------------------------------------------------------------------
# Die zwei Grenzen
# --------------------------------------------------------------------------

def test_nie_gelieferte_anbieter_alarmieren_nicht(tmp_path):
    """0 Funde bei funde_gesamt 0 ist der SIM-only-Fall
    (`hardware_vermarktung`), kein Quellentod - der Alarm schweigt, weil
    es keine Erwartung gibt, die sterben koennte."""
    db = _db(tmp_path)
    for tag in range(1, 12):
        db.protokolliere_lauf("winSIM", f"2026-09-{tag:02d}", funde=0,
                              vollstaendig=True)
    assert db.stille_tage("winSIM") == 0
    assert db.ausfall_alarme() == []


def test_nicht_beobachtete_tage_zaehlen_nicht(tmp_path):
    """Ein Teillauf ohne Fund ist keine Beobachtung von null - genau die
    Bedingung, unter der `protokolliere_lauf` ueberhaupt nicht zaehlt."""
    db = _db(tmp_path)
    db.protokolliere_lauf("o2", "2026-09-01", funde=3, vollstaendig=True)
    for tag in range(2, 20):
        db.protokolliere_lauf("o2", f"2026-09-{tag:02d}", funde=0,
                              vollstaendig=False)
    assert db.stille_tage("o2") == 0
    assert db.ausfall_alarme() == []


def test_der_alarm_loest_nichts_aus(tmp_path):
    """Gegenprobe zur Zusicherung: der Alarm veraendert die Listungen
    nicht. Ein aktiver Bestand bleibt aktiv, egal wie still die Quelle
    ist - Altern steht allein auf `mark_stale`/`vollstaendig`."""
    from test_geraete_store import _listung
    db = _db(tmp_path)
    db.upsert([_listung(anbieter="o2")], "2026-09-01")
    _nulltage(db, 9)
    assert db.ausfall_alarme() == [("o2", 9)]
    eintraege = db.eintraege()
    assert len(eintraege) == 1 and eintraege[0]["status"] == "aktiv"
    assert eintraege[0]["last_verified"] == "2026-09-01"


# --------------------------------------------------------------------------
# Altbestand und Zaehlfuehrung
# --------------------------------------------------------------------------

def _altbestand(tmp_path, termine, letzter_fund, funde_gesamt=100):
    """State in der Form VOR diesem Auftrag: keine `funde_nach_tag`, nur
    die Buchfuehrung, die es seit dem 28.08.2026 gibt."""
    pfad = tmp_path / "geraete_db.json"
    pfad.write_text(json.dumps({
        "updated": letzter_fund, "anbieter": {
            "o2": {"laeufe": len(termine), "funde_gesamt": funde_gesamt,
                   "letzte_funde": 0, "letzter_fund": letzter_fund,
                   "termine": termine}},
        "listungen": []}, ensure_ascii=False), encoding="utf-8")
    return GeraeteDB(pfad)


def test_altbestand_ohne_historie_zaehlt_ueber_die_termine(tmp_path):
    """Der Bestand vom 17.09. traegt KEINE funde_nach_tag. Dennoch ist die
    Zahl ableitbar: `letzter_fund` ist per Definition ein Tag MIT Funden,
    jeder `termine`-Eintrag danach ein beobachteter Tag ohne (sonst
    stuende er als letzter_fund darin). Sieben solche Tage -> Alarm."""
    db = _altbestand(tmp_path,
                     termine=[f"2026-09-{tag:02d}" for tag in range(1, 9)],
                     letzter_fund="2026-09-01")
    assert db.stille_tage("o2") == 7
    assert db.ausfall_alarme() == [("o2", 7)]


def test_altbestand_mit_sechs_stillen_tagen_alarmiert_nicht(tmp_path):
    db = _altbestand(tmp_path,
                     termine=[f"2026-09-{tag:02d}" for tag in range(1, 8)],
                     letzter_fund="2026-09-01")
    assert db.stille_tage("o2") == 6
    assert db.ausfall_alarme() == []


def test_altbestand_ohne_letzter_fund_wird_nicht_geraten(tmp_path):
    """Sehr alter Bestand ohne `letzter_fund`: aus den Terminen allein
    liesse sich nicht ableiten, welche Tage Funde hatten - dann zaehlt
    die Ableitung lieber nichts, statt zu raten."""
    db = _altbestand(tmp_path,
                     termine=[f"2026-09-{tag:02d}" for tag in range(1, 9)],
                     letzter_fund="", funde_gesamt=100)
    assert db.stille_tage("o2") == 0


def test_gleicher_tag_ersetzt_seinen_eintrag(tmp_path):
    """Zwei Laeufe am selben Tag sind EIN Messtag (dieselbe Regel wie die
    TCO-Historie): der spaetere Stand gewinnt, es entsteht keine doppelte
    Zeile - und der Speicherzyklus behaelt die Historie."""
    db = _db(tmp_path)
    db.protokolliere_lauf("o2", "2026-09-01", funde=3, vollstaendig=True)
    db.protokolliere_lauf("o2", "2026-09-01", funde=0, vollstaendig=True)
    b = db.laufbilanz("o2")
    assert b["funde_nach_tag"] == [["2026-09-01", 0]]
    # Der ersetzte Tag zaehlt als EIN stiller Tag, nicht als zwei - und
    # `letzter_fund` (09-01, aus dem ersten Lauf) bleibt der Anker.
    assert db.stille_tage("o2") == 1
    db.save("2026-09-01")
    wieder = GeraeteDB(tmp_path / "geraete_db.json")
    assert wieder.laufbilanz("o2")["funde_nach_tag"] == [["2026-09-01", 0]]


def test_nur_begrenzt_auf_den_lauf(tmp_path):
    """Ein nicht mehr konfigurierter Anbieter wird nicht mehr beobachtet -
    sein eingefrorener Zaehlerstand darf keine Ewigkeitsmeldung geben."""
    db = _db(tmp_path)
    _nulltage(db, 9)
    assert db.ausfall_alarme() == [("o2", 9)]
    assert db.ausfall_alarme(nur={"Vodafone"}) == []
    assert db.ausfall_alarme(nur={"o2"}) == [("o2", 9)]


# --------------------------------------------------------------------------
# Ende-zu-Ende: die Zeile im Protokoll des LAUFS
# --------------------------------------------------------------------------

def test_der_alarm_steht_im_protokoll_des_laufs(tmp_path, caplog):
    """Der einzige Kanal des naechtlichen Laufs ist das Protokoll - hier
    steht die Zeile wirklich drin, nach einem Fund-Tag und sieben
    Null-Tagen. Und der Lauf hat nichts geloest: die zwei Listungen stehen
    noch im Store, gealtert hat in den letzten Laeufen nichts (die
    Zwei-Stufen-Auslistung war nach zwei Null-Tagen fertig - der Alarm
    kam fuenf Tage spaeter und hat KEINE eigene Wirkung)."""
    import test_geraete_pipeline as pipeline_test
    root = _root(tmp_path)
    leer = dict(pipeline_test._SEITEN)
    leer["https://www.medimax.de/c/116/smartphones"] = \
        "<html><body></body></html>"
    with caplog.at_level(logging.WARNING,
                         logger="telco_radar.geraete_pipeline"):
        from telco_radar.geraete_pipeline import run_geraete_stage
        run_geraete_stage(root, {}, "2026-09-01", jetzt=_jetzt(),
                          hole=_hole())
        for tag in range(2, 9):          # 2026-09-02 .. 2026-09-08: 7 Null-Tage
            bilanz = run_geraete_stage(root, {}, f"2026-09-{tag:02d}",
                                       jetzt=_jetzt(), hole=_hole(leer))
    assert ("Geraeteradar-Ausfall: Medimax liefert 7 Tage 0 Saetze "
            "(Quelle pruefen: geraete-quellen.html)") in caplog.text
    assert bilanz["gealtert"] == 0       # der Alarm altert nichts
    assert len(GeraeteDB(root / "data" / "state" / "geraete_db.json")
               .eintraege()) == 2
