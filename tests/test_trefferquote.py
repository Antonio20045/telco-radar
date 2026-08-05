"""Trefferquote je Quelle (scripts/quellen_trefferquote.py).

Diese Kennzahl steuert laut Auftrag den gesamten Ausbau auf 1000 Quellen -
welche Kategorie ausgebaut und welche Quelle stillgelegt wird, haengt an ihr.
Sie darf deshalb nicht bloss plausibel aussehen. Der Kern ist der NENNER: die
Quote rechnet gegen die neuen, nicht gegen die gesammelten Meldungen. Wer das
verwechselt, bestraft jeden statischen Newsroom dafuer, dass er bei jedem
Abruf dieselbe Seite ausliefert.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import quellen_trefferquote as tq  # noqa: E402


def _bericht(datum: str, quellen: list[dict], highlights: list[dict],
             briefing: str = "") -> dict:
    return {
        "date": datum,
        "briefing_md": briefing,
        "regions": {"Europa": {"highlights": highlights}},
        "run": {"sources": quellen},
    }


def _quelle(name: str, url: str, count: int, new: int | None = None,
            status: str = "ok", origin: str = "operator") -> dict:
    rec = {"name": name, "url": url, "count": count, "status": status,
           "origin": origin, "kind": "rss", "region": "europa"}
    if new is not None:
        rec["new"] = new
    return rec


def _highlight(quelle: str, url: str, relevance: int = 3,
               source_url: str = "") -> dict:
    return {"source": quelle, "url": url, "relevance": relevance,
            "source_url": source_url, "title": "Titel"}


def test_nenner_sind_die_neuen_nicht_die_gesammelten():
    """Zwei Quellen, gleich viele Treffer, sehr unterschiedlicher Leerlauf."""
    berichte = [_bericht(
        "2026-08-05",
        [_quelle("Statisch", "https://a.de/news", count=30, new=2),
         _quelle("Schnell", "https://b.de/feed", count=30, new=20)],
        [_highlight("Statisch", "https://a.de/1", source_url="https://a.de/news"),
         _highlight("Schnell", "https://b.de/1", source_url="https://b.de/feed")],
    )]
    nach_name, _, _ = tq.auswerten(berichte)
    assert nach_name["Statisch"].trefferquote == 0.5   # 1 von 2 neuen
    assert nach_name["Schnell"].trefferquote == 0.05   # 1 von 20 neuen


def test_trefferquote_ohne_neue_meldungen_ist_undefiniert():
    """Nicht 0 %: eine Quelle, die nichts Neues hatte, ist nicht schlecht."""
    berichte = [_bericht("2026-08-05",
                         [_quelle("Ruhig", "https://a.de/news", count=30, new=0)],
                         [])]
    nach_name, _, _ = tq.auswerten(berichte)
    assert nach_name["Ruhig"].trefferquote is None


def test_summiert_ueber_mehrere_laeufe():
    quellen = [_quelle("Alpha", "https://a.de/news", count=10, new=5)]
    berichte = [
        _bericht("2026-08-01", quellen,
                 [_highlight("Alpha", "https://a.de/1",
                             source_url="https://a.de/news")]),
        _bericht("2026-08-05", quellen,
                 [_highlight("Alpha", "https://a.de/2",
                             source_url="https://a.de/news")]),
    ]
    b = tq.auswerten(berichte)[0]["Alpha"]
    assert (b.laeufe, b.neu, b.bewertet) == (2, 10, 2)
    assert b.trefferquote == 0.2


def test_im_bericht_zaehlt_nur_verlinkte_meldungen():
    berichte = [_bericht(
        "2026-08-05",
        [_quelle("Alpha", "https://a.de/news", count=10, new=2)],
        [_highlight("Alpha", "https://a.de/drin"),
         _highlight("Alpha", "https://a.de/draussen")],
        briefing="Text mit Link https://a.de/drin und sonst nichts.",
    )]
    assert tq.auswerten(berichte)[0]["Alpha"].im_bericht == 1


def test_relevanzstufen_werden_getrennt_gezaehlt():
    berichte = [_bericht(
        "2026-08-05",
        [_quelle("Alpha", "https://a.de/news", count=10, new=4)],
        [_highlight("Alpha", "https://a.de/1", relevance=2),
         _highlight("Alpha", "https://a.de/2", relevance=3),
         _highlight("Alpha", "https://a.de/3", relevance=5)],
    )]
    b = tq.auswerten(berichte)[0]["Alpha"]
    assert (b.bewertet, b.rel3, b.rel4) == (3, 2, 1)


def test_kanaele_werden_getrennt_ausgewiesen():
    """Ein Betreiber mit zwei Kanaelen: der Anzeigename fasst zusammen, die
    Kanaltabelle trennt - sonst waere nicht zu sehen, welcher Zweitkanal
    ueberhaupt etwas bringt."""
    berichte = [_bericht(
        "2026-08-05",
        [_quelle("Alpha", "https://a.de/news", count=10, new=5),
         _quelle("Alpha", "https://a.de/investoren", count=10, new=5)],
        [_highlight("Alpha", "https://a.de/1", source_url="https://a.de/news"),
         _highlight("Alpha", "https://a.de/2", source_url="https://a.de/news")],
    )]
    nach_name, nach_kanal, laeufe = tq.auswerten(berichte)
    assert nach_name["Alpha"].neu == 10 and len(nach_name["Alpha"].urls) == 2
    assert nach_kanal["https://a.de/news"].bewertet == 2
    assert nach_kanal["https://a.de/investoren"].bewertet == 0
    assert laeufe == ["2026-08-05"]


def test_kanaltabelle_ueberspringt_laeufe_ohne_quellen_url():
    """Ein Zaehler aus Lauf A und ein Nenner aus Lauf B waere schlicht falsch."""
    alt = _bericht("2026-07-01",
                   [_quelle("Alpha", "https://a.de/news", count=10, new=5)],
                   [_highlight("Alpha", "https://a.de/1")])  # ohne source_url
    neu = _bericht("2026-08-05",
                   [_quelle("Alpha", "https://a.de/news", count=10, new=5)],
                   [_highlight("Alpha", "https://a.de/2",
                               source_url="https://a.de/news")])
    _, nach_kanal, laeufe = tq.auswerten([alt, neu])
    assert laeufe == ["2026-08-05"]
    assert nach_kanal["https://a.de/news"].neu == 5


def test_altbestand_liefert_den_nenner_nach(tmp_path):
    """Laeufe bis #67 kennen kein 'new' - dann kommt es aus dem Seen-Store."""
    berichte = [_bericht("2026-07-20",
                         [_quelle("Alpha", "https://a.de/news", count=30)],
                         [_highlight("Alpha", "https://a.de/1")])]
    nach_name, _, _ = tq.auswerten(berichte)
    assert nach_name["Alpha"].neu == 0

    historie = tmp_path / "seen_historie_je_quelle.json"
    historie.write_text(json.dumps([{"quelle": "Alpha", "neu_gesamt": 8}]),
                        encoding="utf-8")
    assert tq.historie_ergaenzen(nach_name, historie) == 1
    assert nach_name["Alpha"].neu == 8
    assert nach_name["Alpha"].trefferquote == 0.125


def test_altbestand_ueberschreibt_kein_laufprotokoll(tmp_path):
    """Sonst zaehlten Protokoll und Altbestand doppelt."""
    berichte = [_bericht("2026-08-05",
                         [_quelle("Alpha", "https://a.de/news", count=30, new=4)],
                         [])]
    nach_name, _, _ = tq.auswerten(berichte)
    historie = tmp_path / "seen_historie_je_quelle.json"
    historie.write_text(json.dumps([{"quelle": "Alpha", "neu_gesamt": 99}]),
                        encoding="utf-8")
    assert tq.historie_ergaenzen(nach_name, historie) == 0
    assert nach_name["Alpha"].neu == 4


def test_ausfaelle_werden_gezaehlt():
    berichte = [
        _bericht("2026-08-01", [_quelle("Alpha", "https://a.de/n", 0, 0, "fail")], []),
        _bericht("2026-08-04", [_quelle("Alpha", "https://a.de/n", 0, 0, "empty")], []),
        _bericht("2026-08-05", [_quelle("Alpha", "https://a.de/n", 5, 5, "ok")], []),
    ]
    b = tq.auswerten(berichte)[0]["Alpha"]
    assert (b.laeufe, b.laeufe_ok, b.laeufe_leer, b.laeufe_fehler) == (3, 1, 1, 1)
    assert abs(b.ausfallquote - 2 / 3) < 1e-9


def test_markdown_laeuft_durch():
    berichte = [_bericht(
        "2026-08-05",
        [_quelle("Alpha", "https://a.de/news", count=10, new=5),
         _quelle("Beta", "https://b.de/feed", count=10, new=5,
                 origin="industry_news")],
        [_highlight("Alpha", "https://a.de/1", source_url="https://a.de/news")],
    )]
    nach_name, nach_kanal, laeufe = tq.auswerten(berichte)
    text = tq.markdown(tq.tabelle(nach_name), berichte,
                       tq.tabelle(nach_kanal), laeufe)
    assert "Trefferquote" in text and "Alpha" in text and "Beta" in text
