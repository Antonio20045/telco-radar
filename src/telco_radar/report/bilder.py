"""Bilder fuer den Wochenbericht: beschaffen, MESSEN, verkleinern, ablegen.

Bis zum 06.08.2026 hatte diese Stufe zwei Konstruktionsfehler, und beide
waren am ausgelieferten Bericht messbar:

1. **Ein Deckel.** `max_bilder=40` bei 193 Meldungen. 153 Meldungen wurden
   nie auch nur versucht - nicht "haben kein Bild", sondern *nie gefragt*.
   Eine Stichprobe von 25 dieser nie versuchten Meldungen ergab: 15 haben
   ein `og:image`, 4 haben keins, 5 antworten mit 403, 1 liefert kein HTML.
   Der Deckel ist weg; die Frist je Meldung und die Nebenlaeufigkeit
   ersetzen ihn.
2. **Die falsche Reihenfolge.** Es galt "Feed-Bild zuerst, `og:image` nur
   wenn der Feed nichts hat". Feeds tragen aber ein `media:thumbnail` -
   also ein bewusst kleines Vorschaubild. 18 der 31 geladenen Bilder waren
   dadurch schmaler als 860 px, der Aufmacher der Ausgabe vom 6.8. lag bei
   120x90 und wurde auf ~620 px hochskaliert.

Jetzt entscheidet die GROESSE, nicht die Herkunft: beide Kandidaten werden
geholt, mit Pillow gemessen, das breitere gewinnt. Nur wenn das Feed-Bild
schon breit genug ist (`_GUT_GENUG`), bleibt der Abruf der Artikelseite aus
- der ist der teure Teil.

Die Bilder werden auf Zeitungsmasse verkleinert und als JPEG abgelegt
(`_BREIT_GROSS` fuer die Meldungen, die gross stehen koennen, `_BREIT_KLEIN`
fuer den Rest). Das ist kein Schoenheitsdienst, sondern Repo-Hygiene: ohne
Umrechnung waeren es bei ~130 Bildern je Lauf und zwei Laeufen pro Woche
mehrere hundert MB im Jahr, und die Historie vergisst nie.

Sie liegen als Pipeline-State unter data/state/report_images/ und werden bei
jedem Rendern nach site/images/ kopiert, wie die Promo-Screenshots auch -
nie von Hand in site/ legen.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

log = logging.getLogger(__name__)

_MAX_BYTES = 6_000_000       # Rohdaten; verkleinert wird danach
_TIMEOUT = 10.0
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_ERLAUBTE_TYPEN = ("image/jpeg", "image/png", "image/webp", "image/avif",
                   "image/jpg")

# Wie viele Meldungen gleichzeitig bearbeitet werden. Jede kostet bis zu
# drei Abrufe (Artikelseite + zwei Bilder); 12 gleichzeitig halten die
# Sammelzeit bei ~190 Meldungen im Bereich einer Minute, ohne dass eine
# einzelne Domain unter Dauerfeuer kommt.
_GLEICHZEITIG = 12

# Zielmasse. Der Aufmacher steht bei 1440 px Fensterbreite rund 620 px
# breit, auf einem Retina-Schirm sind das 1240 echte Pixel - darueber
# hinaus sieht niemand einen Unterschied.
_BREIT_GROSS = 1280
# Das Listenbild steht bei 800, nicht bei 700: eine Meldung von Rang 60 kann
# als Ressortaufmacher rund 380 px breit stehen, auf Retina also 760 echte
# Pixel. Bei 700 waeren genau die Ressortaufmacher wieder hochskaliert - der
# Fehler, den diese Datei gerade behebt, nur eine Ebene tiefer.
_BREIT_KLEIN = 800
_JPEG_QUALITAET = 78
# Ab hier lohnt der zusaetzliche Abruf der Artikelseite nicht mehr: das
# Feed-Bild ist bereits gross genug fuer jede Position auf der Seite.
_GUT_GENUG = 1000
# Darunter ist ein Bild als Bild wertlos - es waere in jeder Position
# hochskaliert. Lieber Textsatz.
_MIND_BREITE = 400
# Was der Aufmacher und die zweite Reihe verlangen (Abnahmekriterium 3).
MIND_BREITE_GROSS = 800

_OG_RE = (
    re.compile(r'<meta[^>]+property=["\']og:image(?::url)?["\'][^>]+content=["\']([^"\']+)', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::url)?["\']', re.I),
    re.compile(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)', re.I),
)
# Logos, Zaehlpixel und Platzhalter sehen aus wie Bilder und sind keine.
#
# "share-image" und "default-image" standen bis zum 06.08.2026 mit in dieser
# Liste. Das war ein Denkfehler: `og:image` IST per Definition das
# Share-Bild, und mehrere Redaktionssysteme benennen die Datei genau so.
# Seit die Groesse gemessen wird, braucht es diesen Verdacht auch nicht mehr
# - ein 1200x630-Bild ist ein Artikelbild, egal wie die Datei heisst, und
# ein 60x60-Logo faellt ohnehin durch `_MIND_BREITE`.
_MUELL = re.compile(
    r"(logo|sprite|favicon|/icons?[-_/.]|placeholder|avatar|1x1|"
    r"pixel|spacer|blank)", re.I)


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
    except (httpx.HTTPError, ValueError, UnicodeDecodeError) as exc:
        log.debug("og:image fehlgeschlagen fuer %s: %s", seiten_url, exc)
    return ""


def _hol(bild_url: str, client: httpx.Client) -> bytes:
    """Laedt die Rohdaten eines Bildes ("" bzw. b"" bei Fehlschlag)."""
    try:
        r = client.get(bild_url, follow_redirects=True)
        if r.status_code != 200:
            return b""
        typ = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if typ not in _ERLAUBTE_TYPEN or len(r.content) > _MAX_BYTES:
            return b""
        if len(r.content) < 2_000:   # Zaehlpixel oder kaputter Platzhalter
            return b""
        return r.content
    except (httpx.HTTPError, OSError) as exc:
        log.debug("Bild-Download fehlgeschlagen fuer %s: %s", bild_url, exc)
    return b""


def masse(daten: bytes) -> tuple[int, int]:
    """Breite und Hoehe eines Bildes aus den Rohdaten - (0, 0) wenn unlesbar.

    Pillow liest dafuer nur den Dateikopf, nicht die Pixel.
    """
    try:
        from PIL import Image
        with Image.open(io.BytesIO(daten)) as im:
            return im.size
    except Exception:                # noqa: BLE001 - jedes kaputte Bild faellt hier durch
        return (0, 0)


# Ein Bild, dessen Pixel praktisch alle denselben Wert haben, zeigt nichts.
# Gemessen an den 15 Promo-Screenshots vom 07.08.2026: der leere
# telekom-deutschland.jpg hat eine Standardabweichung von exakt 0,00, der
# naechstflaue (otelo.jpg, eine dunkle Seite) 38,67. Dazwischen liegt kein
# Grenzfall, die Schwelle ist also unkritisch gewaehlt. Ueber die Dateigroesse
# ginge es auch (6 KB gegen 58-114 KB), aber die haengt an der
# JPEG-Qualitaet; der Bildinhalt tut das nicht.
_MIND_STREUUNG = 6.0


def ist_leer(daten: bytes) -> bool:
    """True, wenn das Bild eine einfarbige Flaeche ist - also nichts zeigt.

    Der Fall, fuer den das gebaut wurde: die Promo-Uebersicht band als
    einziges Bild einen 1280x720-Screenshot ein, der eine weisse Seite war
    (Aufnahme vor dem Seitenaufbau). Masse und Dateityp waren tadellos -
    nur zu sehen war nichts. Wer nur `masse()` prueft, sieht das nie.
    """
    try:
        from PIL import Image, ImageStat
        with Image.open(io.BytesIO(daten)) as im:
            grau = im.convert("L")
            return ImageStat.Stat(grau).stddev[0] < _MIND_STREUUNG
    except Exception:                # noqa: BLE001 - unlesbar zeigt auch nichts
        return True


def _schreibe(daten: bytes, ziel: Path, max_breite: int) -> tuple[int, int]:
    """Verkleinert auf `max_breite` und legt das Bild als JPEG ab.

    Gibt die Masse der ABGELEGTEN Datei zurueck - das ist die Zahl, mit der
    die Seite spaeter rechnet, nicht die des Originals.
    """
    from PIL import Image
    with Image.open(io.BytesIO(daten)) as im:
        im = im.convert("RGB")       # PNG mit Alpha, Palette, CMYK
        if im.width > max_breite:
            hoehe = max(1, round(im.height * max_breite / im.width))
            im = im.resize((max_breite, hoehe), Image.LANCZOS)
        ziel.parent.mkdir(parents=True, exist_ok=True)
        im.save(ziel, "JPEG", quality=_JPEG_QUALITAET, optimize=True,
                progressive=True)
        return im.size


def _dateiname(bild_url: str, max_breite: int) -> str:
    """Stabiler Name. Die Zielbreite gehoert hinein: dieselbe Quell-URL kann
    einmal als Listenbild und einmal als Aufmacherbild gebraucht werden."""
    return f"{hashlib.sha1(bild_url.encode('utf-8')).hexdigest()[:16]}-{max_breite}.jpg"


def lade_und_lege_ab(bild_url: str, ordner: Path, max_breite: int,
                     client: httpx.Client,
                     mind_breite: int = _MIND_BREITE) -> tuple[str, int, int] | None:
    """Holt EIN Bild, misst es, verkleinert es und legt es ab.

    Gibt `(dateiname, breite, hoehe)` der abgelegten Datei zurueck - oder
    None, wenn die URL nichts taugt, der Abruf scheitert, das Bild schmaler
    als *mind_breite* ist, nichts zeigt (`ist_leer`) oder sich nicht
    schreiben laesst. Wirft nie.

    Herausgezogen fuer promo_bilder.py: die Promo-Uebersicht braucht genau
    diesen Ablauf, nur ohne die Feed-gegen-og:image-Abwaegung von
    `_eine_meldung()`. Zwei Kopien davon waeren zwei Orte, an denen die
    Mindestbreite auseinanderlaufen kann - und genau daran ist die
    Bebilderung schon einmal gescheitert (Feed-Thumbnails im Aufmacher).
    Ein Bild, das ein frueherer Lauf schon abgelegt hat, wird nicht erneut
    geholt: der Dateiname haengt an URL und Zielbreite."""
    if not _taugt(bild_url):
        return None
    fertig = ordner / _dateiname(bild_url, max_breite)
    if fertig.exists():
        w, hh = masse(fertig.read_bytes())
        if w >= mind_breite:
            return fertig.name, w, hh
    daten = _hol(bild_url, client)
    if not daten:
        return None
    w, _ = masse(daten)
    if w < mind_breite or ist_leer(daten):
        return None
    try:
        breite, hoehe = _schreibe(daten, fertig, max_breite)
    except Exception as exc:         # noqa: BLE001 - ein kaputtes Bild kippt keinen Lauf
        log.debug("Bild konnte nicht abgelegt werden (%s): %s", bild_url, exc)
        return None
    return fertig.name, breite, hoehe


def _eine_meldung(h: dict, ordner: Path, client: httpx.Client,
                  max_breite: int) -> Counter:
    """Beschafft das beste verfuegbare Bild EINER Meldung.

    Setzt bei Erfolg h["image"], h["image_w"], h["image_h"].
    """
    z: Counter = Counter(geprueft=1)
    # Ein Bild aus einem FRUEHEREN Lauf muss weg, bevor der neue Versuch
    # laeuft. Sonst ueberlebt eine Meldung, deren Bild diesmal nicht zu
    # holen war, mit dem alten Dateinamen - und der zeigt auf eine Datei,
    # die `raeume_auf()` beim naechsten Mal loescht. Genau so entstanden am
    # 06.08.2026 vier Meldungen mit `image`, aber ohne `image_w`.
    for feld in ("image", "image_w", "image_h"):
        h.pop(feld, None)

    feed_url = (h.get("image_url") or "").strip()
    if feed_url and not _taugt(feed_url):
        z["muellfilter"] += 1
        feed_url = ""

    kandidaten: list[tuple[str, bytes, int, int]] = []

    if feed_url:
        # Ein Kandidat, den ein frueherer Lauf schon abgelegt hat, muss nicht
        # erneut durchs Netz - der Dateiname haengt an URL und Zielbreite.
        fertig = ordner / _dateiname(feed_url, max_breite)
        if fertig.exists():
            w, hh = masse(fertig.read_bytes())
            if w >= _MIND_BREITE:
                h["image"], h["image_w"], h["image_h"] = fertig.name, w, hh
                z["geladen"] += 1
                z["aus_cache"] += 1
                return z
        daten = _hol(feed_url, client)
        if daten:
            w, hh = masse(daten)
            if w:
                kandidaten.append((feed_url, daten, w, hh))
                z["feed_bild"] += 1
            else:
                z["unlesbar"] += 1
        else:
            z["feed_abruf_fehl"] += 1

    beste_feedbreite = max((w for _, _, w, _ in kandidaten), default=0)
    if beste_feedbreite < _GUT_GENUG and h.get("url"):
        og_url = og_bild(h["url"], client)
        if og_url and og_url != feed_url:
            daten = _hol(og_url, client)
            if daten:
                w, hh = masse(daten)
                if w:
                    kandidaten.append((og_url, daten, w, hh))
                    z["og_bild"] += 1
                else:
                    z["unlesbar"] += 1
            else:
                z["og_abruf_fehl"] += 1
        elif not og_url:
            z["kein_og"] += 1

    if not kandidaten:
        return z

    # Die Groesse entscheidet - nicht, ob das Bild aus dem Feed kam.
    url, daten, w, hh = max(kandidaten, key=lambda k: k[2])
    if w < _MIND_BREITE:
        z["zu_klein"] += 1
        return z
    try:
        ziel = ordner / _dateiname(url, max_breite)
        breite, hoehe = _schreibe(daten, ziel, max_breite)
    except Exception as exc:         # noqa: BLE001 - ein kaputtes Bild kippt keinen Lauf
        log.debug("Bild konnte nicht abgelegt werden (%s): %s", url, exc)
        z["schreibfehler"] += 1
        return z
    h["image"], h["image_w"], h["image_h"] = ziel.name, breite, hoehe
    z["geladen"] += 1
    return z


def hole_bilder(highlights: list[dict], root: Path,
                gross_bis_rang: int = 40) -> dict:
    """Beschafft Bilder fuer ALLE Meldungen und stempelt sie ein.

    Setzt `h["image"]` auf den Dateinamen im Bildordner sowie `h["image_w"]`
    und `h["image_h"]` auf die abgelegten Masse. Meldungen ohne Bild behalten
    schlicht keins - der Satz faengt das ab, ein Platzhalter waere schlimmer.

    Die dringendsten `gross_bis_rang` Meldungen werden in Aufmachergroesse
    abgelegt (`_BREIT_GROSS`), alle weiteren als Listenbild
    (`_BREIT_KLEIN`). Nur die vorderen koennen auf der Titelseite oder als
    Ressortaufmacher gross stehen; ein 1280-px-JPEG fuer eine Zeile weit
    unten waere reiner Repo-Ballast.

    Gibt die Bilanz zurueck (geprueft, geladen, warum die anderen nicht) -
    die Pipeline schreibt sie ins Laufprotokoll. "0 von 193" und "0 von 40"
    sind zwei verschiedene Befunde, und bis zum 06.08.2026 sah man den
    Unterschied nirgends.
    """
    ordner = bildordner(root)
    kandidaten = sorted(highlights, key=lambda h: (h.get("relevance") or 0),
                        reverse=True)
    if not kandidaten:
        return dict(Counter())

    bilanz: Counter = Counter()
    with httpx.Client(headers={"User-Agent": _UA}, timeout=_TIMEOUT,
                      follow_redirects=True) as client:
        def arbeite(paar: tuple[int, dict]) -> Counter:
            i, h = paar
            breite = _BREIT_GROSS if i < gross_bis_rang else _BREIT_KLEIN
            try:
                return _eine_meldung(h, ordner, client, breite)
            except Exception as exc:  # noqa: BLE001
                log.debug("Bildbeschaffung fuer %s gescheitert: %s",
                          h.get("url"), exc)
                return Counter(geprueft=1, fehler=1)

        with ThreadPoolExecutor(max_workers=_GLEICHZEITIG) as pool:
            for teil in pool.map(arbeite, enumerate(kandidaten)):
                bilanz.update(teil)

    log.info("Bilder: %d von %d Meldungen haben eins (%s)",
             bilanz["geladen"], bilanz["geprueft"],
             ", ".join(f"{k}={v}" for k, v in sorted(bilanz.items())))
    return dict(bilanz)


def raeume_auf(root: Path, reports_dir: Path, behalte_berichte: int = 4) -> int:
    """Loescht Bilder, die kein aktueller Bericht mehr referenziert.

    Ohne das waechst das Repo unbegrenzt. Seit der Deckel weg ist, sind es
    rund 120 statt 9 Bilder je Lauf - deshalb stehen hier jetzt vier statt
    acht Ausgaben. Die letzten vier behalten ihre Bilder, aeltere
    Archivseiten fallen auf den Textsatz zurueck (der Satz kommt ohne Bild
    aus, das ist von Anfang an so gebaut).
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
