"""Tests fuer die Board-Datenaufbereitung (report/promo.py) - reine
Datentransformation, offline, kein Netz/LLM noetig."""
from telco_radar.promo_config import PromoSource
from telco_radar.report.promo import prepare_promo_view


def _src(name="congstar", tier=2, group="", internal_reference=False, kind="static"):
    return PromoSource(name=name, url="https://example.test/", tier=tier,
                       kind=kind, group=group, internal_reference=internal_reference)


def _entry(brand="congstar", headline="10 GB Bonus", status="aktiv",
          first_seen="2026-07-20", last_verified="2026-07-25", image=None,
          image_kind=None):
    e = {"id": f"{brand}:{headline}", "brand": brand, "headline": headline,
         "description": "", "valid_until": None,
         "url": "https://example.test/aktion", "status": status,
         "first_seen": first_seen, "last_verified": last_verified}
    if image:
        e.update({"image": image, "image_w": 1280, "image_h": 720,
                  "image_kind": image_kind or "angebot"})
    return e


def test_every_crawlable_source_gets_a_card_even_without_entries():
    sources = [_src("congstar"), _src("klarmobil")]
    view = prepare_promo_view([_entry(brand="congstar")], sources, "2026-07-25")
    names = {b["name"] for b in view["brands"]}
    assert names == {"congstar", "klarmobil"}
    empty = next(b for b in view["brands"] if b["name"] == "klarmobil")
    assert empty["active_count"] == 0 and empty["active"] == []


def test_skip_kind_sources_are_excluded_from_the_board():
    sources = [_src("congstar"), _src("Deutsche Glasfaser", kind="skip")]
    view = prepare_promo_view([], sources, "2026-07-25")
    assert {b["name"] for b in view["brands"]} == {"congstar"}
    assert view["brands_tracked"] == 1


def test_internal_reference_excluded_from_competitor_counts_but_still_shown():
    sources = [_src("congstar"), _src("Vodafone Deutschland", internal_reference=True)]
    entries = [_entry(brand="congstar"), _entry(brand="Vodafone Deutschland")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["brands_tracked"] == 1          # Vodafone selbst zaehlt nicht
    assert view["brands_active"] == 1
    assert view["active_total"] == 1
    names = {b["name"] for b in view["brands"]}
    assert "Vodafone Deutschland" in names       # wird trotzdem angezeigt
    vf = next(b for b in view["brands"] if b["name"] == "Vodafone Deutschland")
    assert vf["internal_reference"] is True


def test_vodafone_card_sorts_last():
    sources = [_src("Vodafone Deutschland", tier=1, internal_reference=True), _src("congstar")]
    entries = [_entry(brand="Vodafone Deutschland"), _entry(brand="congstar")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["brands"][-1]["name"] == "Vodafone Deutschland"


def test_brands_with_active_offers_sort_before_empty_ones():
    sources = [_src("klarmobil"), _src("congstar")]
    view = prepare_promo_view([_entry(brand="congstar")], sources, "2026-07-25")
    assert view["brands"][0]["name"] == "congstar"


def test_stale_entries_are_kept_separate_from_active():
    """Nur wirklich 'ausgelaufen' (zweimal in Folge nicht bestaetigt) landet
    in der separaten stale-Liste (Fussnote) und faellt aus active_count."""
    sources = [_src("congstar")]
    entries = [_entry(headline="Laeuft"), _entry(headline="Beendet", status="ausgelaufen")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    card = view["brands"][0]
    assert card["active_count"] == 1
    assert len(card["stale"]) == 1
    assert card["has_offers"] is True


def test_grace_period_entries_stay_visible_but_flagged():
    """'evtl. ausgelaufen' (ein einzelner Fehltreffer) darf NICHT einfach von
    der Karte verschwinden - das war der eigentliche Bug. Es bleibt in der
    normalen Angebotsliste, nur mit fading=True markiert, und zaehlt bewusst
    NICHT in active_count (das soll die bestaetigte Zahl bleiben)."""
    sources = [_src("congstar")]
    entries = [_entry(headline="Vermutlich weg", status="evtl. ausgelaufen")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    card = view["brands"][0]
    assert card["active_count"] == 0
    assert card["has_offers"] is True
    assert [o["headline"] for o in card["active"]] == ["Vermutlich weg"]
    assert card["active"][0]["fading"] is True
    assert card["stale"] == []


def test_brand_with_only_grace_entries_does_not_sort_as_empty():
    sources = [_src("klarmobil"), _src("congstar")]
    entries = [_entry(brand="klarmobil", headline="Vermutlich weg", status="evtl. ausgelaufen")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    # klarmobil hat ein sichtbares (wenn auch verblassendes) Angebot,
    # congstar gar keins - klarmobil soll deshalb zuerst stehen.
    assert view["brands"][0]["name"] == "klarmobil"


def test_neu_badge_uses_ten_day_cutoff():
    sources = [_src("congstar")]
    entries = [_entry(headline="Frisch", first_seen="2026-07-24"),
              _entry(headline="Alt", first_seen="2026-06-01")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    by_headline = {e["headline"]: e for e in view["brands"][0]["active"]}
    assert by_headline["Frisch"]["neu"] is True
    assert by_headline["Alt"]["neu"] is False


# ---------------------------------------------------------------- Bilder
# Das Bild haengt seit dem 07.08.2026 am ANGEBOT, nicht an der Marke: eine
# Marke hat bis zu acht Aktionen, und ein Screenshot ihrer Startseite als
# Bild fuer jede einzelne davon beantwortet die Frage der Seite nicht.

def test_das_bild_kommt_vom_angebot_nicht_von_der_marke():
    sources = [_src("congstar")]
    entries = [_scored(headline="Mit Bild", score=80, image="abc-1280.jpg"),
               _scored(headline="Ohne Bild", score=70)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    karte = view["karten"][0]
    assert karte["offer"]["headline"] == "Mit Bild"
    assert karte["bild"] == "images/abc-1280.jpg"
    assert (karte["bild_w"], karte["bild_h"]) == (1280, 720)
    assert view["mit_bild"] == 1


def test_ohne_bild_bleibt_das_feld_leer_statt_auf_ein_marken_bild_zu_zeigen():
    """Kein Ersatzbild von der Marke: eine Kachel ohne belegtes Motiv
    bekommt die Mechanik als Schriftkachel, und dafuer muss die Vorlage die
    Luecke sehen."""
    sources = [_src("congstar")]
    view = prepare_promo_view([_scored(headline="A", score=80)], sources,
                              "2026-07-25")
    assert view["karten"][0]["bild"] == ""
    assert view["mit_bild"] == 0


def test_ein_seitenmotiv_wird_als_solches_gekennzeichnet():
    """Stufe 4 der Zuordnung (promo_bilder.zuordnen) belegt nur, WOMIT die
    Marke wirbt - nicht, dass das Bild dieses eine Angebot zeigt. Die Karte
    schreibt es dazu; ohne die Kennzeichnung behauptet sie mehr, als belegt
    ist."""
    sources = [_src("congstar")]
    entries = [_scored(headline="A", score=80, image="x-1280.jpg",
                       image_kind="motiv")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["karten"][0]["bild_ist_motiv"] is True
    entries = [_scored(headline="A", score=80, image="x-1280.jpg")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["karten"][0]["bild_ist_motiv"] is False


# ---------------------------------------------------------------- Karten
# Je Wettbewerber EINE Karte: seine staerkste sichtbare Aktion. Die Auswahl
# WELCHE stark ist trifft analyze/promo_ranker.py (Score + Hysterese) - hier
# wird nur geprueft, dass die Anzeige das Ergebnis respektiert und nichts
# eigenes dazuerfindet.

def _scored(brand="congstar", headline="A", score=80, highlight=True,
            reason="Weil.", mechanic="wechselpraemie", **kw):
    e = _entry(brand=brand, headline=headline, **kw)
    e.update({"score": score, "highlight": highlight, "score_reason": reason,
              "mechanic": mechanic})
    return e


def test_karten_stehen_nach_score():
    sources = [_src("congstar"), _src("klarmobil"), _src("Blau")]
    entries = [_scored(brand="congstar", score=71),
               _scored(brand="klarmobil", score=88),
               _scored(brand="Blau", score=79)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert [k["brand"]["name"] for k in view["karten"]] == [
        "klarmobil", "Blau", "congstar"]
    assert view["karten"][0]["reason"] == "Weil."
    assert view["karten"][0]["mechanic"] == "Wechsel- oder Altgerätprämie"


def test_je_marke_ein_block_mit_allen_ihren_aktionen():
    """Der Leser denkt in Wettbewerbern: alle Aktionen einer Marke stehen an
    EINEM Ort, die staerkste als `lead`, die uebrigen als `weitere`. Bis zum
    08.08.2026 stand die staerkste oben im Auswahlraster und der Rest weit
    unten in einer Zeilenwand - wer eine Marke verstehen wollte, musste
    zwischen beiden springen."""
    sources = [_src("Telekom"), _src("congstar")]
    entries = [_scored(brand="Telekom", headline="Gerät A", score=90),
               _scored(brand="Telekom", headline="Gerät B", score=88),
               _scored(brand="Telekom", headline="Gerät C", score=86),
               _scored(brand="congstar", headline="Bonus", score=70)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    telekom = view["bloecke"][0]
    assert telekom["name"] == "Telekom"
    assert telekom["lead"]["offer"]["headline"] == "Gerät A"
    assert [k["offer"]["headline"] for k in telekom["weitere"]] == ["Gerät B", "Gerät C"]
    assert [b["name"] for b in view["bloecke"]] == ["Telekom", "congstar"]


def test_die_bloecke_stehen_nach_der_staerksten_aktion_der_marke():
    """Sortiert wird die MARKE, nicht die Einzelaktion - sonst zerfaellt die
    Seite wieder in eine Rangliste quer ueber alle Anbieter."""
    sources = [_src("congstar"), _src("Blau"), _src("klarmobil")]
    entries = [_scored(brand="congstar", headline="A", score=71),
               _scored(brand="congstar", headline="B", score=99),
               _scored(brand="Blau", headline="C", score=88),
               _scored(brand="klarmobil", headline="D", score=40)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert [b["name"] for b in view["bloecke"]] == ["congstar", "Blau", "klarmobil"]
    assert [b["top_score"] for b in view["bloecke"]] == [99, 88, 40]


def test_jede_sichtbare_aktion_steht_genau_einmal():
    sources = [_src("congstar")]
    entries = [_scored(headline="Stark", score=90), _scored(headline="Schwach", score=40),
               _entry(headline="Beendet", status="ausgelaufen")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert [k["offer"]["headline"] for k in view["karten"]] == ["Stark", "Schwach"]
    assert len({k["offer"]["id"] for k in view["karten"]}) == 2


def test_das_highlight_flag_wird_gelesen_nicht_nachgebaut():
    """Ein hoher Score allein macht kein Highlight - das Flag kommt aus der
    Hysterese im Ranker, die Anzeige darf die Schwelle nicht selbst
    nachbilden. Es ordnet die Seite aber NICHT: sortiert wird nach Score,
    sonst haette die Hysterese zwei Wirkungen statt einer."""
    sources = [_src("congstar"), _src("Blau")]
    entries = [_scored(brand="congstar", score=95, highlight=False),
               _scored(brand="Blau", score=70, highlight=True)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert [b["name"] for b in view["bloecke"]] == ["congstar", "Blau"]
    assert view["highlight_count"] == 1
    assert [k["highlight"] for k in view["karten"]] == [False, True]


def test_eine_unbewertete_marke_faellt_hinter_jede_bewertete():
    """Vor dem ersten Bewertungslauf (und bei LLM-Ausfall) darf die Seite
    nicht leer wirken - unbewertete Aktionen stehen weiter da, nur hinten."""
    sources = [_src("congstar"), _src("Blau")]
    entries = [_entry(brand="congstar"), _scored(brand="Blau", score=40)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert [k["brand"]["name"] for k in view["karten"]] == ["Blau", "congstar"]
    assert view["karten"][1]["score"] is None
    assert view["scored_total"] == 1


def test_das_eigene_angebot_steht_in_einem_eigenen_block():
    sources = [_src("congstar"), _src("Vodafone Deutschland", internal_reference=True)]
    entries = [_scored(brand="congstar", score=71),
               _scored(brand="Vodafone Deutschland", headline="Eigenes", score=99)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert [b["name"] for b in view["bloecke"]] == ["congstar"]
    assert view["eigen"]["name"] == "Vodafone Deutschland"
    assert view["eigen"]["lead"]["offer"]["headline"] == "Eigenes"
    # ... und faellt aus der Wettbewerbszaehlung heraus.
    assert [k["brand"]["name"] for k in view["karten"]] == ["congstar"]


def test_der_eigene_block_nimmt_das_beste_eigene_angebot_zuerst():
    sources = [_src("Vodafone Deutschland", internal_reference=True)]
    entries = [_scored(brand="Vodafone Deutschland", headline="schwach", score=20,
                       highlight=False),
               _scored(brand="Vodafone Deutschland", headline="stark", score=77,
                       highlight=False)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["eigen"]["lead"]["offer"]["headline"] == "stark"
    assert [k["offer"]["headline"] for k in view["eigen"]["weitere"]] == ["schwach"]


def test_marken_ohne_aktion_stehen_getrennt_und_zaehlen_nicht_mit():
    sources = [_src("congstar"), _src("klarmobil")]
    view = prepare_promo_view([_scored(brand="congstar")], sources, "2026-07-25")
    assert [b["name"] for b in view["bloecke"]] == ["congstar"]
    assert [b["name"] for b in view["ohne_aktion"]] == ["klarmobil"]
    assert view["brands_tracked"] == 2      # beobachtet werden beide


# ------------------------------------------------------- Motiv & Kachel
# Was eine Karte anstelle eines Bildes zeigt - und was sie NICHT zweimal
# zeigt. Antonio am 08.08.2026: "Viele Karten sind Schriftkacheln mit
# identischem Text ('Wechsel- oder Altgeraetpraemie' x4) - sieht nach Fehler
# aus."

def test_die_schriftkachel_traegt_die_zahlen_des_angebots():
    from telco_radar.report.promo import _kachel_text

    assert _kachel_text({"headline": "Blau Allnet S: 20 GB für 6,99 € monatlich"},
                        "Preisnachlass auf den Tarif") == "20 GB · 6,99 €"
    assert _kachel_text({"headline": "100 Mbit/s statt 50"}, "sonstiges") == "100 Mbit/s"


def test_die_schriftkachel_faellt_erst_auf_den_kern_der_ueberschrift_zurueck():
    """Ohne Zahl der erste Sinnabschnitt - und erst wenn auch der zu lang
    ist, die Mechanik. Sie ist die letzte Wahl, weil vier Marken dieselbe
    fahren koennen und vier gleiche Kacheln wie ein Fehler aussehen."""
    from telco_radar.report.promo import _kachel_text

    assert _kachel_text(
        {"headline": "Junge-Leute-Rabatt auf Magenta Mobil Young 5G Tarife"},
        "Zielgruppentarif") == "Junge-Leute-Rabatt"
    # Die GANZE Ueberschrift taugt nicht - sie steht zwei Zeilen tiefer noch
    # einmal, und dieselbe Aussage zweimal untereinander liest sich als Panne.
    assert _kachel_text({"headline": "Dauerhaft mehr Daten"}, "mehr Datenvolumen") \
        == "mehr Datenvolumen"
    assert _kachel_text(
        {"headline": "Ein ausserordentlich weitschweifig formulierter Sonderfall"},
        "Zielgruppentarif") == "Zielgruppentarif"
    assert _kachel_text({"headline": ""}, "") == "Aktion"


def test_kein_motiv_steht_zweimal_auf_der_seite():
    """promo_bilder vergibt jeden Kandidaten nur einmal - aber je Marke und
    je Lauf. Ein Eintrag, dessen Seite unveraendert blieb, behaelt sein Bild
    aus einem frueheren Lauf; taucht derselbe Kandidat jetzt bei einem
    anderen Angebot auf, stuende dasselbe Motiv zweimal auf der Seite (am
    08.08.2026 bei O2 gemessen: derselbe Router unter zwei Schlagzeilen)."""
    sources = [_src("congstar"), _src("Blau")]
    entries = [_scored(brand="congstar", headline="A", score=90, image="x-1280.jpg"),
               _scored(brand="congstar", headline="B", score=80, image="x-1280.jpg"),
               _scored(brand="Blau", headline="C", score=70, image="x-1280.jpg")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    bilder = [k["bild"] for k in view["karten"] if k["bild"]]
    assert bilder == ["images/x-1280.jpg"]
    # Das staerkste Angebot behaelt es, die schwaecheren werden Textkarten.
    nach_titel = {k["offer"]["headline"]: k for k in view["karten"]}
    assert nach_titel["B"]["bild"] == "" and nach_titel["B"]["bild_w"] is None
    assert view["mit_bild"] == 1


def test_ein_banner_wird_als_banner_erkannt_und_nicht_beschnitten():
    """Ein 1280x410-Werbebanner im 16:9-Ausschnitt zeigt die Haelfte der
    Aussage nicht mehr - bei simplytel blieb blaue Flaeche uebrig."""
    sources = [_src("congstar")]
    entries = [_scored(headline="A", score=90, image="x-1280.jpg")]
    entries[0].update({"image_w": 1280, "image_h": 410})
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["karten"][0]["bild_panorama"] is True
    # Ein gewoehnliches Querformat bleibt eins (800x419 = 1,91).
    entries[0].update({"image_w": 800, "image_h": 419})
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["karten"][0]["bild_panorama"] is False


# ------------------------------------------------------------- Mechaniken
# "Was der Markt gerade faehrt" - die Balken zaehlen MARKEN, nicht Angebote.

def test_mechanik_balken_zaehlen_marken_nicht_angebote():
    sources = [_src("congstar"), _src("Blau"), _src("klarmobil")]
    entries = [
        _scored(brand="congstar", headline="A", mechanic="datenbonus"),
        _scored(brand="congstar", headline="B", mechanic="datenbonus"),
        _scored(brand="congstar", headline="C", mechanic="datenbonus"),
        _scored(brand="Blau", headline="D", mechanic="wechselpraemie"),
        _scored(brand="klarmobil", headline="E", mechanic="wechselpraemie"),
    ]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    balken = {m["label"]: m for m in view["mechaniken"]}
    # Drei Aktionen EINER Marke sind eine Kampagne, zwei Aktionen ZWEIER
    # Marken sind ein Trend - deshalb steht die Wechselpraemie vorn.
    assert view["mechaniken"][0]["label"] == "Wechsel- oder Altgerätprämie"
    assert balken["Wechsel- oder Altgerätprämie"]["marken"] == 2
    assert balken["mehr Datenvolumen"]["marken"] == 1
    assert balken["mehr Datenvolumen"]["n"] == 3


def test_mechanik_sonstiges_taucht_nicht_als_balken_auf():
    """"sonstiges" ist die Auffangkategorie des Rankers - als Balken waere
    sie eine Aussage ueber den Markt, die niemand getroffen hat."""
    sources = [_src("congstar")]
    entries = [_scored(mechanic="sonstiges")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["mechaniken"] == []
