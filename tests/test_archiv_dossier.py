"""Frag das Archiv.

Der Test, der den Auftrag entscheidet, ist
`test_frage_ohne_treffer_erfindet_nichts`: eine Frage, zu der es nichts im
Archiv gibt, muss zu "nichts gefunden" fuehren - nicht zu einer freundlich
formulierten Erfindung.
"""

from __future__ import annotations

import contextlib
import functools
import http.server
import json
import socket
import threading
from pathlib import Path
from urllib.parse import quote

import pytest
from bestand_pfad import BERICHTE

from telco_radar.report.archiv_dossier import (
    ArchivIndex,
    als_dict,
    frage,
    verlauf,
    zerlege,
)


def _e(titel: str, summary: str = "", **kw) -> dict:
    d = {
        "kind": "bericht",
        "title": titel,
        "summary": summary,
        "operator": kw.pop("operator", ""),
        "category": kw.pop("category", ""),
        "source_label": kw.pop("quelle", "presse"),
        "url": kw.pop("url", f"https://x.de/{abs(hash(titel)) % 10000}"),
        "date": kw.pop("date", "2026-08-01"),
    }
    d.update(kw)
    return d


ARCHIV = [
    _e(
        "Telekom hebt den Preis für MagentaMobil L an",
        "Der Grundpreis steigt von 59,95 auf 64,95 Euro.",
        operator="Deutsche Telekom",
        date="2026-07-04",
    ),
    _e(
        "o2 senkt den Preis für unbegrenzte Tarife",
        "Unlimited Max kostet künftig 10 Euro weniger im Monat.",
        operator="o2",
        date="2026-07-18",
    ),
    _e(
        "Vodafone bündelt Streaming in den Mobilfunktarif",
        "Ein Streamingdienst liegt dem Tarif bei.",
        operator="Vodafone",
        date="2026-08-01",
    ),
    _e(
        "1&1 startet Wechselbonus für Neukunden",
        "Bis zu 100 Euro Bonus bei Rufnummernmitnahme.",
        operator="1&1",
        date="2026-08-05",
    ),
    _e(
        "MTN übernimmt IHS Towers",
        "Der Funkturmbetreiber wechselt den Eigentümer.",
        operator="MTN",
        date="2026-06-02",
    ),
]


@pytest.fixture(scope="module")
def index() -> ArchivIndex:
    return ArchivIndex(ARCHIV)


# --------------------------------------------------------------------------- #
# Die Zusage des Auftrags
# --------------------------------------------------------------------------- #


def test_frage_ohne_treffer_erfindet_nichts(index):
    """DER Test dieses Moduls.

    Eine freundlich formulierte Nicht-Antwort ist schlimmer als ein
    ehrliches "dazu steht nichts im Archiv": sie kostet dieselbe Zeit und
    hinterlaesst den Eindruck, die Frage sei beantwortet.
    """
    antwort = frage(index, "Wie viele Satelliten hat Starlink über Grönland?")
    assert not antwort.gefunden
    assert antwort.belege == []
    assert "steht nichts im Archiv" in antwort.begruendung


def test_jede_fussnote_zeigt_auf_einen_echten_eintrag(index):
    """Die zweite Zusage: keine Fussnote ohne real existierendes Item."""
    antwort = frage(index, "Preis unbegrenzte Tarife")
    urls = {e["url"] for e in ARCHIV}
    titel = {e["title"] for e in ARCHIV}
    assert antwort.gefunden
    for beleg in antwort.belege:
        assert beleg.url in urls
        assert beleg.titel in titel


def test_die_aussage_ist_der_eintrag(index):
    """Extraktiv, nicht generativ: es gibt keinen Satz, den nicht schon
    jemand belegt geschrieben hat."""
    antwort = frage(index, "Wechselbonus Rufnummernmitnahme")
    quelle = {e["title"]: e["summary"] for e in ARCHIV}
    for beleg in antwort.belege:
        assert beleg.text == quelle[beleg.titel]


def test_leeres_archiv_sagt_das(index):
    antwort = frage(ArchivIndex([]), "Preis")
    assert not antwort.gefunden and "leer" in antwort.begruendung


def test_frage_ohne_begriffe(index):
    antwort = frage(index, "und die was ist")
    assert not antwort.gefunden
    assert "keine durchsuchbaren Begriffe" in antwort.begruendung


# --------------------------------------------------------------------------- #
# BM25: seltene Woerter tragen die Frage
# --------------------------------------------------------------------------- #


def test_seltener_begriff_schlaegt_haeufigen(index):
    """ "Wie hat sich der Preis unbegrenzter Tarife entwickelt" enthaelt vier
    haeufige und zwei seltene Woerter - nur die seltenen tragen die Frage."""
    antwort = frage(index, "Wie hat sich der Preis für unbegrenzte Tarife entwickelt?")
    assert antwort.belege[0].titel.startswith("o2 senkt den Preis")


def test_treffer_werden_benannt(index):
    antwort = frage(index, "Wechselbonus")
    assert "wechselbonus" in antwort.belege[0].treffer


def test_stoppwoerter_fliegen_raus():
    assert zerlege("Die Frage ist, was der Preis macht") == ["frage", "preis", "macht"]


def test_zerlege_vertraegt_leer():
    assert zerlege("") == [] and zerlege(None) == []


def test_haeufiges_wort_bekommt_kein_negatives_gewicht():
    """Ohne den +1 im Logarithmus zoege ein Wort, das in mehr als der Haelfte
    der Eintraege steht, die Treffer nach UNTEN, die es enthalten."""
    viele = [_e(f"Telekom Meldung {i}", "Telekom tut etwas") for i in range(10)]
    idx = ArchivIndex(viele + [_e("Anderes Thema", "Nichts davon")])
    antwort = frage(idx, "Telekom", mind_score=0.0)
    assert antwort.gefunden
    assert all(b.score > 0 for b in antwort.belege)


# Die folgenden vier Tests messen die RANGFOLGE, nicht die Schwelle, und
# arbeiten dafuer mit winzigen Korpora. Dort steht der Suchbegriff in jedem
# Eintrag, also ist sein IDF-Gewicht korrekterweise nahe null und der Score
# bleibt unter MIND_SCORE. Am echten Bestand (737 Eintraege) erreichen echte
# Fragen 6 bis 9 Punkte und eine Unsinnsfrage exakt 0 - die Schwelle wird
# deshalb hier ausgeschaltet und in test_mind_score_ist_wirksam sowie
# test_frage_ohne_treffer_erfindet_nichts eigens geprueft.
OHNE_SCHWELLE = 0.0


def test_lange_eintraege_werden_nicht_bevorzugt():
    kurz = _e("Wechselbonus", "Wechselbonus")
    lang = _e("Langer Eintrag", "Wechselbonus " + "Fuellwort " * 200)
    idx = ArchivIndex([kurz, lang])
    antwort = frage(idx, "Wechselbonus", mind_score=OHNE_SCHWELLE)
    assert antwort.belege[0].titel == "Wechselbonus"


# --------------------------------------------------------------------------- #
# Form der Antwort
# --------------------------------------------------------------------------- #


def test_antwort_ist_gedeckelt(index):
    viele = [_e(f"Preis Meldung {i}", "Preis Preis") for i in range(40)]
    antwort = frage(ArchivIndex(viele), "Preis", max_belege=5, mind_score=OHNE_SCHWELLE)
    assert len(antwort.belege) == 5


def test_dubletten_erscheinen_einmal():
    doppelt = [
        _e("A", "Wechselbonus", url="https://x.de/1"),
        _e("B", "Wechselbonus", url="https://x.de/1"),
    ]
    antwort = frage(ArchivIndex(doppelt), "Wechselbonus", mind_score=OHNE_SCHWELLE)
    assert len(antwort.belege) == 1


def test_bei_gleichstand_zuerst_das_juengere():
    gleich = [
        _e("Alt", "Wechselbonus", url="https://x.de/1", date="2026-01-01"),
        _e("Neu", "Wechselbonus", url="https://x.de/2", date="2026-08-01"),
    ]
    antwort = frage(ArchivIndex(gleich), "Wechselbonus", mind_score=OHNE_SCHWELLE)
    assert antwort.belege[0].titel == "Neu"


def test_verlauf_zaehlt_die_monate(index):
    antwort = frage(index, "Preis Tarif Bonus", mind_score=0.1)
    reihe = verlauf(antwort)
    assert reihe == sorted(reihe, key=lambda p: p["monat"])
    assert sum(p["anzahl"] for p in reihe) == len(antwort.belege)


def test_als_dict_ist_json_faehig(index):
    d = als_dict(frage(index, "Wechselbonus"))
    json.dumps(d)  # wirft, wenn etwas nicht serialisierbar ist
    assert d["gefunden"] is True
    assert d["belege"][0]["url"].startswith("https://")


def test_als_dict_bei_nichts_gefunden(index):
    d = als_dict(frage(index, "Quantenkryptographie auf dem Mond"))
    assert d["gefunden"] is False and d["belege"] == []
    assert d["begruendung"]


def test_mind_score_ist_wirksam(index):
    """Ohne Schwelle kaeme auf jede Frage irgendetwas zurueck."""
    streng = frage(index, "Türme", mind_score=99.0)
    assert not streng.gefunden


# --------------------------------------------------------------------------- #
# Gegen den echten Suchindex
# --------------------------------------------------------------------------- #


def test_laeuft_gegen_den_echten_bestand():
    """Nicht gegen ein Konstrukt: gegen die Meldungen der Ausgabe 2026-10-02
    im Schnappschuss `BERICHTE`."""
    berichte = sorted(BERICHTE.glob("2*.json"))
    assert berichte

    from telco_radar.report import suchindex

    bericht = json.loads(berichte[-1].read_text(encoding="utf-8"))
    eintraege = []
    regionen = bericht.get("regions") or {}
    for inhalt in regionen.values() if isinstance(regionen, dict) else regionen:
        for h in (inhalt or {}).get("highlights") or []:
            eintraege.append(suchindex.eintrag_bericht(h, bericht["date"]))
    assert eintraege

    idx = ArchivIndex(eintraege)
    # Eine Frage, zu der es nichts geben kann.
    leer = frage(idx, "Unterwasserarchäologie im Bodensee")
    assert not leer.gefunden

    # Eine Frage aus dem Bestand selbst muss sich finden.
    ein_titel = eintraege[0]["title"]
    treffer = frage(idx, ein_titel)
    assert treffer.gefunden
    assert any(b.titel == ein_titel for b in treffer.belege)


# --------------------------------------------------------------------------- #
# Python und Browser muessen dasselbe antworten
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _server(site: Path):
    """Ein lokaler Server statt file://, sonst sperrt ``fetch()`` den Suchindex."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(site)
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()


def _als_meldung(e: dict) -> dict:
    return {
        "title": e["title"],
        "summary": e["summary"],
        "operator": e["operator"],
        "url": e["url"],
        "date": e["date"],
        "category": e["category"] or "Tarif/Pricing",
        "relevance": 4,
        "source": "Beispielquelle",
    }


@pytest.fixture(scope="module")
def suchseite(tmp_path_factory, chromium):
    """Die gerenderte ``suche.html`` im echten Chromium, über einen lokalen Server."""
    from telco_radar.report.html import render_site

    wurzel = tmp_path_factory.mktemp("dossier")
    reports = wurzel / "data" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-08-05.json").write_text(
        json.dumps(
            {
                "date": "2026-08-05",
                "generated_with_llm": True,
                "stats": {"new": len(ARCHIV)},
                "briefing_md": "## Auf einen Blick\n\nText.",
                "regions": {
                    "Europa": {
                        "region_summary": "",
                        "highlights": [_als_meldung(e) for e in ARCHIV],
                    }
                },
                "competitors": [],
                "run": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    site = wurzel / "site"
    render_site(site, reports)
    with _server(site) as basis:
        seite = chromium.new_page()
        try:
            seite.goto(f"{basis}/suche.html")
            yield {"seite": seite, "basis": basis, "site": site}
        finally:
            seite.close()


def _js_frage(seite, eintraege: list[dict], text: str) -> dict:
    return seite.evaluate(
        """([items, q]) => {
            const a = TelcoFrage.frage(items, q);
            return {gefunden: a.gefunden, begruendung: a.begruendung,
                    titel: a.belege.map(b => b.item.title),
                    score: a.belege.map(b => b.score)};
        }""",
        [eintraege, text],
    )


FRAGEN = [
    "Preis Telekom",
    "Wechselbonus",
    "Türme",
    "Streaming im Tarif",
    "Preis",
    "Quantenkryptographie auf dem Mond",
    "der die das",
]


def test_js_fassung_nutzt_dieselben_konstanten(suchseite):
    """Die Browserfassung ist eine zweite Umsetzung derselben Rechnung: dieselben
    Konstanten, dieselben Belege in derselben Reihenfolge mit demselben Score,
    auch am Deckel ``MAX_BELEGE``."""
    from telco_radar.report import archiv_dossier as ad

    seite = suchseite["seite"]
    im_js = seite.evaluate(
        "[TelcoFrage.K1, TelcoFrage.B, TelcoFrage.MIND_SCORE, TelcoFrage.MAX_BELEGE]"
    )
    assert im_js == [ad.K1, ad.B, ad.MIND_SCORE, ad.MAX_BELEGE]

    viele = (
        ARCHIV
        + [
            _e(f"Telekom Preisaktion Nummer {i}", url=f"https://x.de/p{i}")
            for i in range(ad.MAX_BELEGE + 3)
        ]
        + [_e(f"Netzausbau Region {i}", url=f"https://x.de/n{i}") for i in range(40)]
    )
    for archiv in (ARCHIV, viele):
        idx = ArchivIndex(archiv)
        for text in [*FRAGEN, "Telekom Preisaktion"]:
            py = frage(idx, text)
            js = _js_frage(seite, archiv, text)
            assert js["titel"] == [b.titel for b in py.belege], text
            assert js["score"] == pytest.approx(
                [b.score for b in py.belege], abs=0.005
            ), text
    gedeckelt = _js_frage(seite, viele, "Telekom Preisaktion")
    assert len(gedeckelt["titel"]) == ad.MAX_BELEGE


ALLTAGSWORTE = (
    "ab alle allem allen aller alles also am an ander andere anderen auch auf aus"
    " bei beim bin bis bist da damit dann das dass dein deine dem den denn der des"
    " dich die dies diese dieser dieses dir doch dort du durch ein eine einem einen"
    " einer eines er es etwas euch euer für fuer gegen gewesen hab habe haben hat"
    " hatte hier hin hinter ich ihm ihn ihnen ihr ihre im in indem ins ist jede"
    " jedem jeden jeder jedes jene jetzt kann kein keine können man manche mein"
    " meine mit muss mussten nach nicht nichts noch nun nur ob oder ohne sehr sein"
    " seine selbst sich sie sind so solche soll sondern sonst über ueber um und uns"
    " unser unter viel vom von vor während war waren warum was weg weil weiter"
    " welche welcher welches wenn wer werde werden wie wieder will wir wird wo"
    " wollen wurde wurden zu zum zur zwar zwischen a an and are as at be by for"
    " from has have in is it its of on or that the this to was will with"
)


def test_js_fassung_kennt_dieselben_stoppwoerter(suchseite):
    """Beide Fassungen zerlegen jeden Text gleich: die Stoppwörter selbst und den
    Wortschatz echter Meldungen aus dem Schnappschuss."""
    from telco_radar.report import archiv_dossier as ad

    seite = suchseite["seite"]
    nur_stopp = " ".join(sorted(ad.STOPP))
    assert zerlege(nur_stopp) == []
    assert seite.evaluate("t => TelcoFrage.zerlege(t)", nur_stopp) == []

    bericht = json.loads(sorted(BERICHTE.glob("2*.json"))[-1].read_text("utf-8"))
    texte = [nur_stopp, ALLTAGSWORTE, *(f"{e['title']} {e['summary']}" for e in ARCHIV)]
    for inhalt in (bericht.get("regions") or {}).values():
        for h in (inhalt or {}).get("highlights") or []:
            texte.append(" ".join(str(h.get(k) or "") for k in ("title", "summary")))
    assert len(texte) > 20
    im_js = seite.evaluate("ts => ts.map(t => TelcoFrage.zerlege(t))", texte)
    assert im_js == [zerlege(t) for t in texte]


def test_js_fassung_sagt_dasselbe_wenn_nichts_gefunden(suchseite):
    seite = suchseite["seite"]
    faelle = [
        ([], "x"),
        (ARCHIV, "Quantenkryptographie auf dem Mond"),
        (ARCHIV, "der die das"),
    ]
    for archiv, text in faelle:
        py = frage(ArchivIndex(archiv), text)
        js = _js_frage(seite, archiv, text)
        assert not py.gefunden and js["gefunden"] is False, text
        assert js["begruendung"] == py.begruendung, text
    assert py.begruendung.startswith("Die Frage enthält keine")


def test_suchseite_hat_den_behaelter_fuer_die_antwort(suchseite, chromium):
    """Mit einer Frage in der Adresse füllt die Seite den Antwortkasten mit
    denselben Belegen, die die Python-Fassung aus dem ausgelieferten Index zieht."""
    eintraege = json.loads(
        (suchseite["site"] / "search_index.json").read_text(encoding="utf-8")
    )
    idx = ArchivIndex(eintraege)
    seite = chromium.new_page()
    try:
        for text in ("Wechselbonus Neukunden", "Quantenkryptographie auf dem Mond"):
            seite.goto(f"{suchseite['basis']}/suche.html?q={quote(text)}")
            kasten = seite.locator("#dossier-antwort")
            kasten.wait_for(state="visible")
            py = frage(idx, text)
            if py.gefunden:
                titel = kasten.locator(".fa-beleg b").all_inner_texts()
                assert titel == [b.titel for b in py.belege]
                assert "Wechselbonus" in titel[0]
            else:
                leer = kasten.locator(".fa-leer").inner_text()
                assert leer == py.begruendung
    finally:
        seite.close()
