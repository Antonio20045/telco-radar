"""Wahrheitstests fuer die Promo Uebersicht - jede Zahl gegen die Daten.

Die Marktrecherche hatte am 07.08.2026 rund 460 Tests, die Promo Uebersicht
KEINEN einzigen, der ihre gerenderte Seite ansah. Was dabei herauskam, hat
Antonio benannt: "Promo-Uebersicht ist richtig beschissen. Ganz neues
Layout, hier sind auch nirgendwo Bilder."

Gemessen war das exakt richtig, und zwei der Befunde waeren durch einen
Test dieser Art nie entstanden:

* 15 Screenshots lagen unter data/state/promo_images/, verwendet wurde
  genau EINER - und ausgerechnet der war mit 6 KB eine weisse Seite.
* die Karte "Was diese Woche auffaellt" zeigte denselben Angebotstitel
  zweimal hintereinander mit einem freistehenden Punkt am Ende, weil der
  Vorspann aus einem Digest geschnitten wurde, der gar keine Saetze hat.

Diese Datei prueft, was die Seite BEHAUPTET, gegen das, was in
promo_db.json und im Bildordner steht.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from telco_radar.report.html import render_site
from telco_radar.report.promo import prepare_promo_view


class _Quelle:
    """Minimalfassung einer promo_sources.yaml-Quelle."""

    def __init__(self, name, tier=2, internal_reference=False, crawlable=True):
        self.name = name
        self.url = f"https://{name.lower().replace(' ', '')}.test/"
        self.tier = tier
        self.group = ""
        self.internal_reference = internal_reference
        self.crawlable = crawlable


def _angebot(i, brand, score=None, status="aktiv", highlight=False,
             bild=None):
    e = {
        "id": f"id{i}", "brand": brand, "tier": 2,
        "headline": f"Aktion {i} von {brand}",
        "description": f"Beschreibung {i}.",
        "url": f"https://{brand.lower().replace(' ', '')}.test/aktion-{i}",
        "first_seen": "2026-07-20", "last_verified": "2026-08-05",
        "status": status, "valid_until": None,
    }
    if score is not None:
        e |= {"score": score, "highlight": highlight,
              "score_reason": f"Grund {i}.", "mechanic": "preisnachlass"}
    if bild:
        e |= {"image": f"bild-{i}-1280.jpg", "image_w": 1280, "image_h": 720,
              "image_kind": bild}
    return e


MARKEN = ["Alpha Mobil", "Beta Funk", "Gamma Tel", "Delta Connect"]
QUELLEN = [_Quelle(m) for m in MARKEN] + [
    _Quelle("Vodafone Deutschland", tier=1, internal_reference=True)]
EINTRAEGE = [
    _angebot(1, "Alpha Mobil", score=88, highlight=True, bild="angebot"),
    _angebot(2, "Alpha Mobil", score=70),
    _angebot(3, "Alpha Mobil", score=64),
    _angebot(4, "Beta Funk", score=81, highlight=True, bild="motiv"),
    _angebot(5, "Gamma Tel", score=52),
    _angebot(6, "Delta Connect", score=40),
    _angebot(7, "Delta Connect", status="ausgelaufen"),
    _angebot(8, "Vodafone Deutschland", score=60),
]
def _view(eintraege=None):
    return prepare_promo_view(eintraege or EINTRAEGE, QUELLEN, "2026-08-06")


# ----------------------------------------------------------------- Zahlen
def test_die_kopfzahlen_stimmen_mit_den_daten_ueberein():
    """Die drei Zahlen im Kopf sind die einzigen, die ein Leser ungeprueft
    uebernimmt - sie muessen zaehlbar sein."""
    view = _view()
    aktive = [e for e in EINTRAEGE if e["status"] == "aktiv"
              and e["brand"] != "Vodafone Deutschland"]
    assert view["active_total"] == len(aktive)
    assert view["brands_active"] == len({e["brand"] for e in aktive})
    # Vodafone zaehlt nicht als beobachteter Wettbewerber.
    assert view["brands_tracked"] == len(MARKEN)
    # highlight_count zaehlt die hervorgehobenen KARTEN (je Marke eine),
    # nicht die Eintraege - genau das steht auch auf der Seite.
    assert view["highlight_count"] == len(
        {e["brand"] for e in EINTRAEGE if e.get("highlight")})


def test_je_wettbewerber_genau_eine_karte_nach_score():
    """Die eine Form der Seite: gleiche Felder, gleiche Reihenfolge, je
    Marke einmal. Vorher standen hier vier Formen nebeneinander (Aufmacher,
    Beistellspalte, Markenraster, Ruhezone), und dieselbe Marke konnte in
    dreien davon auftauchen."""
    view = _view()
    assert [k["offer"]["id"] for k in view["karten"]] == ["id1", "id4", "id5", "id6"]
    marken = [k["brand"]["name"] for k in view["karten"]]
    assert len(marken) == len(set(marken))
    assert all(not k["brand"]["internal_reference"] for k in view["karten"])


def test_das_bild_gehoert_zum_angebot_und_kennzeichnet_sein_belegniveau():
    """Bis zum 07.08.2026 bekam jede MARKE ein Bild - denselben Screenshot
    fuer alle ihre Angebote. Jetzt haengt es am Angebot, und ein blosses
    Seitenmotiv sagt das auf der Karte."""
    view = _view()
    nach_id = {k["offer"]["id"]: k for k in view["karten"]}
    assert nach_id["id1"]["bild"] == "images/bild-1-1280.jpg"
    assert nach_id["id1"]["bild_ist_motiv"] is False
    assert nach_id["id4"]["bild_ist_motiv"] is True
    assert nach_id["id5"]["bild"] == ""       # kein Beleg, keine Behauptung
    assert view["mit_bild"] == 2


def test_eine_ruhige_woche_laesst_die_seite_nicht_leer():
    """Liegt KEIN Angebot ueber der Schwelle - am 07.08.2026 lag genau eines
    darueber, bei 22 laufenden Aktionen -, darf die Seite nicht leer
    aussehen. Die Karten stehen weiterhin, nur ohne Hervorhebung."""
    ruhig = [dict(e, highlight=False) for e in EINTRAEGE]
    view = prepare_promo_view(ruhig, QUELLEN, "2026-08-06")
    assert view["highlight_count"] == 0
    assert len(view["karten"]) == 4
    assert [k["offer"]["id"] for k in view["karten"]] == ["id1", "id4", "id5", "id6"]


def test_was_oben_als_karte_steht_wiederholt_sich_unten_nicht():
    view = _view()
    oben = {k["offer"]["id"] for k in view["karten"]} | {view["eigen"]["offer"]["id"]}
    unten = {o["id"] for b in view["marken"] for o in b["rest"]}
    assert not oben & unten
    # Verschwunden ist trotzdem nichts: jede sichtbare Aktion steht genau
    # einmal auf der Seite.
    sichtbar = {e["id"] for e in EINTRAEGE if e["status"] != "ausgelaufen"}
    assert oben | unten == sichtbar


def test_das_eigene_angebot_bleibt_ausserhalb_der_wertung():
    view = _view()
    assert view["eigen"]["brand"]["internal_reference"] is True
    assert all(not k["brand"]["internal_reference"] for k in view["karten"])


# ------------------------------------------------------------ leeres Bild
def test_ein_leerer_screenshot_wird_erkannt():
    """Der schaerfste Einzelbefund vom 07.08.2026: das einzige Bild der
    ganzen Seite war eine weisse 1280x720-Flaeche. Masse und Dateityp waren
    tadellos - zu sehen war nichts."""
    from telco_radar.report.bilder import ist_leer

    pytest.importorskip("PIL")
    from PIL import Image
    import io

    def als_jpeg(im):
        puffer = io.BytesIO()
        im.save(puffer, format="JPEG", quality=85)
        return puffer.getvalue()

    weiss = Image.new("RGB", (1280, 720), (255, 255, 255))
    assert ist_leer(als_jpeg(weiss)) is True
    assert ist_leer(b"kein Bild") is True

    # Gegenprobe: ein Bild mit Inhalt faellt nicht durch.
    import random
    rnd = random.Random(1)
    bunt = Image.new("RGB", (1280, 720))
    bunt.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
                  for _ in range(1280 * 720)])
    assert ist_leer(als_jpeg(bunt)) is False


def test_die_echten_screenshots_bestehen_die_pruefung():
    """Gegen die wirklich vorhandenen Dateien, nicht gegen erfundene: 14 der
    15 Screenshots vom 07.08.2026 haben Inhalt, telekom-deutschland.jpg
    nicht. Faellt diese Zusicherung, hat entweder die Schwelle oder die
    Aufnahme ein Problem."""
    from telco_radar.report.bilder import ist_leer

    ordner = Path(__file__).resolve().parent.parent / "data" / "state" / "promo_images"
    if not ordner.exists():
        pytest.skip("Kein Screenshot-Bestand im Arbeitsverzeichnis")
    bilder = sorted(p for p in ordner.iterdir() if p.suffix == ".jpg")
    if not bilder:
        pytest.skip("Kein Screenshot-Bestand im Arbeitsverzeichnis")
    leer = [p.name for p in bilder if ist_leer(p.read_bytes())]
    gut = len(bilder) - len(leer)
    assert gut >= 10, (
        f"Nur {gut} von {len(bilder)} Screenshots haben Inhalt; leer: {leer}")


# ------------------------------------------------------------- Vorspann
def test_ein_digest_wird_nicht_als_analyse_ausgegeben():
    """Der Fehler vom 06.08.2026, an seiner Wurzel: faellt der Promo-Editor
    aus, schreibt `build_digest()` eine Liste von Angebotstiteln unter
    dieselbe Ueberschrift wie die Prosa. Der Vorspann schnitt daraus den
    "ersten Satz" - und zeigte denselben Titel zweimal mit einem
    freistehenden Punkt am Ende."""
    from telco_radar.analyze.promo_editor import build_digest
    from telco_radar.report.html import _promo_lead

    digest = build_digest([_angebot(1, "Alpha Mobil")])
    # Der Titel steht genau EINMAL in der Zeile, nicht blank und nochmal als
    # Linktext.
    assert digest.count("Aktion 1 von Alpha Mobil") == 2  # Text + Quellenbasis
    assert "Aktion 1 von Alpha Mobil [" not in digest
    # Und der Vorspann erkennt, dass das keine Analyse ist.
    assert _promo_lead(digest) == ""


def test_echte_prosa_wird_weiterhin_als_vorspann_genommen():
    from telco_radar.report.html import _promo_lead

    prosa = ("## Was diese Woche auffaellt\n\nMehrere Anbieter senken den "
             "Einstiegspreis. Danach kommt noch mehr Text.\n")
    assert _promo_lead(prosa) == "Mehrere Anbieter senken den Einstiegspreis."


# ------------------------------------------------- die gerenderte Seite
@pytest.fixture
def promo_site(tmp_path):
    """Rendert die echte Seite mit der echten Konfiguration und dem echten
    Bildbestand - ein Test gegen erfundene Marken haette den leeren
    Screenshot nie gefunden."""
    from telco_radar.config import load_config

    wurzel = Path(__file__).resolve().parent.parent
    if not (wurzel / "data" / "state" / "promo_db.json").exists():
        pytest.skip("Kein Promo-Bestand im Arbeitsverzeichnis")
    site = tmp_path / "site"
    render_site(site, wurzel / "data" / "reports", load_config(wurzel))
    return site


def test_die_seite_zeigt_mindestens_zehn_echte_bilder(promo_site):
    """Abnahmekriterium 4 des Auftrags. Vorher: 2 <img> auf der ganzen
    Seite, eines davon das Logo."""
    soup = BeautifulSoup((promo_site / "promo" / "index.html")
                         .read_text(encoding="utf-8"), "html.parser")
    quellen = [img["src"] for img in soup.select("img[src]")
               if "images/" in img["src"] and "logo" not in img["src"]]
    assert len(set(quellen)) >= 10, (
        f"Nur {len(set(quellen))} verschiedene Bilder auf der Seite")
    for src in set(quellen):
        datei = (promo_site / "promo" / src).resolve()
        assert datei.exists(), f"Bildverweis ins Leere: {src}"


def test_der_leere_screenshot_wird_nicht_ausgeliefert(promo_site):
    """Er darf weder als Datei noch als Verweis auf der Seite stehen."""
    from telco_radar.report.bilder import ist_leer

    ordner = promo_site / "promo" / "images"
    assert ordner.exists()
    for bild in ordner.iterdir():
        assert not ist_leer(bild.read_bytes()), (
            f"Leeres Bild ausgeliefert: {bild.name}")


def test_kein_angebotstitel_steht_zweimal_hintereinander(promo_site):
    """Der Textfehler, den Antonio gesehen hat - als Test, nicht als
    Absichtserklaerung."""
    seite = (promo_site / "promo" / "index.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(seite, "html.parser")
    for block in soup.select(".promo-method-body, .paufmacher, .pz"):
        text = " ".join(block.get_text(" ", strip=True).split())
        assert " ." not in text, f"Freistehender Punkt: {text[:90]}"
    # Keine Schlagzeile der Seite steht doppelt in derselben Kachel.
    for kachel in soup.select(".pmarke"):
        titel = [a.get_text(" ", strip=True) for a in kachel.select(".szl")]
        assert len(titel) == len(set(titel)), f"Doppelter Titel: {titel}"


def test_keine_promo_ueberschrift_ist_abgeschnitten(promo_site):
    """Dieselbe Regel wie in der Marktrecherche, ueber dieselbe Klasse."""
    soup = BeautifulSoup((promo_site / "promo" / "index.html")
                         .read_text(encoding="utf-8"), "html.parser")
    schlagzeilen = [e.get_text(" ", strip=True) for e in soup.select(".szl")]
    assert schlagzeilen, "Die Seite traegt keine erkennbare Schlagzeile"
    for t in schlagzeilen:
        assert not t.endswith("…"), f"Abgeschnittene Ueberschrift: {t}"


def test_die_kopfzahlen_der_seite_stimmen_mit_der_datenbank(promo_site):
    """Die Zahlen im Kopf, gegen promo_db.json gerechnet - nicht gegen die
    Zahlen, die dieselbe Funktion ausgerechnet hat."""
    from telco_radar.config import load_config
    from telco_radar.promo_config import load_promo_config

    wurzel = Path(__file__).resolve().parent.parent
    cfg = load_config(wurzel)
    promo_cfg = load_promo_config(cfg.root)
    db = json.loads((wurzel / "data" / "state" / "promo_db.json")
                    .read_text(encoding="utf-8"))
    intern = {s.name for s in promo_cfg.sources if s.internal_reference}
    crawlbar = {s.name for s in promo_cfg.sources
                if getattr(s, "crawlable", True)}
    aktiv = [e for e in db.get("entries", [])
             if e.get("status") == "aktiv"
             and e.get("brand") in crawlbar - intern]

    seite = (promo_site / "promo" / "index.html").read_text(encoding="utf-8")
    assert f"<b>{len(aktiv)}</b> laufende Aktionen" in seite
    assert f"<b>{len({e['brand'] for e in aktiv})}</b> von " in seite
    assert f"von {len(crawlbar - intern)} beobachteten Wettbewerbern" in seite


def test_die_promo_quellenseite_bleibt(promo_site):
    """Sie ist die Belegebene und war ausdruecklich nicht Teil des Umbaus."""
    assert (promo_site / "promo" / "quellen.html").exists()
    assert "Quellen" in (promo_site / "promo" / "index.html").read_text(
        encoding="utf-8")
