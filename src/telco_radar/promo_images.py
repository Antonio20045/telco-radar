"""Shared path/naming helpers for the Promo-Uebersicht hero-image cache.

data/state/promo_images/<slug>.jpg holds one real screenshot per brand,
captured by promo_pipeline.py (see collect/promo_snapshot.py::
capture_hero_image) and read back by report/html.py when rendering the site.
Centralised here so the write side (pipeline) and the read side (renderer)
can never disagree on the slug format or the on-disk location - the same
kind of split-brain bug that would silently make every card fall back to the
colour+initials placeholder even though a screenshot exists on disk.

Persisted like the rest of data/state/ (git-versioned, survives across
runs): a brand's card should keep showing its last-known-good screenshot
even on a run where the source failed or nothing changed, exactly like
promo_db.json entries are never dropped just because one run had no signal.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Filesystem/URL-safe brand key, e.g. "O2 / Telefónica Deutschland" ->
    "o2-telefonica-deutschland". Deliberately ASCII-only and collision-shy
    (falls back to "brand" only for a fully-empty input, never raises).

    German umlauts get a proper transliteration (ae/oe/ue/ss) rather than
    just having their diacritic dropped; everything else (Telefónica's
    "ó", etc.) is handled generically via NFKD decomposition so a future
    brand name doesn't quietly collide with another once accents are
    stripped."""
    normalized = (name or "").strip().lower()
    normalized = (normalized
                  .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
                  .replace("ß", "ss"))
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    slug = _SLUG_RE.sub("-", normalized).strip("-")
    return slug or "brand"


def image_dir(root: Path) -> Path:
    return Path(root) / "data" / "state" / "promo_images"


def image_path(root: Path, brand: str) -> Path:
    return image_dir(root) / f"{slugify(brand)}.jpg"
