"""Das Besuchsfenster gilt JE ABRUF - nicht je Lauf.

Der Befund, den diese Datei festnagelt: `geraete_pipeline.run_geraete_stage`
friert EINEN Zeitstempel ein und reicht ihn bis an jeden einzelnen Abruf
durch. Ein Lauf, der um 07:57 UTC startet, fragte damit um 08:20 immer noch
mit 07:57 - und bekam "im Fenster", obwohl das Fenster von medimax.de und
ep.de (`Visit-time: 0200-0800`) laengst zu war. Der Crawl darf planmaessig
bis zu 25 Minuten dauern, und genau diese beiden Anbieter stehen hinten in
der Reihenfolge: der Verstoss gegen CLAUDE.md Regel 7 war der Regelfall.

`tests/test_geraete_robots.py::test_besuchsfenster` prueft `im_fenster()`
mit einer uebergebenen Uhrzeit und hat die Luecke deshalb nie gesehen - sie
liegt nicht in der Fensterrechnung, sondern auf dem Weg Lauf-Start ->
spaeterer Abruf. Genau diesen Weg gehen die Tests hier.

KEIN TEST HIER HAENGT VOM HEUTIGEN DATUM AB (CLAUDE.md Regel 11): die
Fixture setzt ihren Startzeitpunkt selbst, und die verstrichene Zeit kommt
aus einer eingespeisten Uhr (`_Laufzeit`), nicht aus `time.monotonic()` der
Maschine. Geschlafen wird nie wirklich.
"""
from collections import namedtuple
from datetime import datetime, timedelta, timezone

import pytest

import telco_radar.collect.geraete as G
from telco_radar.collect.geraete import sammle_anbieter
from telco_radar.collect.geraete.robots import RobotsWaechter, lies_robots
from telco_radar.geraete_config import Anbieter, Einstieg

from test_geraete_collect import _FARBEN, _KATALOG, _SEITEN, _fixture

_EINSTIEG = "https://www.medimax.de/c/116/smartphones"
_ROBOTS_MIT_FENSTER = (
    "User-agent: *\n"
    "Disallow: /cart\n"
    "Request-rate: 1/10\n"
    "Crawl-delay: {delay}\n"
    "Visit-time: 0200-0800\n")


# Ein Abruf, wie ihn die Testattrappe sieht: Adresse UND Wanduhrzeit.
_Abruf = namedtuple("_Abruf", "url zeit")


def _um(stunde: int, minute: int = 0, sekunde: int = 0) -> datetime:
    """Ein fester Zeitpunkt - nie `now()`, nie das heutige Datum."""
    return datetime(2026, 8, 11, stunde, minute, sekunde, tzinfo=timezone.utc)


class _Laufzeit:
    """Die eingespeiste Uhr: monotone Sekunden, die der Test selbst stellt.

    Sie ersetzt im Collector das Modul `time` und damit BEIDE Stellen, an
    denen dort Zeit vorkommt - `monotonic()` und `sleep()`. Ein Schlaf
    verbraucht hier Testsekunden statt echter, und jeder Abruf kostet die
    Latenz, die der Test ihm gibt.
    """

    NULLPUNKT = 1000.0           # ein beliebiger, aber fester Startwert

    def __init__(self, latenz: float = 0.0):
        self.t = self.NULLPUNKT
        self.latenz = latenz
        self.geschlafen: list = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, sekunden: float) -> None:
        self.geschlafen.append(sekunden)
        self.t += max(0.0, sekunden)

    def vor(self, sekunden: float) -> None:
        self.t += sekunden


def _anbieter(einstiege=None, **kw):
    vor = {"name": "Medimax", "typ": "handel", "methode": "ldjson",
           "basis_url": "https://www.medimax.de", "rate_limit_sekunden": 0,
           "einstiege": einstiege or [
               Einstieg(url=_EINSTIEG, label="Smartphones", kind="static",
                        pfadmuster="/p/")]}
    vor.update(kw)
    return Anbieter(**vor)


def _lauf(monkeypatch, *, start: datetime, delay: float, latenz: float = 0.0,
          seiten=None, anbieter=None, frist_bis=None):
    """Ein Lauf mit gestellter Uhr. Gibt (Bilanz, Protokoll, Uhr) zurueck."""
    laufzeit = _Laufzeit(latenz=latenz)
    monkeypatch.setattr(G, "time", laufzeit)

    seiten = _SEITEN if seiten is None else seiten
    protokoll: list = []

    def hole(url):
        # Jeder Abruf wird MIT SEINER WANDUHRZEIT protokolliert. Nur so laesst
        # sich die eigentliche Regel pruefen ("kein Abruf ausserhalb des
        # Fensters") statt eines ihrer Symptome.
        protokoll.append(_Abruf(url, start + timedelta(
            seconds=laufzeit.monotonic() - _Laufzeit.NULLPUNKT)))
        if url.endswith("/robots.txt"):
            return (200, _ROBOTS_MIT_FENSTER.format(delay=delay))
        laufzeit.vor(laufzeit.latenz)
        return (200, seiten.get(url, ""))

    waechter = RobotsWaechter(hole=hole)
    bilanz = sammle_anbieter(anbieter or _anbieter(), _KATALOG, _FARBEN, hole,
                             "2026-08-11", waechter, start,
                             frist_bis=frist_bis)
    return bilanz, protokoll, laufzeit


def _adressen(protokoll) -> list:
    return [a.url for a in protokoll]


def _produktabrufe(protokoll) -> list:
    return [a.url for a in protokoll if "/p/" in a.url]


def _ausserhalb(protokoll, regeln) -> list:
    """Alle Abrufe, die ausserhalb des Besuchsfensters hinausgingen."""
    return [(a.url, a.zeit.strftime("%H:%M:%S")) for a in protokoll
            if not regeln.im_fenster(a.zeit)]


# --------------------------------------------------------------------------
# Die Restzeit des Fensters
# --------------------------------------------------------------------------

def test_restzeit_ohne_fenster_ist_none_und_nicht_null():
    """Clean Code 3: "kein Fenster" ist ein fehlender Wert, keine Null.
    Eine 0.0 hiesse hier "Tuer zu" und wuerde jeden Anbieter ohne
    Besuchszeit sofort deckeln."""
    assert lies_robots("User-agent: *\n").restzeit_im_fenster(_um(12)) is None


def test_restzeit_im_fenster_zaehlt_sekundengenau_herunter():
    r = lies_robots(_ROBOTS_MIT_FENSTER.format(delay=10))
    assert r.restzeit_im_fenster(_um(7, 57)) == pytest.approx(3 * 60)
    assert r.restzeit_im_fenster(_um(7, 59, 30)) == pytest.approx(30)
    assert r.restzeit_im_fenster(_um(2, 0)) == pytest.approx(6 * 3600)


def test_restzeit_ausserhalb_ist_null_und_das_ist_eine_aussage():
    r = lies_robots(_ROBOTS_MIT_FENSTER.format(delay=10))
    assert r.restzeit_im_fenster(_um(8, 0)) == 0.0
    assert r.restzeit_im_fenster(_um(1, 59)) == 0.0


def test_restzeit_ueber_mitternacht():
    r = lies_robots("User-agent: *\nVisit-time: 2200-0600\n")
    assert r.restzeit_im_fenster(_um(23, 0)) == pytest.approx(7 * 3600)
    assert r.restzeit_im_fenster(_um(5, 30)) == pytest.approx(30 * 60)
    assert r.restzeit_im_fenster(_um(12, 0)) == 0.0


# --------------------------------------------------------------------------
# DER KERNTEST
# --------------------------------------------------------------------------

def test_fenster_geht_waehrend_des_laufs_zu(monkeypatch):
    """Start INNERHALB des Fensters, Abruf AUSSERHALB.

    07:57 UTC ist drin (02:00-08:00). Der Crawl-delay dieses Hosts betraegt
    hier zehn Minuten; der erste Produktabruf ginge also fruehestens um
    08:07 hinaus - und damit vor verschlossener Tuer. Gegen den alten Stand
    (eingefrorenes `jetzt`) werden alle drei Produktseiten geholt und der
    Einstieg gilt als gelesen.
    """
    bilanz, protokoll, _ = _lauf(monkeypatch, start=_um(7, 57), delay=600)

    # Gegenprobe zuerst: der Einstieg selbst lag noch im Fenster und WURDE
    # geholt. Ohne diese Zeile waere der Test auch dann gruen, wenn die
    # Fixture gar nichts liefert (CLAUDE.md Regel 10).
    assert _EINSTIEG in _adressen(protokoll)

    assert _produktabrufe(protokoll) == []
    assert bilanz.produkte_abgerufen == 0
    assert bilanz.ausserhalb_besuchszeit is True
    assert bilanz.gelesene_einstiege == set()
    assert bilanz.vollstaendig is False


def test_derselbe_lauf_im_fenster_liest_alles(monkeypatch):
    """Die Gegenprobe zum Kerntest: derselbe Aufbau, nur bleibt die Tuer
    offen. Ohne sie bewiese der Kerntest bloss, dass die Fixture klemmt."""
    bilanz, protokoll, _ = _lauf(monkeypatch, start=_um(2, 30), delay=600)

    assert len(_produktabrufe(protokoll)) == 3
    assert bilanz.produkte_abgerufen == 3
    assert bilanz.ausserhalb_besuchszeit is False
    assert bilanz.gelesene_einstiege == {_EINSTIEG}
    assert bilanz.vollstaendig is True


def test_die_uhr_wandert_mit_der_wartezeit_nicht_mit_dem_datumsstempel(monkeypatch):
    """`heute` darf NICHT mitwandern, das Fenster schon.

    Der Lauf beginnt um 02:00 und laeuft ueber Stunden; der Datumsstempel
    jeder Listung bleibt trotzdem der eine Messtag, den der Aufrufer
    gesetzt hat. Wuerde er aus derselben Uhr kommen, zerfiele ein Lauf um
    Mitternacht in zwei Messtermine.
    """
    bilanz, _, _ = _lauf(monkeypatch, start=_um(2, 0), delay=0, latenz=7200)
    assert bilanz.listungen, "Gegenprobe: es gab ueberhaupt Listungen"
    assert {l.abgerufen_am for l in bilanz.listungen} == {"2026-08-11"}


# --------------------------------------------------------------------------
# Teilweise gelesen
# --------------------------------------------------------------------------

def test_teilweise_gelesen_altert_nur_die_wirklich_gelesene_seite(monkeypatch):
    """Zwei Einstiege, das Fenster geht zwischen ihnen zu.

    Der erste Einstieg ist vollstaendig gelesen und steht deshalb in
    `gelesene_einstiege` - genau die Menge, gegen die `GeraeteDB.mark_stale`
    prueft. Der zweite steht nicht darin, also altert nichts aus ihm
    (CLAUDE.md Clean Code 6: "nicht gelesen" ist nicht "leer").
    """
    zweiter = "https://www.medimax.de/c/117/mehr-smartphones"
    seiten = dict(_SEITEN)
    seiten[zweiter] = _fixture("medimax_kategorie.html")
    anbieter = _anbieter(einstiege=[
        Einstieg(url=_EINSTIEG, label="Smartphones", kind="static",
                 pfadmuster="/p/"),
        Einstieg(url=zweiter, label="Mehr", kind="static", pfadmuster="/p/")])

    # 07:30, und jeder Seitenabruf kostet 300 s: der erste Einstieg (1 + 3
    # Seiten) ist um 07:50 fertig, mitten im zweiten geht um 08:00 die Tuer zu.
    bilanz, protokoll, _ = _lauf(monkeypatch, start=_um(7, 30), delay=0,
                                 latenz=300, seiten=seiten, anbieter=anbieter)

    assert bilanz.gelesene_einstiege == {_EINSTIEG}
    assert zweiter not in bilanz.gelesene_einstiege
    assert bilanz.ausserhalb_besuchszeit is True
    assert bilanz.vollstaendig is False
    # Gegenprobe: der erste Einstieg wurde wirklich zu Ende gelesen.
    assert bilanz.produkte_abgerufen >= 3


# --------------------------------------------------------------------------
# Der Deckel auf das Fensterende
# --------------------------------------------------------------------------

def test_fensterfrist_deckelt_auf_das_fensterende(monkeypatch):
    laufzeit = _Laufzeit()
    monkeypatch.setattr(G, "time", laufzeit)

    def hole(url):
        return (200, _ROBOTS_MIT_FENSTER.format(delay=10))

    waechter = RobotsWaechter(hole=hole)
    frist = G._fensterfrist(waechter, "https://www.medimax.de/p/1", _um(7, 55))
    assert frist == pytest.approx(
        laufzeit.monotonic() + 300 - G._FENSTER_PUFFER_SEKUNDEN)


def test_ohne_fenster_deckelt_nichts(monkeypatch):
    laufzeit = _Laufzeit()
    monkeypatch.setattr(G, "time", laufzeit)

    def hole(url):
        return (200, "User-agent: *\nDisallow: /cart\n")

    waechter = RobotsWaechter(hole=hole)
    assert G._fensterfrist(waechter, "https://x.de/p/1", _um(7, 55)) is None


def test_geschlossenes_fenster_deckelt_die_frist_in_die_vergangenheit(monkeypatch):
    """Ein bereits geschlossenes Fenster soll die Produktschleife SOFORT
    beenden, statt sich durch Dutzende Adressen zu arbeiten, die der
    Waechter ohnehin einzeln zurueckweist."""
    laufzeit = _Laufzeit()
    monkeypatch.setattr(G, "time", laufzeit)

    def hole(url):
        return (200, _ROBOTS_MIT_FENSTER.format(delay=10))

    waechter = RobotsWaechter(hole=hole)
    frist = G._fensterfrist(waechter, "https://www.medimax.de/p/1", _um(9, 0))
    assert frist < laufzeit.monotonic()


def test_fristablauf_am_fenster_heisst_besuchszeit_und_nicht_budget(monkeypatch):
    """Wenn der Anteil am Fenster endet, sagt die Bilanz das auch.

    "Budget alle" und "Tuer zu" sind fuer den Abdeckungswaechter zwei
    verschiedene Auskuenfte - die eine ein Ausfall, die andere eine Luecke.
    """
    zweiter = "https://www.medimax.de/c/117/mehr-smartphones"
    seiten = dict(_SEITEN)
    seiten[zweiter] = _fixture("medimax_kategorie.html")
    anbieter = _anbieter(einstiege=[
        Einstieg(url=_EINSTIEG, label="Smartphones", kind="static",
                 pfadmuster="/p/"),
        Einstieg(url=zweiter, label="Mehr", kind="static", pfadmuster="/p/")])

    bilanz, _, _ = _lauf(monkeypatch, start=_um(7, 30), delay=0, latenz=300,
                         seiten=seiten, anbieter=anbieter,
                         frist_bis=10_000_000.0)   # Budget im Ueberfluss

    assert bilanz.status == "frist"
    assert "Besuchszeit" in bilanz.grund
    assert "02:00-08:00" in bilanz.grund
    assert G._FRIST_GRUND_BUDGET not in bilanz.grund
    assert bilanz.ausserhalb_besuchszeit is True


def test_kein_einziger_abruf_verlaesst_das_fenster(monkeypatch):
    """DIE REGEL SELBST, nicht eines ihrer Symptome: kein Abruf geht nach
    08:00 hinaus.

    Der Aufbau zielt auf die eine Luecke, die der Fensterdeckel NICHT
    schliessen kann. `_fensterfrist` wird in der Produktschleife geprueft -
    die Schleife ueber die EINSTIEGSSEITEN kennt ihn nicht. Hier ist der
    erste Einstieg mitsamt seinen drei Produktseiten um 07:58:20 fertig
    (vier Abrufe zu je 500 s ab 07:30), der Deckel hat also nie
    zugeschlagen; der zweite Einstieg wird um 08:03:20 abgerufen - und
    genau den faengt nur die mitlaufende Uhr ab.

    Gegen den alten Stand UND gegen jede Fassung, die die Uhr wieder
    einfriert, geht dieser Abruf hinaus.
    """
    zweiter = "https://www.medimax.de/c/117/mehr-smartphones"
    seiten = dict(_SEITEN)
    seiten[zweiter] = _fixture("medimax_kategorie.html")
    anbieter = _anbieter(einstiege=[
        Einstieg(url=_EINSTIEG, label="Smartphones", kind="static",
                 pfadmuster="/p/"),
        Einstieg(url=zweiter, label="Mehr", kind="static", pfadmuster="/p/")])

    bilanz, protokoll, _ = _lauf(monkeypatch, start=_um(7, 30), delay=0,
                                 latenz=500, seiten=seiten, anbieter=anbieter)
    regeln = lies_robots(_ROBOTS_MIT_FENSTER.format(delay=0))

    assert _ausserhalb(protokoll, regeln) == []
    # Gegenproben: es wurde ueberhaupt gecrawlt, und der Lauf hat das
    # Fenster wirklich ueberdauert - sonst prueft die Zeile darueber nichts.
    assert len(_produktabrufe(protokoll)) == 3
    assert bilanz.gelesene_einstiege == {_EINSTIEG}
    assert zweiter not in _adressen(protokoll)
    assert bilanz.ausserhalb_besuchszeit is True


# --------------------------------------------------------------------------
# Was der Abdeckungswaechter aus einem Teillauf macht
# --------------------------------------------------------------------------

def test_der_teillauf_am_fenster_gilt_als_teilweise_gelesen(monkeypatch):
    """Dieselbe Lage wie `test_teilweise_gelesen_...`, eine Schicht
    weiter: was der Bestand von diesem Lauf erfaehrt.

    Gemessen wurde hier (zwei Einstiege, Start 07:30, 300 s Latenz):
    STATUS frist, LISTUNGEN 3, PRODUKTE 4, FLAG True. Bis zum 22.09.2026
    machte der Waechter daraus NICHT_GELESEN - "gar nicht angefasst" fuer
    einen Anbieter, der vier Produktseiten gelesen und drei Listungen
    geliefert hat. Weil medimax.de und ep.de jede Nacht an ihrem Fenster
    haengen, war das ihr REGELFALL und der Waechter fuer sie blind.
    """
    from telco_radar.analyze.geraete_store import TEILGELESEN
    from telco_radar.geraete_pipeline import _abdeckungszustand

    zweiter = "https://www.medimax.de/c/117/mehr-smartphones"
    seiten = dict(_SEITEN)
    seiten[zweiter] = _fixture("medimax_kategorie.html")
    anbieter = _anbieter(einstiege=[
        Einstieg(url=_EINSTIEG, label="Smartphones", kind="static",
                 pfadmuster="/p/"),
        Einstieg(url=zweiter, label="Mehr", kind="static", pfadmuster="/p/")])

    bilanz, _, _ = _lauf(monkeypatch, start=_um(7, 30), delay=0, latenz=300,
                         seiten=seiten, anbieter=anbieter)

    # Die Messung selbst - ohne sie prueft die Zeile darunter nichts.
    assert bilanz.status == "frist"
    assert len(bilanz.listungen) == 3 and bilanz.produkte_abgerufen == 4
    assert bilanz.ausserhalb_besuchszeit is True
    assert _abdeckungszustand(bilanz) == TEILGELESEN


# --------------------------------------------------------------------------
# DIE ZUSAGE GILT AUCH NACH DER SAMMELPHASE (S2-3)
#
# Die Nachbearbeitungs-Haken der Adapter (`loese_tarifnamen`,
# `ergaenze_buendel`) rufen selbst ab - und bekamen bis zum 22.09.2026 das
# ROHE `hole`: ohne Disallow, ohne Crawl-delay, ohne Fensterpruefung. Sie
# laufen NACH `sammle()`, also an der Stelle, an der der Lauf am weitesten
# fortgeschritten ist und ein Fenster am ehesten zu ist. Die Zusage "die
# Fensterpruefung gilt JE ABRUF" (Modulkopf des Collectors,
# geraete.yml) galt fuer sie nicht.
# --------------------------------------------------------------------------

_HAKEN_ERLAUBT = "https://api.vodafone.de/glados/v2/tariff/v2/hardware?id=1"
_HAKEN_GESPERRT = "https://api.vodafone.de/intern/tariff"


class _Quellen:
    """So viel Quellenverzeichnis, wie `nachsammle_buendel` braucht."""

    def __init__(self, anbieter):
        self._anbieter = anbieter

    def nach_name(self, name):
        return self._anbieter if name == self._anbieter.name else None


class _Bilanz:
    def __init__(self, name, buendel):
        self.name = name
        self.buendel = buendel


def _nachsammeln(monkeypatch, robots: str, *, start=None):
    """Laesst einen Haken zwei Adressen abrufen - eine erlaubte, eine
    gesperrte. Gibt (abgerufene Adressen, Fehler je Adresse) zurueck."""
    import telco_radar.geraete_pipeline as P
    from telco_radar.collect.geraete import Adapter

    laufzeit = _Laufzeit()
    monkeypatch.setattr(G, "time", laufzeit)
    protokoll: list = []
    fehler: list = []

    def hole(url, kopfzeilen=None, **kw):
        protokoll.append(url)
        if url.endswith("/robots.txt"):
            return (200, robots)
        return (200, "{}")

    def haken(hole_, kopfzeilen, rohbuendel):
        for url in (_HAKEN_ERLAUBT, _HAKEN_GESPERRT):
            try:
                hole_(url, kopfzeilen=kopfzeilen)
            except Exception as exc:                      # noqa: BLE001
                fehler.append((url, str(exc)))
        return 0

    monkeypatch.setitem(P.ADAPTER, "ldjson",
                        Adapter(name="probe", lies=lambda text, url="": [],
                                loese_tarifnamen=haken))
    anbieter = _anbieter(name="Vodafone", basis_url="https://www.vodafone.de")
    zeit = start or _um(3, 0)
    P.nachsammle_buendel([_Bilanz("Vodafone", [{"sku": "1"}])],
                         _Quellen(anbieter), hole, uhr=lambda: zeit)
    return protokoll, fehler


def test_der_nachbearbeitungs_haken_haelt_disallow_ein(monkeypatch):
    """Eine per robots.txt gesperrte Adresse wird nicht abgerufen - auch
    nicht aus einem Haken heraus."""
    protokoll, fehler = _nachsammeln(
        monkeypatch, "User-agent: *\nDisallow: /intern\n")

    # Gegenprobe zuerst: die erlaubte Adresse ging hinaus. Ohne sie waere
    # der Test auch dann gruen, wenn der Haken gar nicht laeuft.
    assert _HAKEN_ERLAUBT in protokoll
    assert _HAKEN_GESPERRT not in protokoll
    assert [u for u, _ in fehler] == [_HAKEN_GESPERRT]
    assert "robots.txt" in fehler[0][1]


def test_der_nachbearbeitungs_haken_haelt_die_besuchszeit_ein(monkeypatch):
    """Und das Besuchsfenster ebenso - gemessen an der Uhrzeit DIESES
    Abrufs, nicht am Start des Laufs."""
    protokoll, fehler = _nachsammeln(
        monkeypatch, "User-agent: *\nVisit-time: 0200-0800\n",
        start=_um(9, 0))

    assert _HAKEN_ERLAUBT not in protokoll
    assert _HAKEN_GESPERRT not in protokoll
    assert [u for u, _ in fehler] == [_HAKEN_ERLAUBT, _HAKEN_GESPERRT]
    assert "Besuchszeit" in fehler[0][1]
    # Gegenprobe: im Fenster geht dieselbe Adresse hinaus.
    protokoll, fehler = _nachsammeln(
        monkeypatch, "User-agent: *\nVisit-time: 0200-0800\n",
        start=_um(3, 0))
    assert _HAKEN_ERLAUBT in protokoll and fehler == []
