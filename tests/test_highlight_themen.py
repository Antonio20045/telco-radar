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
    assert ht.finde_kandidaten(LAUNCH[:4] + RAUSCHEN) == []


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
    nachschlag = [
        _meldung("https://e.example/9", "Galaxy Fold8 nun auch in Indien", "Quelle E"),
        _meldung("https://f.example/10", "Samsung senkt Preis des Galaxy Fold8", "Quelle F"),
        _meldung("https://g.example/12", "Galaxy Fold8 ab Freitag im Handel", "Quelle G"),
        _meldung("https://e.example/13", "Galaxy Fold8 in Japan ausverkauft", "Quelle E"),
        _meldung("https://h.example/14", "Netzbetreiber buendeln Galaxy Fold8", "Quelle H"),
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
