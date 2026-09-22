"""Ein Sortiment, das ueber TAGE wegbroeselt, wird gemeldet - vor der Null.

DER BEFUND (22.09.2026, adversarischer Review des tote-Adressen-Pakets)
----------------------------------------------------------------------
Seit tote Produktadressen eine benannte Luecke sind und keinen Lauf mehr
kippen, darf jede vierte Adresse fehlen
(`collect.geraete._MINDESTANTEIL_GELESENER_PRODUKTSEITEN = 0.75`). Damit
rutschte eine langsame Erosion durch JEDES Tor:

  * 24 % tote Adressen je Nacht reissen die Schwelle nicht (sie laesst
    25 % zu),
  * und der Abdeckungswaechter vergleicht mit GESTERN - 24 % weniger
    Zeilen sind weniger als `ABDECKUNG_RUECKGANG = 0.30`.

Der Lauf blieb jede Nacht `ok` und `vollstaendig`, `laeufe` zaehlte hoch,
`mark_stale` listete die fehlenden Geraete brav aus. Nach fuenf Naechten
waren 0,76^5 = 24 % des Sortiments uebrig, ohne dass ein einziger Kanal
angeschlagen haette; laut geworden waere es erst bei null Zeilen
(`ALARM_AUSFALL`) - als Nachruf. VOR dem tote-Adressen-Paket war jeder
dieser Tage ein `fehler` und die Quellenseite sagte "bisher kein
vollstaendiger Lauf"; so gebaut waere der Fix ein Rueckschritt gegen
CLAUDE.md Regel 9.

WAS HIER FESTGENAGELT IST
-------------------------
1. Der Verlauf ueber MEHRERE Naechte loest aus - genau der Fall aus dem
   Review, fuenf Naechte zu je 24 %.
2. Gerechnet wird in GELESENEN PRODUKTADRESSEN, derselben Einheit, in der
   die Schwelle rechnet. Der Abdeckungswaechter rechnet in ZEILEN; das
   sind zwei Groessen, und deshalb kann `ABDECKUNG_RUECKGANG` die
   Schwelle nicht nach unten begruenden (S2-1).
3. Eine STABILE Luecke schweigt: mobilcom-debitels neun tote Adressen
   Nacht fuer Nacht sind keine Erosion.
4. Ein Tag ohne Adressauskunft faellt aus dem Vergleich, statt als "null
   gelesene Adressen" einen Einbruch vorzutaeuschen.

DIE FIXTURES SCHREIBEN DEN BESTAND IN SEINER GESPEICHERTEN FORM
---------------------------------------------------------------
Absicht: gegen den Stand VOR diesem Auftrag faellt jeder Test hier mit
einer ASSERTION und nicht mit einem `TypeError` ueber ein unbekanntes
Schluesselwort - der alte `messtage()` liest die zwei zusaetzlichen
Eintragsfelder einfach nicht, und damit gibt es keinen Erosionsbefund.
Ein Test, der beim Einsammeln stirbt, beweist nichts.

Kein Test haengt am heutigen Datum (CLAUDE.md Regel 11).
"""
import json

from telco_radar.analyze.geraete_store import GELESEN, GeraeteDB

_ANBIETER = "mobilcom-debitel"


def _tag(n: int) -> str:
    return f"2026-09-{n:02d}"


def _bestand(tmp_path, naechte) -> GeraeteDB:
    """`naechte` = [(tag, versucht, tote, zeilen), ...] -> fertiger Store.

    Geschrieben wird die Eintragsform, die `protokolliere_lauf` erzeugt:
    `[Tag, Funde, Zustand, Buendel, Versucht, Tote]`. Alle Naechte sind
    GELESEN - genau darin liegt der Befund, dass naemlich nichts
    aufgefallen ist.
    """
    pfad = tmp_path / "geraete_db.json"
    pfad.write_text(json.dumps({
        "updated": naechte[-1][0],
        "anbieter": {_ANBIETER: {
            "laeufe": len(naechte),
            "funde_gesamt": sum(n[3] for n in naechte),
            "letzter_lauf": naechte[-1][0],
            "letzter_fund": naechte[-1][0],
            "termine": [n[0] for n in naechte],
            "funde_nach_tag": [[tag, zeilen, GELESEN, 0, versucht, tote]
                               for tag, versucht, tote, zeilen in naechte],
        }},
        "listungen": [],
    }, ensure_ascii=False), encoding="utf-8")
    return GeraeteDB(pfad)


# Der gemessene Fall, Nacht fuer Nacht: die toten Adressen der Vornacht
# fallen aus der Sitemap, die naechste Nacht verliert wieder rund ein
# Viertel. Die Zeilen (rund drei je Seite) gehen im selben Takt zurueck -
# jeder EINZELNE Tagesschritt bleibt unter 30 %.
_FUENF_NAECHTE = [
    (_tag(1), 45, 0, 133),      # der letzte heile Tag
    (_tag(2), 45, 11, 100),     # 24,4 % tot - Schwelle haelt (0,756)
    (_tag(3), 34, 8, 77),       # 23,5 % tot
    (_tag(4), 26, 6, 59),       # 23,1 % tot
    (_tag(5), 20, 5, 44),       # 25,0 % tot - genau an der Schwelle
    (_tag(6), 15, 3, 36),       # 20,0 % tot
]


# --------------------------------------------------------------------------
# 1. Der Fall aus dem Review: fuenf Naechte a 24 %
# --------------------------------------------------------------------------

def test_kein_einzelner_tagesschritt_reisst_eine_der_alten_schwellen(tmp_path):
    """Die Voraussetzung des Befunds, ausdruecklich nachgerechnet.

    Ohne diesen Test koennte der Erosionsalarm unten auch deshalb gruen
    sein, weil in Wahrheit laengst `ALARM_RUECKGANG` feuert - dann
    bewiese er nichts. Gemessen wird deshalb ZUERST, dass jeder einzelne
    Schritt unter beiden alten Schwellen bleibt: kein Zeilenrueckgang
    ueber 30 %, keine Nacht mit mehr als jeder vierten toten Adresse.
    """
    from telco_radar.analyze.geraete_store import ABDECKUNG_RUECKGANG
    from telco_radar.collect.geraete import (
        _MINDESTANTEIL_GELESENER_PRODUKTSEITEN,
    )

    for vorher, heute in zip(_FUENF_NAECHTE, _FUENF_NAECHTE[1:]):
        zeilen_vorher, zeilen_heute = vorher[3], heute[3]
        schritt = (zeilen_vorher - zeilen_heute) / zeilen_vorher
        assert schritt <= ABDECKUNG_RUECKGANG, heute[0]
        versucht, tote = heute[1], heute[2]
        anteil = (versucht - tote) / versucht
        assert anteil >= _MINDESTANTEIL_GELESENER_PRODUKTSEITEN, heute[0]


def test_fuenf_naechte_a_vierundzwanzig_prozent_loesen_alarm_aus(tmp_path):
    """DER Test dieses Auftrags: der Verlauf wird laut, bevor der Anbieter
    leer ist.

    Gegen den alten Stand faellt er - dort gibt es ueber alle fuenf
    Naechte keinen einzigen Befund, obwohl drei Viertel des Sortiments
    verschwunden sind. Die ASSERTION steht deshalb vor dem Import des
    neuen Namens: ein Test, der beim Einsammeln stirbt, beweist nichts.
    """
    db = _bestand(tmp_path, _FUENF_NAECHTE)
    gemeldet = {tag: db.abdeckungsalarm(_ANBIETER, tag)
                for tag, _, _, _ in _FUENF_NAECHTE}
    laut = sorted(tag for tag, alarm in gemeldet.items() if alarm is not None)
    assert laut, "kein einziger Befund in fuenf Naechten mit 24 % Schwund"
    # Und zwar frueh: spaetestens in der dritten Nacht, mit noch 26 von
    # 45 gelesenen Seiten - nicht erst bei null.
    assert laut[0] <= _tag(3)

    from telco_radar.analyze.geraete_store import ALARM_EROSION

    assert gemeldet[laut[0]].art == ALARM_EROSION


def test_die_erste_nacht_allein_alarmiert_nicht(tmp_path):
    """Die Gegenprobe nach unten: 24 % in EINER Nacht sind Rauschen, kein
    Befund. Ohne sie waere der Alarm ein Melder fuer jeden normalen Tag."""
    db = _bestand(tmp_path, _FUENF_NAECHTE[:2])
    assert db.abdeckungsalarm(_ANBIETER, _tag(2)) is None


def test_der_befund_nennt_adressen_und_bezugstag(tmp_path):
    """Die Zahlen im Satz sind ADRESSEN und kommen aus dem Bestand - eine
    Meldung ohne nachrechenbare Zahl ist keine."""
    db = _bestand(tmp_path, _FUENF_NAECHTE[:3])
    alarm = db.abdeckungsalarm(_ANBIETER, _tag(3))
    assert alarm is not None, "die dritte Nacht bleibt still"
    assert alarm.vortag == _tag(1)
    assert alarm.adressen_vortag == 45 and alarm.adressen == 26
    assert alarm.prozent == 42
    assert "Produktseiten" in alarm.satz
    assert "45" in alarm.satz and "26" in alarm.satz
    assert alarm.als_dict()["adressen"] == 26

    from telco_radar.analyze.geraete_store import ALARM_EROSION

    assert alarm.art == ALARM_EROSION


# --------------------------------------------------------------------------
# 2. Eine STABILE Luecke ist keine Erosion
# --------------------------------------------------------------------------

def test_dieselben_neun_toten_adressen_jede_nacht_alarmieren_nicht(tmp_path):
    """Der Fall, fuer den das tote-Adressen-Paket gebaut wurde: freenets
    Sitemap fuehrt Nacht fuer Nacht dieselben neun Leichen, gelesen werden
    jede Nacht 36 Seiten und 133 Listungen.

    Wuerde hier gemeldet, waere der Erosionsalarm genau der Totalausfall-
    Fehlalarm, den das Paket abgeschafft hat - nur unter neuem Namen.
    """
    db = _bestand(tmp_path, [(_tag(n), 45, 9, 133) for n in range(1, 9)])
    for n in range(1, 9):
        assert db.abdeckungsalarm(_ANBIETER, _tag(n)) is None


def test_ein_gewachsenes_sortiment_alarmiert_nicht(tmp_path):
    """Gegenprobe nach oben: wer mehr Seiten liefert als vorige Woche, hat
    keinen Schwund. Ein Alarm, der auf einen Betrag statt auf ein
    Vorzeichen sieht, faellt hier."""
    db = _bestand(tmp_path, [(_tag(1), 20, 0, 60), (_tag(2), 30, 0, 90),
                             (_tag(3), 45, 0, 133)])
    assert db.abdeckungsalarm(_ANBIETER, _tag(3)) is None


def test_ein_tag_ohne_adressauskunft_faellt_aus_dem_vergleich(tmp_path):
    """"Nicht versucht" ist nicht "null gelesen" (Clean Code 3/6).

    Ein Anbieter, dessen Adapter an einem Tag keine Produktseite anfasst,
    schreibt `versucht: 0` und `tote: null`. Wuerde dieser Tag als "0
    gelesene Adressen" in den Vergleich eingehen, meldete jeder solche
    Tag 100 % Schwund - und die Meldung waere frei erfunden.
    """
    db = _bestand(tmp_path, [(_tag(1), 45, 0, 133), (_tag(2), 45, 0, 133),
                             (_tag(3), 0, None, 133)])
    assert db.abdeckungsalarm(_ANBIETER, _tag(3)) is None


def test_der_altbestand_ohne_adressfelder_alarmiert_nicht(tmp_path):
    """Die vierstellige Eintragsform von vor dem 22.09.2026 kennt die
    Adresszahlen nicht. Sie darf keinen Befund erzeugen - weder einen
    echten noch einen erfundenen."""
    pfad = tmp_path / "geraete_db.json"
    pfad.write_text(json.dumps({
        "updated": _tag(3),
        "anbieter": {_ANBIETER: {
            "laeufe": 3, "funde_gesamt": 399, "letzter_lauf": _tag(3),
            "letzter_fund": _tag(3),
            "funde_nach_tag": [[_tag(n), 133, GELESEN, 0] for n in (1, 2, 3)],
        }},
        "listungen": [],
    }, ensure_ascii=False), encoding="utf-8")
    db = GeraeteDB(pfad)
    assert db.messtage(_ANBIETER)[-1].gelesene_adressen is None
    assert db.abdeckungsalarm(_ANBIETER, _tag(3)) is None


# --------------------------------------------------------------------------
# 3. S2-1: die Einheit der Schwelle - und was sie wirklich nach unten haelt
# --------------------------------------------------------------------------

def test_der_waechter_rechnet_in_zeilen_die_schwelle_in_adressen(tmp_path):
    """Das Gegenbeispiel, an dem die alte Begruendung der 0,75 zerbricht.

    Sie leitete die Untergrenze aus `ABDECKUNG_RUECKGANG` her - und
    verglich dabei zwei verschiedene Groessen: die Schwelle rechnet in
    ADRESSEN, der Waechter in ZEILEN (Listungen plus Buendel). Am
    21.09.2026 trugen 45 Adressen 133 Listungen, rund drei je Seite und
    ungleich verteilt. Tragen die elf toten Adressen (24,4 %, Schwelle
    haelt) 50 der 133 Listungen, ist der Zeilenrueckgang 37 % - derselbe
    Tag heisst dann zugleich "vollstaendig gelesen" UND loest
    `ALARM_RUECKGANG` aus.

    Das ist kein Widerspruch, sondern die richtige Auskunft aus zwei
    Blickwinkeln - aber es zeigt, dass der Waechter die Schwelle NICHT
    nach unten begruenden kann.
    """
    from telco_radar.analyze.geraete_store import ALARM_RUECKGANG

    db = _bestand(tmp_path, [(_tag(1), 45, 0, 133), (_tag(2), 45, 11, 83)])
    heute = db.messtage(_ANBIETER)[-1]
    assert heute.zustand == GELESEN and heute.vergleichsbasis is True
    assert heute.gelesene_adressen == 34
    alarm = db.abdeckungsalarm(_ANBIETER, _tag(2))
    assert alarm is not None and alarm.art == ALARM_RUECKGANG
    assert alarm.prozent == 38


def test_die_untergrenze_der_schwelle_ist_der_erosionsalarm(tmp_path):
    """Was die 0,75 wirklich nach unten haelt - und der Beleg, dass der
    Abdeckungswaechter es nicht tut.

    Gerechnet wird mit dem SCHLIMMSTEN Fall, den die Schwelle Nacht fuer
    Nacht gerade noch durchlaesst: genau 25 % tote Adressen, also genau
    `1 - _MINDESTANTEIL_GELESENER_PRODUKTSEITEN`. Jeder Tagesschritt
    bleibt damit unter `ABDECKUNG_RUECKGANG` - der Waechter sieht nichts,
    und ohne den Erosionsalarm bliebe es dabei, bis der Anbieter leer ist.
    """
    naechte = [(_tag(1), 48, 0, 144), (_tag(2), 48, 12, 108),
               (_tag(3), 36, 9, 81)]
    db = _bestand(tmp_path, naechte)
    assert db.abdeckungsalarm(_ANBIETER, _tag(2)) is None
    alarm = db.abdeckungsalarm(_ANBIETER, _tag(3))
    assert alarm is not None, \
        "genau an der Schwelle broeselt der Anbieter still weg"
    assert alarm.adressen_vortag == 48 and alarm.adressen == 27

    from telco_radar.analyze.geraete_store import ALARM_EROSION

    assert alarm.art == ALARM_EROSION


def test_das_erosionsfenster_ist_eine_benannte_konstante():
    from telco_radar.analyze.geraete_store import _EROSION_FENSTER_TAGE

    assert _EROSION_FENSTER_TAGE == 7


def test_der_vergleich_endet_am_rand_des_fensters(tmp_path):
    """Die Grenze der Sichtweite, ausdruecklich gemessen (T5).

    Acht Naechte: die erste haelt 45 gelesene Adressen, danach steht der
    Anbieter konstant bei 30 (ein einmaliger Einbruch, keine Erosion).
    Sobald der heile Tag aus dem Sieben-Tage-Fenster faellt, ist der
    aelteste Bezug selbst schon die 30 - und es gibt nichts mehr zu
    melden. Ohne diesen Test koennte das Fenster unbemerkt unendlich
    sein, und ein einmaliger Einbruch meldete sich ewig.
    """
    naechte = [(_tag(1), 45, 0, 133)]
    naechte += [(_tag(n), 30, 0, 90) for n in range(2, 10)]
    db = _bestand(tmp_path, naechte)
    # Solange der heile Tag im Fenster steht (Naechte 2 bis 7), ist der
    # Schwund 33 % und damit ein Befund.
    assert db.abdeckungsalarm(_ANBIETER, _tag(2)) is not None
    # Nacht 9 sieht nur noch die Tage 3 bis 9 - alle mit 30 Adressen.
    assert db.abdeckungsalarm(_ANBIETER, _tag(9)) is None
