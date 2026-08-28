"""Die Vorsortierung darf Kosten sparen - niemals Meldungen verlieren.

Jeder Test hier haelt genau eine der Sicherungen aus dem Modulkopf von
`analyze/vorsortierung.py` fest. Sie sind wichtiger als die Ersparnis: was
diese Stufe faelschlich wegwirft, sieht hinterher aus wie eine duenne
Nachrichtenwoche - dasselbe Bild, das die degenerierten 402-Laeufe vom 15. bis
27.08.2026 abgegeben haben.
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import httpx
import pytest

from telco_radar import pipeline
from telco_radar.analyze import ctm as ctm_mod
from telco_radar.analyze import vorsortierung as vs
from telco_radar.models import Item
from telco_radar.pipeline import vorsortieren, zu_merkende_meldungen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Dieselbe Rechnung wie in test_pipeline.py: ein fest verdrahtetes Fenster
# laeuft mit dem Kalender irgendwann aus, der Test meldete dann die Uhr statt
# einen Umbau (CLAUDE.md §6).
FIXTURE_LOOKBACK = (date.today() - date(2026, 7, 13)).days + 1


FOKUS = ctm_mod.CtmFokus(
    heimatmarkt=["Deutsche Telekom", "Telekom", "o2", "congstar"],
    nachbarmarkt=["Swisscom"],
    direkte_kategorien={"Tarif/Pricing"},
    direkte_stichworte=["esim", "flat", "lieferzeit", "vorbestell"],
)


def _item(titel: str, n: int = 0, summary: str = "") -> Item:
    return Item(title=titel, url=f"https://example.com/{n}-{titel[:12]}",
                source_name="Fachpresse", summary=summary)


# --------------------------------------------------- Mini-Lauf-Umgebung
# Ein echter Lauf mit echter Konfiguration, aber ohne Netz und ohne Modell -
# dieselbe Bauart wie die Ende-zu-Ende-Fixture in test_pipeline.py. Sie
# existiert, weil `run.vorsortierung` nur an einem WIRKLICH geschriebenen
# Bericht-JSON zu pruefen ist; eine Pruefung auf Teilzeichenketten im
# Quelltext von `run()` bleibt gruen, wenn das Feld verschwindet.
_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Sample Telco News</title>
  <link>https://example-telconews.com</link>
  <item>
    <title>Kalenderhinweis zur Hauptversammlung von Firma Ypsilon</title>
    <link>https://example-telconews.com/2026/07/kalenderhinweis</link>
    <pubDate>Tue, 14 Jul 2026 09:00:00 GMT</pubDate>
    <description>Die Hauptversammlung findet wie angekuendigt statt.</description>
  </item>
  <item>
    <title>Firma Ypsilon senkt Preise fuer Reisepakete deutlich</title>
    <link>https://example-telconews.com/2026/07/ypsilon-preise</link>
    <pubDate>Mon, 13 Jul 2026 14:30:00 GMT</pubDate>
    <description>Der Anbieter senkt die Preise seiner Reisepakete.</description>
  </item>
</channel></rss>
"""


@pytest.fixture()
def vorsortier_projekt(tmp_path):
    shutil.copytree(PROJECT_ROOT / "config", tmp_path / "config")
    settings = (tmp_path / "config" / "settings.yaml").read_text(encoding="utf-8")
    # Nebenstufen aus: sie brauchen Netz oder Playwright und haben mit der
    # gepruefen Zusicherung nichts zu tun.
    settings += ("\ncrawl_newsrooms: false\nauto_operator_news: false\n"
                 "focus_competitors: []\npromo_enabled: false\n"
                 "geraete_enabled: false\nuebersetzung_enabled: false\n")
    (tmp_path / "config" / "settings.yaml").write_text(settings, encoding="utf-8")
    (tmp_path / "config" / "watchlist.yaml").write_text(
        "regions:\n  europe:\n    name: \"Europa\"\n    operators: []\n",
        encoding="utf-8")
    (tmp_path / "config" / "news_sources.yaml").write_text(
        "news_sources:\n  - name: \"Sample Telco News\"\n    type: rss\n"
        "    url: \"https://example-telconews.com/feed\"\n    region: europe\n",
        encoding="utf-8")
    (tmp_path / "config" / "tech_sources.yaml").write_text(
        "themes: {}\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def fake_http(monkeypatch):
    def fake_get(url, **kwargs):
        request = httpx.Request("GET", url)
        return httpx.Response(200, content=_FEED.encode("utf-8"),
                              request=request)

    monkeypatch.setattr(httpx, "get", fake_get)


def _antwort(entscheidungen: dict[int, bool]) -> str:
    """Eine Modellantwort im vereinbarten Format."""
    return json.dumps([
        {"nr": nr, "behalten": behalten,
         "grund": "reines Boilerplate" if not behalten else "Marktmeldung"}
        for nr, behalten in entscheidungen.items()])


def _stub(monkeypatch, antwort):
    """Setzt das Modell. `antwort` bekommt die Nutzlast als Liste von Zeilen."""
    gesehen: list[list[dict]] = []

    def fake_complete(system, user, model, max_tokens):
        rows = json.loads(user.split("\n", 1)[1])
        gesehen.append(rows)
        return antwort(rows)

    monkeypatch.setattr(vs, "complete", fake_complete)
    return gesehen


# ------------------------------------------------------------ Grundverhalten

def test_verworfene_meldung_erreicht_den_analysten_nicht(monkeypatch):
    items = [_item("Vorstand beruft neuen CFO", 1),
             _item("Orange senkt Preise auf 9,99 Euro", 2)]
    _stub(monkeypatch, lambda rows: _antwort(
        {r["nr"]: "CFO" not in r["titel"] for r in rows}))

    behalten, bilanz = sortiert(items)

    assert [i.title for i in behalten] == ["Orange senkt Preise auf 9,99 Euro"]
    assert (bilanz.angeboten, bilanz.verworfen, bilanz.behalten) == (2, 1, 1)
    assert bilanz.stichprobe == [
        {"titel": "Vorstand beruft neuen CFO", "quelle": "Fachpresse",
         "grund": "reines Boilerplate"}]


def test_behaltene_meldungen_stehen_in_der_eingabereihenfolge(monkeypatch):
    """`_interleave_by_source` hat die Reihenfolge gesetzt, `max_items`
    schneidet spaeter nach ihr - die Stufe darf sie nicht umruehren."""
    items = [_item(f"Meldung {n}", n) for n in range(10)]
    _stub(monkeypatch, lambda rows: _antwort(
        {r["nr"]: r["nr"] % 3 != 0 for r in rows}))

    behalten, _ = sortiert(items)

    assert [i.title for i in behalten] == [
        f"Meldung {n}" for n in range(10) if n % 3]


def sortiert(items):
    return vs.sortiere_vor(items, model="flash", fokus=FOKUS)


# --------------------------------------------------------- (a) CTM-Durchlass

def test_heimatmarkt_meldung_umgeht_die_vorsortierung(monkeypatch):
    """Ein Modell, das ALLES verwirft, darf die Telekom-Meldung nicht
    erreichen - sie kommt gar nicht erst zur Abstimmung."""
    items = [_item("Telekom startet neuen Tarif", 1),
             _item("Analystenhaus lobt eigene Studie", 2)]
    gesehen = _stub(monkeypatch, lambda rows: _antwort(
        {r["nr"]: False for r in rows}))

    behalten, bilanz = sortiert(items)

    assert [i.title for i in behalten] == ["Telekom startet neuen Tarif"]
    assert bilanz.durchlass == 1
    assert bilanz.geprueft == 1
    # Der Nachweis, dass sie nicht nur gerettet, sondern nie vorgelegt wurde.
    vorgelegt = [r["titel"] for stapel in gesehen for r in stapel]
    assert vorgelegt == ["Analystenhaus lobt eigene Studie"]


def test_portfolio_stichwort_umgeht_die_vorsortierung(monkeypatch):
    items = [_item("Anbieter verkuerzt Lieferzeit auf zwei Tage", 1)]
    _stub(monkeypatch, lambda rows: _antwort({r["nr"]: False for r in rows}))

    behalten, bilanz = sortiert(items)

    assert len(behalten) == 1
    assert (bilanz.durchlass, bilanz.geprueft, bilanz.batches) == (1, 0, 0)


def test_stichwort_trifft_nur_am_wortanfang(monkeypatch):
    """"Inflation" enthaelt "flat". `ctm.deterministische_stufe` darf so
    suchen (dort muss vorher eine Heimatmarkt-Marke getroffen haben), hier
    steht ein ODER - ohne Wortanfang liefe die halbe Ausgabe am Modell vorbei.
    """
    durchlass = vs.CtmDurchlass(FOKUS)
    assert not durchlass.trifft(_item("Inflation drueckt die Umsaetze"))
    assert durchlass.trifft(_item("Neue Flatrate fuer 20 Euro"))
    # Nach rechts bleibt es offen: die Liste enthaelt Wortstaemme.
    assert durchlass.trifft(_item("Geraet ab heute vorbestellbar"))


def test_durchlass_liest_auch_operator_und_zusammenfassung():
    durchlass = vs.CtmDurchlass(FOKUS)
    assert durchlass.trifft(
        Item(title="Neues Angebot im Markt", url="https://x/1",
             source_name="Q", operator="congstar"))
    assert durchlass.trifft(
        _item("Neues Angebot im Markt", 1, summary="Die Telekom zieht nach."))


# ------------------------------------------------------- (b) Fehler-Durchlass

def test_gescheiterter_aufruf_reicht_den_ganzen_stapel_durch(monkeypatch):
    """Ein gescheiterter Aufruf darf nie wie "nichts gefunden" aussehen -
    dieselbe Lehre wie bei PromoExtractionError."""
    def fake_complete(system, user, model, max_tokens):
        raise RuntimeError("provider overloaded")

    monkeypatch.setattr(vs, "complete", fake_complete)
    items = [_item(f"Meldung {n}", n) for n in range(5)]

    behalten, bilanz = sortiert(items)

    assert len(behalten) == 5
    assert bilanz.verworfen == 0
    assert (bilanz.fehler_batches, bilanz.batches) == (1, 1)


def test_totes_modell_reicht_durch(monkeypatch):
    from telco_radar.analyze.llm import LLMModelUnavailable

    def fake_complete(system, user, model, max_tokens):
        raise LLMModelUnavailable("insufficient balance")

    monkeypatch.setattr(vs, "complete", fake_complete)
    behalten, bilanz = sortiert([_item("Irgendetwas", 1)])

    assert len(behalten) == 1
    assert bilanz.fehler_batches == 1


def test_unparsebare_antwort_reicht_durch(monkeypatch):
    _stub(monkeypatch, lambda rows: "Ich habe darueber nachgedacht, aber ...")
    behalten, bilanz = sortiert([_item(f"Meldung {n}", n) for n in range(3)])

    assert len(behalten) == 3
    assert (bilanz.verworfen, bilanz.fehler_batches) == (0, 1)


def test_nur_der_gescheiterte_stapel_geht_ungefiltert_durch(monkeypatch):
    """Ein Ausfall kostet seinen Stapel, nicht die ganze Region."""
    def fake_complete(system, user, model, max_tokens):
        rows = json.loads(user.split("\n", 1)[1])
        if rows[0]["nr"] == 0:
            raise RuntimeError("kaputt")
        return _antwort({r["nr"]: False for r in rows})

    monkeypatch.setattr(vs, "complete", fake_complete)
    items = [_item(f"Meldung {n}", n) for n in range(vs.BATCH_SIZE * 2)]

    behalten, bilanz = sortiert(items)

    assert len(behalten) == vs.BATCH_SIZE
    assert bilanz.verworfen == vs.BATCH_SIZE
    assert (bilanz.batches, bilanz.fehler_batches) == (2, 1)


# ------------------------------------------------ (c) kein Abbruch des Scans

def test_jede_meldung_wird_entweder_geprueft_oder_durchgelassen(monkeypatch):
    """Der Deckel darf den SCAN nicht abbrechen - die Lehre aus `max_produkte`
    und aus dem Uebersetzungsdeckel."""
    items = ([_item(f"Meldung {n}", n) for n in range(120)]
             + [_item("Telekom senkt Preise", 999)])
    gesehen = _stub(monkeypatch, lambda rows: _antwort(
        {r["nr"]: True for r in rows}))

    behalten, bilanz = sortiert(items)

    assert bilanz.durchlass + bilanz.geprueft == bilanz.angeboten == 121
    assert len(behalten) + bilanz.verworfen == 121
    assert sum(len(s) for s in gesehen) == 120
    # Kein Stapel groesser als der Deckel, und keiner faellt weg.
    assert [len(s) for s in gesehen] == [vs.BATCH_SIZE, vs.BATCH_SIZE, 20]


def test_nicht_erwaehnte_meldung_bleibt(monkeypatch):
    """Im Zweifel behalten: eine Nummer, zu der das Modell nichts sagt, ist
    keine Absage."""
    items = [_item(f"Meldung {n}", n) for n in range(4)]
    _stub(monkeypatch, lambda rows: _antwort({0: False}))

    behalten, bilanz = sortiert(items)

    assert [i.title for i in behalten] == ["Meldung 1", "Meldung 2", "Meldung 3"]
    assert bilanz.verworfen == 1


@pytest.mark.parametrize("wert", [True, "true", "ja", "", None, 1, "vielleicht"])
def test_alles_ausser_einer_klaren_absage_behaelt(monkeypatch, wert):
    _stub(monkeypatch, lambda rows: json.dumps(
        [{"nr": r["nr"], "behalten": wert, "grund": "x"} for r in rows]))
    behalten, bilanz = sortiert([_item("Meldung", 1)])

    assert len(behalten) == 1 and bilanz.verworfen == 0


def test_antwort_im_umschlag_wird_gelesen(monkeypatch):
    """Ein Modell, das `{"meldungen": [...]}` liefert, hat die Aufgabe
    richtig gemacht und nur das Format verfehlt."""
    _stub(monkeypatch, lambda rows: json.dumps({"meldungen": [
        {"nr": r["nr"], "behalten": False, "grund": "Boilerplate"}
        for r in rows]}))
    behalten, bilanz = sortiert([_item("Meldung", 1)])

    assert behalten == [] and bilanz.verworfen == 1


def test_fremde_nummer_in_der_antwort_wirft_nichts_weg(monkeypatch):
    _stub(monkeypatch, lambda rows: json.dumps(
        [{"nr": 4711, "behalten": False, "grund": "erfunden"}]))
    behalten, bilanz = sortiert([_item("Meldung", 1)])

    assert len(behalten) == 1 and bilanz.verworfen == 0


# ---------------------------------------------------------------- Schalter

def test_schalter_ist_vorgabemaessig_an_und_abschaltbar():
    assert vs.ist_eingeschaltet({}) is True
    assert vs.ist_eingeschaltet({"vorsortierung_enabled": False}) is False


def test_abgeschaltet_geht_alles_unveraendert_durch(monkeypatch):
    def fake_complete(system, user, model, max_tokens):  # pragma: no cover
        raise AssertionError("die abgeschaltete Stufe darf nicht rufen")

    monkeypatch.setattr(vs, "complete", fake_complete)
    items = [_item(f"Meldung {n}", n) for n in range(3)]
    behalten, bilanz = vs.sortiere_vor(items, model="flash", fokus=FOKUS,
                                       use_llm=False)

    assert behalten == items
    assert (bilanz.verworfen, bilanz.batches, bilanz.behalten) == (0, 0, 3)


def test_die_echte_konfiguration_hat_den_schalter():
    """Ohne Zeile in settings.yaml waere der Schalter eine Behauptung im
    Code - abgeschaltet wird er von Hand, in einer Datei, die jemand findet."""
    import yaml
    from pathlib import Path

    pfad = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8"))
    assert daten["vorsortierung_enabled"] is True


# ------------------------------------------------------ ueber alle Bereiche

def test_bereiche_werden_getrennt_sortiert_und_die_bilanz_summiert(monkeypatch):
    _stub(monkeypatch, lambda rows: _antwort(
        {r["nr"]: "Boilerplate" not in r["titel"] for r in rows}))
    bereiche = {
        "europe": [_item("Boilerplate Personalie", 1), _item("Preis faellt", 2)],
        "thema:chips": [_item("Boilerplate Messeauftritt", 3)],
    }

    ergebnis, bilanz = vs.sortiere_regionen_vor(
        bereiche, model="flash", fokus=FOKUS)

    assert [i.title for i in ergebnis["europe"]] == ["Preis faellt"]
    # Ein Bereich, aus dem nichts uebrig bleibt, faellt aus der Abbildung -
    # sonst stuende er mit leerer Ueberschrift im Bericht.
    assert "thema:chips" not in ergebnis
    assert (bilanz.angeboten, bilanz.verworfen, bilanz.batches) == (3, 2, 2)


def test_bereiche_laufen_auch_nebenlaeufig_vollstaendig(monkeypatch):
    _stub(monkeypatch, lambda rows: _antwort({r["nr"]: True for r in rows}))
    bereiche = {f"r{n}": [_item(f"Meldung {n}", n)] for n in range(6)}

    ergebnis, bilanz = vs.sortiere_regionen_vor(
        bereiche, model="flash", fokus=FOKUS, workers=4)

    assert set(ergebnis) == set(bereiche)
    assert bilanz.angeboten == 6 and bilanz.batches == 6


# ---------------------------------------------------------- (c) Seen-Store

def test_aussortierte_meldung_gilt_als_gelesen(monkeypatch):
    """Der Unterschied zum `_ungelesen`-Mechanismus, und er ist der Grund,
    warum diese Stufe ueberhaupt spart: was hier faellt, wurde bewusst
    verworfen und kommt nicht im naechsten Lauf wieder. Gegengeprueft wird im
    selben Test der andere Fall - eine Meldung aus einem gescheiterten
    Analysten-Stapel bleibt aussen vor.
    """
    alle = [_item("Vorstand beruft neuen CFO", 1),
            _item("Orange senkt Preise", 2),
            _item("Meldung aus totem Stapel", 3)]
    _stub(monkeypatch, lambda rows: _antwort(
        {r["nr"]: "CFO" not in r["titel"] for r in rows}))

    behalten, bilanz = vs.sortiere_regionen_vor(
        {"europe": alle}, model="flash", fokus=FOKUS)
    assert bilanz.verworfen == 1

    # Genau die Verkettung aus pipeline.py: die Vorsortierung meldet NICHTS
    # als ungelesen, der gescheiterte Analysten-Stapel schon.
    ungelesen = {alle[2].id}
    zu_merken = zu_merkende_meldungen(
        alle, {i.id: i for i in alle}, ungelesen, set())

    assert {i.title for i in zu_merken} == {"Vorstand beruft neuen CFO",
                                            "Orange senkt Preise"}
    # Der Aussortierte steht im Store und NICHT mehr vor dem Analysten.
    assert [i.title for i in behalten["europe"]] == ["Orange senkt Preise",
                                                     "Meldung aus totem Stapel"]


# ------------------------------------------------ Einbau in den Lauf

def _spion(monkeypatch):
    """Ersetzt die Stufe durch eine Attrappe, die ihre Aufrufe aufschreibt."""
    aufrufe: list[dict] = []

    def fake(items_by_region, *, model, fokus, workers=1, deadline=None):
        aufrufe.append({"bereiche": dict(items_by_region), "model": model,
                        "workers": workers, "deadline": deadline})
        gekuerzt = {k: v[:1] for k, v in items_by_region.items()}
        return gekuerzt, vs.Bilanz(angeboten=sum(len(v) for v
                                                 in items_by_region.values()),
                                   verworfen=1, batches=1)

    monkeypatch.setattr(vs, "sortiere_regionen_vor", fake)
    return aufrufe


def test_der_lauf_sortiert_vor_und_reicht_das_mechanik_modell_durch(monkeypatch, tmp_path):
    aufrufe = _spion(monkeypatch)
    bereiche = {"europe": [_item("A", 1), _item("B", 2)]}

    gefiltert, bilanz = vorsortieren(
        bereiche, settings={"llm_max_workers": 3}, root=tmp_path,
        model="deepseek-v4-flash", use_llm=True)

    assert [i.title for i in gefiltert["europe"]] == ["A"]
    assert aufrufe[0]["model"] == "deepseek-v4-flash"
    assert aufrufe[0]["workers"] == 3
    assert bilanz["verworfen"] == 1 and bilanz["behalten"] == 1


def test_abgeschalteter_schalter_laesst_den_lauf_unveraendert(monkeypatch, tmp_path):
    aufrufe = _spion(monkeypatch)
    bereiche = {"europe": [_item("A", 1), _item("B", 2)]}

    gefiltert, bilanz = vorsortieren(
        bereiche, settings={"vorsortierung_enabled": False}, root=tmp_path,
        model="flash", use_llm=True)

    assert gefiltert == bereiche and bilanz == {}
    assert aufrufe == []


def test_ohne_modell_wird_nicht_vorsortiert(monkeypatch, tmp_path):
    aufrufe = _spion(monkeypatch)
    bereiche = {"europe": [_item("A", 1)]}

    gefiltert, bilanz = vorsortieren(bereiche, settings={}, root=tmp_path,
                                     model="flash", use_llm=False)

    assert gefiltert == bereiche and bilanz == {} and aufrufe == []


def test_der_lauf_reicht_den_echten_fokus_durch(tmp_path, monkeypatch):
    """Der CTM-Durchlass haengt an config/ctm_fokus.yaml - laedt der Lauf sie
    nicht, umgeht keine einzige Heimatmarkt-Meldung die Stufe."""
    aufrufe = _spion(monkeypatch)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "ctm_fokus.yaml").write_text(
        "heimatmarkt_marken: [Telekom]\ndirekte_stichworte: [esim]\n",
        encoding="utf-8")

    vorsortieren({"europe": [_item("A", 1)]}, settings={}, root=tmp_path,
                 model="flash", use_llm=True)

    assert aufrufe[0]["bereiche"]["europe"][0].title == "A"


# ------------------------------------------------- Frist und Fehlerschutz

def test_ein_fehler_der_stufe_kostet_keine_einzige_meldung(monkeypatch, tmp_path):
    """Die gefaehrlichste Stufe des Laufs ist die, die MELDUNGEN ENTFERNT -
    und sie steht vor dem Analysten. Faellt sie aus, muessen alle Meldungen
    unveraendert beim Analysten ankommen; ein Ausfall darf teuer sein, nie
    verlustreich. Gegen den alten Stand faellt dieser Test: dort riss die
    Ausnahme bis in `run()` durch und kostete den ganzen Lauf."""
    def platzt(*a, **k):
        raise RuntimeError("Anbieter antwortet nicht")

    monkeypatch.setattr(vs, "sortiere_regionen_vor", platzt)
    bereiche = {"europe": [_item("A", 1), _item("B", 2)],
                "asien": [_item("C", 3)]}

    gefiltert, bilanz = vorsortieren(bereiche, settings={}, root=tmp_path,
                                     model="flash", use_llm=True)

    assert {k: [i.title for i in v] for k, v in gefiltert.items()} == \
        {"europe": ["A", "B"], "asien": ["C"]}
    assert bilanz == {}


def test_bei_knapper_restzeit_wird_gar_nicht_erst_vorsortiert(monkeypatch, tmp_path):
    """Dieselbe Rechnung wie `geraete_budget()`: gegen die RESTZEIT DES JOBS,
    nicht gegen das eigene Budget. Die Stufe spart Geld, keine Zeit - ein
    halber Durchlauf spart einen halben Anteil, waehrend der Analyst dahinter
    auf seine Minuten wartet."""
    aufrufe = _spion(monkeypatch)
    bereiche = {"europe": [_item("A", 1), _item("B", 2)]}
    settings = {"job_frist_sekunden": 3000,
                "veroeffentlichung_reserve_sekunden": 420}

    gefiltert, bilanz = vorsortieren(bereiche, settings=settings, root=tmp_path,
                                     model="flash", use_llm=True,
                                     verstrichen=2550)

    assert gefiltert == bereiche and bilanz == {} and aufrufe == []
    # Gegenprobe: mit Luft laeuft sie ganz normal, und die Frist geht mit.
    gefiltert, bilanz = vorsortieren(bereiche, settings=settings, root=tmp_path,
                                     model="flash", use_llm=True,
                                     verstrichen=100)
    assert bilanz and aufrufe and aufrufe[0]["deadline"] is not None


def test_das_budget_rechnet_gegen_die_restzeit_des_jobs():
    from telco_radar.pipeline import vorsortierung_budget

    settings = {"job_frist_sekunden": 3000,
                "veroeffentlichung_reserve_sekunden": 420,
                "vorsortierung_frist_sekunden": 480}
    # Viel Luft: die eigene Obergrenze gewinnt.
    assert vorsortierung_budget(settings, 100) == 480
    # Wenig Luft: die Restzeit gewinnt.
    assert vorsortierung_budget(settings, 2300) == 280
    # Zu wenig: gar nicht anfangen.
    assert vorsortierung_budget(settings, 2560) is None
    # Abgeschaltet bleibt abgeschaltet.
    assert vorsortierung_budget(dict(settings, vorsortierung_enabled=False), 0) is None


def test_nach_der_frist_gehen_die_restlichen_stapel_ungefiltert_durch(monkeypatch):
    """Der Frist-Durchlass: geschnitten wird NIE, gefiltert nur so lange, wie
    Zeit ist. Dieselbe Richtung wie der Fehler-Durchlass."""
    import time

    items = [_item(f"Meldung {n}", n) for n in range(vs.BATCH_SIZE * 3)]
    gesehen = _stub(monkeypatch, lambda rows: _antwort(
        {r["nr"]: False for r in rows}))

    # Eine Frist, die schon abgelaufen ist, BEVOR der erste Stapel laeuft.
    behalten, bilanz = vs.sortiere_vor(items, model="flash", fokus=FOKUS,
                                       deadline=time.monotonic() - 1)
    assert len(behalten) == len(items)
    assert gesehen == []
    assert bilanz.frist_batches == bilanz.batches == 3
    assert bilanz.verworfen == 0

    # Gegenprobe: ohne Frist verwirft dieselbe Attrappe wirklich alles -
    # sonst pruefte der Test seine eigene Fixture.
    behalten, bilanz = vs.sortiere_vor(items, model="flash", fokus=FOKUS)
    assert behalten == [] and bilanz.frist_batches == 0


# ------------------------------------------------------- Bericht-JSON

def test_die_bilanz_steht_im_bericht_json(vorsortier_projekt, fake_http, monkeypatch):
    """`run.vorsortierung` ist der Messauftrag aus dem Premortem - ohne das
    Feld ist nach dem Lauf nicht mehr zu pruefen, was gefallen ist.

    Gemessen wird am WIRKLICH geschriebenen JSON eines Laufs, nicht mehr am
    Quelltext von `run()`: eine Pruefung auf Teilzeichenketten via
    `inspect.getsource` bleibt gruen, wenn das Feld eine Ebene tiefer rutscht,
    `None` wird oder das Schreiben gar nicht mehr stattfindet.
    """
    import json

    from telco_radar.analyze import llm

    def fake_dispatch(system, user, model, max_tokens, retries):
        if "VORSORTIERUNG" in system:
            rows = json.loads(user.split("\n", 1)[1])
            # Alles, was "Kalenderhinweis" heisst, faellt - der Rest bleibt.
            return json.dumps([
                {"nr": r["nr"], "behalten": "Kalenderhinweis" not in r["titel"],
                 "grund": "Terminhinweis"} for r in rows])
        # Jede andere Stufe bekommt eine leere, aber gueltige Antwort und
        # faellt damit in ihren eigenen Regelbetrieb zurueck - sie sind alle
        # failsafe. Was dieser Test prueft, ist das Feld im Bericht-JSON.
        return "{}"

    monkeypatch.setattr(llm, "_dispatch", fake_dispatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    bericht = pipeline.run(vorsortier_projekt, use_llm=True,
                           lookback_days=FIXTURE_LOOKBACK)

    daten = json.loads(bericht.with_suffix(".json").read_text(encoding="utf-8"))
    bilanz = daten["run"]["vorsortierung"]
    assert bilanz is not None, "run.vorsortierung fehlt im geschriebenen JSON"
    assert bilanz["angeboten"] >= 1
    assert bilanz["verworfen"] == 1
    assert bilanz["stichprobe"][0]["grund"] == "Terminhinweis"
    assert "Kalenderhinweis" in bilanz["stichprobe"][0]["titel"]
