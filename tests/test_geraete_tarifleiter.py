"""P3-E1: die Vodafone-Tarifleiter statt fester Datenvolumen-Baender.

Bis zum 28.09.2026 teilte `geraete_tco_band` jede Karte in drei feste
Baender (bis 20 GB, 21 bis 60 GB, ueber 60 GB). Jetzt sind die Stufen die
Vodafone-Tarife "mit Smartphone" aus dem Tarifbestand, und ein Wettbewerber
faellt in die Stufe des naechstgelegenen Vodafone-Volumens.

Dazu der zweite Teil desselben Auftrags: congstar verlinkt zwei
Altprodukte ("Allnet Flat XL/XXL mit Upgrade-Versprechen") weiter ohne
Datum. Der Sammler holt sie nicht mehr und markiert ihren letzten Stand als
zurueckgezogen; Tarifseite und Geraeteseite lassen ihn aus.

Die Saetze hier sind von Hand gebaut (Datum gesetzt, Regel 11); der eine
Test gegen den echten Bestand rechnet seine Erwartung selbst aus der Datei.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from telco_radar.collect.tarif_crawler import TarifSpeicher, sammle
from telco_radar.report import geraete_tco_band as band
from telco_radar.report.tarife_view import lade_staende
from telco_radar.tarif_bezug import Tarifbestand
from telco_radar.tarif_model import ist_zurueckgezogen

WURZEL = Path(__file__).resolve().parents[1]
INF = float("inf")


def _satz(anbieter, name, gb, grund, tid=None):
    return {
        "anbieter": anbieter,
        "name": name,
        "datenvolumen_gb": gb,
        "grundgebuehr": grund,
        "tarif_id": tid or f"{anbieter.lower()}:{name.lower()}",
    }


def _bestand(xl_gb=None) -> dict:
    """Die Vodafone-Leiter vom 25.09.2026 plus je Anbieter ein paar Saetze."""
    saetze = [
        # Absichtlich NICHT in Leiterfolge: geordnet wird nach Grundgebuehr.
        _satz("Vodafone", "Vodafone Mobil L mit Smartphone", 120.0, 59.95),
        _satz("Vodafone", "Vodafone Mobil XS mit Smartphone", 15.0, 29.95),
        _satz("Vodafone", "Vodafone Mobil XL mit Smartphone", xl_gb, 79.95),
        _satz("Vodafone", "Vodafone Mobil M mit Smartphone", 60.0, 49.95),
        _satz("Vodafone", "Vodafone Mobil S mit Smartphone", 30.0, 39.95),
        # Die Tarife OHNE Geraet: andere Volumen, dieselben Stufen.
        _satz(
            "Vodafone", "Vodafone Mobil XS", 18.0, 29.95, "vodafone:vodafone-mobil-xs"
        ),
        _satz("Vodafone", "Vodafone Mobil S", 35.0, 39.95, "vodafone:vodafone-mobil-s"),
        _satz(
            "Vodafone", "Vodafone Mobil XL", None, 79.95, "vodafone:vodafone-mobil-xl"
        ),
        _satz("Telekom", "MagentaMobil XS", 20.0, 29.95, "telekom:xs"),
        _satz("Telekom", "MagentaMobil M", 50.0, 49.95, "telekom:m"),
        _satz("Telekom", "MagentaMobil XL", INF, 84.95, "telekom:xl"),
        _satz("congstar", "Allnet Flat M", 125.0, 24.0, "congstar:m"),
        _satz("1&1", "1&1 All-Net-Flat S", 10.0, 14.99, "11:s"),
        _satz("o2", "O2 Mobile Unlimited M", None, 29.99, "o2:um"),
        _satz("o2", "O2 Mobile M", 45.0, 19.99, "o2:m45"),
    ]
    return {s["tarif_id"]: s for s in saetze}


# --------------------------------------------------------------------------
# Die Leiter
# --------------------------------------------------------------------------


def test_leiter_sind_die_vodafone_tarife_mit_smartphone_nach_preis():
    leiter = band.tarifleiter(_bestand())
    assert [s.key for s in leiter] == ["xs", "s", "m", "l", "xl"]
    assert [s.label for s in leiter] == ["XS", "S", "M", "L", "XL"]
    # Das Volumen ist das des Blatts MIT Smartphone (XS 15, nicht 18 GB).
    assert [s.gb for s in leiter] == [15.0, 30.0, 60.0, 120.0, None]
    assert [s.bereich for s in leiter] == ["15 GB", "30 GB", "60 GB", "120 GB", ""]


def test_eine_stufe_unter_zwei_lesarten_steht_einmal_da():
    bestand = _bestand()
    zweite = dict(bestand["vodafone:vodafone mobil m mit smartphone"])
    zweite["tarif_id"] += "#live_shop"
    bestand[zweite["tarif_id"]] = zweite
    assert [s.key for s in band.tarifleiter(bestand)].count("m") == 1


def test_ohne_vodafone_satz_gibt_es_keine_leiter_und_einen_benannten_grund():
    ohne = {k: v for k, v in _bestand().items() if v["anbieter"] != "Vodafone"}
    leiter = band.tarifleiter(ohne)
    assert leiter == ()
    assert band.tarif_baender(ohne) == {}
    assert band.band_leer_text(leiter) == band.LEITER_FEHLT_TEXT
    # Gegenprobe: mit Leiter ist es der Satz "kein Buendel".
    assert band.band_leer_text(band.tarifleiter(_bestand())) == band.BAND_LEER_TEXT


# --------------------------------------------------------------------------
# Zuordnung
# --------------------------------------------------------------------------


def test_wettbewerber_fallen_in_die_naechste_stufe():
    leiter = band.tarifleiter(_bestand())
    assert band.band_von_gb(10, leiter) == "xs"
    assert band.band_von_gb(20, leiter) == "xs"  # 5 zu 15, 10 zu 30
    assert band.band_von_gb(25, leiter) == "s"
    assert band.band_von_gb(50, leiter) == "m"
    assert band.band_von_gb(125, leiter) == "l"
    assert band.band_von_gb(200, leiter) == "l"  # XL hat kein Volumen


def test_gleichstand_zaehlt_zur_groesseren_stufe():
    leiter = band.tarifleiter(_bestand())
    assert band.band_von_gb(45, leiter) == "m"  # je 15 GB zu S und M
    assert band.band_von_gb(22.5, leiter) == "s"  # je 7,5 GB zu XS und S


def test_fehlendes_volumen_hat_keine_stufe():
    leiter = band.tarifleiter(_bestand())
    assert band.band_von_gb(None, leiter) is None
    assert band.band_von_gb(float("nan"), leiter) is None
    assert band.band_von_gb("kaputt", leiter) is None


def test_unbegrenzt_nur_bei_einer_unbegrenzten_vodafone_stufe():
    """Heute traegt Vodafone XL kein erhobenes Volumen - ein unbegrenzter
    Wettbewerber wird dann nicht geraten, sondern bleibt ohne Stufe. Ist XL
    als unbegrenzt erhoben, faellt er genau dorthin."""
    assert band.band_von_gb(INF, band.tarifleiter(_bestand())) is None
    leiter_inf = band.tarifleiter(_bestand(xl_gb=INF))
    assert band.band_von_gb(INF, leiter_inf) == "xl"
    # Ein endliches Volumen landet nie auf der unbegrenzten Stufe.
    assert band.band_von_gb(10_000, leiter_inf) == "l"


def test_vodafone_tarife_gehen_ueber_den_namen_in_ihre_stufe():
    index = band.tarif_baender(_bestand())
    # 18 GB laege naeher an 15 als an 30, 35 GB naeher an 30 - der Name
    # entscheidet trotzdem, und XL ohne Volumen bleibt XL.
    assert index["vodafone:vodafone-mobil-xs"] == "xs"
    assert index["vodafone:vodafone-mobil-s"] == "s"
    assert index["vodafone:vodafone-mobil-xl"] == "xl"
    assert index["vodafone:vodafone mobil xl mit smartphone"] == "xl"


def test_tarif_baender_ordnet_wettbewerber_nach_volumen():
    index = band.tarif_baender(_bestand())
    assert index["telekom:xs"] == "xs"
    assert index["telekom:m"] == "m"
    assert index["congstar:m"] == "l"
    assert index["11:s"] == "xs"
    assert index["o2:m45"] == "m"
    assert "telekom:xl" not in index  # unbegrenzt, XL ohne Volumen
    assert "o2:um" not in index  # kein Volumen erhoben


def test_katalog_und_chip_tragen_die_leiter():
    leiter = band.tarifleiter(_bestand())
    katalog = band.baender_katalog(leiter)
    assert [b["key"] for b in katalog] == ["xs", "s", "m", "l", "xl"]
    assert katalog[0] == {"key": "xs", "label": "XS", "bereich": "15 GB"}
    assert band.band_label("xs") == "XS"
    assert band.band_label(None) == ""
    assert band._chip(leiter[0]) == "Band XS · 15 GB"
    assert band._chip(leiter[-1]) == "Band XL"


def test_leiter_am_echten_bestand():
    """Gegenprobe gegen die Datei selbst, ohne `tarifleiter`: jede Stufe ist
    genau ein Vodafone-Satz "mit Smartphone", mit seinem Volumen."""
    bestand = Tarifbestand.aus_datei(
        WURZEL / "data" / "state" / "tarife.jsonl"
    ).je_id_aktuell
    erwartet = {}
    for satz in bestand.values():
        name = satz.get("name") or ""
        if satz.get("anbieter") == "Vodafone" and name.endswith(" mit Smartphone"):
            stufe = name.split()[2]
            erwartet[stufe.lower()] = satz.get("datenvolumen_gb")
    assert erwartet, "kein Vodafone-Satz 'mit Smartphone' im Bestand"
    leiter = band.tarifleiter(bestand)
    assert {s.key: s.gb for s in leiter} == erwartet
    preise = [s.grundgebuehr for s in leiter]
    assert preise == sorted(preise)


# --------------------------------------------------------------------------
# congstar: ausgeschlossene Blaetter werden zurueckgezogen
# --------------------------------------------------------------------------

EINSTIEG = "https://www.congstar.de/produktinformationsblaetter/"
BLATT = "https://www.congstar.de/fileadmin/pib/Produktinformationsblatt_545.pdf"
JETZT = datetime(2026, 9, 28, tzinfo=timezone.utc)


class _Antwort:
    def __init__(self, text, typ="text/html"):
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"content-type": typ}


class _Netz:
    def __init__(self, seiten):
        self.seiten = seiten
        self.abgerufen = []

    def __call__(self, url, http_cfg, *a, **kw):
        self.abgerufen.append(url)
        if url not in self.seiten:
            raise RuntimeError(f"404 {url}")
        return self.seiten[url]


def _repo(tmp_path, ausschliessen):
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "state").mkdir(parents=True, exist_ok=True)
    zeilen = "".join(f'\n      - "{a}"' for a in ausschliessen)
    (tmp_path / "config" / "tarif_quellen.yaml").write_text(
        "quellen:\n  - anbieter: congstar\n"
        f'    einstieg: ["{EINSTIEG}"]\n'
        '    pfadmuster: ["produktinformationsblatt"]\n'
        + (f"    ausschliessen:{zeilen}\n" if ausschliessen else ""),
        encoding="utf-8",
    )
    return tmp_path


def _netz():
    text = (
        WURZEL / "tests" / "fixtures" / "tarif_pdfs" / "congstar_allnet_flat_l.txt"
    ).read_text(encoding="utf-8")
    return _Netz(
        {
            EINSTIEG: _Antwort(
                f'<a href="{BLATT}">Produktinformationsblatt '
                "congstar Allnet Flat L mit Upgrade-Versprechen</a>"
            ),
            BLATT: _Antwort(text, typ="text/plain"),
        }
    )


def test_ausgeschlossenes_blatt_wird_nicht_geholt_und_zurueckgezogen(tmp_path):
    root = _repo(tmp_path, [])
    sammle(root, {}, jetzt=JETZT, hole=_netz())
    pfad = root / "data" / "state" / "tarife.jsonl"
    vorher = Tarifbestand.aus_datei(pfad).je_id
    assert len(vorher) == 1, "Grundlinie ohne Ausschluss fehlt"
    tid = next(iter(vorher))

    _repo(tmp_path, ["allnet flat l "])
    netz = _netz()
    _, bilanz = sammle(root, {}, jetzt=JETZT, hole=netz)
    assert BLATT not in netz.abgerufen
    assert bilanz["ausgeschlossen"] == 1

    satz = TarifSpeicher(pfad).letzter(tid)
    assert satz["zurueckgezogen_am"] == "2026-09-28"
    assert ist_zurueckgezogen(satz)
    # Die Zeitreihe bleibt: kein Satz geloescht, nur markiert.
    assert len(pfad.read_text(encoding="utf-8").strip().splitlines()) == 1
    # Beide Leser lassen ihn aus.
    assert Tarifbestand.aus_datei(pfad).je_id == {}
    assert Tarifbestand.aus_datei(pfad).je_id_aktuell == {}
    assert lade_staende(pfad) == []


def test_wieder_gelesenes_blatt_ist_wieder_aktuell(tmp_path):
    root = _repo(tmp_path, [])
    sammle(root, {}, jetzt=JETZT, hole=_netz())
    _repo(tmp_path, ["allnet flat l "])
    sammle(root, {}, jetzt=JETZT, hole=_netz())
    _repo(tmp_path, [])
    sammle(root, {}, jetzt=JETZT, hole=_netz())
    pfad = root / "data" / "state" / "tarife.jsonl"
    assert len(Tarifbestand.aus_datei(pfad).je_id) == 1
    assert len(lade_staende(pfad)) == 1


def test_die_congstar_quelle_schliesst_genau_xl_und_xxl_aus():
    """Gegen die Linkbeschriftungen der congstar-Blattseite vom 28.09.2026:
    XL und XXL fallen, XS bis L bleiben."""
    from telco_radar.collect.tarif_crawler import lade_quellen

    quelle = next(q for q in lade_quellen(WURZEL) if q.anbieter == "congstar")
    texte = {
        "xs": "produktinformationsblatt congstar allnet flat xs mit gb+",
        "s": "produktinformationsblatt congstar allnet flat s flex mit gb+",
        "m": "produktinformationsblatt congstar allnet flat m mit upgrade-versprechen",
        "l": "produktinformationsblatt congstar allnet flat l flex mit "
        "upgrade-versprechen",
        "xl": "produktinformationsblatt congstar allnet flat xl mit "
        "upgrade-versprechen",
        "xl flex": "produktinformationsblatt congstar allnet flat xl flex "
        "mit upgrade-versprechen",
        "xxl": "produktinformationsblatt congstar allnet flat xxl mit "
        "upgrade-versprechen",
    }
    raus = {k for k, t in texte.items() if any(a in t for a in quelle.ausschliessen)}
    assert raus == {"xl", "xl flex", "xxl"}
    assert quelle.max_dokumente == 8


def test_json_bleibt_lesbar_mit_unendlich():
    """`inf` aus der Leiter geht nicht in einen JSON-Knoten: der Katalog
    traegt Text, keine Zahl."""
    katalog = band.baender_katalog(band.tarifleiter(_bestand(xl_gb=INF)))
    assert katalog[-1]["bereich"] == "unbegrenzt"
    json.dumps(katalog, allow_nan=False)
    assert not any(
        isinstance(v, float) and math.isinf(v) for b in katalog for v in b.values()
    )
