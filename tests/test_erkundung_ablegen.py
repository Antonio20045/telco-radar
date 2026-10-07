"""Was vom Artefakt der Klick-Erkundung auf den öffentlichen Zweig darf.

``scripts/erkundung_ablegen.py`` sortiert die heruntergeladenen Artefakte ein und prüft
den Zweig vor dem Commit. Geprüft wird an Ordnern im Wegwerfordner, aufgebaut wie
``actions/download-artifact`` sie ablegt (``neu/erkundung-<a>/<a>/<tag>/``):
Screenshot und Seite bleiben draußen, ein Teilergebnis ohne gültigen Index ersetzt
keinen vollen Stand, ein verschobener Anbieter überschreibt nichts, und der Leckscan
findet Tokens, Sitzungskennungen, Set-Cookie und Bearer auch in gepackten Dateien.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from scripts import erkundung_ablegen as ea

TAG = "2026-10-06"


def _artefakt(neu: Path, anbieter: str, dateien: dict[str, bytes]) -> Path:
    ordner = neu / f"erkundung-{anbieter}" / anbieter / TAG
    ordner.mkdir(parents=True)
    for name, inhalt in dateien.items():
        (ordner / name).write_bytes(inhalt)
    return ordner


def _index(anbieter: str, status: str = "gelesen", **mehr: object) -> bytes:
    daten = {"anbieter": anbieter, "datum": TAG, "status": status, **mehr}
    return json.dumps(daten).encode()


def _namen(ziel: Path) -> list[str]:
    return sorted(
        p.relative_to(ziel).as_posix() for p in ziel.rglob("*") if p.is_file()
    )


def test_nur_strukturdaten_kommen_auf_den_zweig(tmp_path):
    _artefakt(
        tmp_path / "neu",
        "o2",
        {
            "index.json": _index("o2"),
            "bedienelemente-1.json": b"{}",
            "preise-1.json": b"{}",
            "klicks-1.json": b"{}",
            "mitschnitt-1.json": b"{}",
            "seite-1.png": b"\x89PNG\r\n\x1a\n",
            "seite-1.html.gz": gzip.compress(b"<html></html>"),
        },
    )

    abgelegt = ea.einsortieren(tmp_path / "neu", tmp_path / "zweig")

    assert abgelegt == ["o2"]
    assert _namen(tmp_path / "zweig") == [
        f"o2/{TAG}/{n}"
        for n in (
            "bedienelemente-1.json",
            "index.json",
            "klicks-1.json",
            "mitschnitt-1.json",
            "preise-1.json",
        )
    ]


@pytest.mark.parametrize(
    "teil",
    [
        {"bedienelemente-1.json": b"{}"},
        {"index.json": b"{kaputt", "preise-1.json": b"{}"},
        {"index.json": _index("vodafone"), "preise-1.json": b"{}"},
        {"index.json": _index("o2", "verschoben"), "preise-1.json": b"{}"},
    ],
    ids=["ohne_index", "index_kaputt", "fremder_index", "verschoben"],
)
def test_teilergebnis_ersetzt_keinen_vollen_stand(tmp_path, teil):
    voll = {"index.json": _index("o2"), "preise-1.json": b'{"voll": 1}'}
    _artefakt(tmp_path / "erst", "o2", voll)
    ea.einsortieren(tmp_path / "erst", tmp_path / "zweig")
    _artefakt(tmp_path / "neu", "o2", teil)
    _artefakt(tmp_path / "neu", "vodafone", {"index.json": _index("vodafone")})

    abgelegt = ea.einsortieren(tmp_path / "neu", tmp_path / "zweig")

    assert abgelegt == ["vodafone"]
    o2 = tmp_path / "zweig" / "o2" / TAG
    assert sorted(p.name for p in o2.iterdir()) == ["index.json", "preise-1.json"]
    assert (o2 / "preise-1.json").read_bytes() == b'{"voll": 1}'


def test_ohne_gueltigen_index_ist_der_schritt_rot(tmp_path, capsys):
    _artefakt(tmp_path / "neu", "o2", {"bedienelemente-1.json": b"{}"})

    code = ea.main(["einsortieren", str(tmp_path / "neu"), str(tmp_path / "zweig")])

    assert code == 1
    assert "Kein Anbieter hat ein gültiges index.json" in capsys.readouterr().out
    assert not (tmp_path / "zweig").exists()


def test_nur_verschobene_anbieter_sind_kein_fehler(tmp_path, capsys):
    _artefakt(tmp_path / "neu", "o2", {"index.json": _index("o2", "verschoben")})

    code = ea.main(["einsortieren", str(tmp_path / "neu"), str(tmp_path / "zweig")])

    assert code == 0
    assert "Abgelegt: kein Anbieter" in capsys.readouterr().out
    assert (tmp_path / "zweig").is_dir() and _namen(tmp_path / "zweig") == []


JWT = b"eyJhbGciOiJIUzI1NiJ9.eyJzaWQiOiI0MiJ9.c2lnbmF0dXJl"


@pytest.mark.parametrize(
    ("inhalt", "fund"),
    [
        (b'{"access_token": "' + JWT + b'"}', "JSON Web Token"),
        (b'{"koerper": "JSESSIONID=4F2A9C1B7E"}', "Sitzungskennung"),
        (b'{"sessionId": "SITZUNG0815"}', "Sitzungskennung"),
        (b'{"url": "/tarife?cartId=K7q2Wm9Zx4"}', "Warenkorb-Kennung"),
        (b'{"koerper": "{\\"basketId\\": \\"B4sk3tW3rt9Q\\"}"}', "Warenkorb-Kennung"),
        (b'{"warenkorb": "K7q2Wm9Zx4"}', "Warenkorb-Kennung"),
        (b'{"kopf": "Set-Cookie: a=b"}', "Set-Cookie"),
        (b'{"kopf": "Authorization: Bearer abcdefgh12345"}', "Bearer"),
    ],
)
def test_leckscan_findet_tokens_und_sitzungen(tmp_path, inhalt, fund):
    ordner = tmp_path / "zweig" / "o2" / TAG
    ordner.mkdir(parents=True)
    (ordner / "mitschnitt-1.json").write_bytes(inhalt)

    assert ea.pruefe(tmp_path / "zweig") == [
        f"o2/{TAG}/mitschnitt-1.json: {fund} gefunden"
    ]
    assert ea.main(["pruefe", str(tmp_path / "zweig")]) == 1


def test_kartenprobe_kommt_auf_den_zweig_und_durch_den_leckscan(tmp_path):
    karte = b'{"status": "gelesen", "kombinationen": []}'
    _artefakt(
        tmp_path / "neu", "o2", {"index.json": _index("o2"), "karte-1.json": karte}
    )

    abgelegt = ea.einsortieren(tmp_path / "neu", tmp_path / "zweig")

    assert abgelegt == ["o2"]
    assert _namen(tmp_path / "zweig") == [
        f"o2/{TAG}/index.json",
        f"o2/{TAG}/karte-1.json",
    ]
    assert ea.pruefe(tmp_path / "zweig") == []
    leck = b'{"text": "' + JWT + b'"}'
    (tmp_path / "zweig" / "o2" / TAG / "karte-1.json").write_bytes(leck)
    assert ea.pruefe(tmp_path / "zweig") == [
        f"o2/{TAG}/karte-1.json: JSON Web Token gefunden"
    ]
    assert ea.main(["pruefe", str(tmp_path / "zweig")]) == 1


def test_leckscan_sieht_in_gepackte_dateien_und_nennt_fremde_namen(tmp_path):
    ordner = tmp_path / "zweig" / "o2" / TAG
    ordner.mkdir(parents=True)
    (ordner / "seite-1.html.gz").write_bytes(gzip.compress(b"<p>" + JWT + b"</p>"))

    assert ea.pruefe(tmp_path / "zweig") == [
        f"o2/{TAG}/seite-1.html.gz: Datei gehört nicht auf den öffentlichen Zweig",
        f"o2/{TAG}/seite-1.html.gz: JSON Web Token gefunden",
    ]


def test_geschwaerzte_werte_sind_kein_leck(tmp_path):
    ordner = tmp_path / "zweig" / "o2" / TAG
    ordner.mkdir(parents=True)
    sauber = (
        b'{"sessionId": "ENTFERNT", "k": "JSESSIONID=ENTFERNT",'
        b' "c": "sid=[Cookie entfernt]", "a": "Bearer ENTFERNT",'
        b' "u": "/tarife?cartId=ENTFERNT&warenkorb=[Cookie entfernt]",'
        b' "koerper": "{\\"basketId\\": \\"ENTFERNT\\"}",'
        b' "pfad": "add-to-cart-button:nth-of-type(1)",'
        b' "href": "https://www.vodafone.de/shop/warenkorb.html",'
        b' "text": "Warenkorb: 2 Artikel"}'
    )
    (ordner / "mitschnitt-1.json").write_bytes(sauber)

    assert ea.pruefe(tmp_path / "zweig") == []
    assert ea.main(["pruefe", str(tmp_path / "zweig")]) == 0
