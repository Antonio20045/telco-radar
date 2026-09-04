"""Die Geraetestufe als Ganzes: sammeln, aufnehmen, altern, speichern.

Die eine Regel, die diese Datei traegt: `mark_stale` laeuft NUR fuer
Anbieter, deren Bilanz vollstaendig ist. Ein Teilausfall, ein Fristablauf,
eine gesperrte oder ausserhalb ihrer Besuchszeit liegende Quelle heissen
alle "nicht gelesen" - und was nicht gelesen wurde, altert nicht.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from telco_radar.analyze.geraete_store import (
    GeraeteDB,
    STATUS_AKTIV,
    STATUS_VERMUTLICH,
)
from telco_radar.geraete_pipeline import run_geraete_stage

_FIX = Path(__file__).parent / "fixtures" / "geraete"

_KATALOG = {"geraete": [
    {"hersteller": "Apple", "modell": "iPhone 17 Pro Max", "generation": 17,
     "speicher": [256, 512, 1024], "segment": "flagship"},
    {"hersteller": "Samsung", "modell": "Galaxy A57", "generation": 57,
     "speicher": [128, 256], "segment": "mid"},
]}

_FARBEN = {"farben": {"titan-natur": ["Titannatur"], "schwarz": ["Black"]}}

_QUELLEN = {"anbieter": [
    {"name": "Medimax", "typ": "handel", "methode": "ldjson", "rang": 1,
     "basis_url": "https://www.medimax.de", "rate_limit_sekunden": 0,
     "einstiege": [{"url": "https://www.medimax.de/c/116/smartphones",
                    "label": "Smartphones", "pfadmuster": "/p/"}]},
    {"name": "Amazon", "typ": "handel", "methode": "deaktiviert", "rang": 2,
     "aktiv": False, "grund": "erfordert Product-Advertising-API-Zugang"},
]}

_SEITEN = {
    "https://www.medimax.de/c/116/smartphones":
        (_FIX / "medimax_kategorie.html").read_text(encoding="utf-8"),
    "https://www.medimax.de/p/1518897/galaxy-a57-5g-a576b-128gb":
        (_FIX / "medimax_produkt_a57.html").read_text(encoding="utf-8"),
    "https://www.medimax.de/p/1514136/iphone-17-pro-max-256gb":
        (_FIX / "medimax_produkt.html").read_text(encoding="utf-8"),
    "https://www.medimax.de/p/1514200/huelle-iphone-17":
        "<html><body>Zubehör</body></html>",
}


def _root(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir(exist_ok=True)
    for name, daten in (("geraete_katalog.yaml", _KATALOG),
                        ("farben.yaml", _FARBEN),
                        ("geraete_quellen.yaml", _QUELLEN)):
        (tmp_path / "config" / name).write_text(
            yaml.safe_dump(daten, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    return tmp_path


def _hole(seiten=None, protokoll=None):
    seiten = _SEITEN if seiten is None else seiten

    def hole(url):
        if protokoll is not None:
            protokoll.append(url)
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nDisallow: /cart\n")
        return (200, seiten[url]) if url in seiten else (404, "")
    return hole


def _jetzt(stunde=3):
    return datetime(2026, 8, 11, stunde, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------

def test_lauf_schreibt_datenbank_und_historie(tmp_path):
    root = _root(tmp_path)
    bilanz = run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(),
                               hole=_hole())
    assert bilanz["status"] == "ok"
    assert bilanz["listungen"] == 2 and bilanz["neu"] == 2
    assert bilanz["preispunkte"] == 2

    db = json.loads((root / "data" / "state" / "geraete_db.json").read_text(encoding="utf-8"))
    assert db["updated"] == "2026-08-11" and len(db["listungen"]) == 2
    zeilen = (root / "data" / "state" / "geraete_preise.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 2
    preise = sorted(json.loads(z)["preis_ohne_vertrag"] for z in zeilen)
    assert preise == [349.0, 1449.0]


def test_jeder_anbieter_taucht_in_der_bilanz_auf(tmp_path):
    """Akzeptanzkriterium aus Teil E: kein Anbieter fehlt stillschweigend."""
    bilanz = run_geraete_stage(_root(tmp_path), {}, "2026-08-11",
                               jetzt=_jetzt(), hole=_hole())
    namen = {a["anbieter"] for a in bilanz["anbieter"]}
    assert namen == {"Medimax", "Amazon"}
    amazon = [a for a in bilanz["anbieter"] if a["anbieter"] == "Amazon"][0]
    assert amazon["status"] == "uebersprungen" and amazon["grund"]


def test_zweiter_lauf_ohne_treffer_altert_nur_eine_stufe(tmp_path):
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    leer = dict(_SEITEN)
    leer["https://www.medimax.de/c/116/smartphones"] = "<html><body></body></html>"
    bilanz = run_geraete_stage(root, {}, "2026-08-14", jetzt=_jetzt(),
                               hole=_hole(leer))
    assert bilanz["gealtert"] == 2
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert {e["status"] for e in db.eintraege()} == {STATUS_VERMUTLICH}


def test_ein_ausgefallener_anbieter_altert_nichts(tmp_path):
    """Der Kern: 404 auf die Einstiegsseite heisst 'nicht gelesen', nicht
    'keine Geraete mehr da'."""
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    bilanz = run_geraete_stage(root, {}, "2026-08-14", jetzt=_jetzt(),
                               hole=_hole({}))
    assert bilanz["gealtert"] == 0
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert {e["status"] for e in db.eintraege()} == {STATUS_AKTIV}
    medimax = [a for a in bilanz["anbieter"] if a["anbieter"] == "Medimax"][0]
    assert medimax["status"] == "fehler" and medimax["vollstaendig"] is False


def test_ausserhalb_der_besuchszeit_wird_weder_geholt_noch_gealtert(tmp_path):
    """Der Befund, der den Zeitplan bestimmt: medimax.de erlaubt Abrufe nur
    zwischen 02:00 und 08:00 UTC, der Wochenlauf startet 08:30."""
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(3), hole=_hole())

    protokoll = []

    def hole(url):
        protokoll.append(url)
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\nVisit-time: 0200-0800\n")
        return (200, _SEITEN[url]) if url in _SEITEN else (404, "")

    bilanz = run_geraete_stage(root, {}, "2026-08-14", jetzt=_jetzt(8),
                               hole=hole)
    assert bilanz["gealtert"] == 0
    assert [u for u in protokoll if "/p/" in u] == []
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert {e["status"] for e in db.eintraege()} == {STATUS_AKTIV}


def test_unveraenderter_preis_schreibt_keinen_zweiten_punkt(tmp_path):
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    bilanz = run_geraete_stage(root, {}, "2026-08-14", jetzt=_jetzt(),
                               hole=_hole())
    assert bilanz["preispunkte"] == 0
    zeilen = (root / "data" / "state" / "geraete_preise.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 2


def test_zeitbudget_bricht_sauber_ab(tmp_path):
    """Teil F: bei Fristablauf sauber abbrechen, Teilergebnis speichern, im
    Protokoll vermerken - und nichts altern."""
    root = _root(tmp_path)
    bilanz = run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(),
                               hole=_hole(), frist_sekunden=0.0001)
    medimax = [a for a in bilanz["anbieter"] if a["anbieter"] == "Medimax"][0]
    assert medimax["status"] == "frist"
    assert medimax["vollstaendig"] is False
    assert bilanz["gealtert"] == 0


def test_ohne_konfiguration_tut_die_stufe_nichts(tmp_path):
    (tmp_path / "config").mkdir()
    bilanz = run_geraete_stage(tmp_path, {}, "2026-08-11", jetzt=_jetzt(),
                               hole=_hole())
    assert bilanz["status"] == "keine Konfiguration"
    assert not (tmp_path / "data").exists()


def test_hardware_vermarktung_zaehlt_nur_gelesene_laeufe(tmp_path):
    """Ein ausgefallener Abruf darf keine Marke zum SIM-only-Anbieter
    erklaeren."""
    root = _root(tmp_path)
    for tag in ("2026-08-11", "2026-08-14", "2026-08-18"):
        run_geraete_stage(root, {}, tag, jetzt=_jetzt(), hole=_hole({}))
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert db.hardware_vermarktung("Medimax") == "unbekannt"


def test_drei_leere_aber_gelesene_laeufe_ergeben_sim_only(tmp_path):
    root = _root(tmp_path)
    leer = dict(_SEITEN)
    leer["https://www.medimax.de/c/116/smartphones"] = "<html><body></body></html>"
    for tag in ("2026-08-11", "2026-08-14", "2026-08-18"):
        run_geraete_stage(root, {}, tag, jetzt=_jetzt(), hole=_hole(leer))
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert db.hardware_vermarktung("Medimax") == "nein"


def _seite_mit_titel(titel: str, preis: str = "299.00") -> str:
    return ('<html><head><script type="application/ld+json">'
            '{"@type":"Product","name":"%s","offers":{"@type":"Offer",'
            '"price":"%s","priceCurrency":"EUR",'
            '"availability":"https://schema.org/InStock"}}'
            '</script></head><body></body></html>' % (titel, preis))


def test_unerkannte_titel_stehen_im_protokoll(tmp_path, caplog):
    """Der naechtliche Lauf gibt an niemanden zurueck - sein einziger Kanal
    ist das Protokoll. `unbekannte_titel` ist die Arbeitsliste fuer
    `config/geraete_katalog.yaml` (ist der Katalog zu schmal oder der
    Zubehoerfilter zu eng?) und stand bis zum 10.08.2026 nur in der
    Rueckgabe. Im ersten echten Lauf war sie deshalb nicht auffindbar,
    obwohl von 27 abgerufenen ALDI-TALK-Seiten genau EINE eine Listung
    ergab."""
    seiten = dict(_SEITEN)
    seiten["https://www.medimax.de/p/1514200/huelle-iphone-17"] = \
        _seite_mit_titel("Nothing Phone (3a) 128GB")
    with caplog.at_level("INFO", logger="telco_radar.geraete_pipeline"):
        bilanz = run_geraete_stage(_root(tmp_path), {}, "2026-08-11",
                                   jetzt=_jetzt(), hole=_hole(seiten))
    assert "Nothing Phone (3a) 128GB" in bilanz["unbekannte_titel"]
    assert bilanz["unbekannte_titel_gesamt"] == len(bilanz["unbekannte_titel"])
    text = caplog.text
    assert "ohne Katalogtreffer" in text
    assert "Nothing Phone (3a) 128GB" in text


def test_protokoll_nennt_die_listungen_eines_gescheiterten_anbieters(tmp_path,
                                                                    caplog):
    """Ein Anbieter, der 84 Listungen liefert und trotzdem "fehler" heisst,
    ist erklaerbar - aber nur, wenn die Zeile die 84 nennt. Im ersten echten
    Lauf stand dort bloss "mobilcom-debitel -> fehler (kein Einstieg
    lesbar)", und das Gegenteil war wahr."""
    seiten = dict(_SEITEN)
    del seiten["https://www.medimax.de/p/1518897/galaxy-a57-5g-a576b-128gb"]
    with caplog.at_level("INFO", logger="telco_radar.geraete_pipeline"):
        bilanz = run_geraete_stage(_root(tmp_path), {}, "2026-08-11",
                                   jetzt=_jetzt(), hole=_hole(seiten))
    medimax = [a for a in bilanz["anbieter"] if a["anbieter"] == "Medimax"][0]
    assert medimax["status"] == "fehler" and medimax["listungen"] == 1
    assert "Medimax -> fehler, 1 Listungen aus 2 Produktseiten" in caplog.text


def test_nichts_wird_ausserhalb_von_data_state_geschrieben(tmp_path):
    root = _root(tmp_path)
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    geschrieben = {p.relative_to(root).as_posix()
                   for p in root.rglob("*") if p.is_file()}
    ausserhalb = {p for p in geschrieben
                  if not p.startswith(("config/", "data/state/"))}
    assert ausserhalb == set()


def test_teillauf_mit_listungen_landet_in_der_messtermin_buchfuehrung(tmp_path):
    """G0-Befund vom 28.08.2026: mobilcom-debitel bestaetigte jede Nacht
    seine Listungen, wurde am Zeitbudget aber nie fertig - und fehlte
    deshalb KOMPLETT in der Laufbilanz. `_oft_genug` sperrte damit 84 von
    85 Listungen aus der Lifecycle-Auswertung. Ein Teillauf mit Funden
    muss als Messtermin verbucht werden, ohne als vollstaendiger Lauf zu
    zaehlen."""
    root = _root(tmp_path)
    # Eine der Produktseiten faellt aus - der Einstieg gilt damit als
    # unvollstaendig gelesen (status fehler), genau die mobilcom-Lage.
    seiten = dict(_SEITEN)
    del seiten["https://www.medimax.de/p/1514200/huelle-iphone-17"]
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole(seiten))

    from telco_radar.analyze.geraete_store import GeraeteDB
    db = GeraeteDB(root / "data" / "state" / "geraete_db.json")
    assert db.messtermine("Medimax") == ["2026-08-11"]
    assert db.laufbilanz("Medimax").get("laeufe", 0) == 0, \
        "ein Teillauf zaehlt nicht als vollstaendiger Lauf"
    assert db.hardware_vermarktung("Medimax") == "ja"


def test_die_hole_fabrik_gibt_den_statuscode_zurueck_statt_zu_werfen():
    """Der Befund vom 28.08.2026, und er kostete einen ganzen Anbieter.

    `collect.http.fetch` ruft `raise_for_status()`. Die Fabrik reichte die
    Ausnahme durch, der Robots-Waechter landete in seinem Ausnahmezweig
    ("kein Ergebnis heisst nicht erlaubt") und fuehrte den Anbieter als
    nicht abrufbar - obwohl 404 auf einer robots.txt genau das Gegenteil
    bedeutet: keine Regeln. Aufgefallen ist es erst bei `api.vodafone.de`,
    dem ersten konfigurierten Host ohne robots.txt.

    Gegen den alten Stand faellt dieser Test durch."""
    import httpx

    from telco_radar.geraete_pipeline import _hole_fabrik

    class _Antwort:
        status_code = 404
        text = '{"message": "The requested API was not found."}'

    def _werfen(url, cfg, **kw):
        raise httpx.HTTPStatusError("404", request=None, response=_Antwort())

    import telco_radar.collect.http as http_modul
    echt = http_modul.fetch
    http_modul.fetch = _werfen
    try:
        # Die Fabrik bindet `fetch` beim ERZEUGEN, nicht beim Aufruf - sie
        # muss also nach dem Austausch gebaut werden.
        status, text = _hole_fabrik({"timeout_seconds": 5})(
            "https://api.example.de/robots.txt")
    finally:
        http_modul.fetch = echt
    assert status == 404 and "not found" in text.lower()


def test_ein_host_ohne_robots_txt_wird_abgefragt_statt_uebersprungen(tmp_path):
    """Die Gegenprobe auf Anbieterebene: 404 auf der robots.txt heisst
    "keine Einschraenkung", nicht "Finger weg"."""
    import httpx

    root = _root(tmp_path)
    seiten = dict(_SEITEN)

    class _Antwort404:
        status_code = 404
        text = ""

    def _fetch(url, cfg, **kw):
        if url.endswith("/robots.txt"):
            raise httpx.HTTPStatusError("404", request=None,
                                        response=_Antwort404())
        class _Ok:
            status_code = 200
            text = seiten.get(url, "")
        if url not in seiten:
            raise httpx.HTTPStatusError("404", request=None,
                                        response=_Antwort404())
        return _Ok()

    import telco_radar.collect.http as http_modul
    echt = http_modul.fetch
    http_modul.fetch = _fetch
    try:
        bilanz = run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt())
    finally:
        http_modul.fetch = echt
    assert bilanz["listungen"] == 2, bilanz["anbieter"]


# --------------------------------------------------------------------------
# Der Massstab aus dem Tarifbestand (Phase 6, 04.09.2026)
#
# Die Stufe schreibt seit heute `data/state/geraete_tco.json` mit - die
# SIM-only-Referenzen, ohne die ein Geraeteanteil nicht bestimmbar ist.
# Sie steht NACH `db.save()`: ein Messtag ist nicht nachholbar, ein
# Massstab schon (Lehre aus Lauf 31422689829).
# --------------------------------------------------------------------------

_TARIFE = [
    {"tarif_id": "telekom:magentamobil-l", "anbieter": "Telekom",
     "name": "MagentaMobil L", "art": "mobilfunk", "grundgebuehr": 59.95,
     "anschlusspreis": None, "preisphasen": [],
     "dokument_url": "https://www.telekom.de/pib/magentamobil-l",
     "abgerufen_am": "2026-08-11"},
    {"tarif_id": "o2:o2-home-l", "anbieter": "o2", "name": "O2 Home L",
     "art": "festnetz", "grundgebuehr": 44.99, "anschlusspreis": None,
     "preisphasen": [], "dokument_url": "https://x.de/home-l.pdf",
     "abgerufen_am": "2026-08-11"},
]


def _mit_tarifen(root: Path, saetze=None) -> Path:
    zustand = root / "data" / "state"
    zustand.mkdir(parents=True, exist_ok=True)
    (zustand / "tarife.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n"
                for s in (_TARIFE if saetze is None else saetze)),
        encoding="utf-8")
    return root


def test_der_lauf_schreibt_die_sim_only_referenzen(tmp_path):
    root = _mit_tarifen(_root(tmp_path))
    bilanz = run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(),
                               hole=_hole())

    tco = json.loads((root / "data" / "state" / "geraete_tco.json")
                     .read_text(encoding="utf-8"))
    namen = [r["tarif_name"] for r in tco["sim_only"]]
    # Der Festnetztarif ist KEIN Massstab fuer ein Smartphone-Buendel.
    assert namen == ["MagentaMobil L"]
    assert tco["sim_only"][0]["tarif_id"] == "telekom:magentamobil-l"
    assert tco["sim_only"][0]["tarif_sim_only_monatlich"] == 59.95
    assert bilanz["sim_only_referenzen"] == 1
    assert bilanz["tarife_im_bestand"] == 2


def test_ohne_tarifbestand_bleibt_der_geraetebestand_unberuehrt(tmp_path):
    """Kein `tarife.jsonl`: die Stufe laeuft durch, ohne etwas zu verlieren."""
    root = _root(tmp_path)
    bilanz = run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(),
                               hole=_hole())
    assert bilanz["status"] == "ok"
    assert bilanz["sim_only_referenzen"] == 0
    assert (root / "data" / "state" / "geraete_db.json").exists()
    assert GeraeteDB(root / "data" / "state" / "geraete_db.json").eintraege()


def test_ein_leerer_tarifbestand_loescht_den_massstab_nicht(tmp_path):
    """"Nicht gelesen" ist nicht "leer".

    `Tarifbestand.aus_datei` wirft bei fehlender Datei nicht. Ein
    Baseline-Reset, ein Merge-Konflikt oder ein Wettlauf mit `radar.yml`
    saehe damit aus wie "es gibt keine Tarife mehr" - und `ersetze_
    referenzen` loeschte den ganzen Massstab, ohne einen Fehler zu melden.
    Dieselbe Fehlerklasse wie `promo_store.mark_stale` ohne
    `gepruefte_seiten`.
    """
    root = _mit_tarifen(_root(tmp_path))
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    (root / "data" / "state" / "tarife.jsonl").unlink()

    bilanz = run_geraete_stage(root, {}, "2026-08-14", jetzt=_jetzt(),
                               hole=_hole())
    tco = json.loads((root / "data" / "state" / "geraete_tco.json")
                     .read_text(encoding="utf-8"))
    assert len(tco["sim_only"]) == 1          # noch da
    assert bilanz["sim_only_referenzen"] == 0  # aber nicht geschrieben


def test_ein_verschwundener_tarif_verschwindet_aus_dem_massstab(tmp_path):
    """Die Gegenprobe: was der Bestand wirklich hergibt, wird ersetzt.

    Ohne sie bewiese der Test darueber nur, dass nie geloescht wird - und
    dann waere der Massstab wieder die wachsende Liste, gegen die
    `ersetze_referenzen` gebaut ist.
    """
    root = _mit_tarifen(_root(tmp_path))
    run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(), hole=_hole())
    anders = dict(_TARIFE[0], tarif_id="telekom:magentamobil-m",
                  name="MagentaMobil M", grundgebuehr=49.95)
    _mit_tarifen(root, [anders])

    run_geraete_stage(root, {}, "2026-08-14", jetzt=_jetzt(), hole=_hole())
    tco = json.loads((root / "data" / "state" / "geraete_tco.json")
                     .read_text(encoding="utf-8"))
    assert [r["tarif_name"] for r in tco["sim_only"]] == ["MagentaMobil M"]


def test_ein_fehler_beim_massstab_kostet_den_messtag_nicht(tmp_path, monkeypatch):
    """Der Geraetebestand ist zu diesem Zeitpunkt schon gespeichert.

    Ein Messtag ist nicht nachholbar, ein Massstab schon - deshalb steht
    der Block nach `db.save()` und in seinem eigenen Auffangboden.
    """
    import telco_radar.geraete_pipeline as pipeline
    root = _mit_tarifen(_root(tmp_path))

    def kaputt(*_a, **_k):
        raise OSError("Platte voll")
    monkeypatch.setattr(pipeline.TcoDB, "save", kaputt)

    bilanz = run_geraete_stage(root, {}, "2026-08-11", jetzt=_jetzt(),
                               hole=_hole())
    assert bilanz["status"] == "ok"
    assert bilanz["listungen"] > 0
    assert (root / "data" / "state" / "geraete_db.json").exists()
    # Und die Bilanz behauptet NICHT, geschrieben zu haben - das ist der
    # einzige Fall, fuer den dieser Zaehler gebaut ist.
    assert bilanz["sim_only_referenzen"] == 0
