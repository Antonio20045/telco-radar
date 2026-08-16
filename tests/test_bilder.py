"""Die Bildbeschaffung: die GROESSE entscheidet, nicht die Herkunft.

Der Befund vom 06.08.2026, an der ausgelieferten Ausgabe gemessen:

* 31 von 193 Meldungen hatten ein Bild, 153 wurden nie auch nur versucht -
  `max_bilder=40` war ein Deckel, kein Ergebnis.
* 18 der 31 geladenen Bilder waren schmaler als 860 px, weil
  `Item.image_url` aus dem Feed VORRANG hatte. Feeds tragen aber ein
  `media:thumbnail`; das `og:image` derselben Seite ist fast immer 1200x630.

Beide Aussagen sind hier als Test festgehalten - ohne Netz, mit einem
MockTransport und echten, mit Pillow erzeugten Bilddaten.
"""
from __future__ import annotations

import io

import httpx
import pytest

from telco_radar.report import bilder

PIL = pytest.importorskip("PIL.Image")


def _jpeg(breite: int, hoehe: int) -> bytes:
    """Ein echtes JPEG der gewuenschten Groesse - kein Attrappenbyte.

    Rauschen statt Einfarbigkeit: eine gleichfarbige Flaeche komprimiert auf
    wenige hundert Byte, und `_hol()` verwirft alles unter 2 kB als
    Zaehlpixel. Der Test wuerde dann das Richtige aus dem falschen Grund
    scheitern lassen.
    """
    import random
    im = PIL.new("RGB", (breite, hoehe))
    zufall = random.Random(breite * hoehe)
    im.putdata([(zufall.randrange(256), zufall.randrange(256),
                 zufall.randrange(256))
                for _ in range(breite * hoehe)])
    puffer = io.BytesIO()
    im.save(puffer, "JPEG", quality=90)
    return puffer.getvalue()


ARTIKEL_HTML = (
    '<html><head><meta property="og:image" '
    'content="https://example.com/gross.jpg"></head><body>x</body></html>')


def _client(antworten: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        antwort = antworten.get(str(request.url))
        if antwort is None:
            return httpx.Response(404)
        return httpx.Response(antwort.status_code, content=antwort.content,
                              headers=antwort.headers)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _bild_antwort(daten: bytes) -> httpx.Response:
    return httpx.Response(200, content=daten,
                          headers={"content-type": "image/jpeg"})


def test_das_groessere_bild_gewinnt_gegen_das_aus_dem_feed(tmp_path):
    """Der eigentliche Fehler: das Feed-Vorschaubild hatte Vorrang."""
    h = {"url": "https://example.com/artikel",
         "image_url": "https://example.com/thumb.jpg"}
    client = _client({
        "https://example.com/thumb.jpg": _bild_antwort(_jpeg(120, 90)),
        "https://example.com/artikel": httpx.Response(
            200, content=ARTIKEL_HTML, headers={"content-type": "text/html"}),
        "https://example.com/gross.jpg": _bild_antwort(_jpeg(1200, 630)),
    })
    with client:
        bilanz = bilder._eine_meldung(h, tmp_path, client, bilder._BREIT_GROSS)

    assert bilanz["geladen"] == 1
    assert h["image_w"] == 1200, "Das 120x90-Vorschaubild hat gewonnen"
    assert (tmp_path / h["image"]).exists()


def test_ein_grosses_feedbild_erspart_den_abruf_der_artikelseite(tmp_path):
    """Der teure Teil ist der zusaetzliche Abruf - er unterbleibt, wenn das
    Feed-Bild schon breit genug ist."""
    h = {"url": "https://example.com/artikel",
         "image_url": "https://example.com/gross-im-feed.jpg"}
    client = _client({
        "https://example.com/gross-im-feed.jpg": _bild_antwort(_jpeg(1400, 800)),
        # Die Artikelseite ist absichtlich NICHT hinterlegt: wird sie doch
        # abgerufen, kommt 404 und `kein_og` steht in der Bilanz.
    })
    with client:
        bilanz = bilder._eine_meldung(h, tmp_path, client, bilder._BREIT_GROSS)

    assert bilanz["geladen"] == 1
    assert "kein_og" not in bilanz and "og_abruf_fehl" not in bilanz


def test_ein_zu_kleines_bild_wird_gar_nicht_erst_abgelegt(tmp_path):
    """Kein Platzhalter, kein hochskaliertes Vorschaubild - lieber Textsatz."""
    h = {"url": "https://example.com/artikel",
         "image_url": "https://example.com/winzig.jpg"}
    client = _client({
        "https://example.com/winzig.jpg": _bild_antwort(_jpeg(120, 90)),
        "https://example.com/artikel": httpx.Response(
            404, content=b"", headers={"content-type": "text/html"}),
    })
    with client:
        bilanz = bilder._eine_meldung(h, tmp_path, client, bilder._BREIT_GROSS)

    assert bilanz["zu_klein"] == 1
    assert "image" not in h


def test_ein_bild_wird_auf_die_zielbreite_heruntergerechnet(tmp_path):
    """Sonst waeren es bei ~130 Bildern je Lauf und zwei Laeufen pro Woche
    mehrere hundert MB im Jahr - und die git-Historie vergisst nie."""
    h = {"url": "https://example.com/a", "image_url": "https://example.com/xxl.jpg"}
    client = _client({"https://example.com/xxl.jpg": _bild_antwort(_jpeg(2400, 1350))})
    with client:
        bilder._eine_meldung(h, tmp_path, client, bilder._BREIT_KLEIN)

    assert h["image_w"] == bilder._BREIT_KLEIN
    with PIL.open(tmp_path / h["image"]) as im:
        assert im.width == bilder._BREIT_KLEIN


def test_ein_altes_bild_ueberlebt_einen_gescheiterten_versuch_nicht(tmp_path):
    """Sonst zeigt die Meldung auf eine Datei, die `raeume_auf()` beim
    naechsten Lauf loescht. Genau so entstanden am 06.08.2026 vier
    Meldungen mit `image`, aber ohne `image_w`."""
    h = {"url": "https://example.com/a", "image": "aus-dem-vorlauf.jpg",
         "image_url": "https://example.com/weg.jpg"}
    with _client({}) as client:
        bilder._eine_meldung(h, tmp_path, client, bilder._BREIT_GROSS)
    assert "image" not in h


def test_share_image_ist_kein_muell():
    """`og:image` IST per Definition das Share-Bild, und mehrere
    Redaktionssysteme benennen die Datei so. Bis zum 06.08.2026 warf der
    Muellfilter genau die weg."""
    assert bilder._taugt("https://example.com/media/share-image-12345.jpg")
    assert bilder._taugt("https://example.com/default-image/artikel.jpg")
    # Was weiterhin faellt:
    assert not bilder._taugt("https://example.com/assets/logo.png")
    assert not bilder._taugt("https://example.com/img/1x1.gif")


def test_es_gibt_keinen_deckel_mehr(tmp_path, monkeypatch):
    """153 von 193 Meldungen wurden nie versucht. Jede wird geprueft."""
    versuche = []

    def falsche_meldung(h, ordner, client, breite):
        versuche.append(h["url"])
        from collections import Counter
        return Counter(geprueft=1)

    monkeypatch.setattr(bilder, "_eine_meldung", falsche_meldung)
    highlights = [{"url": f"https://example.com/{i}", "relevance": i % 5}
                  for i in range(193)]
    bilanz = bilder.hole_bilder(highlights, tmp_path)

    assert bilanz["geprueft"] == 193
    assert len(set(versuche)) == 193


def _png_mit_transparenz(breite=600, hoehe=400) -> bytes:
    """Ein Freisteller, wie ihn jede Tarifseite traegt: farbiges Motiv auf
    DURCHSICHTIGEM Grund."""
    import io as _io
    from PIL import Image
    im = Image.new("RGBA", (breite, hoehe), (0, 0, 0, 0))
    for x in range(breite // 3, 2 * breite // 3):
        for y in range(hoehe // 3, 2 * hoehe // 3):
            im.putpixel((x, y), (230, 0, 0, 255))
    puffer = _io.BytesIO()
    im.save(puffer, "PNG")
    return puffer.getvalue()


def test_transparenz_wird_auf_weiss_gelegt_nicht_auf_schwarz(tmp_path):
    """Der Fehler, den Antonio am 16.08.2026 als "komplett verpixelt" sah.

    `Image.convert("RGB")` wirft den Alphakanal weg, ohne ihn zu verrechnen -
    was durchsichtig war, wird SCHWARZ. Auf der Promo Uebersicht trugen so 13
    von 51 Motiven schwarze Bloecke. Gegen den Stand von vorher faellt dieser
    Test: dort ist die Ecke (0, 0) rein schwarz.
    """
    from PIL import Image
    ziel = tmp_path / "motiv.jpg"
    bilder._schreibe(_png_mit_transparenz(), ziel, 1280)
    with Image.open(ziel) as fertig:
        ecke = fertig.convert("RGB").getpixel((2, 2))
        mitte = fertig.convert("RGB").getpixel((fertig.width // 2,
                                                fertig.height // 2))
    assert min(ecke) > 230, f"durchsichtiger Grund wurde {ecke}, nicht weiss"
    assert mitte[0] > 150 and mitte[1] < 90, f"Motiv verfaelscht: {mitte}"


def test_ist_leer_misst_die_abgelegte_fassung():
    """Gemessen wird, was auf der Seite landet - also mit Transparenz auf
    Weiss. Ein leerer durchsichtiger Rahmen ist leer, ein Freisteller nicht."""
    import io as _io
    from PIL import Image
    puffer = _io.BytesIO()
    Image.new("RGBA", (600, 400), (0, 0, 0, 0)).save(puffer, "PNG")
    assert bilder.ist_leer(puffer.getvalue())
    assert not bilder.ist_leer(_png_mit_transparenz())
