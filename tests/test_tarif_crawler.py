"""Tarif-Sammler: Linkernte, Versionierung, Feld-Diff - und die Regel.

Der wichtigste Test dieser Datei ist
`test_crawler_ruft_nur_verlinkte_adressen_ab`. Er prueft maschinell, was
sonst nur im Kommentar staende: es wird ausschliesslich abgerufen, was auf
einer konfigurierten Seite als Link stand. Keine geratenen Pfade, keine
hochgezaehlten Blob-IDs.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from telco_radar.collect import tarif_crawler
from telco_radar.collect.tarif_crawler import (
    Feldaenderung, TarifSpeicher, als_item, dokumentlinks, lade_quellen,
    sammle, tarif_id, vergleiche,
)
from telco_radar.tarif_model import Tarif

JETZT = datetime(2026, 8, 8, tzinfo=timezone.utc)
FIX = Path(__file__).parent / "fixtures" / "tarif_pdfs"


# --------------------------------------------------------------------------- #
# Linkernte
# --------------------------------------------------------------------------- #

HUB = """
<html><body>
  <a href="/produktinformationsblatt/magentamobil-l-20240801">L</a>
  <a href="/produktinformationsblatt/magentamobil-basic-20240801">Basic</a>
  <a href="/impressum">Impressum</a>
  <a href="#oben">nach oben</a>
  <a href="javascript:void(0)">nichts</a>
  <a href="/produktinformationsblatt/magentamobil-l-20240801">L nochmal</a>
</body></html>
"""


def test_dokumentlinks_nimmt_nur_passende_pfade():
    links = dokumentlinks(HUB, "https://www.telekom.de/produktinformationsblatt",
                          ["/produktinformationsblatt/"])
    assert links == [
        "https://www.telekom.de/produktinformationsblatt/magentamobil-l-20240801",
        "https://www.telekom.de/produktinformationsblatt/magentamobil-basic-20240801",
    ]


def test_dokumentlinks_entdoppelt_und_haelt_die_reihenfolge():
    links = dokumentlinks(HUB, "https://www.telekom.de/produktinformationsblatt",
                          ["/produktinformationsblatt/"])
    assert len(links) == len(set(links))


def test_die_einstiegsseite_selbst_ist_kein_dokument():
    html = '<a href="https://x.de/pib/">Übersicht</a><a href="/pib/a">A</a>'
    links = dokumentlinks(html, "https://x.de/pib/", ["/pib/"])
    assert links == ["https://x.de/pib/a"]


def test_ohne_muster_zaehlt_jeder_link():
    links = dokumentlinks('<a href="/a.pdf">a</a><a href="/b">b</a>',
                          "https://x.de/", [])
    assert links == ["https://x.de/a.pdf", "https://x.de/b"]


def test_dokumentlinks_vertraegt_leeres_html():
    assert dokumentlinks("", "https://x.de/", ["/pib/"]) == []


# --------------------------------------------------------------------------- #
# Die Tarif-ID
# --------------------------------------------------------------------------- #

def test_tarif_id_ueberlebt_die_jahreszahl():
    """"O2 Mobile Unlimited M Flex (2026)" und dieselbe Zeile im Folgejahr
    sind derselbe Tarif - sonst haette der Diff nie zwei Staende verbunden."""
    assert (tarif_id("o2", "O2 Mobile Unlimited M Flex (2026)")
            == tarif_id("o2", "O2 Mobile Unlimited M Flex (2027)"))


def test_tarif_id_trennt_verschiedene_tarife():
    assert tarif_id("Telekom", "MagentaMobil L") != \
        tarif_id("Telekom", "MagentaMobil Basic")


def test_tarif_id_trennt_anbieter():
    assert tarif_id("o2", "Mobile M") != tarif_id("Telekom", "Mobile M")


def test_tarif_id_ist_stabil_ueber_klammerzusatz():
    assert (tarif_id("Telekom", "MagentaMobil L (Mobilfunk)")
            == tarif_id("Telekom", "MagentaMobil L"))


def test_tarif_id_vertraegt_umlaute():
    assert tarif_id("o2", "Größer Tarif") == "o2:groesser-tarif"


# --------------------------------------------------------------------------- #
# Feld-Diff
# --------------------------------------------------------------------------- #

def _tarif(**kw) -> Tarif:
    t = Tarif(anbieter="Telekom", name="MagentaMobil L",
              dokument_url="https://x.de/pib/l", dokument_hash="abc")
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def test_geaenderter_preis_wird_erkannt():
    alt = {"grundgebuehr": 59.95, "datenvolumen_gb": 80.0}
    ae = vergleiche(alt, _tarif(grundgebuehr=64.95, datenvolumen_gb=80.0))
    assert [(a.feld, a.alt, a.neu) for a in ae] == [
        ("grundgebuehr", 59.95, 64.95)]


def test_ausgefallenes_feld_ist_keine_aenderung():
    """Ein Feld, das der Extraktor diesmal nicht gefunden hat, ist ein
    Ausfall. Als "80 GB -> nicht angegeben" gemeldet waere es die haeufigste
    Falschmeldung dieses Radars."""
    alt = {"grundgebuehr": 59.95, "datenvolumen_gb": 80.0}
    ae = vergleiche(alt, _tarif(grundgebuehr=59.95, datenvolumen_gb=None))
    assert ae == []


def test_neu_hinzugekommenes_feld_zaehlt():
    ae = vergleiche({"grundgebuehr": 59.95},
                    _tarif(grundgebuehr=59.95, drossel_down=64.0))
    assert [a.feld for a in ae] == ["drossel_down"]


def test_unendlich_bleibt_unendlich():
    ae = vergleiche({"datenvolumen_gb": float("inf")},
                    _tarif(datenvolumen_gb=float("inf")))
    assert ae == []


def test_lesbare_form_nennt_einheit():
    a = Feldaenderung("datenvolumen_gb", 80.0, 50.0)
    assert a.lesbar() == "Datenvolumen: 80 GB → 50 GB"


def test_lesbare_form_bei_fehlendem_altwert():
    assert Feldaenderung("drossel_down", None, 64.0).lesbar() == \
        "Drosselung (Download): nicht angegeben → 64 KBit/s"


def test_unbegrenzt_wird_ausgeschrieben():
    assert "unbegrenzt" in Feldaenderung(
        "datenvolumen_gb", float("inf"), 50.0).lesbar()


# --------------------------------------------------------------------------- #
# A9: der Kleingedruckt-Waechter
# --------------------------------------------------------------------------- #

def test_drosselaenderung_bei_gleichem_preis_ist_kleingedrucktes():
    """Das Akzeptanzkriterium aus A9.

    Eine Drosselgrenze von 80 GB auf 50 GB bei gleichem Preis ist eine
    Preiserhoehung, die nirgends als solche auftaucht.
    """
    ae = vergleiche({"grundgebuehr": 59.95, "datenvolumen_gb": 80.0},
                    _tarif(grundgebuehr=59.95, datenvolumen_gb=50.0))
    assert len(ae) == 1
    assert ae[0].ist_kleingedruckt

    item = als_item(_tarif(grundgebuehr=59.95, datenvolumen_gb=50.0), ae, JETZT)
    assert "stillschweigend" in item.title
    assert "ohne dass der Preis sich bewegt" in item.summary


def test_kleingedrucktes_erreicht_ctm_stufe_drei():
    """Die Meldung muss durch die CTM-Linse auf Stufe 3 (DIREKT) kommen -
    sonst steht der stille Konditionswechsel unter "ferner liefen"."""
    from telco_radar.analyze.ctm import DIREKT, deterministische_stufe, lade_fokus
    fokus = lade_fokus(Path(__file__).resolve().parents[1])
    ae = [Feldaenderung("datenvolumen_gb", 80.0, 50.0)]
    item = als_item(_tarif(datenvolumen_gb=50.0), ae, JETZT)
    h = {"operator": item.operator, "title": item.title,
         "summary": item.summary, "category": "Tarif/Pricing"}
    assert deterministische_stufe(h, fokus) == DIREKT


def test_preisaenderung_heisst_anders():
    ae = vergleiche({"grundgebuehr": 59.95}, _tarif(grundgebuehr=64.95))
    item = als_item(_tarif(grundgebuehr=64.95), ae, JETZT)
    assert "ändert den Preis" in item.title
    assert "stillschweigend" not in item.title


def test_zwei_aenderungen_desselben_tarifs_sind_zwei_meldungen():
    """Sonst haelt der Seen-Store die zweite fuer die schon berichtete erste -
    derselbe Fehler, den der Aenderungsradar schon einmal bezahlt hat."""
    ae = [Feldaenderung("grundgebuehr", 59.95, 64.95)]
    a = als_item(_tarif(dokument_hash="hash-eins"), ae, JETZT)
    b = als_item(_tarif(dokument_hash="hash-zwei"), ae, JETZT)
    assert a.id != b.id


def test_item_traegt_origin_und_quelle():
    ae = [Feldaenderung("grundgebuehr", 59.95, 64.95)]
    item = als_item(_tarif(), ae, JETZT)
    assert item.origin == "tarif_dokument"
    assert item.url == "https://x.de/pib/l"
    assert "Produktinformationsblatt" in item.summary


# --------------------------------------------------------------------------- #
# Speicher
# --------------------------------------------------------------------------- #

def test_speicher_haelt_ueber_neuladen(tmp_path):
    p = tmp_path / "tarife.jsonl"
    s = TarifSpeicher(p)
    s.ergaenze({"tarif_id": "telekom:x", "grundgebuehr": 10.0,
                "dokument_hash": "a"})
    s.speichern()
    assert TarifSpeicher(p).letzter("telekom:x")["grundgebuehr"] == 10.0


def test_speicher_liefert_den_juengsten_stand(tmp_path):
    s = TarifSpeicher(tmp_path / "t.jsonl")
    s.ergaenze({"tarif_id": "a", "dokument_hash": "alt"})
    s.ergaenze({"tarif_id": "a", "dokument_hash": "neu"})
    assert s.letzter("a")["dokument_hash"] == "neu"


def test_beruehren_erzeugt_keinen_neuen_satz(tmp_path):
    """Sonst waechst die Datei jede Woche um den vollstaendigen Bestand."""
    s = TarifSpeicher(tmp_path / "t.jsonl")
    s.ergaenze({"tarif_id": "a", "dokument_hash": "x", "abgerufen_am": "alt"})
    s.beruehre("a", "2026-08-08")
    assert len(s.staende) == 1
    assert s.letzter("a")["abgerufen_am"] == "2026-08-08"


def test_speicher_ueberliest_kaputte_zeilen(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text('{"tarif_id":"a"}\nkaputt\n\n', encoding="utf-8")
    assert len(TarifSpeicher(p).staende) == 1


# --------------------------------------------------------------------------- #
# sammle(): die Regel gegen ID-Enumeration
# --------------------------------------------------------------------------- #

class _Antwort:
    def __init__(self, text="", content=b"", typ="text/html"):
        self.text = text
        self.content = content or text.encode("utf-8")
        self.headers = {"content-type": typ}


class _Netz:
    """Ein Netz, das nur kennt, was ihm gesagt wurde - und Buch fuehrt."""

    def __init__(self, seiten: dict):
        self.seiten = seiten
        self.abgerufen: list[str] = []

    def __call__(self, url, http_cfg, *a, **kw):
        self.abgerufen.append(url)
        if url not in self.seiten:
            raise RuntimeError(f"404 {url}")
        return self.seiten[url]


EINSTIEG = "https://telekom.de/produktinformationsblatt"


def _repo(tmp_path: Path, yaml_text: str) -> Path:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "state").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "tarif_quellen.yaml").write_text(
        yaml_text, encoding="utf-8")
    return tmp_path


CONFIG = f"""
quellen:
  - anbieter: Telekom
    einstieg: ["{EINSTIEG}"]
    pfadmuster: ["/produktinformationsblatt/"]
    max_dokumente: 5
"""


def _pib_text() -> str:
    return (FIX / "telekom_magentamobil_l.txt").read_text(encoding="utf-8")


def test_crawler_ruft_nur_verlinkte_adressen_ab(tmp_path):
    """DIE Regel dieses Moduls, maschinell geprueft.

    Die o2-Dokumente liegen unter fortlaufenden Blob-IDs. Sie
    durchzuzaehlen waere trivial - und ist die Grenze, an der aus dem
    Abrufen oeffentlicher Pflichtdokumente das Leerraeumen einer fremden
    Datenbank wird (§ 87b UrhG).
    """
    verlinkt = f"{EINSTIEG}/magentamobil-l-20240801"
    netz = _Netz({
        EINSTIEG: _Antwort(f'<a href="{verlinkt}">L</a>'),
        verlinkt: _Antwort(_pib_text(), typ="text/plain"),
        # Die Falle: erreichbar, aber NICHT verlinkt. Ein enumerierender
        # Crawler wuerde sie finden.
        f"{EINSTIEG}/magentamobil-l-20240802": _Antwort(_pib_text()),
    })
    root = _repo(tmp_path, CONFIG)
    _, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)

    assert bilanz["nicht_verlinkt"] == []
    assert f"{EINSTIEG}/magentamobil-l-20240802" not in netz.abgerufen
    assert set(netz.abgerufen) == {EINSTIEG, verlinkt}


def test_crawler_haelt_die_obergrenze_ein(tmp_path):
    links = "".join(f'<a href="{EINSTIEG}/t{i}">t{i}</a>' for i in range(20))
    seiten = {EINSTIEG: _Antwort(links)}
    for i in range(20):
        seiten[f"{EINSTIEG}/t{i}"] = _Antwort(_pib_text(), typ="text/plain")
    netz = _Netz(seiten)
    root = _repo(tmp_path, CONFIG)
    _, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)
    assert bilanz["verlinkt"] == 20
    # Einstieg plus hoechstens max_dokumente
    assert len(netz.abgerufen) == 1 + 5


def test_erster_lauf_legt_grundlinie_und_meldet_nichts(tmp_path):
    verlinkt = f"{EINSTIEG}/magentamobil-l-20240801"
    netz = _Netz({EINSTIEG: _Antwort(f'<a href="{verlinkt}">L</a>'),
                  verlinkt: _Antwort(_pib_text(), typ="text/plain")})
    root = _repo(tmp_path, CONFIG)
    items, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)
    assert items == []
    assert bilanz["grundlinie"] == 1
    assert (root / "data" / "state" / "tarife.jsonl").exists()


def test_unveraendertes_dokument_erzeugt_keinen_neuen_satz(tmp_path):
    verlinkt = f"{EINSTIEG}/magentamobil-l-20240801"
    seiten = {EINSTIEG: _Antwort(f'<a href="{verlinkt}">L</a>'),
              verlinkt: _Antwort(_pib_text(), typ="text/plain")}
    root = _repo(tmp_path, CONFIG)
    sammle(root, {}, jetzt=JETZT, hole=_Netz(seiten))
    items, bilanz = sammle(root, {}, jetzt=JETZT, hole=_Netz(seiten))
    assert items == []
    assert bilanz["unveraendert"] == 1
    zeilen = (root / "data" / "state" / "tarife.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(zeilen) == 1


def test_geaendertes_dokument_meldet_den_feld_diff(tmp_path):
    verlinkt = f"{EINSTIEG}/magentamobil-l-20240801"
    root = _repo(tmp_path, CONFIG)
    sammle(root, {}, jetzt=JETZT, hole=_Netz({
        EINSTIEG: _Antwort(f'<a href="{verlinkt}">L</a>'),
        verlinkt: _Antwort(_pib_text(), typ="text/plain")}))

    # Dasselbe Dokument, aber die Drosselschwelle halbiert.
    geaendert = _pib_text().replace("Ab Verbrauch von 80 GB",
                                    "Ab Verbrauch von 40 GB")
    items, bilanz = sammle(root, {}, jetzt=JETZT, hole=_Netz({
        EINSTIEG: _Antwort(f'<a href="{verlinkt}">L</a>'),
        verlinkt: _Antwort(geaendert, typ="text/plain")}))

    assert bilanz["geaendert"] == 1
    assert bilanz["kleingedruckt"] == 1
    assert len(items) == 1
    assert "80 GB → 40 GB" in items[0].summary


def test_neues_layout_ohne_wertaenderung_meldet_nichts(tmp_path):
    """Neuer Hash, gleiche Werte: der Anbieter hat das Layout angefasst,
    nicht den Tarif."""
    verlinkt = f"{EINSTIEG}/magentamobil-l-20240801"
    root = _repo(tmp_path, CONFIG)
    sammle(root, {}, jetzt=JETZT, hole=_Netz({
        EINSTIEG: _Antwort(f'<a href="{verlinkt}">L</a>'),
        verlinkt: _Antwort(_pib_text(), typ="text/plain")}))

    umgebaut = _pib_text() + "\n\nHinweis: Stand der Drucklegung.\n"
    items, bilanz = sammle(root, {}, jetzt=JETZT, hole=_Netz({
        EINSTIEG: _Antwort(f'<a href="{verlinkt}">L</a>'),
        verlinkt: _Antwort(umgebaut, typ="text/plain")}))
    assert items == []
    assert bilanz["geaendert"] == 0


def test_fremdes_dokument_wird_nicht_als_tarif_gezaehlt(tmp_path):
    verlinkt = f"{EINSTIEG}/agb"
    netz = _Netz({EINSTIEG: _Antwort(f'<a href="{verlinkt}">AGB</a>'),
                  verlinkt: _Antwort("Allgemeine Geschäftsbedingungen",
                                     typ="text/plain")})
    root = _repo(tmp_path, CONFIG)
    items, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)
    assert items == [] and bilanz["gelesen"] == 0


def test_toter_einstieg_kippt_den_lauf_nicht(tmp_path):
    netz = _Netz({})
    root = _repo(tmp_path, CONFIG)
    items, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)
    assert items == [] and bilanz["fehler"] == 1


def test_fehlende_config_ist_kein_absturz(tmp_path):
    items, bilanz = sammle(tmp_path, {}, jetzt=JETZT, hole=_Netz({}))
    assert items == [] and bilanz["quellen"] == 0


def test_echte_config_ist_ladbar():
    quellen = lade_quellen(Path(__file__).resolve().parents[1])
    assert len(quellen) >= 2
    namen = {q.anbieter for q in quellen}
    assert {"Telekom", "o2"} <= namen
    for q in quellen:
        assert q.einstieg and all(u.startswith("https://") for u in q.einstieg)
        assert q.max_dokumente > 0


def test_bevorzugte_slugs_kommen_zuerst():
    links = [f"{EINSTIEG}/call-start-2017", f"{EINSTIEG}/magentamobil-l-2024"]
    sortiert = tarif_crawler._sortiere(links, ["magentamobil-l-2"])
    assert sortiert[0].endswith("magentamobil-l-2024")


def test_zwei_dokumente_mit_gleichem_titel_bleiben_getrennt(tmp_path):
    """Live gemessen am 08.08.2026 gegen o2.

    `o2-home-l-flex` und `o2-home-l-175-flex` sind zwei getrennte PDFs mit
    derselben Ueberschrift. Ohne Unterscheidung waere das zweite eine neue
    FASSUNG des ersten - und der Diff meldete bei jedem Lauf abwechselnd hin
    und her, ohne dass sich irgendwo etwas geaendert haette.
    """
    a, b = f"{EINSTIEG}/doc-a", f"{EINSTIEG}/doc-b"
    # Zwei Dokumente, gleicher Produktname, verschiedene Werte.
    eins = _pib_text()
    zwei = _pib_text().replace("Ab Verbrauch von 80 GB", "Ab Verbrauch von 30 GB")
    netz = _Netz({
        EINSTIEG: _Antwort(f'<a href="{a}">A</a><a href="{b}">B</a>'),
        a: _Antwort(eins, typ="text/plain"),
        b: _Antwort(zwei, typ="text/plain"),
    })
    root = _repo(tmp_path, CONFIG)
    items, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)

    # Beide sind Grundlinie, keines ist eine Aenderung des anderen.
    assert bilanz["grundlinie"] == 2
    assert items == []
    ids = {json.loads(z)["tarif_id"] for z in
           (root / "data" / "state" / "tarife.jsonl").read_text(
               encoding="utf-8").strip().splitlines()}
    assert len(ids) == 2


def test_dieselbe_adresse_bleibt_eine_versionsfolge(tmp_path):
    """Zwei Staende NACHEINANDER sind eine Versionsfolge - die Trennung oben
    darf das nicht kaputtmachen."""
    url = f"{EINSTIEG}/doc-a"
    root = _repo(tmp_path, CONFIG)
    sammle(root, {}, jetzt=JETZT, hole=_Netz({
        EINSTIEG: _Antwort(f'<a href="{url}">A</a>'),
        url: _Antwort(_pib_text(), typ="text/plain")}))
    items, bilanz = sammle(root, {}, jetzt=JETZT, hole=_Netz({
        EINSTIEG: _Antwort(f'<a href="{url}">A</a>'),
        url: _Antwort(_pib_text().replace("Ab Verbrauch von 80 GB",
                                          "Ab Verbrauch von 30 GB"),
                      typ="text/plain")}))
    assert bilanz["geaendert"] == 1
    assert len(items) == 1
