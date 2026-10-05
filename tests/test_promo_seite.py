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
import shutil
from pathlib import Path

import pytest
from bestand_pfad import BILDER_ZUSTAND, WURZEL, ZUSTAND, abbild
from bs4 import BeautifulSoup

from telco_radar.analyze.promo_ranker import MECHANICS
from telco_radar.report.html import render_site
from telco_radar.report.promo import prepare_promo_view


class _Quelle:
    """Minimalfassung einer promo_sources.yaml-Quelle."""

    def __init__(
        self, name, tier=2, internal_reference=False, crawlable=True, rang=None
    ):
        self.name = name
        self.url = f"https://{name.lower().replace(' ', '')}.test/"
        self.tier = tier
        self.group = ""
        self.internal_reference = internal_reference
        self.crawlable = crawlable
        self.rang = rang
        self.reach = None


def _angebot(i, brand, score=None, status="aktiv", highlight=False, bild=None):
    e = {
        "id": f"id{i}",
        "brand": brand,
        "tier": 2,
        "headline": f"Aktion {i} von {brand}",
        "description": f"Beschreibung {i}.",
        "url": f"https://{brand.lower().replace(' ', '')}.test/aktion-{i}",
        "first_seen": "2026-07-20",
        "last_verified": "2026-08-05",
        "status": status,
        "valid_until": None,
    }
    if score is not None:
        e |= {
            "score": score,
            "highlight": highlight,
            "score_reason": f"Grund {i}.",
            "mechanic": "preisnachlass",
        }
    if bild:
        e |= {
            "image": f"bild-{i}-1280.jpg",
            "image_w": 1280,
            "image_h": 720,
            "image_kind": bild,
        }
    return e


MARKEN = ["Alpha Mobil", "Beta Funk", "Gamma Tel", "Delta Connect"]
QUELLEN = [_Quelle(m, rang=i) for i, m in enumerate(MARKEN, start=1)] + [
    _Quelle("Vodafone Deutschland", tier=1, internal_reference=True, rang=5)
]
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


def test_die_kennzahlen_stimmen_mit_den_daten_ueberein():
    """Die Zahlen, mit denen die Seite rechnet - sie muessen zaehlbar sein.
    Im Kopf steht seit dem 08.08.2026 keine davon mehr (Antonio: die vielen
    Kommentare machen die Seite unruhig); sie tragen die Marktlage-Balken
    und die Wahrheitstests."""
    view = _view()
    aktive = [
        e
        for e in EINTRAEGE
        if e["status"] == "aktiv" and e["brand"] != "Vodafone Deutschland"
    ]
    assert view["active_total"] == len(aktive)
    assert view["brands_active"] == len({e["brand"] for e in aktive})
    assert view["brands_tracked"] == len(MARKEN)
    assert view["highlight_count"] == len([e for e in EINTRAEGE if e.get("highlight")])


def test_je_marke_ein_block_die_bloecke_nach_anbieterrang():
    """Die eine Form der Seite: je Marke ein Block, darin ihre Aktionen in
    gleichen Karten. Vorher standen die staerkste Aktion oben im
    Auswahlraster und alle uebrigen unten in einer eigenen Zeilenwand -
    zwei Darstellungen derselben Sache.

    Die Bloecke stehen nach dem RANG DES ANBIETERS (config/promo_sources.yaml,
    Feld `rang`), nicht nach dem Score ihrer staerksten Aktion."""
    view = _view()
    assert [b["name"] for b in view["bloecke"]] == [
        "Alpha Mobil",
        "Beta Funk",
        "Gamma Tel",
        "Delta Connect",
    ]
    assert [b["lead"]["offer"]["id"] for b in view["bloecke"]] == [
        "id1",
        "id4",
        "id5",
        "id6",
    ]
    alpha = view["bloecke"][0]
    assert [k["offer"]["id"] for k in alpha["weitere"]] == ["id2", "id3"]
    assert all(not b["internal_reference"] for b in view["bloecke"])


def test_eine_starke_aktion_hebt_eine_kleine_marke_nicht_nach_oben():
    """Der Punkt der Rangfolge. Am 08.08.2026 stand Otelo auf Platz eins und
    die Telekom auf Platz zehn, weil deren JS-Seiten in dem Lauf nur zwei
    Angebote hergaben - Antonio: "die groessten Anbieter wie Telekom etc. an
    erster Stelle". Ein Spitzenangebot des Kleinsten darf die Seite nicht
    umsortieren; es steht innerhalb SEINES Blocks vorn."""
    laut = [
        dict(e, score=100, highlight=True) if e["brand"] == "Delta Connect" else e
        for e in EINTRAEGE
    ]
    view = prepare_promo_view(laut, QUELLEN, "2026-08-06")
    assert [b["name"] for b in view["bloecke"]] == [
        "Alpha Mobil",
        "Beta Funk",
        "Gamma Tel",
        "Delta Connect",
    ]
    assert view["bloecke"][-1]["top_score"] == 100


def test_das_bild_gehoert_zum_angebot_und_kennzeichnet_sein_belegniveau():
    """Bis zum 07.08.2026 bekam jede MARKE ein Bild - denselben Screenshot
    fuer alle ihre Angebote. Jetzt haengt es am Angebot, und ein blosses
    Seitenmotiv sagt das auf der Karte."""
    view = _view()
    nach_id = {k["offer"]["id"]: k for k in view["karten"]}
    assert nach_id["id1"]["bild"] == "images/bild-1-1280.jpg"
    assert nach_id["id1"]["bild_ist_motiv"] is False
    assert nach_id["id4"]["bild_ist_motiv"] is True
    assert nach_id["id5"]["bild"] == ""
    assert view["mit_bild"] == 2


def test_eine_ruhige_woche_laesst_die_seite_nicht_leer():
    """Liegt KEIN Angebot ueber der Schwelle - am 07.08.2026 lag genau eines
    darueber, bei 22 laufenden Aktionen -, darf die Seite nicht leer
    aussehen. Die Bloecke stehen weiterhin, nur ohne Hervorhebung."""
    ruhig = [dict(e, highlight=False) for e in EINTRAEGE]
    view = prepare_promo_view(ruhig, QUELLEN, "2026-08-06")
    assert view["highlight_count"] == 0
    assert len(view["bloecke"]) == 4
    assert [b["lead"]["offer"]["id"] for b in view["bloecke"]] == [
        "id1",
        "id4",
        "id5",
        "id6",
    ]


def test_jede_sichtbare_aktion_steht_genau_einmal_auf_der_seite():
    """Die Regel, an der der Umbau haengt. Vorher konnte dieselbe Marke in
    zwei Darstellungen auftauchen; jetzt gibt es einen Ort je Aktion."""
    view = _view()
    gezeigt = [k["offer"]["id"] for b in view["bloecke"] for k in b["karten"]]
    gezeigt += [k["offer"]["id"] for k in view["eigen"]["karten"]]
    assert len(gezeigt) == len(set(gezeigt))
    sichtbar = {e["id"] for e in EINTRAEGE if e["status"] != "ausgelaufen"}
    assert set(gezeigt) == sichtbar


def test_das_eigene_angebot_bleibt_ausserhalb_der_wertung():
    view = _view()
    assert view["eigen"]["internal_reference"] is True
    assert all(not k["brand"]["internal_reference"] for k in view["karten"])


def test_ein_leerer_screenshot_wird_erkannt():
    """Der schaerfste Einzelbefund vom 07.08.2026: das einzige Bild der
    ganzen Seite war eine weisse 1280x720-Flaeche. Masse und Dateityp waren
    tadellos - zu sehen war nichts."""
    from telco_radar.report.bilder import ist_leer

    pytest.importorskip("PIL")
    import io

    from PIL import Image

    def als_jpeg(im):
        puffer = io.BytesIO()
        im.save(puffer, format="JPEG", quality=85)
        return puffer.getvalue()

    weiss = Image.new("RGB", (1280, 720), (255, 255, 255))
    assert ist_leer(als_jpeg(weiss)) is True
    assert ist_leer(b"kein Bild") is True

    import random

    rnd = random.Random(1)
    bunt = Image.new("RGB", (1280, 720))
    bunt.putdata(
        [
            (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256))
            for _ in range(1280 * 720)
        ]
    )
    assert ist_leer(als_jpeg(bunt)) is False


def test_die_echten_screenshots_bestehen_die_pruefung():
    """Gegen die wirklich vorhandenen Dateien, nicht gegen erfundene: 14 der
    15 Screenshots vom 07.08.2026 haben Inhalt, telekom-deutschland.jpg
    nicht. Faellt diese Zusicherung, hat entweder die Schwelle oder die
    Aufnahme ein Problem."""
    from telco_radar.report.bilder import ist_leer

    ordner = BILDER_ZUSTAND / "promo_images"
    bilder = sorted(p for p in ordner.iterdir() if p.suffix == ".jpg")
    leer = [p.name for p in bilder if ist_leer(p.read_bytes())]
    gut = len(bilder) - len(leer)
    assert gut >= 10, (
        f"Nur {gut} von {len(bilder)} Screenshots haben Inhalt; leer: {leer}"
    )


def test_ein_digest_wird_nicht_als_analyse_ausgegeben():
    """Der Fehler vom 06.08.2026, an seiner Wurzel: faellt der Promo-Editor
    aus, schreibt `build_digest()` eine Liste von Angebotstiteln unter
    dieselbe Ueberschrift wie die Prosa. Der Vorspann schnitt daraus den
    "ersten Satz" - und zeigte denselben Titel zweimal mit einem
    freistehenden Punkt am Ende."""
    from telco_radar.analyze.promo_editor import build_digest
    from telco_radar.report.html import _promo_lead

    digest = build_digest([_angebot(1, "Alpha Mobil")])
    assert digest.count("Aktion 1 von Alpha Mobil") == 2
    assert "Aktion 1 von Alpha Mobil [" not in digest
    assert _promo_lead(digest) == ""


def test_echte_prosa_wird_weiterhin_als_vorspann_genommen():
    from telco_radar.report.html import _promo_lead

    prosa = (
        "## Was diese Woche auffaellt\n\nMehrere Anbieter senken den "
        "Einstiegspreis. Danach kommt noch mehr Text.\n"
    )
    assert _promo_lead(prosa) == "Mehrere Anbieter senken den Einstiegspreis."


def test_eine_klein_geschriebene_marke_beendet_den_vorspann_trotzdem():
    """Der Vorspann ist seit dem 08.08.2026 der EINZIGE Leitsatz der Seite -
    er darf nicht auf 280 Zeichen abgeschnitten sein. Genau das passierte im
    Bericht vom 07.08.2026: die allgemeine Satzende-Regel verlangt hinter dem
    Punkt einen Grossbuchstaben, und der naechste Satz begann mit 'winSIM'.
    Die halbe Promo-Landschaft heisst so (congstar, otelo, simplytel,
    mobilcom-debitel)."""
    from telco_radar.report.html import _promo_lead

    prosa = (
        "## Was diese Woche auffaellt\n\nDie Rabattschlacht hat eine neue "
        "Eskalationsstufe erreicht. winSIM senkt die monatlichen "
        "Grundgebuehren seiner gesamten 5G-Allnet-Flat-Palette drastisch, "
        "und auch simplytel zieht mit stark reduzierten Monatspreisen "
        "sowie einem dauerhaften Speed-Upgrade nach.\n"
    )
    assert (
        _promo_lead(prosa)
        == "Die Rabattschlacht hat eine neue Eskalationsstufe erreicht."
    )
    kurz = (
        "## Was diese Woche auffaellt\n\nMehrere Marken, z. B. congstar, "
        "senken den Preis. Danach mehr Text.\n"
    )
    assert _promo_lead(kurz) == "Mehrere Marken, z. B. congstar, senken den Preis."


@pytest.fixture
def promo_site(tmp_path):
    """Rendert die echte Seite mit der echten Konfiguration und dem echten
    Bildbestand - ein Test gegen erfundene Marken haette den leeren
    Screenshot nie gefunden."""
    from telco_radar.config import load_config

    berichte = abbild(tmp_path)
    for name in ("promo_images", "report_images"):
        shutil.copytree(BILDER_ZUSTAND / name, tmp_path / "data" / "state" / name)
    site = tmp_path / "site"
    render_site(site, berichte, load_config(tmp_path))
    return site


def test_die_seite_zeigt_mindestens_zehn_echte_bilder(promo_site):
    """Abnahmekriterium 4 des Auftrags. Vorher: 2 <img> auf der ganzen
    Seite, eines davon das Logo."""
    soup = BeautifulSoup(
        (promo_site / "promo" / "index.html").read_text(encoding="utf-8"), "html.parser"
    )
    quellen = [
        img["src"]
        for img in soup.select("img[src]")
        if "images/" in img["src"] and "logo" not in img["src"]
    ]
    assert len(set(quellen)) >= 10, (
        f"Nur {len(set(quellen))} verschiedene Bilder auf der Seite"
    )
    for src in set(quellen):
        datei = (promo_site / "promo" / src).resolve()
        assert datei.exists(), f"Bildverweis ins Leere: {src}"


def test_der_leere_screenshot_wird_nicht_ausgeliefert(promo_site):
    """Er darf weder als Datei noch als Verweis auf der Seite stehen."""
    from telco_radar.report.bilder import ist_leer

    ordner = promo_site / "promo" / "images"
    assert ordner.exists()
    for bild in ordner.iterdir():
        assert not ist_leer(bild.read_bytes()), f"Leeres Bild ausgeliefert: {bild.name}"


def test_kein_angebotstitel_steht_zweimal_hintereinander(promo_site):
    """Der Textfehler, den Antonio gesehen hat - als Test, nicht als
    Absichtserklaerung."""
    seite = (promo_site / "promo" / "index.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(seite, "html.parser")
    for block in soup.select(".promo-method-body, .paufmacher, .pz"):
        text = " ".join(block.get_text(" ", strip=True).split())
        assert " ." not in text, f"Freistehender Punkt: {text[:90]}"
    for kachel in soup.select(".pmarke"):
        titel = [a.get_text(" ", strip=True) for a in kachel.select(".szl")]
        assert len(titel) == len(set(titel)), f"Doppelter Titel: {titel}"


def test_keine_promo_ueberschrift_ist_abgeschnitten(promo_site):
    """Dieselbe Regel wie in der Marktrecherche, ueber dieselbe Klasse."""
    soup = BeautifulSoup(
        (promo_site / "promo" / "index.html").read_text(encoding="utf-8"), "html.parser"
    )
    schlagzeilen = [e.get_text(" ", strip=True) for e in soup.select(".szl")]
    assert schlagzeilen, "Die Seite traegt keine erkennbare Schlagzeile"
    for t in schlagzeilen:
        assert not t.endswith("…"), f"Abgeschnittene Ueberschrift: {t}"


def test_die_zahl_der_marktlage_stimmt_mit_der_datenbank(promo_site):
    """Die einzigen Zahlen, die auf der Seite stehen: wie viele MARKEN eine
    Mechanik fahren. Gerechnet gegen promo_db.json, nicht gegen die
    Funktion, die sie ausgerechnet hat.

    Die Zahlenzeile im Kopf ("50 laufende Aktionen bei 12 von 14 ...") ist
    am 08.08.2026 gefallen - Antonio: die Seite wirkt unruhig durch die
    vielen Kommentare. Der Test bleibt und wandert mit."""
    from telco_radar.config import load_config
    from telco_radar.promo_config import load_promo_config

    cfg = load_config(WURZEL)
    promo_cfg = load_promo_config(cfg.root)
    db = json.loads((ZUSTAND / "promo_db.json").read_text(encoding="utf-8"))
    intern = {s.name for s in promo_cfg.sources if s.internal_reference}
    crawlbar = {s.name for s in promo_cfg.sources if getattr(s, "crawlable", True)}
    sichtbar = [
        e
        for e in db.get("entries", [])
        if e.get("status") in ("aktiv", "evtl. ausgelaufen")
        and e.get("brand") in crawlbar - intern
    ]

    soup = BeautifulSoup(
        (promo_site / "promo" / "index.html").read_text(encoding="utf-8"), "html.parser"
    )
    zeilen = soup.select(".promo-lage .lage-zeile")
    assert zeilen, "Die Marktlage fehlt auf der Seite"
    assert len(zeilen) <= 5, "Die Marktlage soll eine schmale Leiste bleiben"
    for zeile in zeilen:
        label = zeile.select_one(".lage-label").get_text(strip=True)
        gezaehlt = int(zeile.select_one(".lage-zahl").get_text(strip=True).split()[0])
        marken = {
            e["brand"]
            for e in sichtbar
            if MECHANICS.get(e.get("mechanic") or "") == label
        }
        assert gezaehlt == len(marken), f"{label}: {gezaehlt} statt {len(marken)}"

    assert "laufende Aktionen bei" not in soup.get_text(" ")


def test_die_seite_zeigt_kein_motiv_zweimal(promo_site):
    """Zwei gleiche Kacheln nebeneinander lesen sich als Fehler - am
    08.08.2026 stand bei O2 derselbe Router unter zwei Schlagzeilen."""
    soup = BeautifulSoup(
        (promo_site / "promo" / "index.html").read_text(encoding="utf-8"), "html.parser"
    )
    quellen = [img["src"] for img in soup.select(".pk-bild img[src]")]
    assert len(quellen) == len(set(quellen)), "Ein Motiv steht mehrfach auf der Seite"
    assert soup.select(".pmarke .pk-bild--typo"), "keine Schriftkachel, nichts geprueft"
    for block in soup.select(".pmarke"):
        kacheln = [
            k.get_text(" ", strip=True)
            for k in block.select(".pk-bild--typo .pk-typo-zahl")
        ]
        marke = block.select_one(".pmarke-name").get_text(strip=True)
        assert len(kacheln) == len(set(kacheln)), (
            f"Doppelte Schriftkachel bei {marke}: {kacheln}"
        )


def _bildkaesten(seite) -> list[dict]:
    return seite.eval_on_selector_all(
        ".pk-bild img",
        """els => els.map(e => ({
            geladen: e.complete && e.naturalWidth > 0,
            farbe: getComputedStyle(e).backgroundColor,
            bild: getComputedStyle(e).backgroundImage,
            hoehe: e.getBoundingClientRect().height}))""",
    )


def test_ein_ungeladenes_bild_malt_keinen_grauen_kasten(promo_site, chromium):
    """Der "leere Bildkasten", den Antonio auf der simplytel-Karte sah:
    `loading="lazy"` laesst ein Bild ausserhalb des Sichtfensters ungeladen,
    und eine Hintergrundfarbe auf dem <img> macht daraus einen grauen
    16:9-Kasten. Im Browser gemessen, ohne zu scrollen: kein Bild der
    Promo-Seite, geladen oder nicht, malt eine Fuellung."""
    seite = chromium.new_page(viewport={"width": 1440, "height": 900})
    try:
        seite.goto((promo_site / "promo" / "index.html").as_uri(), wait_until="load")
        kaesten = _bildkaesten(seite)
    finally:
        seite.close()
    assert len(kaesten) >= 10, kaesten
    ungeladen = [k for k in kaesten if not k["geladen"]]
    assert ungeladen, "jedes Bild ist geladen - der Fall wird nicht geprüft"
    assert any(k["hoehe"] > 0 for k in ungeladen), ungeladen
    for k in kaesten:
        assert k["farbe"] == "rgba(0, 0, 0, 0)", k
        assert k["bild"] == "none", k


def test_die_promo_quellenseite_bleibt(promo_site):
    """Sie ist die Belegebene und war ausdruecklich nicht Teil des Umbaus."""
    assert (promo_site / "promo" / "quellen.html").exists()
    assert "Quellen" in (promo_site / "promo" / "index.html").read_text(
        encoding="utf-8"
    )


def test_jede_karte_traegt_ein_motiv(promo_site):
    """Antonio am 08.08.2026: "da fehlen bei einigen Aktionen die Bilder, das
    wirkt so richtig scheisse." Gemessen an der Ausgabe vom 8.8. hatten 37
    von 77 Karten gar nichts an der Motivstelle - nur die grossen bekamen
    ohne Bild eine Schriftkachel -, und weil eine Rasterzeile so hoch ist
    wie ihre hoechste Karte, stand neben jedem Bild eine handbreite Luecke.
    Ein Bild kann fehlen (es muss belegt sein), ein MOTIV nie."""
    soup = BeautifulSoup(
        (promo_site / "promo" / "index.html").read_text(encoding="utf-8"), "html.parser"
    )
    karten = soup.select(".promo-karten .pkarte")
    assert karten
    ohne = [
        k.select_one(".szl").get_text(" ", strip=True)
        for k in karten
        if not k.select_one(".pk-bild")
    ]
    assert not ohne, f"{len(ohne)} Karten ohne Motiv, z. B. {ohne[:3]}"
    for kasten in soup.select(".pk-bild"):
        assert kasten.select_one("img") or kasten.get_text(strip=True)


def test_die_marken_stehen_in_der_reihenfolge_der_konfiguration(promo_site):
    """Die Rangfolge der Anbieter ist gepflegt (config/promo_sources.yaml,
    Feld `rang`) - die Seite muss ihr folgen und nicht dem Score des Tages.
    Am 08.08.2026 stand Otelo auf Platz eins und die Telekom auf Platz
    zehn."""
    from telco_radar.promo_config import load_promo_config

    soup = BeautifulSoup(
        (promo_site / "promo" / "index.html").read_text(encoding="utf-8"), "html.parser"
    )
    gezeigt = [
        b.select_one(".pmarke-name").get_text(strip=True)
        for b in soup.select(".pmarke")
    ]
    cfg = load_promo_config(Path(__file__).resolve().parent.parent)
    rang = {s.name: s.rang for s in cfg.sources}
    wettbewerber = [n for n in gezeigt if not n.startswith("Vodafone")]
    assert wettbewerber == sorted(wettbewerber, key=lambda n: rang[n])
    assert (
        not gezeigt
        or gezeigt[-1].startswith("Vodafone")
        or "Vodafone Deutschland" not in gezeigt
    )


def test_jede_marke_der_konfiguration_hat_einen_eindeutigen_rang():
    """Ein vergessener oder doppelter Rang faellt auf der Seite nicht auf -
    zwei Marken mit demselben Rang stuenden nach Zufall, eine ohne Rang
    rutschte ans Ende. Also wird die Konfiguration selbst geprueft."""
    from telco_radar.promo_config import load_promo_config

    cfg = load_promo_config(Path(__file__).resolve().parent.parent)
    raenge = [s.rang for s in cfg.sources]
    assert all(r for r in raenge), [s.name for s in cfg.sources if not s.rang]
    assert len(set(raenge)) == len(raenge), sorted(raenge)
    mno = [s.rang for s in cfg.sources if s.tier == 1]
    assert max(mno) < min(s.rang for s in cfg.sources if s.tier != 1)
