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
    Feldaenderung, TarifSpeicher, _sortiere, als_item, dokumentlinks,
    juengste_fassung, lade_quellen, linktexte, sammle, tarif_id, vergleiche,
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


# --------------------------------------------------------------------------- #
# Die Vorauswahl: juengste Fassung und Linkbeschriftung
#
# Nachgetragen am 04.09.2026. Bis dahin wurden aus 1114 verlinkten
# Telekom-Dokumenten fuenf ausgewaehlt, und VIER davon waren derselbe Tarif
# in vier Vermarktungsstaenden - der aelteste von 2017.
# --------------------------------------------------------------------------- #

_TELEKOM = "https://www.telekom.de/produktinformationsblatt/"


def test_von_vier_staenden_bleibt_der_neueste():
    """Live gemessen: `magentamobil-l` steht in vier Faellen verlinkt.

    Alle vier tragen die Titelzeile "MagentaMobil L". Ohne diese Auswahl
    bekam die STABILE Tarif-ID `telekom:magentamobil-l` den Stand von 2017
    (54,95 EUR, ohne erkannte Laufzeit), waehrend der aktuelle Stand
    (59,95 EUR) unter einem Hash-Zusatz landete - die Zeitreihe haengt dann
    am toten Produkt.
    """
    links = [_TELEKOM + s for s in ("magentamobil-l-20170601",
                                    "magentamobil-l-20180831",
                                    "magentamobil-l-20220701",
                                    "magentamobil-l-20240801")]
    assert juengste_fassung(links) == [_TELEKOM + "magentamobil-l-20240801"]


def test_verschiedene_tarife_bleiben_alle():
    """Gruppiert wird nach Adressstamm, nicht nach Anbieter."""
    links = [_TELEKOM + s for s in ("magentamobil-s-20240801",
                                    "magentamobil-m-20240801",
                                    "magentamobil-m-20180831")]
    assert juengste_fassung(links) == [_TELEKOM + "magentamobil-s-20240801",
                                       _TELEKOM + "magentamobil-m-20240801"]


def test_eine_variante_ist_ein_eigener_tarif():
    """`-flex` und `-young` sind eigene, aktuell vermarktete Tarife.

    Sie duerfen nicht als aeltere Fassung des Grundtarifs verschwinden -
    ihr Adressstamm ist ein anderer.
    """
    links = [_TELEKOM + s for s in ("magentamobil-s-20240801",
                                    "magentamobil-s-flex-20240801",
                                    "magentamobil-s-young-20251007")]
    assert juengste_fassung(links) == links


def test_adressen_ohne_datum_bleiben_unberuehrt():
    """o2, Vodafone und congstar datieren ihre Dateinamen nicht so.

    Die Reihenfolge bleibt die der Seite - sie ist bei congstar die einzige
    Ordnung, die es gibt, solange `bevorzugt` nichts trifft.
    """
    links = ["https://static2.o9.de/resource/blob/2241742/x/o2-mobile-m.pdf",
             "https://www.congstar.de/x/Produktinformationsblatt_549.pdf",
             "https://www.vodafone.de/x/VF-Mobil-M-Juli-2026.pdf"]
    assert juengste_fassung(links) == links


def test_eine_achtstellige_zahl_ohne_jahr_ist_kein_datum():
    """Dieselbe Vorsicht wie beim Datum aus dem Link in `collect/rss.py`.

    `-19990101` waere ein Datum, `-12345678` ist eine Artikelnummer. Ohne
    die Jahresgrenze frisst die Regel jede numerierte Adresse - und
    loeschte bei congstar reihenweise Dokumente.
    """
    links = ["https://x.de/a/doc-12345678", "https://x.de/a/doc-99887766"]
    assert juengste_fassung(links) == links


def test_bevorzugt_findet_den_tarif_in_der_linkbeschriftung():
    """congstar numeriert seine Dateinamen durch.

    `Produktinformationsblatt_549.pdf` sagt nichts; der Linktext
    "Produktinformationsblatt congstar Allnet Flat L mit Upgrade-
    Versprechen" sagt alles. Ohne den Text kann die Vorauswahl dort nur
    die Seitenreihenfolge nehmen - und die ist keine Zusage.
    """
    links = ["https://www.congstar.de/x/Produktinformationsblatt_9001.pdf",
             "https://www.congstar.de/x/Produktinformationsblatt_549.pdf"]
    texte = {links[0]: "Produktinformationsblatt Homespot & Go S",
             links[1]: "Produktinformationsblatt congstar Allnet Flat L"}
    assert _sortiere(links, ["congstar allnet flat"], texte)[0] == links[1]
    # Ohne die Beschriftung bleibt es bei der Seitenreihenfolge - und die
    # ist bei congstar die einzige Ordnung, die es gibt: die Seite stellt
    # die laufenden Tarife nach oben.
    assert _sortiere(links, ["congstar allnet flat"]) == links


def test_linktexte_liest_dieselbe_menge_wie_dokumentlinks():
    """Sonst bekaeme die Vorauswahl eine Beschriftung zu einer Adresse, die
    gar nicht abgerufen werden darf - oder umgekehrt keine zu einer, die es
    darf."""
    html = ('<a href="/pib/Produktinformationsblatt_1.pdf">Allnet Flat S</a>'
            '<a href="/agb/">AGB</a>'
            '<a href="/pib/Produktinformationsblatt_2.pdf">Allnet Flat M</a>')
    basis = "https://www.congstar.de/produktinformationsblaetter/"
    links = dokumentlinks(html, basis, ["produktinformationsblatt"])
    texte = linktexte(html, basis, ["produktinformationsblatt"])
    assert set(texte) == set(links)
    assert texte[links[0]] == "Allnet Flat S"


def test_ein_einstieg_ohne_dokumentlink_meldet_sich(caplog, tmp_path):
    """Der stumme Ausfall, der die Telekom zwei Monate gekostet hat.

    Ihre Seite antwortet aus GitHub Actions mit einer Challenge: HTTP 202,
    rund 2 KB, kein <a>. Das ist kein Fehlerstatus, `raise_for_status()`
    laesst ihn durch, und der Sammler zaehlte still "0 verlinkt" weiter.
    Ohne Status und Groesse in der Zeile ist eine Challenge nicht von einer
    leeren Rubrik zu unterscheiden.
    """
    import logging
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "tarif_quellen.yaml").write_text(
        "quellen:\n  - anbieter: Telekom\n    einstieg:\n"
        "      - https://www.telekom.de/produktinformationsblatt\n"
        "    pfadmuster:\n      - /produktinformationsblatt/\n",
        encoding="utf-8")

    class Challenge:
        status_code = 202
        text = "<html><body>bitte warten</body></html>"
        content = b"x" * 2048
        headers = {"content-type": "text/html"}

    with caplog.at_level(logging.WARNING):
        _, bilanz = sammle(tmp_path, {}, hole=lambda u, c: Challenge())
    assert bilanz["ohne_links"] == 1
    assert bilanz["fehler"] == 0        # es war eben KEIN Fehler
    assert "202" in caplog.text and "2048" in caplog.text


def test_der_erste_wunsch_frisst_nicht_den_ganzen_einkauf():
    """Reihum durch die Wuensche, nicht Wunsch fuer Wunsch.

    Am 04.09.2026 gemessen: "magentamobil-s-" trifft neun Telekom-Dokumente
    (der Tarif plus Flex-, Young-, Friends- und Happy-Varianten), und sie
    stehen alle vor dem ersten M-Dokument. Ein Deckel von zwoelf brachte
    damit NEUNMAL MagentaMobil S und kein einziges Mal M, L, XL oder Basic.
    Dieselbe Ueberlegung wie `_interleave_by_source` in der Pipeline.
    """
    links = ([f"https://x.de/magentamobil-s-{i}" for i in range(9)]
             + ["https://x.de/magentamobil-m-1", "https://x.de/magentamobil-l-1"])
    gereiht = _sortiere(links, ["magentamobil-s-", "magentamobil-m-",
                                "magentamobil-l-"])
    assert gereiht[:3] == ["https://x.de/magentamobil-s-0",
                           "https://x.de/magentamobil-m-1",
                           "https://x.de/magentamobil-l-1"]
    # Ohne Reihum stuenden hier die naechsten acht S-Dokumente.
    assert gereiht[3] == "https://x.de/magentamobil-s-1"


def test_unerwuenschtes_steht_hinten_und_geht_nicht_verloren():
    """Ein Deckel schneidet, die Vorauswahl loescht nicht.

    Was kein Wunsch trifft, faellt in Seitenreihenfolge ans Ende - es kann
    einen Deckel unterschreiten, aber es verschwindet nicht aus der Liste.
    """
    links = ["https://x.de/anderes-a", "https://x.de/wunsch-1",
             "https://x.de/anderes-b"]
    assert _sortiere(links, ["wunsch"]) == ["https://x.de/wunsch-1",
                                            "https://x.de/anderes-a",
                                            "https://x.de/anderes-b"]


# --------------------------------------------------------------------------- #
# Die zweite Lesart: die Einstiegsseite IST die Nutzlast (seit 04.09.2026)
# --------------------------------------------------------------------------- #

_SHOP = "https://www.1und1.de/handytarife"

CONFIG_LDJSON = f"""
quellen:
  - anbieter: 1&1
    methode: ldjson
    einstieg: ["{_SHOP}"]
    max_dokumente: 10
"""


def _shop_seite(*betraege: str) -> str:
    """Eine Shop-Seite mit je einem Product-Knoten pro Betrag."""
    knoten = "".join(
        '<script type="application/ld+json">'
        '{"@type": "Product", "name": "1&1 All-Net-Flat %s", '
        '"description": "1&1 All-Net-Flat %s 10 GB", '
        '"brand": {"name": "1&1"}, '
        '"offers": {"priceCurrency": "EUR", "price": "%s"}}</script>'
        % (name, name, betrag)
        for name, betrag in zip("SML", betraege))
    return f"<html><body>{knoten}</body></html>"


def _staende(root: Path) -> list[dict]:
    pfad = root / "data" / "state" / "tarife.jsonl"
    return [json.loads(z) for z in pfad.read_text(encoding="utf-8").splitlines()
            if z.strip()]


def test_ldjson_quelle_ruft_ausschliesslich_ihre_einstiegsseite_ab(tmp_path):
    """Kein Link wird geerntet, keine zweite Adresse geholt. Damit ist die
    Regel "nur abrufen, was verlinkt ist" hier trivial erfuellt - abgerufen
    wird genau die Adresse, die in der Konfiguration steht."""
    netz = _Netz({
        _SHOP: _Antwort(_shop_seite("14.99", "19.99")
                        + '<a href="https://www.1und1.de/handytarife-ohne-handy">SIM</a>'),
        "https://www.1und1.de/handytarife-ohne-handy": _Antwort(_shop_seite("14.99")),
    })
    root = _repo(tmp_path, CONFIG_LDJSON)
    _, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)
    assert netz.abgerufen == [_SHOP]
    assert bilanz["geholt"] == 1
    assert bilanz["gelesen"] == 2
    # `verlinkt` bleibt 0: es wurde nichts verlinkt. Eine Null in einer
    # Spalte, die hier nichts messen kann, waere eine Falschmeldung.
    assert bilanz["verlinkt"] == 0


def test_ldjson_satz_traegt_preistyp_und_shop_adresse(tmp_path):
    netz = _Netz({_SHOP: _Antwort(_shop_seite("14.99"))})
    root = _repo(tmp_path, CONFIG_LDJSON)
    sammle(root, {}, jetzt=JETZT, hole=netz)
    satz = _staende(root)[0]
    assert satz["preistyp"] == "live_shop"
    assert satz["dokument_url"] == _SHOP
    assert satz["grundgebuehr"] == 14.99
    assert satz["anbieter"] == "1&1"


def test_pib_satz_bleibt_ein_dokumentsatz(tmp_path):
    """Der Vorgabewert ist `dokument`. Jeder Bestandssatz aus der Zeit vor
    dem 04.09.2026 bleibt beim Wiedereinlesen genau das, was er war."""
    verlinkt = f"{EINSTIEG}/magentamobil-l-20240801"
    netz = _Netz({EINSTIEG: _Antwort(f'<a href="{verlinkt}">L</a>'),
                  verlinkt: _Antwort(_pib_text(), typ="text/plain")})
    root = _repo(tmp_path, CONFIG)
    sammle(root, {}, jetzt=JETZT, hole=netz)
    assert _staende(root)[0]["preistyp"] == "dokument"


def test_zwei_knoten_einer_seite_bleiben_zwei_tarife(tmp_path):
    """Sieben Tarife teilen sich eine Adresse. Waere die Herkunft die
    Adresse statt der Fingerabdruck, waeren zwei gleichnamige Knoten zwei
    Fassungen desselben Tarifs statt zweier Produkte."""
    netz = _Netz({_SHOP: _Antwort(_shop_seite("14.99", "19.99", "24.99"))})
    root = _repo(tmp_path, CONFIG_LDJSON)
    _, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)
    assert bilanz["grundlinie"] == 3
    assert len({s["tarif_id"] for s in _staende(root)}) == 3


def test_zweiter_lauf_derselben_shop_seite_meldet_nichts(tmp_path):
    netz = _Netz({_SHOP: _Antwort(_shop_seite("14.99", "19.99"))})
    root = _repo(tmp_path, CONFIG_LDJSON)
    sammle(root, {}, jetzt=JETZT, hole=netz)
    items, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)
    assert bilanz["unveraendert"] == 2 and bilanz["grundlinie"] == 0
    assert items == []


def test_geaenderter_shop_preis_wird_gemeldet(tmp_path):
    root = _repo(tmp_path, CONFIG_LDJSON)
    sammle(root, {}, jetzt=JETZT,
           hole=_Netz({_SHOP: _Antwort(_shop_seite("14.99"))}))
    items, bilanz = sammle(root, {}, jetzt=JETZT,
                           hole=_Netz({_SHOP: _Antwort(_shop_seite("12.99"))}))
    assert bilanz["geaendert"] == 1
    assert len(items) == 1
    assert "14.99" in items[0].summary and "12.99" in items[0].summary
    # Die Meldung nennt ihre Quellenart. "Gesetzlich vorgeschriebenes
    # Produktinformationsblatt" waere hier schlicht falsch - eine Zahl aus
    # den strukturierten Daten einer Werbeseite traegt keine gesetzliche
    # Wahrheitsbewehrung.
    assert "Der Preis auf der Shop-Seite hat sich geändert" in items[0].summary
    assert "Produktinformationsblatt" not in items[0].summary
    assert items[0].source_name == "1&1 (Shop-Seite)"


def test_shop_seite_ohne_tarif_faellt_auf_statt_stumm_zu_bleiben(tmp_path, caplog):
    """Derselbe Befund wie eine Einstiegsseite ohne Dokumentlink, und er
    muss genauso laut sein: eine Seite, die 200 und 450 KB liefert und
    trotzdem keinen Tarif hergibt, hat ihr Format geaendert oder eine
    Challenge ausgeliefert."""
    netz = _Netz({_SHOP: _Antwort("<html><body>Bitte warten</body></html>")})
    root = _repo(tmp_path, CONFIG_LDJSON)
    with caplog.at_level("WARNING"):
        _, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)
    assert bilanz["ohne_links"] == 1
    assert bilanz["gelesen"] == 0
    assert "KEIN Tarif" in caplog.text


def test_toter_shop_einstieg_kippt_den_lauf_nicht(tmp_path):
    root = _repo(tmp_path, CONFIG_LDJSON)
    _, bilanz = sammle(root, {}, jetzt=JETZT, hole=_Netz({}))
    assert bilanz["fehler"] == 1 and bilanz["gelesen"] == 0


def test_vertippte_methode_wird_laut_und_nicht_zur_vorgabe(tmp_path):
    """Ohne diese Zeile faellt ein Tippfehler erst auf, wenn jemand merkt,
    dass ein Anbieter seit Wochen nichts mehr liefert."""
    netz = _Netz({_SHOP: _Antwort(_shop_seite("14.99"))})
    root = _repo(tmp_path, CONFIG_LDJSON.replace("methode: ldjson",
                                                 "methode: ldjsom"))
    _, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)
    assert bilanz["fehler"] == 1
    assert netz.abgerufen == []


def test_die_ausgelieferte_config_kennt_nur_gebaute_methoden():
    from telco_radar.collect.tarif_crawler import (
        METHODE_KACHELN, METHODE_LDJSON, METHODEN,
    )
    quellen = lade_quellen(Path(__file__).resolve().parents[1])
    assert {q.methode for q in quellen} <= set(METHODEN)
    einsundeins = [q for q in quellen if q.anbieter == "1&1"]
    assert len(einsundeins) == 1
    assert einsundeins[0].methode == METHODE_LDJSON
    assert einsundeins[0].einstieg == ["https://www.1und1.de/handytarife"]
    # o2 steht ZWEIMAL: einmal mit seinen Pflichtblaettern, einmal mit den
    # Preiskacheln der SIM-only-Seite. Das ist kein Duplikat, sondern die
    # Regel aus dem Konfigkopf ("Ein Anbieter darf in beiden Lesarten
    # auftauchen") - und ohne die Kacheln kaeme kein o2-Buendel in den
    # TCO-Bestand.
    o2 = [q for q in quellen if q.anbieter == "o2"]
    assert {q.methode for q in o2} == {"dokumente", METHODE_KACHELN}
    kacheln = [q for q in o2 if q.methode == METHODE_KACHELN][0]
    assert kacheln.einstieg == [
        "https://www.o2online.de/tarife/handyvertrag-ohne-handy/"]


# --------------------------------------------------------------------------
# Zwei Lesarten sind zwei Zeitreihen
# --------------------------------------------------------------------------

def _stand(name, preistyp, grundgebuehr, laufzeit=None):
    from telco_radar.tarif_model import HOCH, Tarif
    tarif = Tarif(anbieter="o2", name=name, preistyp=preistyp,
                  abgerufen_am="2026-09-04", rohtext=f"{name} {grundgebuehr}")
    tarif.confidence["grundgebuehr"] = HOCH
    tarif.grundgebuehr = grundgebuehr
    tarif.laufzeit_monate = laufzeit
    return tarif


def _lege_ab(speicher, tarif, herkunft, im_lauf=None):
    from telco_radar.collect.tarif_crawler import uebernimm_stand
    bilanz = {"grundlinie": 0, "unveraendert": 0, "geaendert": 0,
              "kleingedruckt": 0}
    items = []
    uebernimm_stand(tarif, hash_=herkunft, herkunft=herkunft,
                    speicher=speicher, bilanz=bilanz,
                    im_lauf=im_lauf if im_lauf is not None else {},
                    items=items, jetzt=JETZT)
    return bilanz, items


def test_shop_preis_wird_keine_neue_fassung_des_pflichtblattes(tmp_path):
    """Der Fehler, den der erste o2-Kachellauf am 04.09.2026 gezeigt hat.

    Blatt und Kachel nennen denselben Tarif ("O2 Mobile Unlimited M Flex")
    und tragen deshalb dieselbe Tarif-ID. In EINER Zeitreihe wird die
    Kachel zur naechsten Fassung des Blattes - und `vergleiche` meldet als
    Tarifaenderung, was in Wahrheit der Unterschied zwischen einem PDF und
    einer Werbeseite ist. Genau dagegen ist `preistyp` gebaut.
    """
    from telco_radar.collect.tarif_crawler import TarifSpeicher
    from telco_radar.tarif_model import PREISTYP_DOKUMENT, PREISTYP_LIVE_SHOP
    speicher = TarifSpeicher(tmp_path / "tarife.jsonl")

    bilanz, _ = _lege_ab(speicher, _stand("O2 Mobile Unlimited M Flex",
                                          PREISTYP_DOKUMENT, 39.99, 24),
                         "https://o2.de/blatt.pdf")
    assert bilanz["grundlinie"] == 1

    bilanz, items = _lege_ab(speicher, _stand("O2 Mobile Unlimited M Flex",
                                              PREISTYP_LIVE_SHOP, 39.99),
                             "kachelhash")
    # Eine eigene Grundlinie - KEINE Aenderungsmeldung.
    assert bilanz["grundlinie"] == 1 and bilanz["geaendert"] == 0
    assert items == []
    assert [s["tarif_id"] for s in speicher.staende] == [
        "o2:o2-mobile-unlimited-m-flex",
        "o2:o2-mobile-unlimited-m-flex#live_shop"]


def test_der_zusatz_bleibt_ueber_die_laeufe_stabil(tmp_path):
    """Er ist der PREISTYP und kein Inhaltshash.

    Ein Hash aenderte sich mit jeder Preisaenderung - die Zeitreihe der
    zweiten Lesart zerfiele in lauter Einzelsaetze, und kein Diff
    verbaende je zwei Staende.
    """
    from telco_radar.collect.tarif_crawler import TarifSpeicher
    from telco_radar.tarif_model import PREISTYP_DOKUMENT, PREISTYP_LIVE_SHOP
    speicher = TarifSpeicher(tmp_path / "tarife.jsonl")
    _lege_ab(speicher, _stand("O2 Mobile L", PREISTYP_DOKUMENT, 24.99),
             "https://o2.de/blatt.pdf")
    _lege_ab(speicher, _stand("O2 Mobile L", PREISTYP_LIVE_SHOP, 24.99),
             "hash-eins")
    bilanz, items = _lege_ab(speicher,
                             _stand("O2 Mobile L", PREISTYP_LIVE_SHOP, 22.99),
                             "hash-zwei")
    assert bilanz["geaendert"] == 1 and len(items) == 1
    assert [s["tarif_id"] for s in speicher.staende] == [
        "o2:o2-mobile-l", "o2:o2-mobile-l#live_shop", "o2:o2-mobile-l#live_shop"]


def test_dieselbe_lesart_bleibt_eine_zeitreihe(tmp_path):
    """Die Gegenprobe: ohne sie truennte die Regel auch, was zusammengehoert."""
    from telco_radar.collect.tarif_crawler import TarifSpeicher
    from telco_radar.tarif_model import PREISTYP_LIVE_SHOP
    speicher = TarifSpeicher(tmp_path / "tarife.jsonl")
    _lege_ab(speicher, _stand("O2 Mobile L", PREISTYP_LIVE_SHOP, 24.99), "a")
    bilanz, _ = _lege_ab(speicher,
                         _stand("O2 Mobile L", PREISTYP_LIVE_SHOP, 22.99), "b")
    assert bilanz["geaendert"] == 1
    assert {s["tarif_id"] for s in speicher.staende} == {"o2:o2-mobile-l"}
