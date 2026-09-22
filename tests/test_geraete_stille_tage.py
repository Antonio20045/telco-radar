"""`stille_tage`: wie lange ein Anbieter schon nichts mehr findet.

WAS SICH AM 22.09.2026 GEAENDERT HAT
------------------------------------
Diese Datei hat frueher die FM-2-Schwelle festgenagelt: "Anbieter liefert
sieben beobachtete Tage 0 Saetze -> eine Protokollzeile". Die Schwelle ist
weg. Sie war zu langsam fuer das, wofuer sie gebaut war - 50 Laeufe von
`geraete.yml` waren gruen, darunter die sechs Tage ohne eine einzige
Telekom-Zeile, und eine Meldung nach einer Woche ist kein Waechter, sondern
ein Nachruf. Den Alarm traegt seit P1/C2 der VORTAGSVERGLEICH; er steht mit
seinen eigenen Regeln in `tests/test_geraete_abdeckung.py`.

WAS GEBLIEBEN IST, und deshalb gibt es diese Datei weiter: die MESSUNG
dahinter. `stille_tage` sagt, wie lange die Stille schon dauert - die Zahl
steht in jedem Alarm und auf der Quellenseite. Ihre eine Regel:

    Gezaehlt werden BEOBACHTETE Tage, nicht Kalendertage.

Ein uebersprungener Anbieter (Besuchszeit, Fehler) ist keine Aussage und
zaehlt weder fuer noch gegen ihn. Seit P1/C2 steht auch der nicht gelesene
Tag im Bestand - sichtbar wird er hier trotzdem nicht.
"""
import json

from telco_radar.analyze.geraete_store import (
    GELESEN,
    GeraeteDB,
    LESEFEHLER,
    NICHT_GELESEN,
)


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
# Die Zaehlung
# --------------------------------------------------------------------------

def test_null_tage_werden_gezaehlt(tmp_path):
    db = _db(tmp_path)
    _nulltage(db, 7)
    assert db.stille_tage("o2") == 7


def test_ein_fund_dazwischen_setzt_die_zaehlung_zurueck(tmp_path):
    """Sechs Null-Tage, ein Fund, wieder sechs: nur die letzten sechs
    zaehlen."""
    db = _db(tmp_path)
    _nulltage(db, 6, start=2, erster="2026-09-01")
    db.protokolliere_lauf("o2", "2026-09-08", funde=2, vollstaendig=True)
    for tag in range(9, 15):
        db.protokolliere_lauf("o2", f"2026-09-{tag:02d}", funde=0,
                              vollstaendig=True)
    assert db.stille_tage("o2") == 6


def test_nie_gelieferte_anbieter_sind_nicht_still(tmp_path):
    """0 Funde bei funde_gesamt 0 ist der SIM-only-Fall
    (`hardware_vermarktung`), kein Quellentod - es gibt keine Erwartung,
    die sterben koennte.

    Die zweite Zusicherung ist beim Umbau auf den Vortagsvergleich
    verlorengegangen und steht hier wieder: dieser Anbieter ALARMIERT
    auch nicht. Elf gelesene Tage ohne eine einzige Zeile sind fuer den
    Waechter kein Einbruch - eingebrochen ist nur, wer gestern noch
    geliefert hat.
    """
    db = _db(tmp_path)
    for tag in range(1, 12):
        db.protokolliere_lauf("winSIM", f"2026-09-{tag:02d}", funde=0,
                              vollstaendig=True)
    assert db.stille_tage("winSIM") == 0
    assert db.ausfall_alarme(heute="2026-09-11") == []
    # Gegenprobe: derselbe Anbieter mit EINEM Liefertag davor alarmiert
    # sehr wohl - ohne sie pruefte die Zeile darueber nur, dass die
    # Fixture nichts hergibt (CLAUDE.md Regel 10).
    db.protokolliere_lauf("winSIM", "2026-09-12", funde=5, vollstaendig=True)
    db.protokolliere_lauf("winSIM", "2026-09-13", funde=0, vollstaendig=True)
    assert [a.anbieter for a in
            db.ausfall_alarme(heute="2026-09-13")] == ["winSIM"]


def test_nicht_beobachtete_tage_zaehlen_nicht(tmp_path):
    """Ein Teillauf ohne Fund ist keine Beobachtung von null. Seit P1/C2
    steht der Tag im Journal (der Abdeckungswaechter braucht ihn) - fuer
    diese Zaehlung bleibt er unsichtbar, genau wie vorher, als er gar
    nicht erst geschrieben wurde."""
    db = _db(tmp_path)
    db.protokolliere_lauf("o2", "2026-09-01", funde=3, vollstaendig=True)
    for tag in range(2, 20):
        db.protokolliere_lauf("o2", f"2026-09-{tag:02d}", funde=0,
                              vollstaendig=False)
    assert [m.zustand for m in db.messtage("o2")][-1] == LESEFEHLER
    assert db.stille_tage("o2") == 0


def test_ein_nicht_gelesener_tag_zaehlt_nicht(tmp_path):
    """Dieselbe Regel fuer den Anbieter ausserhalb seiner Besuchszeit."""
    db = _db(tmp_path)
    db.protokolliere_lauf("Medimax", "2026-09-01", funde=3, vollstaendig=True)
    for tag in range(2, 10):
        db.protokolliere_lauf("Medimax", f"2026-09-{tag:02d}", funde=0,
                              vollstaendig=False, zustand=NICHT_GELESEN)
    assert db.stille_tage("Medimax") == 0


def test_ein_teillauf_mit_funden_bricht_die_stille(tmp_path):
    """Was da ist, ist gesehen worden: ein unvollstaendiger Lauf MIT
    Funden zaehlt als Fundtag, auch wenn er nicht durchlief."""
    db = _db(tmp_path)
    _nulltage(db, 3)
    db.protokolliere_lauf("o2", "2026-09-05", funde=7, vollstaendig=False)
    assert db.stille_tage("o2") == 0


# --------------------------------------------------------------------------
# Altbestand und Zaehlfuehrung
# --------------------------------------------------------------------------

def _altbestand(tmp_path, termine, letzter_fund, funde_gesamt=100):
    """State in der Form VOR dem FM-2-Auftrag: keine `funde_nach_tag`, nur
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
    """`letzter_fund` ist per Definition ein Tag MIT Funden, jeder
    `termine`-Eintrag danach ein beobachteter Tag ohne (sonst stuende er
    als letzter_fund darin)."""
    db = _altbestand(tmp_path,
                     termine=[f"2026-09-{tag:02d}" for tag in range(1, 9)],
                     letzter_fund="2026-09-01")
    assert db.stille_tage("o2") == 7


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
    assert db.laufbilanz("o2")["funde_nach_tag"] == \
        [["2026-09-01", 0, GELESEN, 0]]
    # Der ersetzte Tag zaehlt als EIN stiller Tag, nicht als zwei - und
    # `letzter_fund` (09-01, aus dem ersten Lauf) bleibt der Anker.
    assert db.stille_tage("o2") == 1
    db.save("2026-09-01")
    wieder = GeraeteDB(tmp_path / "geraete_db.json")
    assert wieder.laufbilanz("o2")["funde_nach_tag"] == \
        [["2026-09-01", 0, GELESEN, 0]]
