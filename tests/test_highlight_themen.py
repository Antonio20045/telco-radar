"""Temporaere Themenseiten: Kandidatensuche, Pflege, Alterung, Rendern.

Der Auftrag (Antonio, 08.08.2026): "Wenn zu einem Thema/Event viele
Meldungen auftreten (Beispiel: Launch des Samsung Z Fold), will ich eine
temporaere Highlight-Seite zu diesem Thema ... Wenn das Thema nicht mehr
relevant ist, soll die Seite wieder verschwinden."

Geprueft wird beides - dass etwas gefunden wird UND dass das Richtige NICHT
gefunden wird. Der zweite Teil ist der schwierigere: eine Kandidatensuche,
die jede Ausgabe zu einer einzigen Gruppe verbindet, faellt in keinem
Positivtest auf.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from bs4 import BeautifulSoup

from telco_radar.analyze import highlight_topics as ht
from telco_radar.report.html import render_site


def _meldung(url: str, titel: str, quelle: str, *, summary: str = "",
             relevance: int = 4, datum: str = "2026-08-07",
             image_w: int = 0) -> dict:
    h = {"url": url, "title": titel, "headline": titel, "operator": "",
         "source": quelle, "summary": summary or titel, "relevance": relevance,
         "date": datum}
    if image_w:
        h |= {"image": f"{url.rsplit('/', 1)[-1]}.jpg", "image_w": image_w,
              "image_h": round(image_w * 9 / 16)}
    return h


# Ein Ereignis: sechs Meldungen aus vier Quellen ueber denselben Launch.
LAUNCH = [
    _meldung("https://a.example/1", "Samsung stellt Galaxy Fold8 vor", "Quelle A",
             image_w=1200),
    _meldung("https://b.example/2", "Galaxy Fold8 kommt mit neuem Scharnier", "Quelle B",
             image_w=900),
    _meldung("https://c.example/3", "Vorbestellungen fuer Galaxy Fold8 auf Rekordhoehe",
             "Quelle C"),
    _meldung("https://d.example/4", "Operator bewirbt Galaxy Fold8 mit Inzahlungnahme",
             "Quelle D"),
    _meldung("https://a.example/5", "Preis des Galaxy Fold8 in Europa bekannt", "Quelle A"),
    _meldung("https://b.example/6", "Galaxy Fold8 startet in Korea", "Quelle B"),
]
# Rauschen: eine normale Ausgabe ohne gemeinsames Ereignis. Bewusst mit
# verschiedenen Woertern - eine Ausgabe, in der zwoelf Meldungen denselben
# Satzbau haben, pruefte den Haeufigkeitsdeckel statt der Gruppenbildung.
_RAUSCHTITEL = [
    "Regulierer versteigert Frequenzen im Sechs-Gigahertz-Band",
    "Betreiber Alpha meldet Gewinnsprung im zweiten Quartal",
    "Glasfaserausbau in Norwegen kommt schneller voran",
    "Uebernahme zweier Rechenzentren in Brasilien genehmigt",
    "Roaminggebuehren im Pazifikraum sinken erneut",
    "Behoerde untersagt Werbung mit unbelegten Netzversprechen",
    "Neuer Chipsatz halbiert Stromverbrauch von Basisstationen",
    "Streit um Einspeiseentgelte landet vor Gericht",
    "Kabelnetzbetreiber verliert Kundschaft an Funkanschluesse",
    "Notrufsystem faellt in Portugal fuer Stunden aus",
    "Reisetarif buendelt Datenpakete fuer Nordafrika",
    "Bahnstrecken bekommen durchgehende Mobilfunkabdeckung",
]
RAUSCHEN = [
    _meldung(f"https://n.example/{i}", titel, f"Quelle N{i}",
             summary=f"{titel}, berichtet die Fachpresse.")
    for i, titel in enumerate(_RAUSCHTITEL)
]


def _urteil(**kwargs) -> str:
    grund = {"i": 0, "thema": True, "gehoert_zu": None,
             "titel": "Samsung Galaxy Fold8 kommt",
             "leitsatz": "Samsung bringt sein neues Falt-Handy auf den Markt.",
             "suchwoerter": ["Samsung", "Fold8", "Galaxy"]}
    grund.update(kwargs)
    return json.dumps([grund], ensure_ascii=False)


@pytest.fixture
def agent(monkeypatch):
    """Der Themen-Agent als Attrappe - der Rest laeuft echt."""
    aufrufe: list[str] = []

    def stelle(antwort):
        # Bei jeder neuen Antwort von vorn zaehlen: sonst prueft ein Test,
        # ob der Agent NICHT gefragt wurde, gegen die Aufrufe des Laufs davor.
        aufrufe.clear()

        def fake(system, user, model, max_tokens=0, **_):
            aufrufe.append(user)
            if isinstance(antwort, Exception):
                raise antwort
            return antwort
        monkeypatch.setattr(ht, "complete", fake)
        return aufrufe

    return stelle


# ------------------------------------------------------- Kandidatensuche
def test_kandidatensuche_findet_das_ereignis():
    gruppen = ht.finde_kandidaten(LAUNCH + RAUSCHEN)
    assert len(gruppen) == 1
    gruppe = gruppen[0]
    assert {h["url"] for h in gruppe["items"]} == {h["url"] for h in LAUNCH}
    assert gruppe["quellen"] == 4
    assert "fold8" in gruppe["worte"]


def test_kandidatensuche_verbindet_nicht_die_ganze_ausgabe():
    """Der Fehler, den eine Verbindungskette macht.

    Am Bericht vom 07.08.2026 gemessen: wer zwei Meldungen als verwandt
    zaehlt, sobald sie ueber IRGENDEIN Zwischenglied zusammenhaengen, bekommt
    EINE Gruppe aus 129 der 138 Meldungen - jede Ausgabe haengt ueber
    "mobile", "network" oder "2026" mit jeder anderen zusammen. Deshalb
    Wortpaare statt Ketten: das Rauschen darf keine Gruppe bilden.
    """
    assert ht.finde_kandidaten(RAUSCHEN) == []
    gruppen = ht.finde_kandidaten(LAUNCH + RAUSCHEN)
    assert all(len(g["items"]) <= len(LAUNCH) for g in gruppen)


def test_kandidatensuche_verlangt_mehrere_quellen():
    """Fuenf Meldungen aus einer Redaktion sind kein Ereignis, sondern eine
    Redaktion, die nachlegt."""
    eine_quelle = [dict(h, source="Nur eine Quelle") for h in LAUNCH]
    assert ht.finde_kandidaten(eine_quelle + RAUSCHEN) == []


def test_kandidatensuche_verlangt_genug_meldungen():
    """Drei Meldungen sind keine Welle. Vier reichen seit dem 17.08.2026:
    der Pixel-11-Launch stand am 14.08. mit vier Highlights aus vier Quellen
    im Bericht (darunter die Prioritaet-5-Meldung der Woche) und fiel an der
    alten Schwelle 5 - der Schutz vor der einzelnen Redaktion, die nachlegt,
    liegt bei MIND_QUELLEN, nicht bei der Gruppengroesse."""
    assert ht.finde_kandidaten(LAUNCH[:3] + RAUSCHEN) == []
    vier = ht.finde_kandidaten(LAUNCH[:4] + RAUSCHEN)
    assert len(vier) == 1
    assert {h["url"] for h in vier[0]["items"]} == {h["url"] for h in LAUNCH[:4]}


# ------------------------------------------------------- Suchwortzuordnung
def test_zuordnung_verlangt_zwei_suchwoerter():
    muster = ht.suchmuster(["Samsung", "Fold8", "Galaxy"])
    assert ht.treffer("Samsung stellt Galaxy Fold8 vor", muster) == 3
    # Ein einzelner Treffer reicht nicht - sonst zieht "Samsung" jede
    # Geraetemeldung des Herstellers in den Launch.
    assert ht.treffer("Samsung meldet Quartalszahlen", muster) < ht.MIND_TREFFER
    # Wortgrenzen: "Foldables" ist nicht "Fold8", "Galaxys" schon.
    assert ht.treffer("Neue Foldables am Markt", muster) == 0
    assert ht.treffer("samsung und galaxy klein geschrieben", muster) == 2


def test_neue_meldungen_wandern_per_suchwort_ins_thema(tmp_path, agent):
    agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH + RAUSCHEN, tmp_path, "2026-08-07",
                               model="m", use_llm=True)
    nachschlag = [
        _meldung("https://e.example/9", "Galaxy Fold8 nun auch in Indien", "Quelle E"),
        _meldung("https://f.example/10", "Samsung senkt Preis des Galaxy Fold8", "Quelle F"),
        _meldung("https://g.example/11", "Ganz anderes Thema ohne Bezug", "Quelle G"),
    ]
    agent(json.dumps([]))
    ht.pflege_highlight_themen(nachschlag, tmp_path, "2026-08-11",
                               model="m", use_llm=True)

    thema = ht.lade_themen(tmp_path)[0]
    urls = {i["url"] for i in thema["items"]}
    assert "https://e.example/9" in urls and "https://f.example/10" in urls
    assert "https://g.example/11" not in urls
    assert thema["last_active"] == "2026-08-11"
    # Die Woche steht an der Meldung - ein Thema laeuft ueber mehrere Ausgaben.
    assert {i["week"] for i in thema["items"]} == {"2026-08-07", "2026-08-11"}


def test_dieselbe_meldung_kommt_nicht_zweimal_ins_thema(tmp_path, agent):
    agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-07", model="m", use_llm=True)
    agent(json.dumps([]))
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-11", model="m", use_llm=True)

    thema = ht.lade_themen(tmp_path)[0]
    urls = [i["url"] for i in thema["items"]]
    assert len(urls) == len(set(urls)) == len(LAUNCH)


# ------------------------------------------------- Archiv ueber die Laeufe
def _bericht(reports_dir, datum: str, highlights: list[dict]) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{datum}.json").write_text(json.dumps(
        {"date": datum, "regions": {"Europa": {"highlights": highlights}}},
        ensure_ascii=False), encoding="utf-8")


def test_ereignis_ueber_zwei_laeufe_wird_gefunden(tmp_path, agent):
    """Der Pixel-Befund vom 17.08.2026: ein Launch stand am 06.08. mit EINER
    und am 14.08. mit VIER Meldungen im Bericht - in keinem Lauf allein
    genug. Die Kandidatensuche liest deshalb das Berichtsarchiv mit; die
    Meldungen behalten dabei die Woche, in der sie BERICHTET wurden."""
    reports = tmp_path / "reports"
    _bericht(reports, "2026-08-07", [LAUNCH[3]])

    aufrufe = agent(_urteil())
    # Ohne Archiv: drei Meldungen des laufenden Laufs sind zu wenig.
    bilanz = ht.pflege_highlight_themen(LAUNCH[:3] + RAUSCHEN, tmp_path,
                                        "2026-08-14", model="m", use_llm=True)
    assert bilanz["kandidaten"] == 0 and not aufrufe

    aufrufe = agent(_urteil())
    bilanz = ht.pflege_highlight_themen(LAUNCH[:3] + RAUSCHEN, tmp_path,
                                        "2026-08-14", model="m", use_llm=True,
                                        reports_dir=reports)
    assert bilanz["kandidaten"] == 1 and len(aufrufe) == 1
    thema = ht.lade_themen(tmp_path)[0]
    zuordnung = {i["url"]: i["week"] for i in thema["items"]}
    assert len(zuordnung) == 4
    assert zuordnung[LAUNCH[3]["url"]] == "2026-08-07"
    assert all(zuordnung[h["url"]] == "2026-08-14" for h in LAUNCH[:3])


def test_archiv_aelter_als_das_fenster_zaehlt_nicht(tmp_path, agent):
    reports = tmp_path / "reports"
    _bericht(reports, "2026-07-20", [LAUNCH[3]])  # 25 Tage vor "heute"
    aufrufe = agent(_urteil())
    bilanz = ht.pflege_highlight_themen(LAUNCH[:3] + RAUSCHEN, tmp_path,
                                        "2026-08-14", model="m", use_llm=True,
                                        reports_dir=reports)
    assert bilanz["kandidaten"] == 0 and not aufrufe


def test_ein_reines_archiv_ereignis_wird_kein_thema(tmp_path, agent):
    """Das Archiv verstaerkt nur, was gerade Momentum hat: eine Gruppe
    braucht MIND_AKTUELL Meldungen aus dem laufenden Lauf. Eine zwei Wochen
    alte Welle, zu der diese Woche eine einzelne Meldung kommt, bekommt
    keine Seite - sie wuerde als frisches Thema sofort zu altern beginnen."""
    reports = tmp_path / "reports"
    _bericht(reports, "2026-08-07", LAUNCH[1:])
    aufrufe = agent(_urteil())
    bilanz = ht.pflege_highlight_themen([LAUNCH[0]] + RAUSCHEN, tmp_path,
                                        "2026-08-14", model="m", use_llm=True,
                                        reports_dir=reports)
    assert bilanz["kandidaten"] == 0 and not aufrufe


def test_erfasstes_ereignis_wird_dem_agenten_nicht_erneut_vorgelegt(tmp_path, agent):
    """Seit die Suche das Archiv mitliest, findet sie ein erkanntes Ereignis
    in jedem Folgelauf erneut. Der Agent wird dafuer nicht noch einmal
    gefragt - neue Meldungen erreichen das Thema ueber die Suchwoerter."""
    reports = tmp_path / "reports"
    aufrufe = agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH + RAUSCHEN, tmp_path, "2026-08-14",
                               model="m", use_llm=True, reports_dir=reports)
    assert len(ht.lade_themen(tmp_path)) == 1 and len(aufrufe) == 1

    _bericht(reports, "2026-08-14", LAUNCH)
    aufrufe = agent(_urteil())
    bilanz = ht.pflege_highlight_themen(LAUNCH + RAUSCHEN, tmp_path,
                                        "2026-08-15", model="m", use_llm=True,
                                        reports_dir=reports)
    assert bilanz["kandidaten"] == 0 and not aufrufe
    assert len(ht.lade_themen(tmp_path)) == 1


def test_der_seltenheitsdeckel_rechnet_je_ausgabe():
    """Am zusammengelegten Korpus vom 15.08.2026 gemessen (610 Meldungen aus
    sieben Ausgaben): n // 5 = 122 liesse "eine" (119x) als Bindewort durch,
    und Fuellwort-Gruppen verdraengten die echten. Je Ausgabe gerechnet
    bleibt der Deckel im kalibrierten Band."""
    assert ht._seltenheitsdeckel(610, 1) == 122
    assert ht._seltenheitsdeckel(610, 7) == 17
    # Untergrenze: doppelte Mindestgruppe, auch bei winzigen Ausgaben.
    assert ht._seltenheitsdeckel(10, 1) == 2 * ht.MIND_MELDUNGEN


# --------------------------------------------------------------- Spezifitaet
def test_spezifitaet_gewichtet_ereignis_vor_rauschen():
    """Der Befund vom 27.08.2026: worte=['quartal','zweiten',...] (reines
    Finanzrauschen) hatte keinen Punktabzug gegenueber worte=['apple',
    'iphone','september','ultra'] (Produktname plus Datumssprache) - beide
    zaehlten nur nach roher Groesse. Rein rauschige Bindewoerter zaehlen
    nichts, eine blosse Wortpaarung ohne jede Ereignissprache ("deutsche"/
    "telekom" - eine Firma, kein Vorgang) fast nichts, Ereignissprache zaehlt
    doppelt."""
    assert ht._spezifitaet(["quartal", "zweiten"]) == 0.0
    assert ht._spezifitaet(["halbjahr", "ergebnis", "prozent"]) == 0.0
    # Zwei Woerter ohne jede Ereignis-/Datumssprache: eine Firma, kein
    # Vorgang - ohne dass das Modul eine Firmenliste braucht.
    assert ht._spezifitaet(["deutsche", "telekom"]) == 0.1
    apple = ht._spezifitaet(["apple", "iphone", "september", "ultra"])
    samsung = ht._spezifitaet(["samsung", "fold8", "galaxy"])
    assert apple > samsung > ht._spezifitaet(["quartal", "zweiten"])


def test_spezifitaet_belohnt_nicht_die_blosse_wortzahl():
    """Die Summe `eigen + 2*ereignis` war unbeschraenkt, also gewann, wer
    mehr Bindewoerter hatte. Am echten Korpus vom 27.08.2026 trugen fuenf der
    sechs Top-Kandidaten den Wert 10,0 - mit tragenden Woertern wie "keine",
    "text", "your" und "weiteren". `_kandidat_aus_gruppe` liefert bis zu acht
    Woerter; eine praezise Gruppe kommt oft mit vier aus und verlor damit
    gegen das Rauschen. Gegen den alten Stand faellt dieser Test (dort 8,0
    gegen 6,0)."""
    allerwelts = ht._spezifitaet(["keine", "text", "your", "weiteren",
                                  "konkreten", "gelten", "sollen", "dazu"])
    apple = ht._spezifitaet(["apple", "iphone", "september", "ultra"])
    assert apple > allerwelts


def test_spezifitaet_zaehlt_produktbezeichnungen_mit():
    """Ein Bindewort mit einer Ziffer ist praktisch immer eine Modell- oder
    Generationsbezeichnung, also ein Eigenname - und Eigennamen benennen
    Vorgaenge. Grossschreibung steht nicht zur Verfuegung, `wortmenge` hat
    sie entfernt."""
    mit = ht._spezifitaet(["google", "pixel-11-serie", "kamera"])
    ohne = ht._spezifitaet(["google", "geraete", "kamera"])
    assert mit > ohne


def test_grosse_finanzgruppen_verdraengen_die_produktgruppe_nicht():
    """Wahrheitstest aus dem Korpus vom 27.08.2026: die Apple-Keynote-Gruppe
    (10 Meldungen, 5 Quellen, alle Schwellen erfuellt) stand auf Rang 17 von
    116 Rohgruppen, weil MAX_KANDIDATEN=6 nach roher Groesse schnitt und
    sechs groessere Finanzrauschen-Gruppen (Quartalszahlen, Halbjahres-
    ergebnis, ...) die Plaetze belegten. Sechs solche Gruppen sind hier
    bewusst GROESSER (6 Meldungen) als die Produktgruppe (4) - nach der alten
    Regel (Groesse zuerst) waeren das die Top 6, die Produktgruppe faellt
    komplett heraus. Nach der Spezifitaets-Regel steht sie trotzdem drin."""
    rausch_paare = [
        ("quartal", "zweiten"), ("halbjahr", "ergebnis"), ("umsatz", "milliarden"),
        ("gewinn", "prozent"), ("bilanz", "revenue"), ("quartalszahlen", "millionen"),
    ]
    finanzgruppen = []
    for gi, (rw1, rw2) in enumerate(rausch_paare):
        for i in range(6):
            finanzgruppen.append(_meldung(
                f"https://finanz{gi}.example/{i}",
                f"Firmenkuerzel{gi}{i} meldet {rw1} und {rw2} fuer den Berichtszeitraum",
                f"Quelle{gi}-{i % 3}"))
    produktgruppe = [_meldung(f"https://produkt.example/{i}",
                              "Apple stellt neues iPhone Ultra im September vor",
                              f"QuelleP{i}") for i in range(4)]

    gruppen = ht.finde_kandidaten(finanzgruppen + produktgruppe)
    assert len(gruppen) <= ht.MAX_KANDIDATEN
    produkt_urls = {h["url"] for h in produktgruppe}
    treffer = [g for g in gruppen if produkt_urls <= {h["url"] for h in g["items"]}]
    assert len(treffer) == 1, "die Produktgruppe muss unter den Top-6 stehen"
    # Und die reinste Rauschgruppe (nur die zwei Finanzwoerter als Bindeglied)
    # steht NICHT vor ihr - hier faellt sie sogar ganz heraus.
    quartal_dabei = [g for g in gruppen if set(g["worte"]) == {"quartal", "zweiten"}]
    assert quartal_dabei == [] or quartal_dabei[0]["spezifitaet"] < treffer[0]["spezifitaet"]


# ------------------------------------------------------------- Antizipation
_ANKUENDIGUNG = [
    _meldung("https://k.example/1", "Apple laedt zur Keynote am 9. September",
             "Quelle K1", summary="Apple laedt zur Keynote am 9. September ein "
             "- Vorstellung neuer Geraete erwartet."),
    _meldung("https://k.example/2", "Apple Keynote Termin steht: September 9",
             "Quelle K2", summary="Der Konzern bestaetigt die Keynote fuer "
             "September 9 - neue Produkte erwartet."),
    _meldung("https://k.example/3", "Analysten erwarten neue Geraete zur Keynote",
             "Quelle K3", summary="Zur bevorstehenden Keynote am 9. September "
             "werden mehrere neue Geraete erwartet."),
]
_OHNE_ANKUENDIGUNG = [
    _meldung("https://o.example/1", "Firma Zeta bringt neues Ladekabel",
             "Quelle O1", summary="Firma Zeta bringt ein neues Ladekabel fuer "
             "Reisende auf den Markt."),
    _meldung("https://o.example/2", "Zubehoer von Firma Zeta jetzt erhaeltlich",
             "Quelle O2", summary="Das Ladekabel von Firma Zeta ist jetzt im "
             "Handel erhaeltlich."),
    _meldung("https://o.example/3", "Test des neuen Ladekabels von Firma Zeta",
             "Quelle O3", summary="Wir haben das neue Ladekabel von Firma Zeta "
             "getestet."),
]


def test_ankuendigungssprache_ergibt_einen_bevorstehenden_kandidaten():
    """Drei Meldungen aus drei Quellen sind fuer finde_kandidaten() zu wenig
    (MIND_MELDUNGEN=4) - der Antizipations-Pfad verlangt nur drei, dafuer
    Ankuendigungssprache (Keynote-Datumsangaben in mindestens der Haelfte
    der Meldungen)."""
    assert ht.finde_kandidaten(_ANKUENDIGUNG) == []
    gruppen = ht.finde_antizipation(_ANKUENDIGUNG)
    assert len(gruppen) == 1
    gruppe = gruppen[0]
    assert gruppe["bevorstehend"] is True
    assert {h["url"] for h in gruppe["items"]} == {h["url"] for h in _ANKUENDIGUNG}
    assert gruppe["quellen"] == 3


def test_ohne_ankuendigungssprache_kein_antizipationskandidat():
    """Dieselbe Gruppengroesse und Quellenzahl, aber ohne Ankuendigungs-
    oder Datumssprache: kein bevorstehendes Ereignis, kein Kandidat."""
    assert ht.finde_antizipation(_OHNE_ANKUENDIGUNG) == []


def _ankuendigungsgruppe(nr: int, marke: str, tag: int) -> list[dict]:
    """Drei Meldungen aus drei Quellen ueber EINEN angekuendigten Termin."""
    return [
        _meldung(f"https://v{nr}.example/{k}",
                 f"{marke} laedt zur Keynote am {tag}. Oktober",
                 f"Quelle V{nr}{k}",
                 summary=f"{marke} laedt zur Keynote am {tag}. Oktober ein - "
                         f"die Vorstellung neuer {marke}-Geraete wird erwartet.")
        for k in range(3)]


def test_hoechstens_drei_antizipationsgruppen_werden_vorgelegt():
    """Der Antizipations-Pfad war ungedeckelt. Am echten Korpus vom
    27.08.2026 (1023 Meldungen aus vier Ausgaben) lieferte er 28 Gruppen und
    trieb die Nutzlast an den Agenten auf ueber 64 000 Zeichen - mit einem
    Denkspur-Modell reisst das `_TOKENS`, die Antwort bricht mitten im JSON
    ab, und das Ergebnis sind NULL Themen. Gegen den alten Stand faellt
    dieser Test (dort: acht Gruppen)."""
    marken = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta",
              "Theta"]
    roh = [m for nr, marke in enumerate(marken)
           for m in _ankuendigungsgruppe(nr, marke, 5 + nr)]
    # Die Voraussetzung ausgeschrieben: OHNE Deckel waeren es wirklich mehr
    # als drei - sonst pruefte der Test seine eigene Fixture.
    gefunden = [g for g in ht.finde_antizipation(roh, "2026-09-20")]
    assert len(ht._gruppen(roh, mind_meldungen=ht.MIND_MELDUNGEN_ANTIZIPATION,
                           mind_quellen=ht.MIND_QUELLEN_ANTIZIPATION)[0]) > 3
    assert len(gefunden) == ht.MAX_ANTIZIPATION == 3


def test_eine_vergangene_datumsangabe_ist_kein_bevorstehendes_ereignis():
    """"12. August" in einem Lauf vom 27.08. ist ein Rueckblick. Am Korpus
    vom 27.08.2026 lagen 30 von 40 Datumstreffern in der Vergangenheit.
    Gegen den alten Stand faellt dieser Test - dort zaehlte jede Tag-und-
    Monat-Angabe."""
    rueckblick = [
        _meldung(f"https://r.example/{k}",
                 f"Rueckblick auf den Netzausfall am 12. August", f"Quelle R{k}",
                 summary="Was am 12. August im Netz von Firma Iota geschah - "
                         "eine Rekonstruktion des Ausfalls am 12. August.")
        for k in range(3)]
    assert ht.finde_antizipation(rueckblick, "2026-08-27") == []
    # Gegenprobe: derselbe Text mit einem noch bevorstehenden Termin.
    assert ht._kuenftiger_termin("Termin am 12. September", date(2026, 8, 27))
    assert not ht._kuenftiger_termin("Termin am 12. August", date(2026, 8, 27))


def test_ein_bereits_stattgefundenes_ereignis_traegt_keine_ankuendigung():
    """"vorgestellt" berichtet ueber etwas, das gerade stattgefunden hat -
    das Gegenteil dessen, was dieser Pfad sucht. Am Korpus vom 27.08.2026
    kam es fuer 31 der Treffer auf, mehr als jedes andere Wort und mehr als
    alle Datumsangaben zusammen. Fuer den Spezifitaets-Bonus zaehlt es
    weiter mit."""
    vergangen = [
        _meldung(f"https://p.example/{k}",
                 "Firma Kappa hat ihr neues Modell vorgestellt", f"Quelle P{k}",
                 summary="Firma Kappa hat auf einer Veranstaltung ihr neues "
                         "Modell vorgestellt und praesentiert die Preise.")
        for k in range(3)]
    assert ht.finde_antizipation(vergangen, "2026-08-27") == []
    assert "vorgestellt" in ht.EREIGNIS_WOERTER


def test_antizipation_konkurriert_nicht_um_max_kandidaten(tmp_path, agent):
    """Die Ankuendigungsgruppe (3 Meldungen) wird ZUSAETZLICH zu den sechs
    Top-Kandidaten der normalen Suche vorgelegt, nicht anstelle einer davon -
    LAUNCH bildet dafuer einen ganz normalen (ausreichend grossen)
    Kandidaten."""
    aufrufe = agent(json.dumps([
        {"i": 0, "thema": True, "gehoert_zu": None,
         "titel": "Samsung Galaxy Fold8 kommt", "leitsatz": "Samsung.",
         "suchwoerter": ["Samsung", "Fold8", "Galaxy"],
         "bevorstehend": False, "event_datum": None},
        {"i": 1, "thema": True, "gehoert_zu": None,
         "titel": "Apple kuendigt Keynote an", "leitsatz": "Apple laedt ein.",
         "suchwoerter": ["Apple", "Keynote", "September"],
         "bevorstehend": True, "event_datum": "2026-09-09"},
    ]))
    bilanz = ht.pflege_highlight_themen(LAUNCH + RAUSCHEN + _ANKUENDIGUNG, tmp_path,
                                        "2026-08-27", model="m", use_llm=True)
    # Beide Kandidaten wurden vorgelegt - der Agent sah zwei, nicht einen.
    payload = json.loads(aufrufe[0])
    assert len(payload["kandidaten"]) == 2
    assert payload["kandidaten"][1]["bevorstehendes_ereignis"] is True
    assert bilanz["neu"] == ["samsung-galaxy-fold8-kommt", "apple-kuendigt-keynote-an"]
    themen = {t["slug"]: t for t in ht.lade_store(tmp_path)["topics"]}
    assert themen["apple-kuendigt-keynote-an"]["event_datum"] == "2026-09-09"
    assert "event_datum" not in themen["samsung-galaxy-fold8-kommt"]


# ------------------------------------------------------------- Alterung
def _lauf_ohne_zuwachs(tmp_path, agent, datum):
    agent(json.dumps([]))
    return ht.pflege_highlight_themen(RAUSCHEN, tmp_path, datum,
                                      model="m", use_llm=True)


def test_thema_endet_nach_vier_laeufen_ohne_zuwachs(tmp_path, agent):
    agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH + RAUSCHEN, tmp_path, "2026-08-07",
                               model="m", use_llm=True)
    assert len(ht.lade_themen(tmp_path)) == 1

    for n, datum in enumerate(("2026-08-11", "2026-08-14", "2026-08-18"), start=1):
        bilanz = _lauf_ohne_zuwachs(tmp_path, agent, datum)
        assert bilanz["beendet"] == []
        assert len(ht.lade_themen(tmp_path)) == 1, f"nach {n} stillen Laeufen"

    bilanz = _lauf_ohne_zuwachs(tmp_path, agent, "2026-08-21")
    assert bilanz["beendet"] == ["samsung-galaxy-fold8-kommt"]
    assert ht.lade_themen(tmp_path) == []
    # Beendet heisst nicht geloescht: der Speicher bleibt das Gedaechtnis.
    store = ht.lade_store(tmp_path)
    assert [t["status"] for t in store["topics"]] == ["beendet"]


def test_beendetes_thema_wird_nicht_neu_entdeckt(tmp_path, agent):
    agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-07", model="m", use_llm=True)
    for datum in ("2026-08-11", "2026-08-14", "2026-08-18", "2026-08-21"):
        _lauf_ohne_zuwachs(tmp_path, agent, datum)
    assert ht.lade_themen(tmp_path) == []

    # Dieselben Meldungen noch einmal - und der Agent wuerde wieder
    # zustimmen. Der Speicher darf sie trotzdem nicht als neu ausgeben.
    aufrufe = agent(_urteil())
    bilanz = ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-09-01",
                                        model="m", use_llm=True)
    assert bilanz["neu"] == []
    assert ht.lade_themen(tmp_path) == []
    # Der Agent wurde gar nicht erst gefragt - der Kandidat war schon weg.
    assert aufrufe == []


def _urteil_bevorstehend(event_datum: str) -> str:
    return json.dumps([{
        "i": 0, "thema": True, "gehoert_zu": None,
        "titel": "Samsung Galaxy Fold8 kommt", "leitsatz": "Samsung.",
        "suchwoerter": ["Samsung", "Fold8", "Galaxy"],
        "bevorstehend": True, "event_datum": event_datum,
    }])


def test_thema_mit_bevorstehendem_ereignis_altert_nicht_vor_der_frist(tmp_path, agent):
    """Ein Ereignis in zehn Tagen: vier Laeufe ganz ohne Zuwachs duerfen das
    Thema NICHT beenden - vor dem Termin ist ein duennes Echo der Normalfall,
    nicht ein Zeichen, dass das Thema erledigt ist (CLAUDE.md, Auftrag P1).
    Gegen den alten Stand faellt das rot: dort gibt es kein event_datum, und
    das Thema waere nach dem vierten Lauf beendet - genau wie in
    test_thema_endet_nach_vier_laeufen_ohne_zuwachs oben."""
    agent(_urteil_bevorstehend("2026-09-06"))
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-27", model="m", use_llm=True)
    assert ht.lade_store(tmp_path)["topics"][0]["event_datum"] == "2026-09-06"

    for n, datum in enumerate(
            ("2026-08-31", "2026-09-03", "2026-09-07", "2026-09-10"), start=1):
        bilanz = _lauf_ohne_zuwachs(tmp_path, agent, datum)
        assert bilanz["beendet"] == []
        assert len(ht.lade_themen(tmp_path)) == 1, f"nach {n} stillen Laeufen"


def test_thema_mit_bevorstehendem_ereignis_altert_nach_der_frist(tmp_path, agent):
    """Dieselbe Ausgangslage, aber die Laeufe liegen alle NACH event_datum +
    EREIGNIS_SCHUTZ_TAGE (2026-09-13): die normale Vier-Laeufe-Alterung greift
    wieder, unveraendert."""
    agent(_urteil_bevorstehend("2026-09-06"))
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-27", model="m", use_llm=True)

    for n, datum in enumerate(("2026-09-14", "2026-09-17", "2026-09-20"), start=1):
        bilanz = _lauf_ohne_zuwachs(tmp_path, agent, datum)
        assert bilanz["beendet"] == []
        assert len(ht.lade_themen(tmp_path)) == 1, f"nach {n} Laeufen nach der Frist"

    bilanz = _lauf_ohne_zuwachs(tmp_path, agent, "2026-09-23")
    assert bilanz["beendet"] == ["samsung-galaxy-fold8-kommt"]
    assert ht.lade_themen(tmp_path) == []


def test_ein_halluziniertes_event_datum_macht_kein_thema_unsterblich(tmp_path, agent):
    """`event_datum` kommt aus einem Modell und setzt die Alterung aus.
    "2028-09-09" ist ein formal gueltiger Kalendertag und haette das Thema
    damit ZWEI JAHRE aktiv gehalten - eine Seite im Fokusband, zu der nie
    wieder eine Meldung kommt und die keine Alterung mehr erreicht. Gegen den
    alten Stand faellt dieser Test.

    Gerechnet wird gegen das durchgereichte `heute`, nie gegen die Uhr -
    sonst meldete der Test die naechste Mitternacht statt den naechsten
    Umbau (CLAUDE.md §6)."""
    agent(_urteil_bevorstehend("2028-09-09"))
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-27",
                               model="m", use_llm=True)
    thema = ht.lade_store(tmp_path)["topics"][0]
    # Gar nicht erst uebernommen: ein Termin jenseits des Horizonts ist
    # Roadmap, kein Termin.
    assert "event_datum" not in thema

    # Und selbst als BESTANDSdatum - etwa aus einem Lauf vor dieser Regel -
    # schuetzt es nicht mehr.
    thema["event_datum"] = "2028-09-09"
    assert ht._durch_event_geschuetzt(thema, "2026-08-27") is False
    # Die normale Alterung greift damit wieder.
    for datum in ("2026-08-31", "2026-09-03", "2026-09-07"):
        assert _lauf_ohne_zuwachs(tmp_path, agent, datum)["beendet"] == []
    assert _lauf_ohne_zuwachs(tmp_path, agent, "2026-09-10")["beendet"] == \
        ["samsung-galaxy-fold8-kommt"]


def test_ein_event_datum_in_der_vergangenheit_wird_nicht_uebernommen(tmp_path, agent):
    """Ein Datum, das schon vorbei ist, kann kein bevorstehendes Ereignis
    schuetzen - der Prompt verlangt ohnehin `null` dafuer, hier zaehlt es
    doppelt."""
    agent(_urteil_bevorstehend("2026-07-01"))
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-27",
                               model="m", use_llm=True)
    assert "event_datum" not in ht.lade_store(tmp_path)["topics"][0]


def test_die_datumspruefung_liest_niemals_die_uhr():
    """Ohne `heute` wird nur das FORMAT geprueft. Ein Test, dessen Ergebnis
    vom Tag abhaengt, meldet die naechste Mitternacht statt den naechsten
    Umbau."""
    assert ht._valid_iso_datum("2028-09-09") == "2028-09-09"
    assert ht._valid_iso_datum("2028-09-09", "2026-08-27") == ""
    assert ht._valid_iso_datum("2026-09-09", "2026-08-27") == "2026-09-09"
    assert ht._valid_iso_datum("2026-02-30", "2026-01-01") == ""
    assert ht._valid_iso_datum("nicht datum", "2026-08-27") == ""


def test_thema_ohne_event_datum_altert_wie_bisher(tmp_path, agent):
    """Bestandsschutz: ein Thema ohne event_datum (jedes Thema vor diesem
    Auftrag) ist von der Sperre unberuehrt - _durch_event_geschuetzt() greift
    fuer ein solches Thema NIE, unabhaengig vom Datum des Laufs."""
    agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-07", model="m", use_llm=True)
    thema = ht.lade_store(tmp_path)["topics"][0]
    assert "event_datum" not in thema
    assert ht._durch_event_geschuetzt(thema, "2026-08-07") is False
    assert ht._durch_event_geschuetzt(thema, "2099-01-01") is False


# ------------------------------------------------------------- Failsafe
def test_ohne_llm_entsteht_kein_thema(tmp_path):
    bilanz = ht.pflege_highlight_themen(LAUNCH + RAUSCHEN, tmp_path,
                                        "2026-08-07", use_llm=False)
    assert bilanz["neu"] == []
    assert ht.lade_themen(tmp_path) == []


def test_gescheiterter_agent_legt_nichts_an_pflegt_aber_weiter(tmp_path, agent):
    agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-07", model="m", use_llm=True)

    agent(RuntimeError("Anbieter antwortet nicht"))
    # Der Nachschlag traegt ZWEI Dinge: neue Fold8-Meldungen (die per
    # Suchwort ins bestehende Thema wandern und deshalb KEINEN neuen
    # Kandidaten mehr bilden - _schon_erfasst) und ein zweites, fremdes
    # Ereignis, das dem gescheiterten Agenten als Kandidat vorliegt.
    nachschlag = [
        _meldung("https://e.example/9", "Galaxy Fold8 nun auch in Indien", "Quelle E"),
        _meldung("https://f.example/10", "Samsung senkt Preis des Galaxy Fold8", "Quelle F"),
        _meldung("https://g.example/12", "Galaxy Fold8 ab Freitag im Handel", "Quelle G"),
        _meldung("https://e.example/13", "Galaxy Fold8 in Japan ausverkauft", "Quelle E"),
        _meldung("https://h.example/14", "Netzbetreiber buendeln Galaxy Fold8", "Quelle H"),
        _meldung("https://p.example/1", "Ausfall im Kernnetz von Beta Telecom", "Quelle P"),
        _meldung("https://q.example/2", "Beta Telecom entschuldigt sich fuer Kernnetz-Ausfall", "Quelle Q"),
        _meldung("https://r.example/3", "Regulierer prueft Kernnetz-Ausfall bei Beta Telecom", "Quelle R"),
        _meldung("https://s.example/4", "Beta Telecom nennt Ursache des Kernnetz-Ausfall", "Quelle S"),
    ] + RAUSCHEN
    bilanz = ht.pflege_highlight_themen(nachschlag, tmp_path, "2026-08-11",
                                        model="m", use_llm=True)

    assert bilanz["neu"] == []
    assert "error" in bilanz
    thema = ht.lade_themen(tmp_path)[0]
    # Die Pflege braucht kein Modell - ein Aussetzer des Anbieters darf ein
    # laufendes Thema nicht altern lassen, obwohl neue Meldungen da waren.
    assert "https://e.example/9" in {i["url"] for i in thema["items"]}
    assert thema["runs_ohne_zuwachs"] == 0


def test_unlesbarer_speicher_kippt_den_lauf_nicht(tmp_path):
    ht.store_pfad(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    ht.store_pfad(tmp_path).write_text("{kaputt", encoding="utf-8")
    assert ht.lade_themen(tmp_path) == []
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-07", use_llm=False)


def test_agent_ohne_suchwoerter_legt_kein_thema_an(tmp_path, agent):
    """Ein Thema ohne Suchwoerter koennte nie wachsen - es waere eine Seite,
    die beim naechsten Lauf sofort zu altern beginnt."""
    agent(_urteil(suchwoerter=["Samsung"]))
    bilanz = ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-07",
                                        model="m", use_llm=True)
    assert bilanz["neu"] == []


def test_zwei_urteile_mit_denselben_suchwoertern_ergeben_ein_thema(tmp_path, agent):
    """Der Agent bekommt die laufenden Themen und soll sie wiedererkennen -
    verlassen darf sich der Speicher darauf nicht."""
    agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH, tmp_path, "2026-08-07", model="m", use_llm=True)
    agent(_urteil(titel="Der Fold8 kommt nach Europa"))
    ht.pflege_highlight_themen(LAUNCH + RAUSCHEN, tmp_path, "2026-08-11",
                               model="m", use_llm=True)
    assert len(ht.lade_store(tmp_path)["topics"]) == 1


# ------------------------------------------------------------ Slug/Anker
def test_slug_ist_stabil_und_kommt_aus_dem_titel():
    """Die Seite heisst nach ihrem Titel, und zwar in jedem Lauf gleich -
    der Link steht in Mails."""
    from telco_radar.report.html import _slug
    from telco_radar.textwerkzeug import slug

    assert slug is _slug
    assert slug("Samsung Galaxy Fold8 kommt") == "samsung-galaxy-fold8-kommt"
    assert slug("Übernahme: IHS Towers & MTN") == "uebernahme-ihs-towers-mtn"
    assert slug("Samsung Galaxy Fold8 kommt") == slug(" samsung  galaxy fold8 kommt ")


# --------------------------------------------------------------- Rendern
def _projekt(tmp_path, highlights):
    """Ein Projektverzeichnis mit einer Ausgabe und den Bilddateien dazu."""
    from telco_radar.report.bilder import bildordner

    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    ordner = bildordner(tmp_path)
    ordner.mkdir(parents=True, exist_ok=True)
    for h in highlights:
        if h.get("image"):
            (ordner / h["image"]).write_bytes(b"kein echtes Bild")
    (reports / "2026-08-07.json").write_text(json.dumps({
        "date": "2026-08-07", "generated_with_llm": True,
        "stats": {"new": 200}, "briefing_md": "## Auf einen Blick\n\nText.",
        "regions": {"Global": {"region_summary": "", "highlights": highlights}},
        "competitors": [],
        "run": {"duration_seconds": 900.0, "models": {"analyst": "m", "editor": "m"},
                "phases": [], "analysts": [], "sources": [],
                "source_summary": {"ok": 1, "empty": 0, "failed": 0}},
    }, ensure_ascii=False), encoding="utf-8")
    return reports


def test_aktives_thema_bekommt_eine_seite_ein_beendetes_nicht(tmp_path, agent):
    reports = _projekt(tmp_path, LAUNCH + RAUSCHEN)
    agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH + RAUSCHEN, tmp_path / "data" / "state",
                               "2026-08-07", model="m", use_llm=True)

    site = tmp_path / "site"
    render_site(site, reports)
    seite = site / "thema" / "samsung-galaxy-fold8-kommt.html"
    assert seite.exists()

    soup = BeautifulSoup(seite.read_text(encoding="utf-8"), "html.parser")
    assert soup.select_one("h1").get_text(strip=True) == "Samsung Galaxy Fold8 kommt"
    # Jede Meldung des Themas steht auf der Seite, keine doppelt.
    schlagzeilen = [e.get_text(" ", strip=True) for e in soup.select(".szl")]
    assert len(schlagzeilen) == len(LAUNCH) == len(set(schlagzeilen))
    # Die Titelseite fuehrt hin - und zwar nur sie, nicht die Archivwoche.
    assert "thema/samsung-galaxy-fold8-kommt.html" in \
        (site / "index.html").read_text(encoding="utf-8")
    assert "thema/samsung-galaxy-fold8-kommt.html" not in \
        (site / "reports" / "2026-08-07.html").read_text(encoding="utf-8")

    # Endet das Thema, verschwindet die Seite - der Ordner spiegelt den
    # Speicher, wie site/images/ auch.
    for datum in ("2026-08-11", "2026-08-14", "2026-08-18", "2026-08-21"):
        agent(json.dumps([]))
        ht.pflege_highlight_themen([], tmp_path / "data" / "state", datum,
                                   model="m", use_llm=True)
    render_site(site, reports)
    assert not seite.exists()
    assert "thema/" not in (site / "index.html").read_text(encoding="utf-8")


def test_themenseite_zeigt_nur_belegbare_aktionen(tmp_path, agent):
    reports = _projekt(tmp_path, LAUNCH)
    agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH, tmp_path / "data" / "state",
                               "2026-08-07", model="m", use_llm=True)
    thema = ht.lade_themen(tmp_path / "data" / "state")[0]

    from telco_radar.report.thema import build_thema_view

    angebote = [
        {"brand": "Marke A", "headline": "Galaxy Fold8 mit Vertrag",
         "description": "Das neue Samsung-Modell im Tarif.", "status": "aktiv",
         "url": "https://promo.example/a"},
        {"brand": "Marke B", "headline": "Samsung-Aktion",
         "description": "Rabatt auf Zubehoer.", "status": "aktiv",
         "url": "https://promo.example/b"},
        {"brand": "Marke C", "headline": "Galaxy Fold8 zum Sparpreis",
         "description": "Samsung Falt-Handy guenstiger.", "status": "ausgelaufen",
         "url": "https://promo.example/c"},
    ]
    view = build_thema_view(thema, angebote)
    # Nur A: B trifft ein einziges Suchwort, C laeuft nicht mehr.
    assert [a["url"] for a in view["aktionen"]] == ["https://promo.example/a"]


def test_themenseite_verweist_nicht_auf_geloeschte_bilder(tmp_path, agent):
    """Wie bei den Archivwochen: `raeume_auf()` loescht die Bilder aelterer
    Ausgaben, die Verweise bleiben im Speicher stehen."""
    reports = _projekt(tmp_path, LAUNCH)
    agent(_urteil())
    ht.pflege_highlight_themen(LAUNCH, tmp_path / "data" / "state",
                               "2026-08-07", model="m", use_llm=True)
    from telco_radar.report.bilder import bildordner
    for bild in bildordner(tmp_path).iterdir():
        bild.unlink()

    site = tmp_path / "site"
    render_site(site, reports)
    html = (site / "thema" / "samsung-galaxy-fold8-kommt.html").read_text(encoding="utf-8")
    assert "images/" not in html


def test_kein_zu_kleines_bild_in_einer_grossen_position(tmp_path, agent):
    """Abnahmekriterium 6 des Portals, als Test.

    Der Aufmacher stellt sein Bild rund 500 px breit dar, die zweite Reihe
    rund 580 px. Ein schmaleres Bild in dieser Position wird hochskaliert -
    genau der Befund vom 06.08.2026, nur eine Seite weiter.
    """
    from telco_radar.report.thema import MIND_BREITE_BILD, build_thema_view

    schmal = [dict(h, image=f"klein{i}.jpg", image_w=320, image_h=180)
              for i, h in enumerate(LAUNCH)]
    agent(_urteil())
    ht.pflege_highlight_themen(schmal, tmp_path, "2026-08-07", model="m", use_llm=True)
    view = build_thema_view(ht.lade_themen(tmp_path)[0])

    assert view["aufmacher"] is not None, "die Position bleibt besetzt"
    assert "image" not in view["aufmacher"], "nur das Bild faellt weg"
    assert all("image" not in h for h in view["zwei"])

    # Gegenprobe: ein tragfaehiges Bild bleibt und fuehrt.
    agent(_urteil())
    breit = schmal[:3] + [dict(schmal[3], image="gross.jpg",
                               image_w=MIND_BREITE_BILD, image_h=400)] + schmal[4:]
    ht.pflege_highlight_themen(breit, tmp_path / "b", "2026-08-07",
                               model="m", use_llm=True)
    view = build_thema_view(ht.lade_themen(tmp_path / "b")[0])
    assert view["aufmacher"]["image"] == "gross.jpg"
