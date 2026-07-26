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
