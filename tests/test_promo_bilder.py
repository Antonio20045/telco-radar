"""Tests fuer die Bildzuordnung der Promo-Uebersicht (promo_bilder.py) -
reine Zuordnungslogik, offline (der Abruf wird ersetzt).

Das Modul beantwortet eine Frage, die vorher niemand gestellt hat: WELCHES
Bild einer Aktionsseite gehoert zu WELCHEM Angebot? Bis zum 07.08.2026 gab
es je Marke einen Screenshot ihrer Startseite, den alle ihre Angebote
teilten. Die Tests hier halten fest, dass die Zuordnung belegt sein muss -
und dass ein blosses Seitenmotiv sich als solches zu erkennen gibt.
"""
from __future__ import annotations

from collections import Counter

from telco_radar import promo_bilder


def _kand(src, anchor="", context="", hint_w=0):
    return {"src": src, "anchor": anchor, "context": context, "hint_w": hint_w}


def _angebot(eid="a1", headline="Allnet Flat M mit 125 GB",
             description="", url="https://marke.test/tarife/allnet-m/"):
    return {"id": eid, "headline": headline, "description": description,
            "url": url}


# ----------------------------------------------------------- die Stufen
def test_der_anker_schlaegt_alles_andere():
    """Stufe 1: das Bild steht im Link des Angebots. Das ist keine
    Heuristik, sondern die Struktur der Seite."""
    kandidaten = [
        _kand("https://marke.test/b/text.jpg",
              context="Allnet Flat M mit 125 GB Datenvolumen"),
        _kand("https://marke.test/b/anker.jpg",
              anchor="https://marke.test/tarife/allnet-m/"),
    ]
    bewertet = promo_bilder.rangfolge(_angebot(), kandidaten)
    assert bewertet[0][1]["src"].endswith("anker.jpg")
    assert bewertet[0][0] >= 3.0


def test_derselbe_pfad_mit_anderen_parametern_zaehlt_noch():
    """Stufe 2: `.../allnet-m/?tarif=s` und `.../allnet-m#angebot` sind
    dieselbe Detailseite - genau so unterscheiden sich Tiefenlink und
    Bildanker in der Praxis."""
    kandidaten = [_kand("https://marke.test/b/x.jpg",
                        anchor="https://marke.test/tarife/allnet-m?tarif=s")]
    bewertet = promo_bilder.rangfolge(_angebot(), kandidaten)
    assert 2.0 <= bewertet[0][0] < 3.0


def test_ein_fremder_anker_belegt_nichts():
    kandidaten = [_kand("https://marke.test/b/x.jpg",
                        anchor="https://marke.test/ganz/woanders/")]
    assert promo_bilder.rangfolge(_angebot(), kandidaten) == []


def test_seltene_woerter_belegen_haeufige_nicht():
    """Stufe 3, und der Grund fuer die 1/Haeufigkeit-Gewichtung: "Tarif"
    steht neben jedem Bild einer Tarifseite, "Kinder-Smartwatch" neben
    genau einem. Dieselbe Rechnung wie beim roten Faden der Titelseite."""
    angebot = _angebot(headline="imoo Kinder-Smartwatch mit Kinogutschein",
                       url="")
    kandidaten = [_kand(f"https://marke.test/b/tarif{i}.jpg",
                        context="Tarif Angebot Handy") for i in range(8)]
    kandidaten.append(_kand("https://marke.test/b/watch.jpg",
                            context="imoo Kinder-Smartwatch Z1"))
    bewertet = promo_bilder.rangfolge(angebot, kandidaten,
                                      promo_bilder._haeufigkeiten(kandidaten))
    assert [k["src"] for _, k in bewertet] == ["https://marke.test/b/watch.jpg"]


def test_ein_wort_das_ueberall_steht_belegt_gar_nichts():
    angebot = _angebot(headline="Tarif Angebot", url="")
    kandidaten = [_kand(f"https://marke.test/b/{i}.jpg", context="Tarif Angebot")
                  for i in range(6)]
    assert promo_bilder.rangfolge(
        angebot, kandidaten, promo_bilder._haeufigkeiten(kandidaten)) == []


# ---------------------------------------------------------- die Vergabe
def test_jedes_bild_wird_hoechstens_einmal_vergeben():
    """Zwei Kacheln nebeneinander mit demselben Motiv lesen sich als
    Fehler; im Zweifel ist eine Zeile die ehrlichere Darstellung."""
    angebote = [_angebot("a1", url="https://marke.test/x/"),
                _angebot("a2", url="https://marke.test/x/")]
    kandidaten = [_kand("https://marke.test/b/eins.jpg",
                        anchor="https://marke.test/x/")]
    zuordnung = promo_bilder.zuordnen(angebote, kandidaten)
    assert zuordnung["a1"]["quellen"] == ["https://marke.test/b/eins.jpg"]
    assert "a2" not in zuordnung


def test_bis_zu_drei_ersatzkandidaten_je_angebot():
    """Der erste Kandidat kann beim Abruf durchfallen (zu klein, 403,
    kaputt) - ein zweiter Versuch ist billiger als eine leere Kachel."""
    kandidaten = [_kand(f"https://marke.test/b/{i}.jpg",
                        anchor="https://marke.test/tarife/allnet-m/")
                  for i in range(5)]
    zuordnung = promo_bilder.zuordnen([_angebot()], kandidaten)
    assert len(zuordnung["a1"]["quellen"]) == 3


def test_logos_verbrauchen_keinen_kandidatenplatz():
    """Gemessen bei ALDI TALK: `aldilogo.png` stand ganz oben auf der Seite
    und gewann damit die Motivstufe, obwohl der Abruf es hinterher ohnehin
    verworfen haette."""
    kandidaten = [_kand("https://marke.test/coremedias/aldilogo.png", hint_w=900),
                  _kand("https://marke.test/b/kampagne.jpg", hint_w=1300)]
    zuordnung = promo_bilder.zuordnen([_angebot(url="")], kandidaten)
    assert zuordnung["a1"]["quellen"] == ["https://marke.test/b/kampagne.jpg"]


def test_das_seitenmotiv_geht_nur_an_das_staerkste_angebot():
    """Stufe 4 belegt nur, WOMIT die Marke wirbt - nicht, welches ihrer
    acht Angebote gemeint ist. Deshalb bekommt es genau eine Karte, und die
    Karte schreibt es dazu (art="motiv")."""
    angebote = [_angebot("a1", url=""), _angebot("a2", url=""),
                _angebot("a3", url="")]
    kandidaten = [_kand("https://marke.test/b/buehne.jpg", hint_w=1600),
                  _kand("https://marke.test/b/zweitens.jpg", hint_w=1600)]
    zuordnung = promo_bilder.zuordnen(angebote, kandidaten)
    assert list(zuordnung) == ["a1"]
    assert zuordnung["a1"]["art"] == "motiv"
    assert zuordnung["a1"]["quellen"][0].endswith("buehne.jpg")


def test_ein_belegtes_bild_verdraengt_das_seitenmotiv():
    angebote = [_angebot("a1", url="https://marke.test/tarife/allnet-m/")]
    kandidaten = [_kand("https://marke.test/b/buehne.jpg", hint_w=1600),
                  _kand("https://marke.test/b/echt.jpg",
                        anchor="https://marke.test/tarife/allnet-m/")]
    zuordnung = promo_bilder.zuordnen(angebote, kandidaten)
    assert zuordnung["a1"]["art"] == "angebot"
    assert zuordnung["a1"]["quellen"][0].endswith("echt.jpg")


def test_testsiegel_werden_nie_zum_seitenmotiv():
    """Sie heissen nach ihrem Herausgeber, nicht nach "logo" - der
    URL-Muellfilter fasst sie nicht. Ihr alt-Text tut es (congstar bindet
    drei davon in 1920 px ein)."""
    kandidaten = [
        _kand("https://marke.test/b/csm_tuev-saarland.jpg", hint_w=1920,
              context='TÜV Saarland Siegel mit der Bewertung "SEHR GUT"'),
        _kand("https://marke.test/b/csm_kampagne.jpg", hint_w=1920,
              context="Sommeraktion"),
    ]
    zuordnung = promo_bilder.zuordnen([_angebot(url="")], kandidaten)
    assert zuordnung["a1"]["quellen"] == ["https://marke.test/b/csm_kampagne.jpg"]


def test_ohne_kandidaten_bleibt_die_zuordnung_leer():
    assert promo_bilder.zuordnen([_angebot()], []) == {}
    assert promo_bilder.zuordnen([], [_kand("https://marke.test/b/x.jpg")]) == {}


# ------------------------------------------------------------ der Abruf
def test_hole_bilder_stempelt_die_felder_ein(tmp_path, monkeypatch):
    monkeypatch.setattr(promo_bilder, "lade_und_lege_ab",
                        lambda url, *a, **kw: ("abc-1280.jpg", 1280, 720))
    eintraege = {"a1": {"id": "a1"}}
    bilanz = promo_bilder.hole_bilder(
        {"a1": {"quellen": ["https://marke.test/b/x.jpg"], "art": "motiv"}},
        eintraege, tmp_path)
    assert eintraege["a1"]["image"] == "abc-1280.jpg"
    assert eintraege["a1"]["image_w"] == 1280
    assert eintraege["a1"]["image_src"] == "https://marke.test/b/x.jpg"
    assert eintraege["a1"]["image_kind"] == "motiv"
    assert bilanz == Counter(geprueft=1, geladen=1)


def test_hole_bilder_nimmt_den_naechsten_kandidaten(tmp_path, monkeypatch):
    versuche = []

    def _fake(url, *a, **kw):
        versuche.append(url)
        return ("zwei-1280.jpg", 900, 500) if url.endswith("zwei.jpg") else None

    monkeypatch.setattr(promo_bilder, "lade_und_lege_ab", _fake)
    eintraege = {"a1": {"id": "a1"}}
    promo_bilder.hole_bilder(
        {"a1": {"quellen": ["https://marke.test/eins.jpg",
                            "https://marke.test/zwei.jpg"], "art": "angebot"}},
        eintraege, tmp_path)
    assert len(versuche) == 2
    assert eintraege["a1"]["image"] == "zwei-1280.jpg"


def test_ein_gescheiterter_abruf_loescht_den_alten_verweis(tmp_path, monkeypatch):
    """Sonst zeigt die Seite auf eine Datei, die `raeume_auf()` als
    unreferenziert loescht - genau so entstanden am 06.08.2026 vier
    Meldungen mit `image`, aber ohne Datei."""
    monkeypatch.setattr(promo_bilder, "lade_und_lege_ab", lambda *a, **kw: None)
    eintraege = {"a1": {"id": "a1", "image": "alt.jpg", "image_w": 800,
                        "image_h": 450, "image_src": "https://alt.test/a.jpg",
                        "image_kind": "angebot"}}
    bilanz = promo_bilder.hole_bilder(
        {"a1": {"quellen": ["https://marke.test/neu.jpg"], "art": "angebot"}},
        eintraege, tmp_path)
    assert "image" not in eintraege["a1"]
    assert "image_kind" not in eintraege["a1"]
    assert bilanz["ohne_bild"] == 1


def test_ein_unveraendertes_bild_wird_nicht_erneut_geholt(tmp_path, monkeypatch):
    ordner = promo_bilder.bildordner(tmp_path)
    ordner.mkdir(parents=True)
    (ordner / "abc-1280.jpg").write_bytes(b"x")

    def _darf_nicht(*a, **kw):
        raise AssertionError("Abruf trotz unveraendertem Bild")

    monkeypatch.setattr(promo_bilder, "lade_und_lege_ab", _darf_nicht)
    eintraege = {"a1": {"id": "a1", "image": "abc-1280.jpg",
                        "image_src": "https://marke.test/b/x.jpg"}}
    bilanz = promo_bilder.hole_bilder(
        {"a1": {"quellen": ["https://marke.test/b/x.jpg"], "art": "angebot"}},
        eintraege, tmp_path)
    assert bilanz["unveraendert"] == 1
    assert eintraege["a1"]["image_kind"] == "angebot"


def test_raeume_auf_loescht_nur_unreferenzierte(tmp_path):
    ordner = promo_bilder.bildordner(tmp_path)
    ordner.mkdir(parents=True)
    (ordner / "gebraucht.jpg").write_bytes(b"x")
    (ordner / "verwaist.jpg").write_bytes(b"x")
    geloescht = promo_bilder.raeume_auf(tmp_path, [{"image": "gebraucht.jpg"}])
    assert geloescht == 1
    assert (ordner / "gebraucht.jpg").exists()
    assert not (ordner / "verwaist.jpg").exists()
