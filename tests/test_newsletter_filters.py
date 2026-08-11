"""Die Verknuepfungsregel und die Stichwortsuche.

Das Paket, das am gruendlichsten geprueft gehoert, weil hier alle spaeteren
Fehlermeldungen herkommen: eine Mail mit dem falschen Inhalt sieht aus wie
eine Mail und faellt erst dem Empfaenger auf.

Die vier Falschtreffer-Faelle `spark`, `tim`, `globe` und `orange` sind die
bekannten Problembegriffe aus `collect._AMBIGUOUS_TERMS` - dort gibt es
dagegen eine gepflegte Blockliste, hier nicht (die Begriffe tippt der
Abonnent). Sie muessen also an der Wortgrenze und an der Mindestlaenge
scheitern, nicht an einer Liste.
"""
from datetime import date
from pathlib import Path

import json
import pytest

from telco_radar.newsletter.config import lade_katalog
from telco_radar.newsletter.filters import (
    Eintrag, Filtersatz, Stichwort, baue_stichwort_index, lies_filtersatz,
    lies_stichwoerter, stichwort_fehler, vorschau, waehle)

WURZEL = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def katalog():
    return lade_katalog(WURZEL)


def _eintrag(i, *, bereich="marktrecherche", region="europa", ressort="tarife",
             betreiber="", titel=None, text="", gewicht=0):
    return Eintrag(id=f"e{i}", bereich=bereich,
                   titel=titel if titel is not None else f"Meldung {i}",
                   text=text, url=f"https://beispiel.test/{i}",
                   absender="Fachpresse", region=region, ressort=ressort,
                   betreiber=betreiber, gewicht=gewicht, datum="2026-08-11")


# ==================================================  Verknuepfungsregel  ===

def test_leere_auswahl_heisst_alles(katalog):
    """Die Erwartung fast aller Nutzer - und die gefaehrlichste Zeile des
    Pakets, wenn sie falsch herum gebaut ist."""
    eintraege = [_eintrag(1), _eintrag(2, region="asien", ressort="netz")]
    treffer = waehle(eintraege, Filtersatz(), katalog)
    assert len(treffer) == 2


def test_zwischen_den_dimensionen_gilt_und(katalog):
    """Europa UND Bundling - nicht alles aus Europa PLUS alles zu Bundling."""
    passt = _eintrag(1, region="europa", ressort="tarife")
    nur_region = _eintrag(2, region="europa", ressort="netz")
    nur_ressort = _eintrag(3, region="asien", ressort="tarife")
    satz = Filtersatz(regionen=("europa",), kategorien=("tarife",))
    ids = {t.eintrag.id for t in waehle([passt, nur_region, nur_ressort],
                                        satz, katalog)}
    assert ids == {"e1"}


def test_innerhalb_einer_dimension_gilt_oder(katalog):
    eintraege = [_eintrag(1, region="europa"), _eintrag(2, region="nordamerika"),
                 _eintrag(3, region="asien")]
    satz = Filtersatz(regionen=("europa", "nordamerika"))
    ids = {t.eintrag.id for t in waehle(eintraege, satz, katalog)}
    assert ids == {"e1", "e2"}


def test_eine_kategorie_uebersetzt_in_ihre_ressorts(katalog):
    satz = Filtersatz(kategorien=("satellit",))
    eintraege = [_eintrag(1, ressort="satellit"), _eintrag(2, ressort="tarife")]
    assert {t.eintrag.id for t in waehle(eintraege, satz, katalog)} == {"e1"}


def test_ein_unbekannter_schluessel_gilt_nicht_als_leer(katalog):
    """Die heikelste Stelle von `lies_filtersatz`: haette man den unbekannten
    Schluessel weggeworfen, waere die Dimension leer - und "leer heisst
    alles" wuerde dem Abonnenten die ganze Welt schicken statt gar nichts."""
    satz = lies_filtersatz({"regions": ["europa-alt-und-weg"]}, katalog)
    assert satz.regionen == ("europa-alt-und-weg",)
    assert waehle([_eintrag(1, region="europa")], satz, katalog) == []


# =====================================================  Wettbewerber  ======

def test_wettbewerber_trifft_ueber_das_betreiberfeld(katalog):
    satz = Filtersatz(wettbewerber=("telekom",))
    treffer = waehle([_eintrag(1, betreiber="Deutsche Telekom"),
                      _eintrag(2, betreiber="Orange")], satz, katalog)
    assert {t.eintrag.id for t in treffer} == {"e1"}


def test_wettbewerber_trifft_auch_ueber_die_ueberschrift(katalog):
    """Eine branchenweite Meldung hat kein Betreiberfeld - und genau in
    solchen Meldungen stehen drei Anbieter gleichzeitig."""
    satz = Filtersatz(wettbewerber=("o2",))
    treffer = waehle([_eintrag(1, betreiber="",
                               titel="Telekom und O2 streiten über Roaming")],
                     satz, katalog)
    assert len(treffer) == 1


def test_wettbewerber_trifft_nicht_in_der_zusammenfassung(katalog):
    """Der Suchtext der STICHWOERTER ist Titel plus Zusammenfassung; der
    Wettbewerbsfilter sieht bewusst nur Betreiber und Ueberschrift. Sonst
    liefert jede Meldung, die o2 im Nebensatz erwaehnt, ein o2-Abo voll."""
    satz = Filtersatz(wettbewerber=("o2",))
    eintrag = _eintrag(1, titel="Netzausbau in Bayern",
                       text="Beteiligt ist unter anderem O2.")
    assert waehle([eintrag], satz, katalog) == []


def test_die_marke_trifft_nicht_als_teilwort(katalog):
    """"1&1" darf nicht in "1&10" treffen, "Telekom" nicht in "Telekomm"."""
    satz = Filtersatz(wettbewerber=("telekom",))
    assert waehle([_eintrag(1, titel="Telekommunikation in Ghana")],
                  satz, katalog) == []


# =======================================================  Stichwoerter  ====

def test_stichwoerter_sind_additiv_und_begruendet(katalog):
    """Die eine Regel, die entscheidet, ob Stichwort-Abos als nuetzlich oder
    als kaputt empfunden werden."""
    passt_nicht = _eintrag(1, region="asien",
                           titel="Starlink startet Mobilfunkdienst")
    satz = Filtersatz(regionen=("europa",),
                      stichwoerter=(Stichwort("Starlink"),))
    treffer = waehle([passt_nicht], satz, katalog)
    assert len(treffer) == 1
    assert treffer[0].ueber_stichwort
    assert treffer[0].stichwort == "Starlink"


def test_ein_filtertreffer_bleibt_ein_filtertreffer(katalog):
    """Auch wenn zusaetzlich ein Stichwort passt - sonst stuende neben jeder
    zweiten Zeile "Ihr Stichwort", und die Markierung waere wertlos."""
    satz = Filtersatz(regionen=("europa",), stichwoerter=(Stichwort("Netzausbau"),))
    treffer = waehle([_eintrag(1, region="europa", titel="Netzausbau in Hessen")],
                     satz, katalog)
    assert treffer[0].grund == "filter"
    assert treffer[0].stichwort == ""


def test_stichworttreffer_stehen_hinter_den_filtertreffern(katalog):
    """Eine Zugabe, keine Uebernahme: das Stichwort darf die wichtigste
    Meldung des gewaehlten Bereichs nicht verdraengen."""
    satz = Filtersatz(regionen=("europa",), stichwoerter=(Stichwort("Starlink"),))
    eintraege = [_eintrag(1, region="asien", titel="Starlink weltweit",
                          gewicht=99),
                 _eintrag(2, region="europa", titel="Kleine Meldung", gewicht=1)]
    treffer = waehle(eintraege, satz, katalog)
    assert [t.eintrag.id for t in treffer] == ["e2", "e1"]


def test_ein_eintrag_steht_hoechstens_einmal_in_der_ausgabe(katalog):
    satz = Filtersatz(stichwoerter=(Stichwort("Netzausbau"), Stichwort("Hessen")))
    treffer = waehle([_eintrag(1, titel="Netzausbau in Hessen")], satz, katalog)
    assert len(treffer) == 1


def test_deutsche_komposita_treffen_am_bindestrich():
    """Die eine Fallunterscheidung, die im Deutschen wirklich zaehlt."""
    s = Stichwort("Netzausbau")
    assert s.trifft("Der Glasfaser-Netzausbau stockt")
    assert s.trifft("Netzausbau in Bayern")
    assert s.trifft("Netzausbau-Pläne der Telekom")


def test_ein_kurzes_wort_geht_nicht_im_kompositum_unter():
    """"Netz" darf NICHT in "Netzwerkkarte" treffen - der Fall, an dem eine
    zu grosszuegige Regel als Erstes auffliegt."""
    assert not Stichwort("Netz").trifft("Die Netzwerkkarte ist defekt")
    assert Stichwort("Netz").trifft("Das Netz ist überlastet")


@pytest.mark.parametrize("begriff, harmlos", [
    ("spark", "Die Sparkasse investiert in Glasfaser"),
    ("globe", "Globetrotter eröffnet Filiale"),
    ("orange", "Orangensaft im Bordbistro"),
    ("smart", "Smartphone-Absatz steigt"),
    ("bell", "Bellheim bekommt Glasfaser"),
])
def test_die_bekannten_problembegriffe_erzeugen_keine_falschtreffer(begriff, harmlos):
    """Dieselben Begriffe, an denen sich das Fachpresse-Tagging verschluckt
    hat. Dort haelt eine gepflegte Blockliste dagegen; hier muss die
    Wortgrenze allein reichen, denn diese Begriffe tippt der Abonnent."""
    assert not Stichwort(begriff).trifft(harmlos), f"{begriff} in {harmlos!r}"


def test_die_problembegriffe_treffen_ihren_echten_fall():
    """Die Gegenprobe. Ohne sie belegt der Test oben nur, dass das Muster
    nie etwas findet."""
    assert Stichwort("spark").trifft("Spark New Zealand meldet Zahlen")
    assert Stichwort("globe").trifft("Globe Telecom baut aus")
    assert Stichwort("orange").trifft("Orange kauft Anteile in Spanien")


def test_zu_kurze_stichwoerter_werden_abgewiesen(katalog):
    """`tim`, `vi` und `au` fallen an der Mindestlaenge - genau die Faelle,
    fuer die es im Tagging eine Blockliste braucht."""
    for kurz in ("tim", "vi", "au", "one"):
        assert stichwort_fehler(kurz, katalog), kurz
    assert stichwort_fehler("Starlink", katalog) == ""


def test_eine_phrase_darf_kurze_woerter_enthalten(katalog):
    """"5G in Afrika" ist als Ganzes eindeutig, auch wenn "5G" zwei Zeichen
    hat - gemessen wird das LAENGSTE Wort."""
    assert stichwort_fehler("5G in Afrika", katalog) == ""
    assert Stichwort("5G in Afrika", "phrase").trifft(
        "Der Ausbau von 5G in Afrika beschleunigt sich")


def test_eine_phrase_toleriert_bindestrich_und_umbruch():
    s = Stichwort("Fixed Wireless Access", "phrase")
    assert s.trifft("Anbieter setzen auf Fixed Wireless Access")
    assert s.trifft("Anbieter setzen auf Fixed-Wireless-Access")
    assert s.trifft("Anbieter setzen auf Fixed Wireless\nAccess")
    assert not s.trifft("Fixed Line und Wireless Access getrennt")


def test_die_betriebsart_wird_abgeleitet_wenn_sie_fehlt():
    """Wer "Fixed Wireless Access" eintippt, meint nicht drei Stichwoerter."""
    assert lies_stichwoerter(["Fixed Wireless Access"])[0].mode == "phrase"
    assert lies_stichwoerter(["Starlink"])[0].mode == "word"
    assert lies_stichwoerter([{"term": "Starlink", "mode": "phrase"}])[0].mode == "phrase"


def test_stichwoerter_sehen_nur_titel_und_zusammenfassung():
    """Nicht den Absender - sonst traefe "Telekom" jede Meldung aus einem
    Telekom-Newsroom, auch die ueber ein Rechenzentrum in Indien."""
    e = _eintrag(1, titel="Neuer Tarif", text="Ohne Bezug.")
    e.absender = "Telekom Newsroom"
    assert not Stichwort("Telekom").trifft(e.suchtext)


# ============================================================  Deckel  =====

def test_die_ausgabe_ist_auf_acht_eintraege_gedeckelt(katalog):
    eintraege = [_eintrag(i, gewicht=100 - i) for i in range(20)]
    treffer = waehle(eintraege, Filtersatz(), katalog)
    assert len(treffer) == katalog.grenzen.max_eintraege == 8
    # ... und zwar die wichtigsten.
    assert [t.eintrag.id for t in treffer] == [f"e{i}" for i in range(8)]


def test_mehr_als_zehn_stichwoerter_werden_beschnitten(katalog):
    roh = {"keywords": [f"Stichwort{i:02d}" for i in range(25)]}
    satz = lies_filtersatz(roh, katalog)
    assert len(satz.stichwoerter) == katalog.grenzen.max_stichwoerter == 10


# =====================================  Vorschau und ihr Browser-Index  ====

@pytest.fixture()
def archiv(tmp_path):
    reports = tmp_path / "data" / "reports"
    reports.mkdir(parents=True)
    def bericht(datum, meldungen):
        (reports / f"{datum}.json").write_text(json.dumps({
            "date": datum,
            "regions": {"Europa": {"highlights": [
                {"headline": t, "summary": s, "url": f"https://x.test/{i}"}
                for i, (t, s) in enumerate(meldungen)]}},
        }), encoding="utf-8")
    bericht("2026-08-08", [("Netzausbau in Hessen", "Glasfaser kommt."),
                           ("Starlink startet", "Satellit für Mobilfunk.")])
    bericht("2026-08-05", [("Netzausbau in Bayern", "Weiterer Ausbau.")])
    # Aelter als das Fenster - darf NICHT mitzaehlen.
    bericht("2026-05-01", [("Netzausbau im Frühjahr", "Alt.")])
    return reports


def test_die_vorschau_zaehlt_meldungen_im_fenster(archiv):
    heute = date(2026, 8, 11)
    assert vorschau("Netzausbau", archiv, tage=30, heute=heute) == 2
    assert vorschau("Starlink", archiv, tage=30, heute=heute) == 1
    assert vorschau("Kernfusion", archiv, tage=30, heute=heute) == 0


def test_das_fenster_wirkt_wirklich(archiv):
    """Ohne diese Gegenprobe belegt der Test oben nur, dass irgendetwas
    gezaehlt wird - der alte Bericht muss den Unterschied machen."""
    heute = date(2026, 8, 11)
    assert vorschau("Netzausbau", archiv, tage=200, heute=heute) == 3


def test_der_browser_index_sagt_dasselbe_wie_die_vorschau(archiv):
    """Die Anmeldeseite kann `vorschau()` nicht aufrufen - sie zaehlt im
    Browser gegen diesen Index. Laufen die zwei auseinander, sagt die Seite
    eine Zahl voraus, die der Versand nie einloest, und beide sind fuer sich
    gruen. Dieselbe Falle wie beim Archiv-Dialog in app.js.

    Geprueft wird JEDES Wort des Index, nicht ein Beispiel - und dass
    ueberhaupt welche geprueft wurden."""
    heute = date(2026, 8, 11)
    index = baue_stichwort_index(archiv, tage=30, heute=heute)
    assert index["woerter"], "leerer Index - der Test prueft sonst nichts"
    abweichungen = []
    for wort, n in index["woerter"].items():
        gezaehlt = vorschau(wort, archiv, tage=30, heute=heute)
        if gezaehlt != n:
            abweichungen.append((wort, n, gezaehlt))
    assert not abweichungen, abweichungen
    assert len(index["woerter"]) >= 5
    assert index["meldungen"] == 3


def test_der_index_kennt_nur_woerter_ab_vier_zeichen(archiv):
    """Dieselbe Grenze wie `min_stichwort_laenge`. Kuerzere kann niemand
    eintragen, sie muessten also gar nicht erst ausgeliefert werden."""
    index = baue_stichwort_index(archiv, tage=30, heute=date(2026, 8, 11))
    assert all(len(w) >= 4 for w in index["woerter"])


# ==========================================================  Katalog  ======

def test_die_kategorien_zeigen_auf_echte_ressorts():
    """Ein umbenanntes Ressort wuerde in newsletter.yaml still ins Leere
    zeigen - die Kategorie waere fuer immer leer, ohne dass irgendwo etwas
    rot wird. Genau die Sorte Test, die diese Codebasis schon einmal teuer
    bezahlt hat."""
    from telco_radar.report.html import _RESSORT_LABEL
    katalog = lade_katalog(WURZEL)
    gepruefte = 0
    for auswahl in katalog.kategorien:
        assert auswahl.ressorts, auswahl.key
        for ressort in auswahl.ressorts:
            assert ressort in _RESSORT_LABEL, f"{auswahl.key} -> {ressort}"
            gepruefte += 1
    assert gepruefte == len(katalog.kategorien) >= 6


def test_die_regionen_zeigen_auf_echte_regionen():
    """Dasselbe fuer die Regionen: die Schluessel sind die Slugs der
    Regionsnamen aus der Watchlist."""
    from telco_radar.config import load_config
    from telco_radar.newsletter.quelle import region_schluessel
    katalog = lade_katalog(WURZEL)
    cfg = load_config(WURZEL)
    # `region_name` ist der deutsche Name - genau der, der im Bericht-JSON
    # als Schluessel der `regions`-Tabelle steht.
    echte = {region_schluessel(op.region_name) for op in cfg.operators}
    gewaehlt = katalog.schluessel("regionen") - {"global"}
    assert echte, "keine Betreiber geladen - der Test prueft sonst nichts"
    assert gewaehlt <= echte | {"global"}, sorted(gewaehlt - echte)
    assert echte <= katalog.schluessel("regionen"), sorted(echte - gewaehlt)


def test_ein_doppelter_schluessel_faellt_beim_laden_auf(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "newsletter.yaml").write_text(
        "grenzen: {}\n"
        "bereiche:\n  - {key: a, label: A}\n  - {key: a, label: B}\n"
        "regionen:\n  - {key: europa, label: Europa}\n"
        "wettbewerber:\n  - {key: t, label: T}\n"
        "kategorien:\n  - {key: k, label: K, ressorts: [tarife]}\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="zweimal"):
        lade_katalog(tmp_path)


def test_eine_leere_dimension_faellt_beim_laden_auf(tmp_path):
    """Kein stiller Rueckfall: bei leeren Dimensionen wuerde "leer heisst
    alles" jedem Abonnenten alles schicken."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "newsletter.yaml").write_text(
        "bereiche: []\nregionen: []\nwettbewerber: []\nkategorien: []\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="leer"):
        lade_katalog(tmp_path)


def test_eine_fehlende_datei_ist_ein_fehler(tmp_path):
    with pytest.raises(FileNotFoundError):
        lade_katalog(tmp_path)
