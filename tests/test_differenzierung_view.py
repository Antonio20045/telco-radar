"""Die Datenaufbereitung der Differenzierungs-Seite
(report/differenzierung_view.py).

Der Anlass ist ein Inhaltsfehler, kein Layoutwunsch: die Seite las bis zum
08.08.2026 nur `differentiation_db.json` (den Web-Sweep). Der zweite
Speicher, `differentiation.jsonl` (der Kurator ueber den woechentlichen
Presse-Crawl), wurde jede Woche gefuellt und nie angezeigt. Hier steht
festgenagelt, dass beide ankommen - und was bei einer Kollision gilt.
"""
import pytest

from telco_radar.report import differenzierung_view as view

THEMES = [("ki", "KI & Assistenten"), ("cloud", "Cloud & Speicher"),
          ("gaming", "Gaming")]
FARBEN = {"ki": "#7b3fe4", "cloud": "#0d9488", "gaming": "#8a2be2"}
STICHTAG = "2026-08-07"


def db_eintrag(**kw):
    e = {"id": "https://a.example.com/x", "theme": "ki", "operator": "SK Telecom",
         "region": "Asien", "what": "Perplexity Pro 12 Monate gratis.",
         "url": "https://www.a.example.com/x", "source": "a.example.com",
         "date": "2026", "why": "KI-Bundle als Tarif-Bonus.",
         "first_seen": "2026-06-15", "last_verified": "2026-07-31",
         "status": "aktiv"}
    e.update(kw)
    return e


def store_eintrag(**kw):
    e = {"id": "https://b.example.com/y", "first_seen": "2026-08-06",
         "theme": "gaming",
         "title": "Akses Nonton Piala Dunia FIFA 2026 Lebih Fleksibel 13 Jun 2026",
         "summary": "Telkomsel bringt Cloud-Gaming auf Mobilgeraete. "
                    "Der Dienst startet zunaechst in Jakarta.",
         "url": "https://www.b.example.com/y", "operator": "Telkomsel",
         "region": "Asien", "date": None, "category": "Partnerschaft",
         "relevance": 4,
         "why_it_matters": "Cloud-Gaming gewinnt als Differenzierungsmerkmal. "
                           "Vodafone sollte pruefen, ob ein eigenes Angebot traegt.",
         "source": "Telkomsel"}
    e.update(kw)
    return e


def auf(db=None, store=None, stichtag=STICHTAG):
    return view.aufbereiten(db or [], store or [], THEMES, stichtag, FARBEN)


# --------------------------------------------------------------- der Merge
def test_beide_speicher_landen_im_bestand():
    """Der eigentliche Befund: der Kurator lief jede Woche umsonst."""
    d = auf([db_eintrag()], [store_eintrag()])
    assert d["gesamt"] == 2
    assert {e["herkunft"] for e in d["bestand"]} == {"sweep", "presse"}


def test_bei_gleicher_url_gewinnt_die_diffdb():
    """Beide Speicher koennen dieselbe Meldung kennen. Der DiffDB-Eintrag ist
    fuer die Anzeige geschrieben, der Store-Eintrag ist Rohtext."""
    gleich = "https://www.a.example.com/x"
    d = auf([db_eintrag()], [store_eintrag(url=gleich, id=gleich)])
    assert d["gesamt"] == 1
    assert d["bestand"][0]["herkunft"] == "sweep"
    assert d["bestand"][0]["what"] == "Perplexity Pro 12 Monate gratis."


def test_dedupe_ueber_die_normalisierte_url_nicht_die_rohe():
    """http/https und "www." duerfen nicht zwei Eintraege ergeben - beide
    Speicher deduplizieren intern ueber dieselbe Normalisierung."""
    d = auf([db_eintrag(url="https://www.a.example.com/x")],
            [store_eintrag(url="http://a.example.com/x", id="andere-id")])
    assert d["gesamt"] == 1


# ------------------------------------------------ Mapping der Store-Felder
def test_store_eintrag_wird_auf_die_kartenform_gebracht():
    d = auf([], [store_eintrag()])
    e = d["bestand"][0]
    assert e["operator"] == "Telkomsel"
    assert e["region"] == "Asien"
    assert e["theme"] == "gaming"
    # Domain aus der URL - der Store fuehrt dort ein Quellen-LABEL
    # ("Telkomsel"), die Karte zeigt aber die Domain wie ueberall sonst.
    assert e["source"] == "b.example.com"


def test_hauptzeile_kommt_aus_der_deutschen_zusammenfassung_nicht_aus_dem_titel():
    """Gemessen am Bestand vom 08.08.2026 sind die Originaltitel mehrsprachig
    und tragen ein angehaengtes Datum. Auf einer deutschen Seite fuer Leser
    ohne Technik-Hintergrund (CLAUDE.md §8) ist das keine Schlagzeile."""
    e = auf([], [store_eintrag()])["bestand"][0]
    assert e["what"] == "Telkomsel bringt Cloud-Gaming auf Mobilgeraete."
    assert "Piala Dunia" not in e["what"]


def test_ohne_zusammenfassung_bleibt_der_titel_als_rueckfall():
    e = auf([], [store_eintrag(summary="")])["bestand"][0]
    assert e["what"].startswith("Akses Nonton")


def test_why_kommt_aus_why_it_matters():
    e = auf([], [store_eintrag()])["bestand"][0]
    assert e["why"] == "Cloud-Gaming gewinnt als Differenzierungsmerkmal."


@pytest.mark.parametrize("text,erwartet", [
    # Ein Punkt in einer Zahlangabe ist kein Satzende - drei von 51
    # Bestandssaetzen haben genau diese Form.
    ("Gutschriften bei Ausfaellen, auf rund 50 Mio. Kunden ausgeweitet.",
     "Gutschriften bei Ausfaellen, auf rund 50 Mio. Kunden ausgeweitet."),
    ("Vorlage fuer Vodafone, z.B. Bundles. Der zweite Satz faellt weg.",
     "Vorlage fuer Vodafone, z.B. Bundles."),
    ("Nur ein Satz ohne Punkt", "Nur ein Satz ohne Punkt"),
    ("Erster Satz. Zweiter Satz. Dritter.", "Erster Satz."),
])
def test_erster_satz_schneidet_nur_an_echten_satzgrenzen(text, erwartet):
    assert view.erster_satz(text) == erwartet


def test_erster_satz_endet_nie_mit_auslassungspunkten():
    """Abnahmekriterium 5 des Portals: keine abgeschnittene Ueberschrift."""
    lang = ("Ein sehr langer erster Satz, der viele Nebensaetze enthaelt und "
            "trotzdem vollstaendig bleiben muss. Und noch einer.")
    assert not view.erster_satz(lang).endswith("…")
    assert view.erster_satz(lang).endswith("muss.")


# ---------------------------------------------------------- die Neu-Regel
def test_neu_gilt_zehn_tage_ab_dem_stand_der_ausgabe():
    frisch = db_eintrag(id="f", url="https://f.example.com/", first_seen="2026-08-05")
    alt = db_eintrag(id="a", url="https://a2.example.com/", first_seen="2026-06-01")
    d = auf([frisch, alt])
    nach_id = {e["url"]: e for e in d["bestand"]}
    assert nach_id["https://f.example.com/"]["neu"] is True
    assert nach_id["https://a2.example.com/"]["neu"] is False
    assert d["neu_ist_rueckfall"] is False
    assert [e["url"] for e in d["neu"]] == ["https://f.example.com/"]


def test_ohne_neue_eintraege_stehen_oben_die_zuletzt_geprueften():
    """Eine ruhige Woche darf die Seite nicht enthaupten."""
    a = db_eintrag(id="a", url="https://a2.example.com/",
                   first_seen="2026-01-01", last_verified="2026-07-31")
    b = db_eintrag(id="b", url="https://b2.example.com/",
                   first_seen="2026-01-01", last_verified="2026-08-01")
    d = auf([a, b])
    assert d["neu_ist_rueckfall"] is True
    assert [e["url"] for e in d["neu"]][0] == "https://b2.example.com/"


def test_hoechstens_drei_karten_stehen_oben():
    """Drei seit dem 08.08.2026: die Radar-Karten tragen jetzt ein Motiv und
    stehen zu dritt in voller Breite. Sechs Bildkarten waeren wieder die
    Kachelwand, nur bunter."""
    viele = [db_eintrag(id=str(i), url=f"https://x{i}.example.com/",
                        first_seen="2026-08-05") for i in range(12)]
    assert len(auf(viele)["neu"]) == view.MAX_NEU == 3


# ------------------------------------------------------------- die Hebel
def test_hebel_ohne_eintraege_erscheinen_nicht():
    """Zwoelfmal "Noch keine bestaetigten Beispiele" war zwoelfmal derselbe
    leere Kasten."""
    d = auf([db_eintrag(theme="ki")])
    assert [h["key"] for h in d["hebel"]] == ["ki"]
    assert d["n_hebel"] == 1


def test_hebel_behalten_die_reihenfolge_der_themenliste():
    d = auf([db_eintrag(id="g", url="https://g.example.com/", theme="gaming"),
             db_eintrag(theme="ki")])
    assert [h["key"] for h in d["hebel"]] == ["ki", "gaming"]


def test_innerhalb_eines_hebels_stehen_die_juengsten_zuerst():
    alt = db_eintrag(id="alt", url="https://alt.example.com/", first_seen="2026-05-01")
    neu = db_eintrag(id="neu", url="https://neu.example.com/", first_seen="2026-08-06")
    mitte = db_eintrag(id="m", url="https://m.example.com/", first_seen="2026-07-01")
    hebel = auf([alt, neu, mitte])["hebel"][0]
    assert [e["first_seen"] for e in hebel["eintraege"]] == [
        "2026-08-06", "2026-07-01", "2026-05-01"]


def test_jeder_hebel_traegt_zahl_farbe_und_etikett():
    d = auf([db_eintrag(), db_eintrag(id="z", url="https://z.example.com/")])
    h = d["hebel"][0]
    assert (h["n"], h["farbe"], h["label"]) == (2, "#7b3fe4", "KI & Assistenten")
    # Die Karten oben mischen die Hebel und muessen ihren selbst benennen.
    assert all(e["hebel_label"] == "KI & Assistenten" for e in h["eintraege"])


def test_ein_unbekannter_hebel_faellt_aus_der_bibliothek_bleibt_aber_im_bestand():
    """Der Suchindex speist sich aus `bestand` - ein Eintrag mit einem
    Hebel, den THEMES nicht kennt, darf nicht unauffindbar werden."""
    d = auf([db_eintrag(theme="unbekannt")])
    assert d["hebel"] == []
    assert d["gesamt"] == 1
    assert len(d["neu"]) == 1


def test_leerer_bestand_bricht_nicht():
    d = auf([], [])
    assert {k: v for k, v in d.items() if k != "marktbild"} == {
        "bestand": [], "hebel": [], "neu": [], "neu_ist_rueckfall": True,
        "gesamt": 0, "n_hebel": 0}
    assert d["marktbild"]["gesamt"] == 0
    assert d["marktbild"]["hebel_balken"] == []


def test_kaputter_stichtag_macht_niemanden_neu():
    d = auf([db_eintrag(first_seen="2026-08-06")], stichtag="")
    assert all(e["neu"] is False for e in d["bestand"])
    assert d["neu_ist_rueckfall"] is True


# ------------------------------------- beobachtend statt empfehlend (§8)
# Beide Speicher liefern Begruendungen, die Vodafone etwas RATEN - der
# Kurator-Prompt fragt ausdruecklich danach ("why it matters"). Auf der
# oeffentlichen Seite hat das nichts verloren (CLAUDE.md §8). Die Regel und
# ihre Begruendung stehen in textwerkzeug.ohne_vodafone_rat; hier steht, dass
# die Karten sie wirklich anwenden.
def test_die_begruendung_verliert_ihren_vodafone_ratschlag():
    e = auf([db_eintrag(why="Ein Modell, das Vodafone prüfen könnte: "
                            "KI-Bundles binden Kunden.")])["bestand"][0]
    assert e["why"] == "KI-Bundles binden Kunden."


def test_eine_reine_empfehlung_laesst_die_karte_ohne_zweitzeile():
    """Die Karte bleibt - nur die Zeile faellt. Eine leere Zeile ist besser
    als eine Empfehlung."""
    e = auf([db_eintrag(why="Vodafone sollte prüfen, ob das trägt.")])["bestand"][0]
    assert e["why"] == ""
    assert e["what"] == "Perplexity Pro 12 Monate gratis."


def test_eine_beobachtung_ueber_vodafone_bleibt_stehen():
    beobachtung = ("Vodafone-Afrika-Gesellschaften könnten Marktanteile an "
                   "Reisende verlieren, wenn MTN ein eSIM-Angebot platziert.")
    e = auf([db_eintrag(why=beobachtung)])["bestand"][0]
    assert e["why"] == beobachtung


def test_beim_presse_eintrag_faellt_der_rat_VOR_der_kuerzung():
    """Reihenfolge, und sie ist der ganze Punkt: steht der Ratschlag im
    ERSTEN Satz, nimmt `erster_satz()` zuerst den Befund mit."""
    e = auf([], [store_eintrag(
        why_it_matters="Vodafone sollte prüfen, ob das trägt. "
                       "Cloud-Gaming gewinnt an Bedeutung.")])["bestand"][0]
    assert e["why"] == "Cloud-Gaming gewinnt an Bedeutung."
