"""1&1-SIM-only-Referenzen von der SIM-only-Seite (S-5, 09.09.2026).

DIE FIXTURE IST DIE ECHTE SEITE
-------------------------------
`tests/fixtures/tarife/1und1_handytarife_ohne_handy.html.gz` ist die
rohe, ungekuerzte HTTP-Antwort vom 09.09.2026 (Herkunft: URL, Status,
SHA-256 in `tests/fixtures/tarife/_herkunft.json`, abgerufen mit dem
Absender TelcoRadar/1.0) - dieselbe Disziplin wie beim Telekom-Adapter
(seit dem 11.08.2026: eine erfundene Fixture sieht einem echten Abruf
zum Verwechseln aehnlich). `1und1_details_all_net_flat_s.html.gz` ist
das verlinkte Tarifdetails-Dokument zum Tarif All-Net-Flat S.

DIE ERWARTETEN WERTE SIND GEMESSEN, NICHT GERATEN (09.09.2026):
    1&1 All-Net-Flat S       14,99 €   10 GB   3 Monate je 9,99 €
    1&1 All-Net-Flat M       14,99 €   50 GB   DAUERHAFT
    1&1 All-Net-Flat L       19,99 €  150 GB   DAUERHAFT
    1&1 Unlimited on demand S 19,99 €  10 GB   3 Monate je 14,99 €
    1&1 Unlimited on demand M 19,99 €  50 GB   DAUERHAFT
    1&1 Unlimited on demand L 24,99 € 150 GB   DAUERHAFT
    1&1 Unlimited XL         39,99 €   unbegrenzt (keine GB-Zahl)

Kein Tarif traegt eine Bindungsdauer: Weder die Seite noch das
Tarifdetails-Dokument ordnen dem Preis eine Laufzeit zu (beide nennen
die Varianten "mit"/"ohne" nur unverbunden nebeneinander).
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from telco_radar.collect.tarif_einsundeins_simonly import (
    SEITEN_URL, anschlusspreis_aus_details, kacheln, referenzen_aus_html,
    sammle)
from telco_radar.tco_model import sim_only_id

_FIX = Path(__file__).parent / "fixtures" / "tarife"
_SLUG_ANF_S = ("tariff-anf-s-mvl-bundle-anf-s-mvl-oos-group-0")
_SLUG_XL = ("tariff-anf-xxl-unlimited-xl-ovl-bundle-"
            "tariff-anf-xxl-unlimited-xl-ovl-oos-group-1")

# (Name, Monatspreis, Volumen in GB oder None, Aktionsphase oder None)
_ERWARTET = [
    ("1&1 All-Net-Flat S", 14.99, 10.0, (3, 9.99)),
    ("1&1 All-Net-Flat M", 14.99, 50.0, None),
    ("1&1 All-Net-Flat L", 19.99, 150.0, None),
    ("1&1 Unlimited on demand S", 19.99, 10.0, (3, 14.99)),
    ("1&1 Unlimited on demand M", 19.99, 50.0, None),
    ("1&1 Unlimited on demand L", 24.99, 150.0, None),
    ("1&1 Unlimited XL", 39.99, None, None),
]


def _seite() -> str:
    with gzip.open(_FIX / "1und1_handytarife_ohne_handy.html.gz", "rt",
                   encoding="utf-8") as fh:
        return fh.read()


def _details_anf_s() -> str:
    with gzip.open(_FIX / "1und1_details_all_net_flat_s.html.gz", "rt",
                   encoding="utf-8") as fh:
        return fh.read()


# ------------------------------------------------------------- die Kacheln

def test_die_echte_seite_liefert_alle_sieben_tarife():
    """Der Kern des Abnahmekriteriums 2: JEDE gelistete Auspraegung.

    Die Erwartung ist die vollstaendige Liste der Messung vom 09.09. -
    fehlt eine, war das Parsen unvollstaendig; ist die Seite leer oder
    unlesbar, liefert `kacheln` nichts und dieser Test faellt ROT
    (Abnahmekriterium 4).
    """
    kacheln_ = kacheln(_seite())
    nach_name = sorted(k["name"] for k in kacheln_)
    assert nach_name == sorted(name for name, *_ in _ERWARTET)


@pytest.mark.parametrize("name,preis,volumen,aktion", _ERWARTET)
def test_preis_volumen_und_aktionsphase_je_tarif(name, preis, volumen,
                                                 aktion):
    """Jeder Wert einzeln gegen die Messung - Sabotage am Parser (falsche
    Selektoren, geloeschte Phasen-Extraktion) faellt je Taruf auf."""
    kachel = next(k for k in kacheln(_seite()) if k["name"] == name)
    assert kachel["dauerpreis"] == preis
    assert kachel["volumen_gb"] == volumen
    assert kachel["aktion"] == aktion


def test_die_details_url_steht_nur_mit_verlinkter_adresse_daran():
    """Nur verlinkte Adressen (§ 87b UrhG): die Tarifdetails-Adresse kommt
    aus dem `data-iframe`-Attribut der Kachel und geht auf den Anbieter."""
    kachel = next(k for k in kacheln(_seite()) if k["name"] == "1&1 All-Net-Flat S")
    assert kachel["details_url"].startswith(
        "https://mobile.1und1.de/details-all-net-flat-preisliste"
        "?chosenTariff=tariff-anf-s-mvl")


def test_eine_leere_oder_unlesbare_seite_liefert_keine_kacheln():
    assert kacheln("") == []
    assert kacheln("<html><body>Wartung</body></html>") == []


# ---------------------------------------------------------- die Referenzen

def test_referenzen_treffen_die_ids_und_preise_des_bestands():
    """Abnahmekriterium 3: die neuen Saetze muessen auf DENSELBEN Schluesseln
    stehen wie die bestehenden 1&1-Referenzen, sonst waeren es neue Tarife
    und die Bündel haengen in der Luft."""
    refs = referenzen_aus_html(_seite(), abgerufen_am="2026-09-09")
    nach_name = {r.tarif_name: r for r in refs}
    for name, preis, _volumen, _aktion in _ERWARTET:
        r = nach_name[name]
        assert r.id == sim_only_id("1&1", name)
        assert r.tarif_id == f"11:{sim_only_id('1&1', name).split('--')[-1]}"
        assert r.tarif_sim_only_monatlich == preis
        assert r.anbieter == "1&1"
        assert r.quelle_url == SEITEN_URL
        assert r.quelle_art == "live_shop"


def test_die_ids_treffen_den_tarifbestand_des_repos():
    """Der Anker gegen den ECHTEN Bestand (CLAUDE.md § 6: ein Lookup, der
    ins Leere geht, ist grün und prüft nichts).

    Benennt 1&1 einen Tarif auf der SIM-only-Seite anders als im
    Tarifbestand, fällt DIESER Test rot - und genau das ist seine Aufgabe:
    die Umbenennung würde sonst die alte Referenz-ID löschen, eine neue
    anlegen (`first_seen` resettet) und Bündel am alten `tarif_id` ihren
    Massstab verlieren, ohne dass ein anderer Test etwas meldet. Der
    Join geht gegen `data/state/tarife.jsonl`, die Quelle, aus der die
    Bestandsableitung stammt.
    """
    bestand: dict[str, str] = {}
    pfad = Path(__file__).parent.parent / "data" / "state" / "tarife.jsonl"
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        satz = json.loads(zeile)
        if satz.get("anbieter") == "1&1":
            bestand[satz.get("name", "")] = satz.get("tarif_id", "")
    refs = referenzen_aus_html(_seite(), abgerufen_am="2026-09-09")
    zugeordnet = {r.tarif_name: r for r in refs if r.tarif_name in bestand}
    # Die Zaehlung NAGELT den Join fest: ohne sie faende der Test auch bei
    # null Treffern dieselbe (leere) Menge "uebereinstimmend".
    assert len(zugeordnet) == len(refs) == 7
    for name, r in zugeordnet.items():
        assert r.tarif_id == bestand[name]


def test_bindungsdauer_bleibt_leer_und_wird_nicht_geraten():
    """Weder Seite noch Tarifdetails ordnen dem Preis eine Laufzeit zu -
    das Feld bleibt `None` (Regel E1), niemals 24 aus der FAQ-Phrase."""
    refs = referenzen_aus_html(_seite(), abgerufen_am="2026-09-09")
    assert refs
    assert all(r.bindung_monate is None for r in refs)


def test_anschlusspreis_kommt_nur_aus_dem_eigenen_tarifdetails():
    """Die Gebuehr steht nicht auf der Seite, sondern im verlinkten
    Tarifdetails-Dokument - ohne dessen Text bleibt sie offen."""
    ohne = referenzen_aus_html(_seite(), abgerufen_am="2026-09-09")
    s = next(r for r in ohne if r.tarif_name == "1&1 All-Net-Flat S")
    assert s.anschlusspreis is None

    mit = referenzen_aus_html(
        _seite(), details={_SLUG_ANF_S: _details_anf_s()},
        abgerufen_am="2026-09-09")
    s = next(r for r in mit if r.tarif_name == "1&1 All-Net-Flat S")
    assert s.anschlusspreis == 19.90
    m = next(r for r in mit if r.tarif_name == "1&1 All-Net-Flat M")
    assert m.anschlusspreis is None  # dessen Details wurden nicht mitgegeben


def test_aktionsphase_ist_ein_rabatt_und_kein_preis():
    s = next(r for r in referenzen_aus_html(_seite(),
                                            abgerufen_am="2026-09-09")
             if r.tarif_name == "1&1 All-Net-Flat S")
    assert len(s.rabatte) == 1
    rabatt = s.rabatte[0]
    assert rabatt.von_monat == 1
    assert rabatt.bis_monat == 3
    assert "9,99" in rabatt.name
    assert rabatt.betrag_monatlich is None  # kein Abgleich zur Kennzahl
    # Der Referenzpreis bleibt der Dauerpreis - 24 Monate zu einem
    # 3-Monats-Aktionspreis zu rechnen waere die falsche Zahl.
    assert s.tarif_sim_only_monatlich == 14.99


def test_details_ohne_gebuehrzeile_liefert_keinen_anschlusspreis():
    text = ("<td><strong>Allgemeines</strong></td>"
            "<td>hier steht keine Gebühr</td>")
    assert anschlusspreis_aus_details(text) is None
    assert anschlusspreis_aus_details("") is None


def test_widerspruch_zwischen_kachel_und_ldjson_laesst_den_tarif_weg():
    """Das Kreuzzeug: ld+json und Kachel muessen denselben Betrag nennen.
    Weicht einer ab, ist unklar, was der Preis ohne Geraet ist - dann
    bleibt der Tarif weg statt geraten zu werden."""
    seite = _seite().replace('"price": "14.99"', '"price": "99.99"', 1)
    refs = referenzen_aus_html(seite, abgerufen_am="2026-09-09")
    namen = {r.tarif_name for r in refs}
    assert "1&1 All-Net-Flat S" not in namen
    assert "1&1 All-Net-Flat M" in namen  # unberuehrt


# ----------------------------------------------------------------- sammle

class _Attrappe:
    """Netzattrappe fuer `sammle` - robots erlauben alles."""

    def __init__(self, antworten: dict[str, tuple[int, str]]):
        self.antworten = antworten
        self.abrufe: list[str] = []

    def __call__(self, url, kopfzeilen=None, user_agent=None):
        self.abrufe.append(url)
        return self.antworten[url]


def test_sammle_holt_details_nur_fuer_verlinkte_slug_adressen():
    seite, details = _seite(), _details_anf_s()
    attrappe = _Attrappe({
        SEITEN_URL: (200, seite),
        "https://mobile.1und1.de/robots.txt": (200, ""),
        "https://www.1und1.de/robots.txt": (200, ""),
        "https://mobile.1und1.de/details-all-net-flat-preisliste"
        "?chosenTariff=tariff-anf-s-mvl&chosenNet=1u1&lightbox=true"
        "&bk=false": (200, details),
    })
    refs, protokoll = sammle(attrappe, "2026-09-09", abstand_sekunden=0)
    assert len(refs) == 7
    assert protokoll["details"] == 1
    assert protokoll["details_gescheitert"] == 6  # Messgrenze, kein Preis
    # Nur verlinkte Adressen (§ 87b): jeder Abruf ist die Seite selbst,
    # eine robots.txt oder eine Details-Adresse aus einem data-iframe
    # derselben Antwort - nichts kombiniert, nichts hochgezaehlt.
    erlaubt = {SEITEN_URL, "https://www.1und1.de/robots.txt",
               "https://mobile.1und1.de/robots.txt"} | {
        k["details_url"] for k in kacheln(seite) if k["details_url"]}
    assert set(attrappe.abrufe) <= erlaubt
    s = next(r for r in refs if r.tarif_name == "1&1 All-Net-Flat S")
    assert s.anschlusspreis == 19.90
    assert s.abgerufen_am == "2026-09-09"


def test_sammle_ohne_erlaubnis_holt_gar_nichts():
    """Robots sperrt die Seite -> kein einziger Abruf, keine Referenz -
    eine dokumentierte Messgrenze statt einer Umgehung."""
    gesperrt = _Attrappe({
        "https://www.1und1.de/robots.txt": (
            200, "User-agent: *\nDisallow: /handytarife-ohne-handy\n"),
    })
    refs, protokoll = sammle(gesperrt, "2026-09-09", abstand_sekunden=0)
    assert refs == []
    assert gesperrt.abrufe == ["https://www.1und1.de/robots.txt"]


def test_sammle_mit_http_fehler_liefert_keine_referenzen():
    kaputt = _Attrappe({
        "https://www.1und1.de/robots.txt": (200, "User-agent: *\n"),
        SEITEN_URL: (503, ""),
    })
    refs, _protokoll = sammle(kaputt, "2026-09-09", abstand_sekunden=0)
    assert refs == []


def test_sammle_wirft_nicht_wenn_der_seitenabruf_stirbt():
    """Ein Netzfehler NACH der robots-Freigabe ist eine Messgrenze, kein
    Grund, den Lauf zu verlieren (Lehre aus Lauf 31422689829: eine
    Nebenstufe darf den Erfolg des Jobs nicht kosten)."""

    def _tot(url, kopfzeilen=None, user_agent=None):
        if url.endswith("/robots.txt"):
            return (200, "User-agent: *\n")
        raise ConnectionError("Netz weg")

    refs, _protokoll = sammle(_tot, "2026-09-09", abstand_sekunden=0)
    assert refs == []
