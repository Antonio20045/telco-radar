"""Die Dauerseite "Der deutsche Wettbewerb" - Datenaufbereitung und Seite.

Die Seite entsteht komplett beim Rendern aus dem Berichtsarchiv (kein
Pipeline-State, kein LLM). Getestet wird deshalb genau das, was dabei
schiefgehen kann und auf der Seite NICHT auffiele:

* eine Meldung steht zweimal in der Chronik, weil zwei Wochen dieselbe URL
  in zwei Schreibweisen tragen,
* eine Meldung traegt das Datum ihres letzten Abrufs statt das ihrer
  Aufnahme - dann erzaehlt die Chronik den Crawler statt den Markt,
* ein fremder Konzern landet in der Chronik ("A1 Telekom Austria" unter
  Deutsche Telekom),
* eine Aktion wird dem falschen Wettbewerber zugeschrieben, weil `group`
  ein NETZ nennt und keinen Eigentuemer,
* der Vodafone-Ratschlag aus der Analystennotiz steht auf einer Seite, die
  berichten und nicht beraten soll.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from telco_radar.report.html import render_site
from telco_radar.report.wettbewerb import build_wettbewerb_view

FOCUS = [
    {"name": "Deutsche Telekom", "aliases": ["Telekom", "T-Mobile", "Magenta"]},
    {"name": "1&1", "aliases": ["1und1", "Drillisch"]},
]


class Quelle:
    """Minimale Nachbildung einer Promo-Quelle (promo_config.PromoSource)."""

    def __init__(self, name, group, internal_reference=False):
        self.name = name
        self.group = group
        self.internal_reference = internal_reference


def _h(titel, operator="", url=None, category="Netz/Technologie", note=""):
    return {"schlagzeile": titel, "title": titel, "operator": operator,
            "url": url or f"https://example.com/{abs(hash(titel)) % 9999}",
            "category": category, "de_title": note,
            "source_domain": "example.com"}


def _woche(datum, highlights=(), competitors=()):
    return {"date": datum, "highlights": list(highlights),
            "competitors": list(competitors)}


def _profil(name, moves=(), summary="Lagebild.", themes=("5G",), error=""):
    return {"name": name, "n_items": 3, "summary": summary,
            "themes": list(themes), "moves": list(moves), "error": error}


def _move(titel, url, category="Tarif/Pricing", note=""):
    return {"title": titel, "url": url, "category": category, "note": note}


def _telekom(view):
    return next(w for w in view["wettbewerber"] if w["name"] == "Deutsche Telekom")


def _eintraege(w):
    return [e for m in w["monate"] for e in m["eintraege"]]


# ------------------------------------------------------------ Dedup / Datum
def test_dieselbe_meldung_steht_nur_einmal_in_der_chronik():
    """Feeds wechseln zwischen http/https, mit und ohne www., und haengen
    Kampagnenparameter an. Ohne Normalisierung stuende dieselbe Meldung in
    jeder Woche erneut in der Chronik."""
    view = build_wettbewerb_view([
        _woche("2026-07-20", competitors=[_profil("Deutsche Telekom", [
            _move("Telekom baut aus", "https://www.telekom.com/a?utm_source=rss")])]),
        _woche("2026-07-27", competitors=[_profil("Deutsche Telekom", [
            _move("Telekom baut aus", "http://telekom.com/a/")])]),
    ], FOCUS)

    eintraege = _eintraege(_telekom(view))
    assert len(eintraege) == 1
    # ... und zwar mit dem Datum der AUFNAHME, nicht des letzten Abrufs.
    assert eintraege[0]["datum"] == "2026-07-20"


def test_die_chronik_gruppiert_nach_monaten_neueste_zuerst():
    view = build_wettbewerb_view([
        _woche("2026-06-30", competitors=[_profil("Deutsche Telekom", [
            _move("Juni-Meldung", "https://x.de/1")])]),
        _woche("2026-07-06", competitors=[_profil("Deutsche Telekom", [
            _move("Juli-Meldung", "https://x.de/2")])]),
        _woche("2026-08-03", competitors=[_profil("Deutsche Telekom", [
            _move("August-Meldung", "https://x.de/3")])]),
    ], FOCUS)

    monate = _telekom(view)["monate"]
    assert [m["monat"] for m in monate] == ["2026-08", "2026-07", "2026-06"]
    assert [m["n"] for m in monate] == [1, 1, 1]


def test_jede_chronikzeile_traegt_ihr_eigenes_datum():
    """Bis zum 08.08.2026 stand die Tageszahl nur beim ersten Eintrag ihres
    Tages - eine Zeilenmarke, die sich nicht wiederholt. Das ging, solange
    die Chronik EINE Spalte war. Sie steht jetzt in zwei (die Seite war
    6777 px hoch), und ein Spaltenumbruch mitten in einer Tagesgruppe liesse
    oben in Spalte zwei Meldungen ohne Datum stehen. Jede Zeile traegt ihr
    Datum deshalb selbst, dafuer kurz."""
    view = build_wettbewerb_view([
        _woche("2026-08-03", competitors=[_profil("Deutsche Telekom", [
            _move("Eins", "https://x.de/1"), _move("Zwei", "https://x.de/2")])]),
        _woche("2026-08-05", competitors=[_profil("Deutsche Telekom", [
            _move("Drei", "https://x.de/3")])]),
    ], FOCUS)

    eintraege = _eintraege(_telekom(view))
    assert [e["tag"] for e in eintraege] == ["5.8.", "3.8.", "3.8."]


# ------------------------------------------------------------- Alias-Match
def test_ein_fremder_konzern_kommt_nicht_in_die_chronik():
    """Der Alias "Telekom" trifft auch "A1 Telekom Austria" und "Türk
    Telekom" - zwei Konzerne, die der Deutschen Telekom nicht gehoeren.
    Der Absender muss mit dem Namen BEGINNEN."""
    view = build_wettbewerb_view([_woche("2026-08-03", highlights=[
        _h("Eigene Meldung", operator="Telekom Deutschland"),
        _h("T-Mobile US legt zu", operator="T-Mobile US"),
        _h("Fremde Meldung", operator="A1 Telekom Austria"),
        _h("Auch fremd", operator="Türk Telekom"),
    ])], FOCUS)

    titel = {e["titel"] for e in _eintraege(_telekom(view))}
    assert titel == {"Eigene Meldung", "T-Mobile US legt zu"}


def test_ohne_absender_entscheidet_die_ueberschrift():
    """Branchenweite Meldungen tragen keinen Betreiber - `_flatten()` leert
    dort die Platzhalter des Analysten. Dann bleibt nur der Titel."""
    view = build_wettbewerb_view([_woche("2026-08-03", highlights=[
        _h("Deutsche Telekom und 1&1 einigen sich"),
        _h("Zwei Anbieter einigen sich"),
    ])], FOCUS)

    assert [e["titel"] for e in _eintraege(_telekom(view))] == \
        ["Deutsche Telekom und 1&1 einigen sich"]


def test_die_meldung_gewinnt_gegen_den_move_derselben_url():
    """Beide Quellen nennen dieselbe Meldung: die Meldung mit der deutschen
    Schlagzeile des Analysten, der Move mit der Originalueberschrift des
    Feeds. Fuer eine Leserschaft ohne Technikhintergrund ist das der
    Unterschied - also gewinnt die Meldung."""
    view = build_wettbewerb_view([_woche("2026-08-03", highlights=[
        _h("Telekom bündelt Google One in Mobilfunktarife",
           operator="Deutsche Telekom", url="https://telekom.com/g")],
        competitors=[_profil("Deutsche Telekom", [
            _move("DT bundles Google One into mobile tariffs",
                  "https://telekom.com/g")])])], FOCUS)

    eintraege = _eintraege(_telekom(view))
    assert len(eintraege) == 1
    assert eintraege[0]["titel"] == "Telekom bündelt Google One in Mobilfunktarife"
    assert eintraege[0]["herkunft"] == "meldung"


def test_doppelt_kodierte_entitaeten_werden_aufgeloest():
    """Manche Feeds liefern "1&amp;1" im Titel. Jinja escaped beim Einsetzen
    erneut - auf der Seite stuende sonst woertlich "1&amp;1"."""
    view = build_wettbewerb_view([_woche("2026-08-03", competitors=[
        _profil("1&1", [_move("Neue Serie bei 1&amp;1", "https://x.de/9")])])],
        FOCUS)

    eins = next(w for w in view["wettbewerber"] if w["name"] == "1&1")
    assert _eintraege(eins)[0]["titel"] == "Neue Serie bei 1&1"


# ------------------------------------------------------- Vodafone-Ratschlag
@pytest.mark.parametrize("note,erwartet", [
    ("Telekom bietet Google One mit Rabatt an – Vodafone muss gegenhalten.",
     "Telekom bietet Google One mit Rabatt an."),
    ("DT testet Drohnen als Basisstationen; für Vodafone entsteht Druck.",
     "DT testet Drohnen als Basisstationen."),
    ("Telekom erhöht das Aktienrückkaufprogramm um 3 Milliarden Euro.",
     "Telekom erhöht das Aktienrückkaufprogramm um 3 Milliarden Euro."),
    # Kein trennbarer Befund: lieber gar keine Einordnung als eine Empfehlung.
    ("Vodafone sollte die Preisentwicklung im Blick behalten.", ""),
])
def test_die_notiz_verliert_ihren_vodafone_ratschlag(note, erwartet):
    """Die Website berichtet, sie beraet nicht (CLAUDE.md §8). Der
    Wettbewerber-Prompt verlangt aber "the angle for Vodafone" in demselben
    Satz - satzweise streichen wuerde den Befund mitnehmen."""
    view = build_wettbewerb_view([_woche("2026-08-03", competitors=[
        _profil("Deutsche Telekom",
                [_move("Titel", "https://x.de/1", note=note)])])], FOCUS)

    assert _eintraege(_telekom(view))[0]["note"] == erwartet


# ------------------------------------------------------------ Promo-Aktionen
def test_aktionen_folgen_dem_eigentuemer_nicht_dem_netz():
    """ALDI TALK sendet ueber Telefónica ("MEDION / Telefónica-Netz") und
    Penny Mobil ueber die Telekom ("Telekom-Netz (D1)") - beide gehoeren
    diesen Konzernen NICHT. Wer das verwechselt, schreibt einem
    Wettbewerber fremde Aktionen zu."""
    quellen = [Quelle("congstar", "Deutsche Telekom"),
               Quelle("Penny Mobil", "Telekom-Netz (D1)"),
               Quelle("winSIM", "1&1 / Drillisch"),
               Quelle("Vodafone", "Vodafone", internal_reference=True)]
    angebote = [
        {"brand": "congstar", "headline": "Prepaid-Paket", "status": "aktiv",
         "url": "https://congstar.de/a", "mechanic": "wechselpraemie", "score": 67},
        {"brand": "Penny Mobil", "headline": "Fremd", "status": "aktiv",
         "url": "https://penny.de/a", "score": 90},
        {"brand": "winSIM", "headline": "Datenpaket", "status": "aktiv",
         "url": "https://winsim.de/a", "score": 50},
        {"brand": "congstar", "headline": "Abgelaufen", "status": "ausgelaufen",
         "url": "https://congstar.de/b", "score": 99},
    ]
    view = build_wettbewerb_view([_woche("2026-08-03")], FOCUS,
                                 angebote, quellen)

    telekom = _telekom(view)
    assert telekom["marken"] == ["congstar"]
    assert telekom["aktionen_n"] == 1
    assert [a["headline"] for a in telekom["aktionen"]] == ["Prepaid-Paket"]
    eins = next(w for w in view["wettbewerber"] if w["name"] == "1&1")
    assert eins["marken"] == ["winSIM"]


def test_ohne_promo_konfiguration_behauptet_die_seite_keine_leere_lage():
    """render_site() ohne cfg kennt keine Promo-Quellen. "Keine Aktion
    bestaetigt" waere dann eine Aussage ueber eine Pruefung, die nie
    stattgefunden hat."""
    ohne = build_wettbewerb_view([_woche("2026-08-03")], FOCUS)
    mit = build_wettbewerb_view([_woche("2026-08-03")], FOCUS,
                                [], [Quelle("congstar", "Deutsche Telekom")])
    assert ohne["promo_bekannt"] is False
    assert mit["promo_bekannt"] is True


# ------------------------------------------------------------ Profil / Fehler
def test_das_juengste_profil_gewinnt_und_der_themenverlauf_zeigt_die_wochen():
    view = build_wettbewerb_view([
        _woche("2026-07-27", competitors=[
            _profil("Deutsche Telekom", summary="Alt.", themes=["Router"])]),
        _woche("2026-08-03", competitors=[
            _profil("Deutsche Telekom", summary="Neu.", themes=["Glasfaser"])]),
    ], FOCUS)

    telekom = _telekom(view)
    assert telekom["summary"] == "Neu."
    assert telekom["profil_datum"] == "2026-08-03"
    assert [w["datum"] for w in telekom["themen_verlauf"]] == \
        ["2026-08-03", "2026-07-27"]


def test_ein_gescheitertes_profil_bleibt_sichtbar():
    """Ein Teilausfall darf nicht aussehen wie ein ruhiger Wettbewerber -
    dieselbe Regel wie auf der Wochenseite."""
    view = build_wettbewerb_view([_woche("2026-08-03", competitors=[
        _profil("Deutsche Telekom", summary="", themes=[],
                error="JSONDecodeError: Expecting value")])], FOCUS)

    telekom = _telekom(view)
    assert telekom["summary"] == ""
    assert telekom["fehler"].startswith("JSONDecodeError")
    assert telekom["fehler_datum"] == "2026-08-03"


def test_ohne_fokus_folgt_die_seite_den_profilen_des_letzten_laufs():
    """render_site() ohne cfg hat keine focus_competitors. Die Seite bleibt
    trotzdem gefuellt, statt leer zu laufen."""
    view = build_wettbewerb_view([_woche("2026-08-03", competitors=[
        _profil("Deutsche Telekom"), _profil("Telefónica / O2")])], [])

    assert [w["name"] for w in view["wettbewerber"]] == \
        ["Deutsche Telekom", "Telefónica / O2"]
    assert [w["anker"] for w in view["wettbewerber"]] == \
        ["deutsche-telekom", "telefonica-o2"]


# ------------------------------------------------------------- Die Seite
BERICHT = {
    "date": "2026-08-05",
    "generated_with_llm": True,
    "stats": {"new": 40},
    "briefing_md": "## Auf einen Blick\n\nText.",
    "regions": {"Europa": {"highlights": [
        {"title": "Telekom startet Tarif", "operator": "Deutsche Telekom",
         "url": "https://telekom.de/t", "category": "Tarif/Pricing",
         "relevance": 5, "summary": "Ein neuer Tarif startet.",
         "date": "2026-08-05", "source": "teltarif"},
        {"title": "Meldung ohne Bezug", "operator": "Orange",
         "url": "https://orange.fr/x", "category": "Netz/Technologie",
         "relevance": 4, "summary": "Etwas anderes.", "date": "2026-08-05",
         "source": "Fachpresse"},
    ]}},
    "competitors": [
        {"name": "Deutsche Telekom", "n_items": 5, "summary": "Lagebild.",
         "themes": ["Glasfaser"], "error": "",
         "moves": [{"title": "Telekom kauft zu", "url": "https://telekom.com/m",
                    "category": "M&A", "note": "Zukauf im Kerngeschäft."}]},
    ],
    "run": {"duration_seconds": 1, "models": {}, "phases": [], "analysts": [],
            "sources": [], "source_summary": {}},
}


def _render(tmp_path, bericht=None):
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-05.json").write_text(
        json.dumps(bericht or BERICHT, ensure_ascii=False), encoding="utf-8")
    site = tmp_path / "site"
    render_site(site, reports)
    return site


def test_die_seite_wird_gerendert_und_traegt_beide_quellen(tmp_path):
    site = _render(tmp_path)
    soup = BeautifulSoup((site / "wettbewerb.html").read_text(encoding="utf-8"),
                         "html.parser")

    assert soup.select_one("#deutsche-telekom") is not None
    titel = [e.get_text(" ", strip=True) for e in soup.select(".wb-titel")]
    assert "Telekom startet Tarif" in titel        # aus den Meldungen
    assert "Telekom kauft zu" in titel             # aus dem Profil
    assert "Meldung ohne Bezug" not in titel       # fremder Absender
    assert "Lagebild." in soup.select_one(".wb-summary").get_text(strip=True)


def test_jede_schlagzeile_der_seite_traegt_szl_und_ist_vollstaendig(tmp_path):
    """Die Wahrheitstests des Portals haengen an `szl` (CLAUDE.md §5)."""
    site = _render(tmp_path)
    soup = BeautifulSoup((site / "wettbewerb.html").read_text(encoding="utf-8"),
                         "html.parser")

    schlagzeilen = [e.get_text(" ", strip=True) for e in soup.select(".szl")]
    assert len(schlagzeilen) == len(soup.select(".wb-titel"))
    assert schlagzeilen and not any(t.endswith("…") for t in schlagzeilen)


def test_die_titelseite_verweist_statt_zu_wiederholen(tmp_path):
    """Die Detailkarten sind auf die Wettbewerbsseite umgezogen. Auf der
    Titelseite steht je Wettbewerber eine Zeile - und der Anker
    #deutschland-fokus bleibt, er ist das Ziel der alten Weiterleitung."""
    site = _render(tmp_path)
    index = (site / "index.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(index, "html.parser")

    assert soup.select_one("#deutschland-fokus") is not None
    assert not soup.select(".comp-card"), "Die Detailkarten stehen noch auf der Titelseite"
    zeilen = soup.select(".wb-kurz-zeile")
    assert len(zeilen) == 1
    assert zeilen[0].select_one("a")["href"] == "wettbewerb.html#deutsche-telekom"
    assert "Lagebild." in zeilen[0].get_text(" ", strip=True)
    # Die Chronik selbst steht NICHT ein zweites Mal auf der Titelseite.
    assert "Telekom kauft zu" not in index


def test_die_archivwoche_verweist_mit_richtigem_pfad(tmp_path):
    """reports/<datum>.html liegt eine Ebene tiefer - ein "wettbewerb.html"
    ohne Prefix waere dort ein 404."""
    site = _render(tmp_path)
    archiv = (site / "reports" / "2026-08-05.html").read_text(encoding="utf-8")
    assert 'href="../wettbewerb.html#deutsche-telekom"' in archiv


def test_der_laufende_monat_steht_offen_und_aeltere_klappen_zu(tmp_path):
    """Sonst waere die Seite nach einem Jahr unlesbar lang - und der Monat,
    um den es meistens geht, staende ganz oben in einem Meer aus Archiv."""
    zwei_monate = dict(BERICHT)
    site = tmp_path / "site"
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-05.json").write_text(json.dumps(zwei_monate),
                                             encoding="utf-8")
    alt = dict(zwei_monate, date="2026-07-06", competitors=[
        {"name": "Deutsche Telekom", "n_items": 1, "summary": "Alt.",
         "themes": [], "error": "",
         "moves": [{"title": "Alte Meldung", "url": "https://telekom.com/alt",
                    "category": "M&A", "note": ""}]}], regions={})
    (reports / "2026-07-06.json").write_text(json.dumps(alt), encoding="utf-8")
    render_site(site, reports)

    soup = BeautifulSoup((site / "wettbewerb.html").read_text(encoding="utf-8"),
                         "html.parser")
    offen = soup.select_one(".wb-chronik > .wb-monat")
    assert "August 2026" in offen.get_text(" ", strip=True)
    aelter = soup.select(".wb-chronik details.wb-aelter")
    assert len(aelter) == 1
    assert "Juli 2026" in aelter[0].summary.get_text(" ", strip=True)
    assert "Alte Meldung" in aelter[0].get_text(" ", strip=True)


def test_die_seite_steht_auch_ohne_einen_einzigen_bericht(tmp_path):
    """Bootstrap: die Navigation verweist auf die Seite, also muss sie da
    sein - mit einer Erklaerung statt einer leeren Ueberschrift."""
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    site = tmp_path / "site"
    render_site(site, reports)

    html = (site / "wettbewerb.html").read_text(encoding="utf-8")
    assert "noch kein Bericht im Archiv" in html


def test_der_alte_dateiname_zeigt_wieder_auf_die_echte_seite(tmp_path):
    site = _render(tmp_path)
    html = (site / "wettbewerber.html").read_text(encoding="utf-8")
    assert 'content="0; url=wettbewerb.html"' in html


def test_stillgelegte_quellen_erreichen_die_chronik_nicht(tmp_path):
    """`_SUPPRESSED_SOURCE_DOMAINS` gilt fuer die ganze oeffentliche Site.
    Die Moves kommen aus der Berichtsdatei und muessen denselben Filter
    passieren wie die Meldungen - sonst lebt eine entfernte Quelle in der
    Chronik weiter, und zwar fuer immer."""
    bericht = json.loads(json.dumps(BERICHT))
    bericht["competitors"][0]["moves"].append(
        {"title": "Deal bei inside digital", "category": "Tarif/Pricing",
         "url": "https://www.inside-digital.de/deals/o2-tarif", "note": ""})
    site = _render(tmp_path, bericht)

    html = (site / "wettbewerb.html").read_text(encoding="utf-8")
    assert "inside-digital" not in html
    assert "Deal bei inside digital" not in html


# ------------------------------------------------- Hoehe der Seite (Layout)
# Antonio am 08.08.2026: "mach Wettbewerb das Layout besser, sodass man nicht
# so viel runterscrollen muss." Die Seite war 6777 px hoch, allein der
# laufende Monat der Telekom 2600 davon. Die Gegenmassnahmen sind messbar,
# also werden sie gemessen - und keine davon darf eine Meldung verlieren.

def _bericht_mit_moves(n: int) -> dict:
    moves = [{"title": f"Meldung {i}", "url": f"https://telekom.com/m{i}",
              "category": "M&A", "note": f"Notiz {i}."} for i in range(n)]
    return dict(BERICHT, competitors=[
        dict(BERICHT["competitors"][0], moves=moves)])


def test_der_laufende_monat_zeigt_seinen_anfang_und_haelt_den_rest_bereit():
    view = build_wettbewerb_view(
        [_woche("2026-08-05", competitors=[_profil("Deutsche Telekom", [
            _move(f"Meldung {i}", f"https://x.de/{i}") for i in range(30)])])],
        FOCUS)
    august = _telekom(view)["monate"][0]
    assert august["n"] == 30
    assert len(august["offen"]) == 12
    assert len(august["rest"]) == 18
    # Zusammen sind es wieder alle, in derselben Reihenfolge.
    assert august["offen"] + august["rest"] == august["eintraege"]


def test_keine_meldung_geht_beim_einklappen_verloren(tmp_path):
    """Der Rest steht in einem <details>, nicht im Nichts - die Chronik
    zaehlt weiterhin, was sie zeigt."""
    site = _render(tmp_path, _bericht_mit_moves(20))
    soup = BeautifulSoup((site / "wettbewerb.html").read_text(encoding="utf-8"),
                         "html.parser")
    abschnitt = soup.select_one("section.wb")
    assert len(abschnitt.select(".wb-zeile")) == 21   # 20 Moves + die Meldung
    rest = abschnitt.select_one("details.wb-mehr-monat")
    assert rest is not None
    assert len(rest.select(".wb-zeile")) == 21 - 12


def test_der_name_traegt_den_abschnitt(tmp_path):
    """"Die Namen prominenter, zu dezent" - der Name stand als 11,5-px-
    Etikett ueber einem Abschnitt voller 16-px-Schlagzeilen."""
    site = _render(tmp_path)
    soup = BeautifulSoup((site / "wettbewerb.html").read_text(encoding="utf-8"),
                         "html.parser")
    name = soup.select_one("section.wb .wb-name")
    assert name.name == "h2"
    assert name.get_text(strip=True) == "Deutsche Telekom"
    css = (site / "style.css").read_text(encoding="utf-8")
    assert ".wb-name{" in css and "var(--serif)" in css.split(".wb-name{")[1][:200]
