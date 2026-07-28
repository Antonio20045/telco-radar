"""Tests fuer die Board-Datenaufbereitung (report/promo.py) - reine
Datentransformation, offline, kein Netz/LLM noetig."""
from telco_radar.promo_config import PromoSource
from telco_radar.report.promo import prepare_promo_view


def _src(name="congstar", tier=2, group="", internal_reference=False, kind="static"):
    return PromoSource(name=name, url="https://example.test/", tier=tier,
                       kind=kind, group=group, internal_reference=internal_reference)


def _entry(brand="congstar", headline="10 GB Bonus", status="aktiv",
          first_seen="2026-07-20", last_verified="2026-07-25", image_url=None):
    return {"brand": brand, "headline": headline, "description": "",
            "valid_until": None, "url": "https://example.test/aktion",
            "status": status, "first_seen": first_seen,
            "last_verified": last_verified, "image_url": image_url}


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


def test_image_url_picked_from_entries_when_present():
    sources = [_src("congstar")]
    entries = [_entry(headline="A", image_url=None),
              _entry(headline="B", image_url="https://example.test/hero.jpg")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["brands"][0]["image_url"] == "https://example.test/hero.jpg"


def test_captured_screenshot_takes_priority_over_entry_og_image():
    """Ein echter Playwright-Screenshot (siehe promo_images.py/report/html.py)
    soll immer vor dem per-Eintrag og:image/twitter:image-Fund gewaehlt
    werden - og:image ist meist nur ein generisches Marken-Logo (siehe
    claude/promo-uebersicht-umsetzung.md), der Screenshot ist die
    verlaesslichere, "richtigere" Quelle."""
    sources = [_src("congstar")]
    entries = [_entry(headline="A", image_url="https://example.test/logo.png")]
    view = prepare_promo_view(entries, sources, "2026-07-25",
                              images={"congstar": "images/congstar.jpg"})
    assert view["brands"][0]["image_url"] == "images/congstar.jpg"


def test_missing_images_arg_falls_back_to_entry_image_url():
    """Rueckwaerts-kompatibel: Aufrufer, die (noch) kein images-Mapping
    uebergeben, verhalten sich exakt wie vor der Screenshot-Funktion."""
    sources = [_src("congstar")]
    entries = [_entry(headline="A", image_url="https://example.test/logo.png")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["brands"][0]["image_url"] == "https://example.test/logo.png"


def test_brand_without_screenshot_or_og_image_has_none():
    sources = [_src("congstar"), _src("klarmobil")]
    entries = [_entry(brand="congstar", headline="A", image_url=None)]
    view = prepare_promo_view(entries, sources, "2026-07-25",
                              images={"klarmobil": "images/klarmobil.jpg"})
    by_name = {b["name"]: b for b in view["brands"]}
    assert by_name["congstar"]["image_url"] is None
    assert by_name["klarmobil"]["image_url"] == "images/klarmobil.jpg"


# ------------------------------------------------------------- Highlights
# Die Auswahl selbst trifft analyze/promo_ranker.py (Score + Hysterese) - hier
# wird nur geprueft, dass die Anzeige das Flag respektiert und nichts eigenes
# dazuerfindet.

def _scored(brand="congstar", headline="A", score=80, highlight=True,
            reason="Weil.", mechanic="wechselpraemie", **kw):
    e = _entry(brand=brand, headline=headline, **kw)
    e.update({"score": score, "highlight": highlight, "score_reason": reason,
              "mechanic": mechanic})
    return e


def test_highlights_are_ranked_by_score():
    sources = [_src("congstar"), _src("klarmobil"), _src("Blau")]
    entries = [_scored(brand="congstar", score=71),
               _scored(brand="klarmobil", score=88),
               _scored(brand="Blau", score=79)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert [h["brand"]["name"] for h in view["highlights"]] == [
        "klarmobil", "Blau", "congstar"]
    assert view["highlight_count"] == 3
    assert view["hero"]["brand"]["name"] == "klarmobil"
    assert view["hero"]["reason"] == "Weil."


def test_only_flagged_offers_become_highlights():
    """Ein hoher Score allein reicht nicht - das Flag kommt aus der Hysterese
    im Ranker, die Anzeige darf die Schwelle nicht selbst nachbilden."""
    sources = [_src("congstar")]
    entries = [_scored(headline="A", score=95, highlight=False),
               _scored(headline="B", score=70, highlight=True)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert [h["offer"]["headline"] for h in view["highlights"]] == ["B"]


def test_unscored_offers_never_become_highlights():
    sources = [_src("congstar")]
    entries = [_entry(headline="A")]
    entries[0]["highlight"] = True          # Flag ohne Zahl darf nicht greifen
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["highlights"] == []
    assert view["scored_total"] == 0


def test_own_brand_is_an_anchor_not_part_of_the_ranking():
    sources = [_src("congstar"), _src("Vodafone Deutschland", internal_reference=True)]
    entries = [_scored(brand="congstar", score=71),
               _scored(brand="Vodafone Deutschland", headline="Eigenes", score=99)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert [h["brand"]["name"] for h in view["highlights"]] == ["congstar"]
    assert view["own_anchor"]["brand"]["name"] == "Vodafone Deutschland"
    assert view["own_anchor"]["offer"]["headline"] == "Eigenes"
    assert view["hero"]["brand"]["name"] == "congstar"


def test_own_anchor_picks_the_best_scored_own_offer():
    sources = [_src("Vodafone Deutschland", internal_reference=True)]
    entries = [_scored(brand="Vodafone Deutschland", headline="schwach", score=20,
                       highlight=False),
               _scored(brand="Vodafone Deutschland", headline="stark", score=77,
                       highlight=False)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["own_anchor"]["offer"]["headline"] == "stark"


def test_hero_falls_back_to_old_behaviour_without_any_scores():
    """Vor dem ersten Bewertungslauf (und bei LLM-Ausfall) darf die Seite
    nicht leer wirken - dann gilt wieder das bisherige Verhalten."""
    sources = [_src("congstar"), _src("Vodafone Deutschland", internal_reference=True)]
    entries = [_entry(brand="congstar"), _entry(brand="Vodafone Deutschland")]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["highlights"] == []
    assert view["hero"]["brand"]["name"] == "Vodafone Deutschland"


def test_highlight_list_is_capped_and_reports_the_remainder():
    sources = [_src(f"Marke{i}") for i in range(12)]
    entries = [_scored(brand=f"Marke{i}", score=70 + i) for i in range(12)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert view["highlight_count"] == 9
    assert view["highlight_dropped"] == 3
    assert len(view["highlight_rest"]) == 8      # ohne die Hero-Karte


def test_only_the_best_offer_per_brand_reaches_the_highlights():
    """Gegen SKU-Flut: an den echten Daten vom 27.07.2026 kamen neun der
    besten fuenfzehn Treffer von der Telekom - dieselbe Geraeteaktion, einmal
    je Modell. Oben gehoert Marktbreite hin, nicht der groesste Katalog."""
    sources = [_src("Telekom"), _src("congstar")]
    entries = [_scored(brand="Telekom", headline="Gerät A", score=90),
               _scored(brand="Telekom", headline="Gerät B", score=88),
               _scored(brand="Telekom", headline="Gerät C", score=86),
               _scored(brand="congstar", headline="Bonus", score=70)]
    view = prepare_promo_view(entries, sources, "2026-07-25")
    assert [h["offer"]["headline"] for h in view["highlights"]] == ["Gerät A", "Bonus"]
    assert view["highlight_dropped"] == 2      # Gerät B und C stehen unten
