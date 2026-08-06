"""Bilder fuer den Wochenbericht: beschaffen, pruefen, lokal ablegen.

Eine Zeitung ohne Bilder ist eine Textwueste - genau das war der Befund am
06.08.2026. Die Meldungen selbst tragen aber keine Bilder, also holt diese
Stufe sie aus zwei Quellen, in dieser Reihenfolge:

1. **Aus dem Feed-Eintrag** (`Item.image_url`, gesetzt in collect/rss.py).
   Kostet keinen zusaetzlichen Abruf und funktioniert auch bei Seiten, die
   einen direkten Aufruf mit 403 abweisen - den Feed haben wir ja schon.
2. **`og:image` der Artikelseite.** Nur fuer die wenigen Meldungen, die es
   auf die Titelseite schaffen, und nur wenn (1) nichts geliefert hat.

Gemessen am Bericht vom 05.08.2026: von den acht dringendsten Meldungen
liefern vier ein `og:image`, drei Seiten antworten dem Abruf mit 403
(Mobile World Live, Telecoms.com, Capacity Media), eine hat keins. Der
Layout MUSS also ohne Bild auskommen - es gibt keine Garantie, und ein
Platzhalterbild waere schlimmer als keins.

Die Bilder werden heruntergeladen und liegen als Pipeline-State unter
data/state/report_images/. Sie werden bei jedem Rendern nach site/images/
kopiert, wie die Promo-Screenshots auch - nie von Hand in site/ legen.
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

log = logging.getLogger(__name__)

# Groesse: gross genug fuer den Aufmacher (rund 900px breit dargestellt),
# klein genug, dass ein Bericht das Repo nicht sprengt.
_MAX_BYTES = 1_400_000
_TIMEOUT = 12.0
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_ERLAUBTE_TYPEN = ("image/jpeg", "image/png", "image/webp", "image/avif")
_ENDUNG = {"image/jpeg": ".jpg", "image/png": ".png",
           "image/webp": ".webp", "image/avif": ".avif"}

_OG_RE = (
    re.compile(r'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::url)?["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)', re.I),
)
# Logos, Zaehlpixel und Platzhalter sehen aus wie Bilder und sind keine.
_MUELL = re.compile(
    r"(logo|sprite|icon|favicon|placeholder|avatar|1x1|pixel|spacer|blank|"
    r"default[-_]?(image|thumb)|share[-_]?image)", re.I)


def bildordner(root: Path) -> Path:
    return Path(root) / "data" / "state" / "report_images"


def _taugt(url: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    return not _MUELL.search(urlsplit(url).path)


def og_bild(seiten_url: str, client: httpx.Client) -> str:
    """Die og:image-URL einer Artikelseite, oder "" wenn es keine gibt."""
    try:
        r = client.get(seiten_url, follow_redirects=True)
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return ""
        # Nur der Kopfbereich - og:image steht im <head>, und manche
        # Artikelseiten sind mehrere Megabyte gross.
        kopf = r.text[:200_000]
        for muster in _OG_RE:
            m = muster.search(kopf)
            if m:
                url = urljoin(str(r.url), m.group(1).strip())
                if _taugt(url):
                    return url
    except (httpx.HTTPError, ValueError) as exc:
        log.debug("og:image fehlgeschlagen fuer %s: %s", seiten_url, exc)
    return ""


def _lade(bild_url: str, ziel_ordner: Path, client: httpx.Client) -> str:
    """Laedt ein Bild und gibt den Dateinamen zurueck ("" bei Fehlschlag)."""
    name_basis = hashlib.sha1(bild_url.encode("utf-8")).hexdigest()[:16]
    for endung in set(_ENDUNG.values()):
        vorhanden = ziel_ordner / f"{name_basis}{endung}"
        if vorhanden.exists():
            return vorhanden.name        # schon aus einem frueheren Lauf da
    try:
        r = client.get(bild_url, follow_redirects=True)
        if r.status_code != 200:
            return ""
        typ = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if typ not in _ERLAUBTE_TYPEN or len(r.content) > _MAX_BYTES:
            return ""
        # Winzige Dateien sind Zaehlpixel oder kaputte Platzhalter.
        if len(r.content) < 4_000:
            return ""
        ziel_ordner.mkdir(parents=True, exist_ok=True)
        ziel = ziel_ordner / f"{name_basis}{_ENDUNG[typ]}"
        ziel.write_bytes(r.content)
        return ziel.name
    except (httpx.HTTPError, OSError) as exc:
        log.debug("Bild-Download fehlgeschlagen fuer %s: %s", bild_url, exc)
    return ""


def hole_bilder(highlights: list[dict], root: Path, max_bilder: int = 40,
                og_versuche: int = 34) -> int:
    """Beschafft Bilder fuer die wichtigsten Meldungen und stempelt sie ein.

    Setzt `h["image"]` auf den Dateinamen im Bildordner. Meldungen ohne Bild
    behalten schlicht keins - der Layout faengt das ab.

    Die dringendsten Meldungen zuerst. Der Deckel liegt bei 40, weil die
    Meldungsseite ALLE Meldungen der Woche zeigt und nicht nur die der
    Titelseite - gemessen am 05.08.2026 kommen dabei 20 Bilder fuer 92
    Meldungen zusammen, der Rest bleibt Textsatz.
    """
    ordner = bildordner(root)
    kandidaten = sorted(highlights, key=lambda h: (h.get("relevance") or 0),
                        reverse=True)[:max_bilder]
    if not kandidaten:
        return 0

    geladen = 0
    og_offen = og_versuche
    with httpx.Client(headers={"User-Agent": _UA}, timeout=_TIMEOUT) as client:
        for h in kandidaten:
            bild_url = (h.get("image_url") or "").strip()
            if not _taugt(bild_url) and og_offen > 0 and h.get("url"):
                og_offen -= 1
                bild_url = og_bild(h["url"], client)
            if not _taugt(bild_url):
                continue
            name = _lade(bild_url, ordner, client)
            if name:
                h["image"] = name
                geladen += 1
    log.info("Bilder: %d von %d geprueften Meldungen haben eins", geladen,
             len(kandidaten))
    return geladen


def raeume_auf(root: Path, reports_dir: Path, behalte_berichte: int = 8) -> int:
    """Loescht Bilder, die kein aktueller Bericht mehr referenziert.

    Ohne das waechst das Repo unbegrenzt: rund 9 Bilder je Lauf mal zwei
    Laeufe pro Woche sind ueber ein Jahr etwa 200 MB, fuer Bilder, die nach
    zwei Wochen niemand mehr ansieht. Die letzten `behalte_berichte`
    Ausgaben behalten ihre Bilder - so bleibt das Archiv der jungen Wochen
    bebildert, aeltere Archivseiten fallen auf den Textsatz zurueck (der
    Layout kommt ohne Bild aus, das ist von Anfang an so gebaut).
    """
    import json
    ordner = bildordner(root)
    if not ordner.exists():
        return 0
    berichte = sorted(
        (f for f in reports_dir.glob("*.json")
         if re.fullmatch(r"\d{4}-\d{2}-\d{2}", f.stem)),
        reverse=True)[:behalte_berichte]
    gebraucht: set[str] = set()
    for f in berichte:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for region in (d.get("regions") or {}).values():
            for h in region.get("highlights") or []:
                if h.get("image"):
                    gebraucht.add(h["image"])
    geloescht = 0
    for bild in ordner.iterdir():
        if bild.is_file() and bild.name not in gebraucht:
            try:
                bild.unlink()
                geloescht += 1
            except OSError:
                pass
    if geloescht:
        log.info("Bilder aufgeraeumt: %d nicht mehr referenzierte geloescht",
                 geloescht)
    return geloescht
