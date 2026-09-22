"""Tote Produktadressen in der Quelle sind eine Luecke, kein Totalausfall.

DER BEFUND (gemessen am 22.09.2026)
-----------------------------------
mobilcom-debitel stand in `data/state/geraete_db.json` mit NULL
vollstaendigen Laeufen und ganz ohne `letzter_lauf`, obwohl es seit dem
29.08.2026 an 23 Tagen je 133 Listungen lieferte. Im Lauf 35579982862
(21.09.2026) steht woertlich: "mobilcom-debitel -> fehler, 133 Listungen
aus 36 Produktseiten (210 Preissaetze gelesen) (Einstieg gelesen, aber
unvollstaendig ausgewertet: 36 Produktseiten abgerufen, 133 Listungen)" -
daneben neun Zeilen "uebersprungen (HTTP 404)".

Die Ursache ist keine Sperre und kein Zeitbudget: freenets EIGENE
sitemap.xml fuehrt veraltete Produktadressen. 45 der 383 `<loc>`-Eintraege
trafen die konfigurierten Pfadmuster, neun davon antworteten mit HTTP 404.
Neun tote Adressen kippten damit einen Lauf, der 36 von 45 Seiten gelesen
und 133 Listungen geliefert hat, auf Status `fehler` - der Ausfall-Alarm
hat ihn deshalb nie gemeldet, und sein Bestand alterte nie sauber.

WAS HIER FESTGENAGELT IST
-------------------------
1. Eine tote Produktadresse wird GEZAEHLT und benannt, nicht als Ausfall
   gewertet. Der Lauf bleibt vollstaendig.
2. Die Schwelle ist eine benannte Konstante und greift: zu viele tote
   Adressen sind doch ein unvollstaendiger Lauf - an der Grenze genau.
3. Nur eine ANTWORT des Anbieters (404/410) ist eine tote Adresse. Ein
   Serverfehler, eine robots-Sperre oder ein Netzfehler heissen weiter
   "nicht gelesen" (CLAUDE.md Clean Code 6).
4. Scheitert der EINSTIEG selbst, bleibt es ein Fehler (Clean Code 5).
5. Die Zahl steht im Protokoll und auf der Quellenseite, nicht nur im Log.

Kein Test haengt am heutigen Datum (CLAUDE.md Regel 11); die Fixtures
setzen ihr Datum selbst.
"""
from pathlib import Path

from telco_radar.analyze.geraete_store import GeraeteDB
from telco_radar.collect.geraete import sammle_anbieter
from telco_radar.collect.geraete.robots import RobotsWaechter
from telco_radar.geraete_config import Anbieter, Einstieg
from telco_radar.geraete_model import Geraet, Katalog
from telco_radar.geraete_pipeline import run_geraete_stage
from telco_radar.report import geraete_view
from telco_radar.report.html import _env
from test_geraete_pipeline import _jetzt, _root

_FIX = Path(__file__).parent / "fixtures" / "geraete"
_PRODUKT = (_FIX / "medimax_produkt.html").read_text(encoding="utf-8")

_KATALOG = Katalog(geraete=[
    Geraet(hersteller="Apple", modell="iPhone 17 Pro Max", generation=17,
           speicher=[256, 512, 1024], segment="flagship"),
])
_FARBEN = {"titannatur": "titan-natur"}

_EINSTIEG = "https://www.medimax.de/c/116/smartphones"


def _kategorie(urls) -> str:
    anker = "".join(f'<a href="{u}">Produkt</a>' for u in urls)
    return f"<html><body>{anker}</body></html>"


def _seiten(lebend: int, tot: int, einstieg: str = _EINSTIEG,
            marke: str = "") -> dict:
    """Eine Kategorieseite mit `lebend` erreichbaren und `tot` toten
    Produktadressen. Was nicht im dict steht, antwortet 404 - genau die
    Lage der freenet-Sitemap.

    `marke` unterscheidet die Adressen zweier Einstiege desselben
    Anbieters; ohne sie zeigten beide Kategorieseiten auf dieselben
    Produkte, und ein Anbieter mit zwei Einstiegen waere in Wahrheit
    einer mit einem.
    """
    lebende = [f"https://www.medimax.de/p/1{marke}0{i}/iphone-17-pro-max-256gb"
               for i in range(lebend)]
    tote = [f"https://www.medimax.de/p/9{marke}0{i}/weg" for i in range(tot)]
    seiten = {einstieg: _kategorie(lebende + tote)}
    for url in lebende:
        seiten[url] = _PRODUKT
    return seiten


def _anbieter(**kw) -> Anbieter:
    vor = {"name": "mobilcom-debitel", "typ": "handel", "methode": "ldjson",
           "basis_url": "https://www.medimax.de", "rate_limit_sekunden": 0,
           "einstiege": [Einstieg(url=_EINSTIEG, label="Smartphones",
                                  pfadmuster="/p/")]}
    vor.update(kw)
    return Anbieter(**vor)


def _lauf(seiten: dict, antwort=None):
    """`antwort(url) -> (status, text) | None` haengt einzelne Statuscodes
    davor - fuer alles andere gilt: bekannt = 200, unbekannt = 404."""
    def hole(url):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /cart\n")
        eigen = antwort(url) if antwort else None
        if eigen is not None:
            return eigen
        return (200, seiten[url]) if url in seiten else (404, "")

    return sammle_anbieter(_anbieter(), _KATALOG, _FARBEN, hole, "2026-08-11",
                           RobotsWaechter(hole=hole), _jetzt())


# --------------------------------------------------------------------------
# 1. Neun tote Adressen kippen keinen gelesenen Lauf
# --------------------------------------------------------------------------

def test_tote_produktadressen_kippen_einen_gelesenen_lauf_nicht():
    """Der gemessene Fall, nachgebaut: 45 Adressen, 9 davon tot, 36
    gelesen. Vor dem Fix: Status `fehler`, `vollstaendig` False, null
    vollstaendige Laeufe seit drei Wochen."""
    bilanz = _lauf(_seiten(lebend=36, tot=9))
    assert bilanz.gelesene_einstiege == {_EINSTIEG}
    assert bilanz.vollstaendig is True
    assert bilanz.status == "ok"
    assert bilanz.produkte_abgerufen == 36
    assert bilanz.produkte_versucht == 45
    # Die Luecke ist BENANNT und nicht stillschweigend 0 (Clean Code 3):
    # jede tote Adresse steht mit ihrem Statuscode da.
    assert len(bilanz.tote_adressen) == 9
    assert all("HTTP 404" in eintrag for eintrag in bilanz.tote_adressen)
    assert "/p/900/weg" in bilanz.tote_adressen[0]


def test_ohne_tote_adressen_bleibt_die_liste_leer():
    """Gegenprobe: ein sauberer Lauf darf nicht heimlich Luecken melden -
    sonst waere die Zahl oben auch ohne 404 gruen."""
    bilanz = _lauf(_seiten(lebend=36, tot=0))
    assert bilanz.tote_adressen == []
    assert bilanz.produkte_versucht == 36
    assert bilanz.vollstaendig is True


# --------------------------------------------------------------------------
# 2. Die Schwelle - und die Grenze genau
# --------------------------------------------------------------------------

def test_die_schwelle_ist_eine_benannte_konstante():
    from telco_radar.collect.geraete import (
        _MINDESTANTEIL_GELESENER_PRODUKTSEITEN,
    )

    assert _MINDESTANTEIL_GELESENER_PRODUKTSEITEN == 0.75


def test_genau_die_schwelle_reicht_noch():
    """Drei von vier gelesen = 0,75. Die Grenze wird ERREICHT, nicht
    ueberschritten - der Rand, an dem eine Schwelle falsch beurteilt wird
    (T5)."""
    bilanz = _lauf(_seiten(lebend=3, tot=1))
    assert bilanz.vollstaendig is True
    assert bilanz.gelesene_einstiege == {_EINSTIEG}


def test_unter_der_schwelle_ist_der_lauf_unvollstaendig():
    """Die Gegenprobe, die verhindert, dass die Schwelle lasch wird: bei
    6 von 10 gelesenen Seiten ist die Quelle umgebaut, nicht veraltet -
    und `mark_stale` darf kein halbes Sortiment altern."""
    bilanz = _lauf(_seiten(lebend=6, tot=4))
    assert bilanz.gelesene_einstiege == set()
    assert bilanz.vollstaendig is False
    assert bilanz.status == "fehler"
    # Und das Protokoll sagt, woran es lag - nicht "kein Einstieg lesbar".
    assert "4 von 10 Produktadressen tot" in bilanz.grund
    assert "kein Einstieg lesbar" not in bilanz.grund


def test_eine_tote_adresse_unter_zwei_reisst_die_schwelle():
    """Der kleinste Fall, an dem die Schwelle wirklich rechnet: 1 von 2
    gelesen sind 0,50. Ohne ihn koennte die Schwelle auf 0,5 sinken, ohne
    dass ein Test faellt."""
    bilanz = _lauf(_seiten(lebend=1, tot=1))
    assert bilanz.vollstaendig is False


# --------------------------------------------------------------------------
# 3. Nur eine Antwort des Anbieters ist eine tote Adresse
# --------------------------------------------------------------------------

def test_ein_serverfehler_ist_keine_tote_adresse():
    """HTTP 500 heisst "wir wissen nicht, was auf dieser Seite steht" -
    nicht gelesen ist nicht leer (Clean Code 6). Eine einzige solche
    Seite macht den Einstieg unvollstaendig, obwohl 35 von 36 Seiten
    durchkamen."""
    seiten = _seiten(lebend=36, tot=0)
    kaputt = "https://www.medimax.de/p/100/iphone-17-pro-max-256gb"

    bilanz = _lauf(seiten, antwort=lambda u: (500, "") if u == kaputt else None)
    assert bilanz.tote_adressen == []
    assert bilanz.gelesene_einstiege == set()
    assert bilanz.vollstaendig is False


def test_gone_ist_eine_tote_adresse():
    """410 ist die ausdrueckliche Auskunft "gibt es nicht mehr" - noch
    eindeutiger als 404 und deshalb ebenso eine Luecke, kein Ausfall."""
    seiten = _seiten(lebend=36, tot=0)
    weg = "https://www.medimax.de/p/100/iphone-17-pro-max-256gb"

    bilanz = _lauf(seiten, antwort=lambda u: (410, "") if u == weg else None)
    assert len(bilanz.tote_adressen) == 1
    assert "HTTP 410" in bilanz.tote_adressen[0]
    assert bilanz.vollstaendig is True


def test_eine_robots_sperre_ist_keine_tote_adresse():
    """Eine gesperrte Adresse kommt gar nicht bis zu einer Antwort - sie
    hat keinen Statuscode und darf deshalb nie als tot durchgehen."""
    seiten = _seiten(lebend=36, tot=0)

    def hole(url):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /p/\n")
        return (200, seiten[url]) if url in seiten else (404, "")

    bilanz = sammle_anbieter(_anbieter(), _KATALOG, _FARBEN, hole,
                             "2026-08-11", RobotsWaechter(hole=hole), _jetzt())
    assert bilanz.tote_adressen == []
    assert bilanz.gelesene_einstiege == set()


# --------------------------------------------------------------------------
# 4. Der Einstieg selbst bleibt ein Fehler
# --------------------------------------------------------------------------

def test_ein_toter_einstieg_bleibt_ein_fehler():
    """Die Lockerung gilt fuer PRODUKTADRESSEN. Antwortet die
    Einstiegsseite selbst 404, ist der Anbieter ungelesen - sonst waere
    eine abgeschaltete Quelle ein vollstaendiger Lauf mit null Geraeten,
    und `mark_stale` alterte alles (Clean Code 5)."""
    bilanz = _lauf({})
    assert bilanz.status == "fehler"
    assert bilanz.vollstaendig is False
    assert bilanz.tote_adressen == []
    assert bilanz.produkte_versucht == 0
    assert "HTTP 404" in bilanz.grund


# --------------------------------------------------------------------------
# 5. Die Zahl steht im Protokoll und auf der Quellenseite
# --------------------------------------------------------------------------

_QUELLEN_MIT_TOTER_ADRESSE = {"anbieter": [
    {"name": "Medimax", "typ": "handel", "methode": "ldjson", "rang": 1,
     "basis_url": "https://www.medimax.de", "rate_limit_sekunden": 0,
     "einstiege": [{"url": _EINSTIEG, "label": "Smartphones",
                    "pfadmuster": "/p/"}]},
]}


def _stufe(tmp_path, tag: str, lebend: int, tot: int, root=None,
           robots: str = "User-agent: *\nDisallow: /cart\n", stunde: int = 3):
    """Ein Lauf der ganzen Stufe. `root` wiederverwendet einen bestehenden
    Bestand - so lassen sich zwei Naechte hintereinander messen."""
    import yaml

    if root is None:
        root = _root(tmp_path)
        (root / "config" / "geraete_quellen.yaml").write_text(
            yaml.safe_dump(_QUELLEN_MIT_TOTER_ADRESSE, allow_unicode=True,
                           sort_keys=False), encoding="utf-8")
    seiten = _seiten(lebend=lebend, tot=tot)

    def hole(url):
        if url.endswith("/robots.txt"):
            return (200, robots)
        return (200, seiten[url]) if url in seiten else (404, "")

    return root, run_geraete_stage(root, {}, tag, jetzt=_jetzt(stunde),
                                   hole=hole)


def test_der_lauf_zaehlt_wieder_als_vollstaendiger_lauf(tmp_path):
    """Der Kern des Befunds, von der Stufe aus gemessen: 23 Tage lang
    `laeufe: 0` und kein `letzter_lauf`, obwohl jede Nacht Listungen
    ankamen."""
    root, bilanz = _stufe(tmp_path, "2026-08-11", lebend=36, tot=9)
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    gebucht = db.laufbilanz("Medimax")
    assert gebucht["laeufe"] == 1
    assert gebucht["letzter_lauf"] == "2026-08-11"
    # Und die Luecke ist gebucht, nicht verschwiegen.
    assert gebucht["tote_adressen"] == 9
    satz = [a for a in bilanz["anbieter"] if a["anbieter"] == "Medimax"][0]
    assert satz["status"] == "ok"
    assert satz["tote_adressen"] == 9
    assert satz["produkte_versucht"] == 45


def test_ein_lauf_ohne_produktseiten_bucht_keine_null(tmp_path):
    """Clean Code 3: "nicht versucht" ist None, nicht 0. Sonst stuende
    fuer einen nie abgerufenen Anbieter "0 tote Adressen" - eine
    Entwarnung, die niemand gemessen hat."""
    root, _ = _stufe(tmp_path, "2026-08-11", lebend=0, tot=0)
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert db.laufbilanz("Medimax")["tote_adressen"] is None


def test_die_quellenseite_nennt_die_toten_adressen(tmp_path):
    """Die Zahl gehoert auf die Seite und nicht nur ins Log - gemessen am
    ECHTEN Makro der Quellenseite, nicht an einer Kopie davon."""
    from telco_radar.geraete_config import lade_katalog, lade_quellen

    root, _ = _stufe(tmp_path, "2026-08-11", lebend=36, tot=9)
    daten = geraete_view.aufbereiten(root / "data" / "state",
                                     lade_quellen(root), lade_katalog(root),
                                     heute="2026-08-11")
    zeile = {z["name"]: z for z in daten["quellenlage"]["zeilen"]}["Medimax"]
    assert zeile["tote_satz"] == "9 verlinkte Produktseiten gibt es nicht mehr"
    modul = _env().get_template("geraete_quellen.html.j2").make_module(
        {"geraete": {"quellenlage": {"zeilen": [], "ohne_hardware": [],
                                     "aufgefuehrt": 0, "liefernd": 0,
                                     "seiten": 0},
                     "stand": "", "pruefung": {}},
         "prefix": ""})
    assert "9 verlinkte Produktseiten gibt es nicht mehr" in modul.zeile(zeile)


def test_ohne_tote_adressen_steht_keine_null_auf_der_seite(tmp_path):
    """Gegenprobe: ein sauberer Lauf traegt keinen Luecken-Satz - sonst
    waere der Test darueber auch mit einem fest verdrahteten Satz gruen."""
    from telco_radar.geraete_config import lade_katalog, lade_quellen

    root, _ = _stufe(tmp_path, "2026-08-11", lebend=36, tot=0)
    daten = geraete_view.aufbereiten(root / "data" / "state",
                                     lade_quellen(root), lade_katalog(root),
                                     heute="2026-08-11")
    zeile = {z["name"]: z for z in daten["quellenlage"]["zeilen"]}["Medimax"]
    assert zeile["tote_satz"] == ""


# --------------------------------------------------------------------------
# 6. Der Lesezustand: GELESEN, nicht TEILGELESEN
# --------------------------------------------------------------------------

def test_tote_adressen_ergeben_gelesen_und_nicht_teilgelesen(tmp_path):
    """Kein ZWEITER Teilzustand neben dem des Abdeckungswaechters
    (Clean Code 7). TEILGELESEN heisst "abgebrochen, was durchkam ist
    nicht das Sortiment" - deshalb taugt so ein Tag nicht als
    Vergleichsbasis. Bei toten Adressen ist nichts abgebrochen: jede
    genannte Adresse wurde versucht, die fehlenden hat der Anbieter selbst
    beantwortet. Waere dieser Tag TEILGELESEN, haette der Anbieter nie
    wieder eine vollstaendige Basis und liefe dauerhaft in
    `ALARM_OHNE_BASIS`."""
    from telco_radar.analyze.geraete_store import GELESEN, TEILGELESEN

    root, _ = _stufe(tmp_path, "2026-08-11", lebend=36, tot=9)
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    tag = db.messtage("Medimax")[-1]
    assert tag.zustand == GELESEN
    assert tag.zustand != TEILGELESEN
    assert tag.vergleichsbasis is True


def test_unter_der_schwelle_ist_der_tag_ein_lesefehler(tmp_path):
    """Die Gegenprobe: reisst die Schwelle, ist es ein Leseversuch, der
    nicht durchkam - und damit ein Ausfall, kein stiller gruener Tag."""
    from telco_radar.analyze.geraete_store import LESEFEHLER

    root, _ = _stufe(tmp_path, "2026-08-11", lebend=6, tot=4)
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert db.messtage("Medimax")[-1].zustand == LESEFEHLER


# --------------------------------------------------------------------------
# 7. Was KEINE tote Adresse ist - die Wege, die keinen Statuscode haben
# --------------------------------------------------------------------------

def test_eine_abweisung_der_abrufschleuse_hat_keinen_statuscode():
    """Der Kern der Unterscheidung, am kleinsten Baustein gemessen.

    Die `Abrufschleuse` wirft, BEVOR ein Abruf hinausgeht - robots-Sperre,
    Besuchsfenster, unlesbare robots.txt. Da hat niemand geantwortet, und
    `status` bleibt `None`. Das Feld und nicht der Meldungstext traegt die
    Unterscheidung; eine Ausnahme ohne Statuscode kann deshalb nie unter
    die toten Adressen geraten (Clean Code 3: kein erfundener Wert).
    """
    from telco_radar.collect.geraete import _TOTE_STATUS, GeraeteAbrufFehler

    exc = GeraeteAbrufFehler("Visit-time 0200-0800, Abruf um 12:00")
    assert exc.status is None
    assert exc.status not in _TOTE_STATUS


def test_die_besuchszeit_beendet_den_lauf_ohne_tote_adresse():
    """Die Tuer geht MITTEN in der Produktschleife zu (S2-3).

    Bis hierher war nur das Disallow getestet. Die Besuchszeit ist der
    zweite Weg durch dieselbe Schleuse und der Regelfall bei medimax.de
    und ep.de: die Uhr laeuft waehrend des Laufs aus dem Fenster
    (0200-0800), und ab da weist die Schleuse jede weitere Adresse ab.
    Was dabei ausfaellt, ist NICHT gelesen - kein Statuscode, keine tote
    Adresse, und die Seite gilt als unvollstaendig (Clean Code 6).
    """
    from datetime import timedelta

    seiten = _seiten(lebend=6, tot=0)
    robots = "User-agent: *\nCrawl-delay: 0\nVisit-time: 0200-0800\n"
    # Die ersten Abrufe liegen im Fenster, danach ist es 09:00 - eine Uhr,
    # die waehrend des Laufs weiterlaeuft, und genau das tut sie in echt.
    takte = {"n": 0}

    def uhr():
        takte["n"] += 1
        return _jetzt(3) if takte["n"] <= 4 else _jetzt(3) + timedelta(hours=6)

    def hole(url):
        if url.endswith("/robots.txt"):
            return (200, robots)
        return (200, seiten[url]) if url in seiten else (404, "")

    bilanz = sammle_anbieter(_anbieter(), _KATALOG, _FARBEN, hole,
                             "2026-08-11", RobotsWaechter(hole=hole),
                             _jetzt(3), uhr=uhr)
    assert bilanz.tote_adressen == []
    assert bilanz.ausserhalb_besuchszeit is True
    assert bilanz.vollstaendig is False
    assert bilanz.produkte_abgerufen < bilanz.produkte_versucht


def test_http_403_ist_keine_tote_adresse():
    """403 heisst Autorisierung, nicht "gibt es nicht" (CLAUDE.md Regel 14).

    Ein Bot-Schutz, der auf einmal 403 liefert, ist der Anfang eines
    echten Ausfalls - er darf niemals als gepflegte Luecke durchgehen und
    den Lauf vollstaendig lassen, sonst altert `mark_stale` ein
    Sortiment, das es noch gibt.
    """
    seiten = _seiten(lebend=36, tot=0)
    gesperrt = "https://www.medimax.de/p/100/iphone-17-pro-max-256gb"

    bilanz = _lauf(seiten,
                   antwort=lambda u: (403, "") if u == gesperrt else None)
    assert bilanz.tote_adressen == []
    assert bilanz.gelesene_einstiege == set()
    assert bilanz.vollstaendig is False


def test_eine_202_challenge_ist_keine_tote_adresse():
    """202 ist fuer `raise_for_status()` kein Fehler, und die Challenge-
    Seite liefert still null Listungen (CLAUDE.md, Fallstricke).

    Der Abruf KAM durch - die Adresse lebt. Sie darf deshalb weder als
    tot gezaehlt werden noch den Einstieg unvollstaendig machen; was
    fehlt, sind Listungen, und dafuer stehen `rohsaetze` und der
    Abdeckungswaechter.
    """
    seiten = _seiten(lebend=36, tot=0)
    challenge = "https://www.medimax.de/p/100/iphone-17-pro-max-256gb"

    bilanz = _lauf(seiten, antwort=lambda u: (202, "<html><body>Bitte "
                                              "warten</body></html>")
                   if u == challenge else None)
    assert bilanz.tote_adressen == []
    assert bilanz.produkte_abgerufen == 36
    assert bilanz.vollstaendig is True


# --------------------------------------------------------------------------
# 8. Mehrere Einstiege: die Schwelle rechnet je Einstieg
# --------------------------------------------------------------------------

_EINSTIEG_ZWEI = "https://www.medimax.de/c/117/handys"


def test_nur_der_einstieg_mit_zu_vielen_toten_adressen_faellt_aus():
    """Ein Anbieter mit zwei Kategorieseiten, von denen nur EINE zerfaellt.

    Die Schwelle rechnet je EINSTIEG und nicht ueber den Anbieter: 4 von
    10 toten Adressen auf der einen Seite duerfen die andere nicht
    mitnehmen (sonst kostete eine umgebaute Unterkategorie das ganze
    Sortiment), und die heile Seite darf die kaputte nicht decken (sonst
    alterte `mark_stale` deren Rest).

    Gemessen wird beides: die kaputte Seite ist NICHT in
    `gelesene_einstiege`, die heile schon - und `mark_stale` haengt genau
    an dieser Menge.
    """
    seiten = _seiten(lebend=6, tot=4, einstieg=_EINSTIEG, marke="1")
    seiten.update(_seiten(lebend=10, tot=0, einstieg=_EINSTIEG_ZWEI,
                          marke="2"))
    anbieter = _anbieter(einstiege=[
        Einstieg(url=_EINSTIEG, label="Smartphones", pfadmuster="/p/"),
        Einstieg(url=_EINSTIEG_ZWEI, label="Handys", pfadmuster="/p/"),
    ])

    def hole(url):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /cart\n")
        return (200, seiten[url]) if url in seiten else (404, "")

    bilanz = sammle_anbieter(anbieter, _KATALOG, _FARBEN, hole, "2026-08-11",
                             RobotsWaechter(hole=hole), _jetzt())
    assert bilanz.gelesene_einstiege == {_EINSTIEG_ZWEI}
    assert bilanz.status == "ok"
    assert bilanz.vollstaendig is True
    assert bilanz.produkte_versucht == 20
    assert len(bilanz.tote_adressen) == 4
    assert f"{_EINSTIEG}: 4 von 10 Produktadressen tot" in bilanz.grund
    assert _EINSTIEG_ZWEI not in bilanz.grund


# --------------------------------------------------------------------------
# 9. "Nicht gemessen" steht auch im PROTOKOLL als Luecke (Clean Code 3)
# --------------------------------------------------------------------------

def test_ein_lauf_ohne_produktseiten_bucht_auch_im_protokoll_keine_null(
        tmp_path):
    """Dieselbe Regel wie im Bestand - und bis zum 22.09.2026 stand im
    Protokoll-JSON genau die Entwarnung, die
    `test_ein_lauf_ohne_produktseiten_bucht_keine_null` fuer den Bestand
    verbietet: `"tote_adressen": 0` und `"produkte_versucht": 0` fuer
    einen Anbieter, der keine einzige Produktseite versucht hat. Zwei
    Kanaele, eine Wahrheit (Clean Code 7)."""
    root, bilanz = _stufe(tmp_path, "2026-08-11", lebend=0, tot=0)
    satz = [a for a in bilanz["anbieter"] if a["anbieter"] == "Medimax"][0]
    assert satz["tote_adressen"] is None
    assert satz["produkte_versucht"] is None
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert db.laufbilanz("Medimax")["tote_adressen"] is None


def test_eine_nacht_ohne_abruf_loescht_die_gemessene_luecke_nicht(tmp_path):
    """Eine Nicht-Messung darf eine Messung nicht ueberschreiben.

    Erste Nacht: neun tote Adressen, gemessen und gebucht. Zweite Nacht:
    der Anbieter steht ausserhalb seiner Besuchszeit und wird gar nicht
    angefasst - keine Produktseite versucht, also keine Aussage ueber
    tote Adressen. Vorher schrieb dieser Lauf `None` in den Bestand und
    raeumte die gestern gemessenen neun von der Quellenseite ab, obwohl
    die Luecke unveraendert bestand (Clean Code 6).
    """
    from telco_radar.geraete_config import lade_katalog, lade_quellen

    root, _ = _stufe(tmp_path, "2026-08-11", lebend=36, tot=9)
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert db.laufbilanz("Medimax")["tote_adressen"] == 9

    _stufe(tmp_path, "2026-08-12", lebend=36, tot=9, root=root, stunde=12,
           robots="User-agent: *\nVisit-time: 0200-0800\n")
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert db.laufbilanz("Medimax")["tote_adressen"] == 9, \
        "eine Nacht ohne Abruf hat die gemessene Luecke geloescht"
    daten = geraete_view.aufbereiten(root / "data" / "state",
                                     lade_quellen(root), lade_katalog(root),
                                     heute="2026-08-12")
    zeile = {z["name"]: z for z in daten["quellenlage"]["zeilen"]}["Medimax"]
    assert zeile["tote_satz"] == "9 verlinkte Produktseiten gibt es nicht mehr"
