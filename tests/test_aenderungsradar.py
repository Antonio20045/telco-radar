"""Aenderungsradar auf Tarifseiten (collect/aenderungen.py).

Die Frage, an der so ein Radar steht oder faellt, ist nicht "erkennt er eine
Aenderung?", sondern "haelt er den Mund, wenn sich nur die Darstellung
aendert?". Visualping gibt an, rund 83 % der erkannten Aenderungen als
irrelevant aussortieren zu muessen - das ist die Groessenordnung des
Rauschens. Ein System mit vierzig Falschmeldungen die Woche wird nach zwei
Wochen ignoriert, und dann ist es schlechter als keines.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from telco_radar.collect import aenderungen as A

JETZT = datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc)

SEITE = A.Tarifseite(marke="o2", was="Tarifübersicht",
                     url="https://www.o2online.de/tarife/")


def _html(rumpf: str) -> str:
    return f"<html><body><main>{rumpf}</main></body></html>"


# ------------------------------------------------------ was NICHT meldet

def test_umsortierte_kacheln_sind_keine_aenderung():
    """Ein Anbieter, der seine Kacheln neu anordnet, aendert dieselbe
    Wertmenge - und loest deshalb nichts aus."""
    a = A.werte(A._text(_html(
        "<div>Mobile M 39,99 €</div><div>Mobile S 19,99 €</div>")))
    b = A.werte(A._text(_html(
        "<div>Mobile S 19,99 €</div><div>Mobile M 39,99 €</div>")))
    assert A.vergleiche(a, b) == ([], [])


def test_uhrzeit_und_zaehler_sind_kein_wert():
    """Ohne diese Regel meldet JEDER Abruf eine Aenderung."""
    a = A.werte(A._text(_html(
        "Mobile M 39,99 € · Stand 08.08.2026 14:32 Uhr · 1200 Bewertungen")))
    b = A.werte(A._text(_html(
        "Mobile M 39,99 € · Stand 09.08.2026 07:05 Uhr · 1204 Bewertungen")))
    assert A.vergleiche(a, b) == ([], [])


def test_werbebanner_ohne_wert_loest_nichts_aus():
    a = A.werte(A._text(_html("<p>Jetzt wechseln!</p> Mobile M 39,99 €")))
    b = A.werte(A._text(_html("<p>Sommeraktion!</p> Mobile M 39,99 €")))
    assert A.vergleiche(a, b) == ([], [])


def test_skripte_und_navigation_zaehlen_nicht():
    html = ("<html><body><nav>Tarife 5 GB</nav>"
            "<script>var p='99,99 €'</script>"
            "<main>Mobile M 39,99 €</main>"
            "<footer>Service 24 Monate</footer></body></html>")
    w = A.werte(A._text(html))
    assert any("39.99€" in x for x in w)
    assert not any("99.99€" in x for x in w)
    assert not any("24monate" in x for x in w)


# ------------------------------------------------------------ was meldet

def test_gesenkter_anschlusspreis_wird_erkannt():
    """Der Beispielfall des Auftragsdokuments."""
    alt = A.werte(A._text(_html("Anschlusspreis für Mobile M 39,99 €")))
    neu = A.werte(A._text(_html("Anschlusspreis für Mobile M 0 €")))
    dazu, weg = A.vergleiche(alt, neu)
    assert any("0€" in x for x in dazu)
    assert any("39.99€" in x for x in weg)


def test_gleicher_preis_an_verschiedenen_etiketten_bleibt_unterscheidbar():
    """Ohne das Etikett waeren "9,99 €" an zwei Stellen derselbe Wert, und
    eine Aenderung beim Anschlusspreis saehe aus wie eine beim Monatspreis."""
    w = A.werte(A._text(_html("Anschlusspreis 9,99 € Monatspreis 9,99 €")))
    assert len(w) == 2


def test_neues_datenvolumen_wird_erkannt():
    alt = A.werte(A._text(_html("Mobile M mit 20 GB")))
    neu = A.werte(A._text(_html("Mobile M mit 40 GB")))
    dazu, weg = A.vergleiche(alt, neu)
    assert dazu and weg


# ------------------------------------------------------------- Grundlinie

def test_der_erste_abruf_meldet_nie(tmp_path, monkeypatch):
    """Sonst bestuende die erste Ausgabe nach dem Einbau aus vierzig "neuen"
    Preisen, die alle schon immer so dastanden."""
    _bereite(tmp_path, _viele_werte() + "<div>Mobile M 39,99 €</div>", monkeypatch)
    items, bilanz = A.sammle(tmp_path, {}, heute=JETZT)
    assert items == []
    assert bilanz["grundlinie"] == 1


def test_zweiter_abruf_mit_aenderung_meldet(tmp_path, monkeypatch):
    _bereite(tmp_path, _viele_werte() + "<div>Mobile M 39,99 €</div>", monkeypatch)
    A.sammle(tmp_path, {}, heute=JETZT)
    _bereite(tmp_path, _viele_werte() + "<div>Mobile M 29,99 €</div>", monkeypatch)
    items, bilanz = A.sammle(tmp_path, {}, heute=JETZT)
    assert bilanz["geaendert"] == 1
    assert len(items) == 1
    assert "29.99" in items[0].summary and "39.99" in items[0].summary
    assert items[0].operator == "o2"
    assert items[0].origin == "tarif_change"


def test_zweiter_abruf_ohne_aenderung_meldet_nicht(tmp_path, monkeypatch):
    _bereite(tmp_path, _viele_werte() + "<div>Mobile M 39,99 €</div>", monkeypatch)
    A.sammle(tmp_path, {}, heute=JETZT)
    items, bilanz = A.sammle(tmp_path, {}, heute=JETZT)
    assert items == [] and bilanz["geaendert"] == 0


def test_ein_umbau_wird_nicht_als_vierzig_meldungen_ausgegeben(tmp_path,
                                                               monkeypatch):
    _bereite(tmp_path, "".join(f"<div>Tarif{i} {i},99 €</div>"
                               for i in range(1, 11)), monkeypatch)
    A.sammle(tmp_path, {}, heute=JETZT)
    _bereite(tmp_path, "".join(f"<div>Neu{i} {i}0,49 €</div>"
                               for i in range(1, 11)), monkeypatch)
    items, bilanz = A.sammle(tmp_path, {}, heute=JETZT)
    assert items == []
    assert bilanz["umgebaut"] == 1


def test_seite_ohne_werte_wird_nicht_als_alles_entfallen_gemeldet(tmp_path,
                                                                  monkeypatch):
    """Die teuerste Falschmeldung, die dieser Radar produzieren kann: eine
    per JavaScript aufgebaute Seite meldet sonst jeden Preis als entfallen."""
    _bereite(tmp_path, _viele_werte(), monkeypatch)
    A.sammle(tmp_path, {}, heute=JETZT)
    _bereite(tmp_path, "<div id='app'></div>", monkeypatch)
    items, bilanz = A.sammle(tmp_path, {}, heute=JETZT)
    assert items == []
    assert bilanz["ohne_werte"] == 1


def test_eine_handvoll_werte_aus_dem_fliesstext_reicht_nicht(tmp_path,
                                                             monkeypatch):
    """GEMESSEN ueber alle 16 Seiten am 08.08.2026: eine Uebersicht, die ihre
    Preistabelle wirklich ausliefert, bringt 16 bis 54 Werte. Drei Werte
    stammen aus der Prosa drumherum ("...sparst du 10 %") - ein Diff darauf
    meldet Textaenderungen als Preisaenderungen."""
    _bereite(tmp_path, "<p>Du sparst 10 % und bekommst bis zu 1 GB.</p>",
             monkeypatch)
    items, bilanz = A.sammle(tmp_path, {}, heute=JETZT)
    assert bilanz["ohne_werte"] == 1 and bilanz["grundlinie"] == 0


# ---------------------------------------------------------------- Kennung

def test_die_kennung_kommt_aus_url_und_inhalt_nicht_aus_dem_titel():
    """Sonst haette der Seen-Store die zweite Preisaenderung derselben Seite
    fuer eine schon berichtete gehalten."""
    a = A.Aenderung(seite=SEITE, dazu=["preis|29.99€"], weg=["preis|39.99€"])
    b = A.Aenderung(seite=SEITE, dazu=["preis|19.99€"], weg=["preis|29.99€"])
    assert a.kennung() != b.kennung()
    # ... und sie ist stabil.
    assert a.kennung() == A.Aenderung(
        seite=SEITE, dazu=["preis|29.99€"], weg=["preis|39.99€"]).kennung()
    assert A.als_item(a, JETZT).id == a.kennung()


# ------------------------------------------------------------ Konfiguration

def test_die_ausgelieferte_liste_bleibt_klein_und_deutsch():
    seiten = A.lade_seiten(Path(__file__).resolve().parents[1])
    assert 10 <= len(seiten) <= 25, "15-25 URLs, nicht mehr"
    assert all(s.url.startswith("https://") for s in seiten)
    # Der eigene Vergleichsanker - ohne ihn ist jede Zahl der anderen ein
    # Wert ohne Bezugsgroesse.
    assert any("vodafone" in s.marke.lower() for s in seiten)


def test_fehlende_konfiguration_legt_nichts_lahm(tmp_path):
    assert A.lade_seiten(tmp_path) == []
    items, bilanz = A.sammle(tmp_path, {}, heute=JETZT)
    assert items == [] and bilanz["seiten"] == 0


# ------------------------------------------------------------------ Helfer

def _viele_werte() -> str:
    """Eine Seite, die den Mindestumfang einer echten Tarifuebersicht hat."""
    return "".join(f"<div>Tarif{i} {i},99 EUR mit {i}0 GB</div>"
                   for i in range(1, 8))


def _bereite(root: Path, rumpf: str, monkeypatch) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "tarif_seiten.yaml").write_text(
        'seiten:\n  - marke: "o2"\n    was: "Tarifübersicht"\n'
        '    url: "https://www.o2online.de/tarife/"\n', encoding="utf-8")

    class Antwort:
        text = _html(rumpf)

    monkeypatch.setattr(A, "fetch", lambda *a, **k: Antwort())
