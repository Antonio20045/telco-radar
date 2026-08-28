"""Wen die Uebersetzungsstufe ueberhaupt ansieht - und was der Analyst liest.

Diese Datei schliesst die Luecke, an der das Feature vom 13.08.2026 still
gescheitert ist. Die bestehenden Tests pruefen die FORM: liegt eine
Uebersetzung vor, erscheint der rote Link an allen drei Gewichtungen. Alle
waren gruen. Live war trotzdem kein einziger Link zu sehen, weil niemand die
AUSWAHL geprueft hat:

    Lauf vom 14.08.2026 - 944 neue Meldungen, 58 im Bericht,
    4 Uebersetzungen, davon 0 zu einer berichteten Meldung.
    ueber_deckel: 887.

Zwei getrennte Fehler, beide hier festgenagelt:

  1. Die Stufe lief auf `new_items`. Der rote Link haengt an der Karte einer
     Meldung, und eine Karte bekommt nur, was der Analyst behalten hat -
     eine Uebersetzung zu einer nicht berichteten Meldung hat keinen Ort.
  2. Der Deckel brach den SCAN ab, nicht die Arbeit. 887 Meldungen wurden
     nie angesehen, und die 40 Plaetze gingen an die Anfangsposition der
     Liste statt an die erkannt fremdsprachigen.

Dazu die dritte Zusicherung, die Antonio am 15.08.2026 verlangt hat: der
Analyst bekommt den Artikeltext, nicht nur die Ueberschrift.
"""
from __future__ import annotations

import json
from datetime import date

from telco_radar.analyze import agents
from telco_radar.models import Item
from telco_radar.uebersetzung import stufe as stufe_mod
from telco_radar.uebersetzung.store import UebersetzungsStore

from test_uebersetzung import ENGLISCH, SPANISCH, _item

# Deutscher Fliesstext ab 200 Zeichen - vorgefiltert, kein Kandidat, egal ob
# vor oder nach dem 27.08.2026.
DEUTSCH = (
    "Die Bundesnetzagentur hat mitgeteilt, dass die Vergabe der Frequenzen "
    "im kommenden Jahr stattfinden soll. Die Behoerde nannte dabei weder "
    "einen genauen Termin noch die Bedingungen, unter denen die Anbieter "
    "mitbieten duerfen. "
) * 2


def _highlight(item: Item, **kw) -> dict:
    """Ein Highlight so, wie der Analyst es zurueckgibt.

    Die `summary` ist DEUTSCH - das ist der Punkt. Der Analyst schreibt seine
    Bewertung in der Zielsprache, auch zu einem spanischen Artikel.
    """
    h = {"title": item.title, "url": item.url,
         "summary": "Der Betreiber hat nach eigenen Angaben eine neue "
                    "Tarifstruktur mit hoeherem Datenvolumen vorgestellt.",
         "relevance": 4}
    h.update(kw)
    return h


# ------------------------------------------------- Nur berichtete Meldungen
def test_nur_berichtete_meldungen_kommen_in_die_stufe():
    """Der Fehler, der das ganze Vorhaben unsichtbar gemacht hat."""
    berichtet = _item(url="https://beispiel.test/a/1", volltext=SPANISCH)
    nicht_berichtet = _item(url="https://beispiel.test/a/2", volltext=SPANISCH)
    by_url = {i.url: i for i in (berichtet, nicht_berichtet)}

    raus = stufe_mod.berichtete_items([_highlight(berichtet)], by_url)

    assert [i.url for i in raus] == [berichtet.url]
    assert nicht_berichtet not in raus, (
        "eine Meldung ohne Karte hat keinen Ort fuer den roten Link")


def test_die_zuordnung_trifft_wirklich_und_ist_nicht_bloss_leer():
    """Ein Lookup ins Leere ist gruen und prueft nichts (CLAUDE.md §6).

    Ohne diese Zeile wuerde der Test oben auch dann bestehen, wenn
    `berichtete_items` grundsaetzlich `[]` zurueckgaebe.
    """
    items = [_item(url=f"https://beispiel.test/a/{i}", volltext=SPANISCH)
             for i in range(5)]
    by_url = {i.url: i for i in items}
    highlights = [_highlight(i) for i in items]

    raus = stufe_mod.berichtete_items(highlights, by_url)

    assert len(raus) == len(highlights) == 5


def test_die_reihenfolge_folgt_dem_bericht():
    """Schneidet Deckel oder Frist, faellt die unwichtigste Meldung weg."""
    items = [_item(url=f"https://beispiel.test/a/{i}") for i in range(4)]
    by_url = {i.url: i for i in items}
    # Der Bericht sortiert nach Relevanz - die Stufe darf nicht umsortieren.
    reihenfolge = [items[2], items[0], items[3], items[1]]

    raus = stufe_mod.berichtete_items(
        [_highlight(i) for i in reihenfolge], by_url)

    assert [i.url for i in raus] == [i.url for i in reihenfolge]


def test_dieselbe_meldung_zweimal_im_bericht_wird_einmal_uebersetzt():
    """Eine Meldung steht in mehreren Ressorts - das kostet keinen zweiten
    Modellaufruf."""
    item = _item(volltext=SPANISCH)
    by_url = {item.url: item}

    raus = stufe_mod.berichtete_items(
        [_highlight(item), _highlight(item)], by_url)

    assert len(raus) == 1


def test_ein_highlight_ohne_item_faellt_weg_statt_zu_werfen():
    """Der Analyst kann eine Adresse umschreiben - das darf nichts kosten."""
    item = _item(url="https://beispiel.test/a/1")
    raus = stufe_mod.berichtete_items(
        [_highlight(item), {"url": "https://umgeschrieben.test/x"}, {}],
        {item.url: item})
    assert [i.url for i in raus] == [item.url]


def test_die_spracherkennung_bekommt_das_item_nicht_das_highlight():
    """Der eine Grund, warum die Stufe auf Items laeuft und nicht auf
    Highlights.

    Das Highlight traegt die DEUTSCHE Zusammenfassung des Analysten. Liefe
    die Vorauswahl darauf, waere jede Meldung "deutsch" und es wuerde nie
    wieder etwas uebersetzt - der Fehler waere derselbe wie vorher, nur mit
    einer anderen Begruendung im Protokoll.
    """
    item = _item(volltext=SPANISCH, title="Titulo")
    h = _highlight(item)
    [raus] = stufe_mod.berichtete_items([h], {item.url: item})

    assert raus.volltext == SPANISCH
    # Gegenprobe, dass der Fall wirklich eintritt: die deutsche Fassung des
    # Analysten ist lang genug, dass die Vorauswahl auf ihr messen WUERDE.
    from telco_radar.uebersetzung.sprache import ist_fremdsprachig
    assert not ist_fremdsprachig(h["summary"] * 3, h["title"])[0]
    assert ist_fremdsprachig(raus.volltext, raus.title)[0]


# ------------------------------------------------------------- Der Deckel
def test_der_deckel_schneidet_erst_nach_dem_scan(tmp_path, monkeypatch):
    """887 von 944 Meldungen wurden am 14.08.2026 nie angesehen.

    Der spanische Artikel steht hier ans ENDE der Liste, hinter mehr
    textlosen Meldungen als der Deckel zulaesst. Gegen den alten Stand faellt
    dieser Test: dort war die Schleife nach drei Kandidaten fertig und der
    spanische Artikel nie gesehen.
    """
    monkeypatch.setattr(stufe_mod, "uebersetze",
                        lambda *a, **k: ("Deutscher Titel", ["Ein Absatz."]))
    monkeypatch.setattr(stufe_mod, "hole_volltext",
                        lambda item, *a, **k: _feed_ergebnis(item))
    textlos = [_item(url=f"https://beispiel.test/leer/{i}") for i in range(9)]
    spanisch = _item(url="https://beispiel.test/es/1", volltext=SPANISCH)

    bilanz = stufe_mod.lauf(textlos + [spanisch], tmp_path,
                            {"uebersetzung_max_je_lauf": 3}, "modell",
                            frist_sekunden=30, heute=date(2026, 8, 15))

    assert bilanz["uebersetzt"] == 1
    gespeichert = UebersetzungsStore(
        tmp_path / "data" / "state" / "uebersetzungen.jsonl")
    assert gespeichert.get(spanisch.id) is not None, (
        "der einzige fremdsprachige Artikel darf nicht hinter textlosen "
        "Meldungen im Deckel verhungern")


def _feed_ergebnis(item):
    """`hole_volltext` ohne Netz: nimmt, was am Item steht."""
    from telco_radar.uebersetzung.volltext import VolltextErgebnis
    if item.volltext:
        return VolltextErgebnis(text=item.volltext, herkunft="feed")
    return VolltextErgebnis(grund="kein Fliesstext erkannt")


def test_sicher_fremdsprachige_stehen_vor_den_unbestimmten(tmp_path,
                                                           monkeypatch):
    """Wer erkannt fremdsprachig ist, wartet nicht hinter einem
    "vielleicht"."""
    monkeypatch.setattr(stufe_mod, "uebersetze",
                        lambda *a, **k: ("T", ["A"]))
    abgerufen = []

    def _merke(item, *a, **k):
        abgerufen.append(item.url)
        return _feed_ergebnis(item)

    monkeypatch.setattr(stufe_mod, "hole_volltext", _merke)
    textlos = [_item(url=f"https://beispiel.test/leer/{i}") for i in range(3)]
    spanisch = _item(url="https://beispiel.test/es/1", volltext=SPANISCH)

    stufe_mod.lauf(textlos + [spanisch], tmp_path, {}, "modell",
                   frist_sekunden=30, heute=date(2026, 8, 15))

    assert abgerufen[0] == spanisch.url


def test_englische_kandidaten_stehen_vor_den_unbestimmten(tmp_path,
                                                           monkeypatch):
    """Dieselbe Zusicherung wie oben, jetzt fuer Englisch (E5, 27.08.2026).

    Vor der Entscheidung war ein englischer Artikel gar kein Kandidat -
    dieser Test haette also gegen den alten Stand keinen englischen Abruf
    gesehen und waere trivial gruen gewesen. Er prueft deshalb zusaetzlich,
    dass der englische Artikel ueberhaupt abgerufen UND uebersetzt wird."""
    monkeypatch.setattr(stufe_mod, "uebersetze",
                        lambda *a, **k: ("T", ["A"]))
    abgerufen = []

    def _merke(item, *a, **k):
        abgerufen.append(item.url)
        return _feed_ergebnis(item)

    monkeypatch.setattr(stufe_mod, "hole_volltext", _merke)
    textlos = [_item(url=f"https://beispiel.test/leer/{i}") for i in range(3)]
    englisch = _item(url="https://beispiel.test/en/1", volltext=ENGLISCH)

    bilanz = stufe_mod.lauf(textlos + [englisch], tmp_path, {}, "modell",
                            frist_sekunden=30, heute=date(2026, 8, 15))

    assert abgerufen[0] == englisch.url
    assert bilanz["uebersetzt"] == 1


def test_deckel_kommt_aus_settings_und_faellt_auf_sechzig_zurueck(tmp_path,
                                                                   monkeypatch):
    """Der Deckel wuchs am 27.08.2026 mit dem Kandidatenstrom von 40 auf 60
    (settings-Schluessel `uebersetzung_max_je_lauf`). Gegen den alten Stand
    (Vorgabe 40) faellt dieser Test: die 45. bis 60. Meldung waeren dort
    ueber dem Deckel geblieben."""
    monkeypatch.setattr(stufe_mod, "uebersetze", lambda *a, **k: ("T", ["A"]))
    monkeypatch.setattr(stufe_mod, "hole_volltext",
                        lambda item, *a, **k: _feed_ergebnis(item))
    items = [_item(url=f"https://beispiel.test/es/{i}", volltext=SPANISCH)
             for i in range(50)]

    bilanz = stufe_mod.lauf(items, tmp_path / "vorgabe", {}, "modell",
                            frist_sekunden=30, heute=date(2026, 8, 15))

    assert bilanz["ueber_deckel"] == 0
    assert bilanz["uebersetzt"] == 50

    # Ein expliziter Wert aus settings gewinnt weiterhin gegen die Vorgabe.
    # Eigener Store-Pfad, sonst gelten die 50 Meldungen von oben schon als
    # "schon uebersetzt" und die Vorauswahl sieht sie nie wieder an.
    bilanz_explizit = stufe_mod.lauf(
        items, tmp_path / "explizit", {"uebersetzung_max_je_lauf": 3},
        "modell", frist_sekunden=30, heute=date(2026, 8, 15))
    assert bilanz_explizit["ueber_deckel"] == 47


def test_ueber_deckel_zaehlt_nur_was_wirklich_wegfaellt(tmp_path,
                                                        monkeypatch):
    """`ueber_deckel: 887` bei 40 bearbeiteten Meldungen war die Zahl, an der
    der Fehler zu sehen war - sie muss stimmen."""
    monkeypatch.setattr(stufe_mod, "uebersetze", lambda *a, **k: ("T", ["A"]))
    monkeypatch.setattr(stufe_mod, "hole_volltext",
                        lambda item, *a, **k: _feed_ergebnis(item))
    # Fuenf spanische, zwei deutsche. Die deutschen werden vorgefiltert und
    # stehen deshalb NICHT ueber dem Deckel. (Bis zum 27.08.2026 stand hier
    # Englisch - seit MUTTERSPRACHEN nur noch "de" enthaelt, waere ein
    # englisches Beispiel selbst sicher fremdsprachig, siehe der Test unten.)
    items = [_item(url=f"https://beispiel.test/es/{i}", volltext=SPANISCH)
             for i in range(5)]
    items += [_item(url=f"https://beispiel.test/de/{i}", volltext=DEUTSCH)
              for i in range(2)]

    bilanz = stufe_mod.lauf(items, tmp_path, {"uebersetzung_max_je_lauf": 2},
                            "modell", frist_sekunden=30,
                            heute=date(2026, 8, 15))

    assert bilanz["angeboten"] == 7
    assert bilanz["vorgefiltert"] == 2
    assert bilanz["sicher_fremd"] == 5
    assert bilanz["uebersetzt"] == 2
    assert bilanz["ueber_deckel"] == 3, (
        "gezaehlt wird, was der Deckel wegschneidet - nicht, was die "
        "Vorauswahl ohnehin verworfen hat")


def test_die_protokollzeile_nennt_die_angebotene_menge():
    """Ohne diese Zahl war im Protokoll nicht zu sehen, dass die Stufe auf
    der falschen Menge lief."""
    bilanz = stufe_mod.lauf([], "/tmp", {}, "modell", frist_sekunden=1,
                            heute=date(2026, 8, 15))
    assert "berichteten Meldungen" in stufe_mod.protokollzeile(bilanz)


# ------------------------------------------------- Was der Analyst zu sehen bekommt
def test_der_analyst_sieht_den_volltext_nicht_nur_die_ueberschrift():
    """52 der 164 crawlbaren Quellen liefern kein `summary`.

    Dort bewertete der Analyst bis zum 15.08.2026 allein aus dem Titel -
    obwohl bei jeder dritten Meldung `content:encoded` schon am Item lag.
    """
    item = _item(title="Kurzer Titel", summary="", volltext=SPANISCH)
    nutzlast = json.loads(agents._items_payload([item]))
    assert SPANISCH[:200] in nutzlast[0]["text"]


def test_der_analyst_sieht_deutlich_mehr_als_dreihundert_zeichen():
    """Die alte Kappung. Der Teaser ist im Median 206 Zeichen lang -
    `[:300]` schnitt also auch dort, wo Text war, mitten im Satz ab."""
    assert len(SPANISCH) > 300, "sonst prueft der Test die Kappung nicht"
    item = _item(volltext=SPANISCH)
    snippet = json.loads(agents._items_payload([item]))[0]["text"]
    # Vollstaendig, nicht bei 300 Zeichen abgeschnitten.
    assert snippet == SPANISCH.strip()
    assert len(snippet) > 300


def test_ein_langer_artikel_wird_auf_die_grenze_gekappt():
    """Die Grenze ist eine Eingabe-Rechnung: 15 Meldungen je Stapel."""
    lang = SPANISCH * 5
    assert len(lang) > agents.ANALYST_TEXT_ZEICHEN, (
        "die Textprobe muss laenger sein als die Grenze, sonst prueft der "
        "Test die Grenze nicht")
    item = _item(volltext=lang)
    snippet = json.loads(agents._items_payload([item]))[0]["text"]
    assert len(snippet) == agents.ANALYST_TEXT_ZEICHEN


def test_ohne_volltext_gewinnt_der_teaser():
    item = _item(summary="Ein Teaser mit Inhalt.", volltext="")
    snippet = json.loads(agents._items_payload([item]))[0]["text"]
    assert snippet == "Ein Teaser mit Inhalt."


def test_der_laengere_von_beiden_gewinnt():
    """Ein Feed kann einen langen Teaser und ein kurzes `content:encoded`
    tragen - genommen wird, was mehr hergibt."""
    item = _item(summary="X" * 400, volltext="Y" * 50)
    snippet = json.loads(agents._items_payload([item]))[0]["text"]
    assert snippet.startswith("X")


def test_ohne_jeden_text_bleibt_die_nutzlast_gueltig():
    """Der Fall, den die 52 Newsroom-Quellen liefern: nur ein Titel."""
    item = _item(title="Nur ein Titel", summary="", volltext="")
    zeile = json.loads(agents._items_payload([item]))[0]
    assert zeile["text"] == ""
    assert zeile["title"] == "Nur ein Titel"


def test_ein_stapel_bleibt_im_eingabebudget():
    """BATCH_SIZE Meldungen mal die Textgrenze - die Rechnung dahinter.

    Die Obergrenze wird GERECHNET. Als feste Zahl (45000) hing sie an
    BATCH_SIZE=15 und schlug am 27.08.2026 bei der Erhoehung auf 24 an,
    obwohl das Eingabefenster derselbe geblieben war - der Test haette eine
    Kostenmassnahme als Ueberlauf gemeldet.
    """
    items = [_item(url=f"https://beispiel.test/a/{i}", volltext="Z" * 40000)
             for i in range(agents.BATCH_SIZE)]
    nutzlast = agents._items_payload(items)
    # Je Meldung der gekappte Text plus die Metafelder.
    obergrenze = agents.BATCH_SIZE * (agents.ANALYST_TEXT_ZEICHEN + 500)
    assert len(nutzlast) < obergrenze, (
        "ein Stapel darf das Eingabefenster nicht sprengen")
    # Und absolut: ~4 Zeichen je Token, die konfigurierten Modelle tragen
    # 1M Kontext - ein Stapel muss weit darunter bleiben.
    assert len(nutzlast) < 200_000
