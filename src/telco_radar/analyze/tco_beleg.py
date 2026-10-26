"""Belege, die ihrer Zeile widersprechen (Preisprüfung 26.10.2026)."""

from __future__ import annotations

import base64
import binascii
import re

_EE_BELEG = re.compile(r"-ee-\d+(?:gb|tb)-|enterprise-edition")


def beleg_widerspricht(eintrag: dict) -> bool:
    """Der Beleg ist eine Enterprise Edition, die SKU das normale Modell
    (Preisprüfung 26.10.2026: o2 S26 und Telekom S26 FE, bis 102 € daneben)."""
    sku = str(eintrag.get("sku_id") or "")
    ee_sku = "enterprise" in sku or "-ee-" in sku
    return bool(_EE_BELEG.search(_beleg_klartext(eintrag))) and not ee_sku


def _beleg_klartext(eintrag: dict) -> str:
    """Der Beleg samt o2-REST-Konfiguration, die das Modell Base64-kodiert trägt."""
    url = str(eintrag.get("quelle_url") or "")
    if "/rest/configuration/" not in url:
        return url
    teil = url.rsplit("/", 1)[-1].split("?")[0]
    try:
        return url + " " + base64.b64decode(teil + "=" * (-len(teil) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError):
        return url
