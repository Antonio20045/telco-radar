"""1&1: die zwei Leser, die der Klick-Lauf von der Anbieterseite braucht.

Preise misst seit 20.11.2026 nur der Klick-Lauf (config/klickkarten/1und1.yaml,
alle Tarife der Tarifauswahl); der Gerätelauf ruft 1&1 nicht ab, und es gibt
keinen 1&1-Adapter mehr. Geblieben sind die Bereitstellungsgebühr der
Tarifdetail-Seite (``klickanschluss``) und der Tarifname ohne Volumenklammer
(``klickanschluss``, ``klickraster``).
"""

from __future__ import annotations

import html as html_modul
import re

from ...tarif_model import zahl

_GEBUEHR_FENSTER = 2000
_BEREITSTELLUNGS_RE = re.compile(r"Einmalige Bereitstellungsgebühr")
_MIT_SMARTPHONE_RE = re.compile(r"Tarif mit Smartphone:?\s*</strong>\s*([^<]{1,40})")
_KLAMMERZUSATZ_RE = re.compile(r"\s*\([^()]*\)\s*$")


def bereitstellungsgebuehr(text: str) -> float | None:
    """Die einmalige Bereitstellungsgebühr des Tarifs MIT Smartphone.

    None, wenn die Antwort sie nicht nennt - der Iframe ist auch ohne
    diese Zeile eine gueltige Tarifseite, und ein fehlender Betrag wird
    nie angenommen (E1).
    """
    roh = text or ""
    anfang = _BEREITSTELLUNGS_RE.search(roh)
    if not anfang:
        return None
    treffer = _MIT_SMARTPHONE_RE.search(
        roh, anfang.end(), anfang.end() + _GEBUEHR_FENSTER
    )
    if not treffer:
        return None
    return zahl(html_modul.unescape(treffer.group(1)))


def tarifname_bereinigt(name: str) -> str:
    """ "1&1 All-Net-Flat M (50 GB)" -> "1&1 All-Net-Flat M".

    Das Raster haengt das Volumen in Klammern an; der Tarifbestand fuehrt
    den Namen ohne (`/handytarife`), und `tarif_bezug` loest nur den auf.
    """
    text = " ".join(html_modul.unescape(name or "").split())
    return _KLAMMERZUSATZ_RE.sub("", text).strip()
