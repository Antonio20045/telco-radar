"""Wahrheitstests fuer das Ereignis-Clustering (analyze/clustering.py).

Die Faelle stammen aus der ECHTEN Ausgabe vom 07.08.2026 - jener, an der die
Doppelmeldungen aufgefallen sind. Ein Test, der sich seine Meldungen ausdenkt,
prueft die Schwellen nicht, sondern die Fantasie des Autors.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from telco_radar.analyze import clustering as C
from telco_radar.models import Item

JETZT = datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)


def _item(titel, *, url=None, operator=None, quelle="Testquelle",
          stunden=0, summary=""):
    return Item(title=titel, url=url or f"https://x.test/{abs(hash(titel))}",
                source_name=quelle, operator=operator,
                published=JETZT - timedelta(hours=stunden), summary=summary)


def _gruppen_mit_mehreren(gruppen):
    return [g for g in gruppen if g.mitglieder]


# --------------------------------------------------------------- Wortmengen

def test_zahlen_mit_einheit_werden_normalisiert():
    z = C.zahlenmenge("Indosat launches 1 GW AI infra play with $800M backing")
    assert "1gw" in z


def test_jahreszahl_ist_keine_kennzeichnende_zahl():
    assert C.zahlenmenge("Outlook 2026 for European telcos") == frozenset()


def test_nackte_kleine_zahl_ist_keine_kennzeichnende_zahl():
    """"600" und "5" stehen in jeder zweiten Ueberschrift. Ohne diese Regel
    entwerten sie SCHWELLE_MIT_ZAHL, die gerade auf Seltenheit beruht."""
    assert C.zahlenmenge("AT&T puts 600 to work for coverage") == frozenset()
    assert "34,95eur" in C.zahlenmenge("Telekom-Flat für 34,95 € im Monat")


def test_wortmenge_wirft_stoppwoerter_aus_allen_sprachen():
    worte = C.wortmenge("Digi lanza un nuevo servicio para las llamadas")
    assert "digi" in worte and "llamada" in worte
    assert "las" not in worte and "para" not in worte


# ------------------------------------------------ deterministischer Vorfilter

def test_zayo_dreifachmeldung_wird_ein_ereignis():
    """Drei Fachmedien, dieselbe Nvidia-Partnerschaft. Der klarste Fall:
    fast identische Ueberschriften."""
    items = [
        _item("Zayo teams with Nvidia to expand AI network capacity",
              quelle="Light Reading"),
        _item("Zayo teams with NVIDIA to scale network capacity for AI factories",
              quelle="Telecoms.com"),
        _item("Zayo Teams with NVIDIA to Scale Critical Network Capacity for "
              "AI Factories", quelle="The Fast Mode"),
    ]
    gruppen = C.gruppiere(items)
    assert len(gruppen) == 1
    assert gruppen[0].quellen == 3
    assert len(gruppen[0].belege()) == 2


def test_indosat_wird_ueber_die_gemeinsame_zahl_gefunden():
    """Der Fall, den NUR der Zahlen-Abgleich faengt: 17 % gemeinsame Woerter,
    aber beide Meldungen nennen "1 GW"."""
    items = [
        _item("Indosat launches 1 GW AI infra play with $800M Ooredoo backing",
              operator="Ooredoo"),
        _item("IOH makes 1GW Indonesian AI data centre play",
              operator="Indosat Ooredoo Hutchison"),
    ]
    gruppen = C.gruppiere(items)
    assert len(gruppen) == 1


def test_ohne_gemeinsamen_akteur_kein_ereignis():
    """Zwei Betreiber, dieselbe Formulierung - nie dasselbe Ereignis.

    Das ist der Fall, den die Grossschreibung allein NICHT loest: im
    Deutschen sind "Tarif" und "Datenvolumen" grossgeschrieben und saehen
    damit wie Eigennamen aus. Das Betreiberfeld entscheidet.
    """
    items = [
        _item("Vodafone startet neuen Tarif mit unbegrenztem Datenvolumen",
              operator="Vodafone"),
        _item("Orange startet neuen Tarif mit unbegrenztem Datenvolumen",
              operator="Orange"),
    ]
    assert len(C.gruppiere(items)) == 2


def test_folgeereignis_ausserhalb_des_zeitfensters_bleibt_getrennt():
    """Die wichtigste Sicherung: "Samsung stellt vor" und "Samsung startet
    den Verkauf" zwei Wochen spaeter sind ZWEI Ereignisse, auch wenn die
    Ueberschriften fast gleich lauten."""
    a = _item("Samsung Officially Launches Galaxy Z Fold8 Ultra and Flip8",
              operator="Samsung", stunden=0)
    b = _item("Samsung Officially Launches Galaxy Z Fold8 Ultra and Flip8 "
              "in Europe", operator="Samsung", stunden=14 * 24)
    assert len(C.gruppiere([a, b])) == 2


def test_haeufiger_name_verbindet_nicht():
    """Ohne die Seltenheitsrechnung verband "Networks"/"Cloud"/"Teams" im
    Testlauf ueber die Ausgabe vom 07.08.2026 146 Paare."""
    items = [_item(f"Anbieter{i} Expands Cloud Networks for Enterprise "
                   f"Customers in Region {i}") for i in range(20)]
    assert len(_gruppen_mit_mehreren(C.gruppiere(items))) == 0


def test_gruppe_nimmt_nicht_unbegrenzt_auf():
    items = [_item(f"Zayo teams with Nvidia to expand AI network capacity {i}",
                   quelle=f"Q{i}") for i in range(20)]
    for g in C.gruppiere(items):
        assert g.quellen <= C.MAX_MITGLIEDER


def test_vertreter_ist_die_erste_meldung_der_eingabe():
    """Die Pipeline sortiert vorher nach Datum absteigend - der Vertreter ist
    damit die frischeste Meldung, und ihre Belege stehen darunter."""
    a = _item("Zayo teams with Nvidia to expand AI network capacity",
              url="https://a.test/1")
    b = _item("Zayo Teams with NVIDIA to Scale Network Capacity",
              url="https://b.test/2")
    gruppen = C.gruppiere([a, b])
    assert gruppen[0].vertreter.url == "https://a.test/1"


# --------------------------------------------------------- ID und Stabilitaet

def test_id_kommt_aus_der_url_nicht_aus_dem_titel():
    """Ein aus dem Titel gehashter Schluessel ist beim naechsten Lauf ein
    anderer, sobald eine Redaktion ihre Ueberschrift nachtraeglich aendert."""
    a = C.Gruppe(vertreter=_item("Erste Fassung der Ueberschrift",
                                 url="https://x.test/artikel-7"))
    b = C.Gruppe(vertreter=_item("Nachtraeglich geaenderte Ueberschrift",
                                 url="https://www.x.test/artikel-7/?utm_source=x"))
    assert a.id == b.id


# ----------------------------------------------------------- LLM-Graubereich

def test_digi_landet_im_graubereich_und_wird_zusammengelegt():
    """Der Grenzfall des Auftragsdokuments: gleicher Akteur, gleiches Thema,
    verschiedene Formulierungen. Der Vorfilter allein legt ihn NICHT
    zusammen - das Modell entscheidet."""
    items = [
        _item("Tras Movistar, O2 y Orange, Digi estrena un filtro para "
              "identificar las llamadas spam", operator="Digi"),
        _item("Digi lanza un nuevo servicio gratis que te avisará cuando "
              "recibas una llamada de spam", operator="Digi", stunden=20),
    ]
    assert len(C.gruppiere(items)) == 2      # ohne Modell: zwei Meldungen

    gefragt = []

    def _ja(system, user, model=None, max_tokens=None):
        gefragt.append(json.loads(user))
        return '{"gleich": true}'

    import telco_radar.analyze.clustering as mod
    alt = mod.complete
    mod.complete = _ja
    try:
        gruppen = C.gruppiere(items, model="testmodell", use_llm=True)
    finally:
        mod.complete = alt
    assert len(gruppen) == 1
    assert len(gefragt) == 1
    assert "Digi" in gefragt[0]["A"]["titel"]


def test_modell_sagt_nein_und_die_meldungen_bleiben_getrennt():
    items = [
        _item("Tras Movistar, O2 y Orange, Digi estrena un filtro para "
              "identificar las llamadas spam", operator="Digi"),
        _item("Digi lanza un nuevo servicio gratis que te avisará cuando "
              "recibas una llamada de spam", operator="Digi", stunden=20),
    ]
    import telco_radar.analyze.clustering as mod
    alt = mod.complete
    mod.complete = lambda *a, **k: '{"gleich": false}'
    try:
        assert len(C.gruppiere(items, model="m", use_llm=True)) == 2
    finally:
        mod.complete = alt


def test_gescheiterter_modellaufruf_trennt_statt_zu_raten():
    items = [
        _item("Disney+ annonce étudier le lancement d’une offre gratuite",
              operator="Disney"),
        _item("Josh D’Amaro, CEO de Disney: Estamos considerando una oferta "
              "gratis para Disney+", operator="Disney", stunden=8),
    ]
    import telco_radar.analyze.clustering as mod
    alt = mod.complete

    def _kaputt(*a, **k):
        raise ValueError("leere Antwort")

    mod.complete = _kaputt
    try:
        assert len(C.gruppiere(items, model="m", use_llm=True)) == 2
    finally:
        mod.complete = alt


def test_deckel_waechst_mit_der_meldungsmenge():
    assert C._deckel(100, None) == C.MAX_LLM_PRUEFUNGEN
    assert C._deckel(2000, None) == 120
    assert C._deckel(2000, 5) == 5


# --------------------------------------------------------------- ClusterStore

def test_store_erkennt_den_nachdruck_eines_ereignisses(tmp_path):
    store = C.ClusterStore(tmp_path / "clusters.jsonl")
    g = C.Gruppe(vertreter=_item(
        "Zayo teams with Nvidia to expand AI network capacity",
        operator="Zayo"))
    store.merke([g], JETZT.date().isoformat())

    frisch = C.ClusterStore(tmp_path / "clusters.jsonl")
    assert len(frisch) == 1
    nachdruck = _item("Zayo teams with NVIDIA to expand AI network capacity",
                      operator="Zayo")
    assert frisch.zuordnen(nachdruck, JETZT) is not None


def test_store_ordnet_ausserhalb_des_zeitfensters_nicht_mehr_zu(tmp_path):
    store = C.ClusterStore(tmp_path / "clusters.jsonl")
    store.merke([C.Gruppe(vertreter=_item(
        "Zayo teams with Nvidia to expand AI network capacity",
        operator="Zayo"))], "2026-08-01")
    spaeter = _item("Zayo teams with Nvidia to expand AI network capacity",
                    operator="Zayo")
    assert store.zuordnen(spaeter, JETZT + timedelta(days=5)) is None


def test_store_ordnet_eine_andere_meldung_desselben_absenders_nicht_zu(tmp_path):
    store = C.ClusterStore(tmp_path / "clusters.jsonl")
    store.merke([C.Gruppe(vertreter=_item(
        "Zayo teams with Nvidia to expand AI network capacity",
        operator="Zayo"))], JETZT.date().isoformat())
    anders = _item("Zayo meldet Quartalszahlen mit hoeherem Umsatz",
                   operator="Zayo")
    assert store.zuordnen(anders, JETZT) is None


def test_store_zaehlt_mitglieder_ueber_laeufe_hinweg(tmp_path):
    pfad = tmp_path / "clusters.jsonl"
    v = _item("Zayo teams with Nvidia", url="https://a.test/1", operator="Zayo")
    g1 = C.Gruppe(vertreter=v, mitglieder=[_item("x", url="https://b.test/2")])
    C.ClusterStore(pfad).merke([g1], "2026-08-07")
    g2 = C.Gruppe(vertreter=v, mitglieder=[_item("y", url="https://c.test/3")])
    store = C.ClusterStore(pfad)
    store.merke([g2], "2026-08-08")
    rec = C.ClusterStore(pfad).cluster[g1.id]
    assert rec["quellenzahl"] == 3
    assert rec["erstes_datum"] == "2026-08-07"
    assert rec["letztes_datum"] == "2026-08-08"


# ------------------------------------------------------------- echte Ausgabe

# --------------------------------------------- Schutz des Seen-Stores

def test_beleg_faellt_mit_seinem_vertreter_aus_dem_seen_store():
    """Die dritte Schutzstufe. Ohne sie waeren gebuendelte Meldungen der
    teuerste Fall ueberhaupt: der Vertreter kaeme im naechsten Lauf wieder,
    seine Belege nie - und das Protokoll saehe normal aus."""
    from telco_radar.pipeline import zu_merkende_meldungen

    v = _item("Zayo teams with Nvidia", url="https://a.test/1")
    beleg = _item("Zayo Teams with NVIDIA", url="https://b.test/2")
    unbeteiligt = _item("Ganz andere Meldung", url="https://c.test/3")
    alle = [v, beleg, unbeteiligt]
    zuordnung = {v.id: v, beleg.id: v, unbeteiligt.id: unbeteiligt}

    # Der Stapel des Vertreters ist gescheitert.
    merken = zu_merkende_meldungen(alle, zuordnung, {v.id}, set())
    assert [i.url for i in merken] == ["https://c.test/3"]

    # Ohne Ausfall wird alles gemerkt - auch die Belege.
    merken = zu_merkende_meldungen(alle, zuordnung, set(), set())
    assert len(merken) == 3


def test_beleg_faellt_mit_der_region_seines_vertreters():
    """Ein Beleg kann aus einer anderen Region stammen als sein Vertreter -
    dann entscheidet die Region des VERTRETERS, denn dort wurde bewertet."""
    from telco_radar.pipeline import zu_merkende_meldungen

    v = _item("Zayo teams with Nvidia", url="https://a.test/1")
    v.region = "global"
    beleg = _item("Zayo Teams with NVIDIA", url="https://b.test/2")
    beleg.region = "europe"
    merken = zu_merkende_meldungen([v, beleg], {v.id: v, beleg.id: v},
                                   set(), {"global"})
    assert merken == []


# ------------------------------------------------------------- echte Ausgabe

@pytest.mark.parametrize("fall", [
    ("SpaceX small cell plan serves up more Musk madness",
     "Musk’s Starlink plots small cell rollout to rival US mobile operators"),
    ("Improving GPT-5.6 Sol in ChatGPT and expanding access to GPT-5.6 Luna "
     "for free users",
     "ChatGPT cambia y elimina los límites en GPT-5.6 Luna para OpenAI"),
    ("AST SpaceMobile targets beta D2D service with next BlueBird launch",
     "D2D, Ast SpaceMobile lancia altri tre satelliti BlueBird"),
])
def test_belegte_dubletten_der_ausgabe_vom_7_august(fall):
    a, b = fall
    assert len(C.gruppiere([_item(a), _item(b, stunden=5)])) == 1


# --------------------------------------------------------------------------- #
# Der Absturz aus Lauf #86
# --------------------------------------------------------------------------- #

def test_zusammenlegen_verschiebt_keine_offenen_zweifelsfaelle(monkeypatch):
    """Lauf #86 starb mit "IndexError: list index out of range".

    Die Zweifelsfaelle merkten sich ihre Zielgruppe als INDEX in `gruppen`.
    Legt die Modellstufe zwei Gruppen zusammen, entfernt sie eine mit
    `gruppen.pop(i)` - und das verschiebt jeden gespeicherten Index oberhalb
    von i um eins. Der naechste Zweifelsfall zeigte dann auf die falsche
    Gruppe, und wenn genug gepoppt war, ins Leere.

    Lokal war das unsichtbar: die Stufe laeuft nur mit Modell, und alle
    lokalen Laeufe waren `--no-llm`.
    """
    # Zwoelf Themen zu je zwei Meldungen: die Paare liegen im Graubereich,
    # die Themen untereinander sind verschieden. So bleiben die Gruppen klein
    # genug, dass MAX_MITGLIEDER die Schleife nicht vorher abwuergt.
    worte = ["alpha beta gamma delta", "epsilon zeta eta theta",
             "iota kappa lambda my", "ny xi omikron pi"]
    items = []
    for t in range(12):
        marke = f"Marke{t}"
        for k in range(2):
            items.append(Item(
                title=f"{marke} {worte[k % len(worte)]} thema{t}",
                url=f"https://x.test/{t}-{k}", source_name="q", operator=marke,
                published=JETZT - timedelta(hours=t),
                summary=f"{marke} {worte[(k + 1) % len(worte)]} thema{t}"))

    # Die Reihenfolge der Zweifelsfaelle entscheidet, ob der Fehler auftritt:
    # es muss zuerst ein FRUEHER Index aufgeloest werden, damit die spaeteren
    # danebenzeigen. Der echte Rang haengt an den Profilen, hier wird er
    # deshalb erzwungen.
    monkeypatch.setattr(C, "_grau_rang",
                        lambda a, b, w: 1000.0 - abs(hash(a.item.url)) % 1000)
    monkeypatch.setattr(C, "_frage_modell", lambda a, b, m: True)

    gruppen = C.gruppiere(items, model="m", use_llm=True,
                                   max_llm_pruefungen=500)

    # Kein Absturz - und jede Meldung ist genau einmal vertreten.
    gesehen = [g.vertreter.id for g in gruppen] + \
              [m.id for g in gruppen for m in g.mitglieder]
    assert len(gesehen) == len(set(gesehen)) == len(items)


def test_aufgeloeste_zielgruppe_nimmt_nichts_mehr_auf(monkeypatch):
    """Eine Gruppe, die selbst schon in eine andere gehaengt wurde, ist kein
    gueltiges Ziel mehr - sonst landet eine Meldung in einer Gruppe, die
    niemand zurueckgibt, und ist damit still verschwunden."""
    worte = ["alpha beta gamma delta", "epsilon zeta eta theta",
             "iota kappa lambda my"]
    items = [Item(title=f"Marke{t} {worte[k % len(worte)]} thema{t}",
                  url=f"https://x.test/{t}-{k}", source_name="q",
                  operator=f"Marke{t}",
                  published=JETZT - timedelta(hours=t),
                  summary=f"Marke{t} {worte[(k + 1) % len(worte)]} thema{t}")
             for t in range(8) for k in range(3)]
    monkeypatch.setattr(C, "_frage_modell", lambda a, b, m: True)

    gruppen = C.gruppiere(items, model="m", use_llm=True,
                                   max_llm_pruefungen=500)

    alle = [g.vertreter.id for g in gruppen] + \
           [m.id for g in gruppen for m in g.mitglieder]
    assert len(alle) == len(set(alle)) == len(items), \
        "eine Meldung ist beim Zusammenlegen verloren gegangen oder doppelt"
