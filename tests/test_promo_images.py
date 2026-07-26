"""Tests fuer promo_images.py - Slug-/Pfad-Helfer fuer den Hero-Screenshot-
Cache. Reine Pfadlogik, offline, kein Netz/Playwright noetig."""
from pathlib import Path

from telco_radar.promo_images import image_dir, image_path, slugify


def test_slugify_lowercases_and_hyphenates():
    assert slugify("O2 / Telefónica Deutschland") == "o2-telefonica-deutschland"


def test_slugify_transliterates_german_umlauts():
    assert slugify("Käse & Größe") == "kaese-groesse"


def test_slugify_strips_leading_trailing_hyphens():
    assert slugify("  -winSIM-  ") == "winsim"


def test_slugify_never_empty():
    assert slugify("") == "brand"
    assert slugify("!!!") == "brand"


def test_slugify_stable_and_collision_free_for_known_brands():
    """Zwei erkennbar unterschiedliche Markennamen duerfen nie auf denselben
    Slug fallen - sonst wuerde eine Marke die Screenshot-Datei der anderen
    ueberschreiben."""
    names = ["Telekom Deutschland", "Vodafone Deutschland", "O2 / Telefónica Deutschland",
            "1&1 Mobilfunk", "congstar", "Otelo", "Blau", "ALDI TALK",
            "mobilcom-debitel", "klarmobil", "Lidl Connect", "Penny Mobil",
            "winSIM", "PremiumSIM", "simplytel"]
    slugs = [slugify(n) for n in names]
    assert len(set(slugs)) == len(names)


def test_image_path_uses_slug_and_data_state_promo_images():
    root = Path("/tmp/telco-radar-test-root")
    p = image_path(root, "O2 / Telefónica Deutschland")
    assert p == image_dir(root) / "o2-telefonica-deutschland.jpg"
    assert p.parent == root / "data" / "state" / "promo_images"
