"""Das Bild zum Preis: WebP unter dem Größenziel."""

from __future__ import annotations

import io
import random
from types import SimpleNamespace

import pytest
from PIL import Image

from telco_radar.collect.geraete.belegbild import (
    BREITE_MAX,
    ZIEL_BYTES,
    BildFehler,
    speichere_bilder,
    verkleinere,
    zwischenname,
)
from telco_radar.collect.geraete.klicklauf import ERFASST


def png(breite: int, hoehe: int, rauschen: bool) -> bytes:
    zufall = random.Random(7)
    bild = Image.new("RGB", (breite, hoehe), (250, 250, 250))
    if rauschen:
        bild.putdata([(zufall.randrange(256),) * 3 for _ in range(breite * hoehe)])
    ziel = io.BytesIO()
    bild.save(ziel, "PNG")
    return ziel.getvalue()


def test_zwischenname_ist_die_beleg_id():
    assert zwischenname("abc123") == "abc123.webp"


def test_breites_bild_wird_schmaler_und_klein():
    daten = verkleinere(png(2400, 800, rauschen=True))
    bild = Image.open(io.BytesIO(daten))
    assert bild.format == "WEBP"
    assert bild.width <= BREITE_MAX
    assert len(daten) <= ZIEL_BYTES


def test_einfaches_bild_bleibt_klein():
    daten = verkleinere(png(600, 300, rauschen=False))
    assert Image.open(io.BytesIO(daten)).size == (600, 300)
    assert len(daten) <= ZIEL_BYTES


def test_kein_bild_ist_eine_benannte_ausnahme():
    with pytest.raises(BildFehler):
        verkleinere(b"das ist kein png")


def ergebnis(beleg_id: str | None, bild: bytes | None, status: str = ERFASST):
    paket = None
    if beleg_id is not None:
        paket = SimpleNamespace(
            beleg=SimpleNamespace(beleg_id=beleg_id, bildfolge=()), folgebilder={}
        )
    return SimpleNamespace(status=status, beleg=paket, screenshot_png=bild)


def test_bilder_heissen_wie_die_beleg_id_und_fehlendes_wird_gezaehlt(tmp_path):
    lauf = SimpleNamespace(
        adresse="https://anbieter.example/",
        ergebnisse=[
            ergebnis("abc", png(600, 300, rauschen=False)),
            ergebnis(None, png(600, 300, rauschen=False)),
            ergebnis("def", None),
            ergebnis("ghi", b"kein png"),
            ergebnis("jkl", png(600, 300, rauschen=False), status="fehler"),
        ],
    )
    bilanz = speichere_bilder(lauf, tmp_path / "belege")
    assert (bilanz.geschrieben, bilanz.ohne_bild, bilanz.fehler) == (1, 2, 1)
    assert [p.name for p in (tmp_path / "belege").iterdir()] == ["abc.webp"]
