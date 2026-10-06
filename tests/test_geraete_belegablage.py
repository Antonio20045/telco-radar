"""Ablage der Belege (Datenkonzept Geräteradar, Abschnitt 10): Ordner und Bucket.

Der Bucket ist ein lokaler Server auf 127.0.0.1 (``tests/belegserver.py``), der
Schlüssel ein BEISPIEL. Die SigV4-Vektoren stammen aus der AWS-Dokumentation zu S3
(„Signature Calculations for the Authorization Header: Transferring Payload in a Single
Chunk“, Beispiele GET Object und PUT Object).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

import pytest
from belegbau import paket
from belegserver import Anfrage, Antwort, belegserver

from telco_radar.collect.geraete.belegablage import (
    NICHT_EINGERICHTET,
    UMGEBUNG,
    ArchivFehler,
    ArchivNichtEingerichtet,
    B2Ablage,
    LokaleAblage,
    pruefe_schluessel,
    waehle_ablage,
)
from telco_radar.collect.geraete.belegarchiv import ARCHIVIERT, OHNE_BELEG, archiviere
from telco_radar.collect.geraete.belegsignatur import signiere
from telco_radar.collect.geraete.klickecho import Variante
from telco_radar.collect.geraete.klicklauf import (
    BELEG_OFFEN,
    ERFASST,
    Klicklauf,
    Kombiergebnis,
)

ZEIT = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)
GEHEIM = "BEISPIELgeheimerSchluessel0815"
AWS_SCHLUESSEL = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
AWS_ZEIT = datetime(2013, 5, 24, tzinfo=UTC)
SCHLUESSEL = "beispielanbieter/2026-10-03/abc.webp"


def _umgebung(endpunkt: str) -> dict[str, str]:
    return {
        "BELEG_ARCHIV_ENDPUNKT": endpunkt,
        "BELEG_ARCHIV_REGION": "eu-central-003",
        "BELEG_ARCHIV_BUCKET": "telco-belege",
        "BELEG_ARCHIV_KEY_ID": "003beispielkennung",
        "BELEG_ARCHIV_KEY": GEHEIM,
    }


def test_signatur_stimmt_mit_dem_aws_beispiel_get_object():
    leer = hashlib.sha256(b"").hexdigest()

    kopf = signiere(
        "GET",
        "https://examplebucket.s3.amazonaws.com/test.txt",
        {"Range": "bytes=0-9"},
        leer,
        schluessel_id="AKIAIOSFODNN7EXAMPLE",
        schluessel=AWS_SCHLUESSEL,
        region="us-east-1",
        zeitpunkt=AWS_ZEIT,
    )

    assert kopf["Authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/"
        "aws4_request, SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
        "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"
    )
    assert AWS_SCHLUESSEL not in str(kopf)


def test_signatur_stimmt_mit_dem_aws_beispiel_put_object():
    inhalt = hashlib.sha256(b"Welcome to Amazon S3.").hexdigest()

    kopf = signiere(
        "PUT",
        "https://examplebucket.s3.amazonaws.com/test$file.text",
        {
            "Date": "Fri, 24 May 2013 00:00:00 GMT",
            "x-amz-storage-class": "REDUCED_REDUNDANCY",
        },
        inhalt,
        schluessel_id="AKIAIOSFODNN7EXAMPLE",
        schluessel=AWS_SCHLUESSEL,
        region="us-east-1",
        zeitpunkt=AWS_ZEIT,
    )

    assert kopf["Authorization"].endswith(
        "Signature=98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd"
    )


def test_lokale_ablage_legt_liest_und_loescht(tmp_path):
    ablage = LokaleAblage(tmp_path)

    ablage.lege(SCHLUESSEL, b"bild", "image/webp")
    gelesen = ablage.lies(SCHLUESSEL)
    ablage.loesche(SCHLUESSEL)
    ablage.loesche(SCHLUESSEL)

    assert gelesen == b"bild"
    assert ablage.lies(SCHLUESSEL) is None
    assert (tmp_path / "beispielanbieter" / "2026-10-03").is_dir()


@pytest.mark.parametrize("schluessel", ["../x", "/abs", "a//b", "a b", "", "a/../b"])
def test_ungueltiger_schluessel_wirft(tmp_path, schluessel):
    with pytest.raises(ValueError, match="ungültiger Ablageschlüssel"):
        LokaleAblage(tmp_path).lege(schluessel, b"x", "x")
    assert pruefe_schluessel(SCHLUESSEL) == SCHLUESSEL


def test_fehlende_zugangsdaten_heissen_archiv_nicht_eingerichtet():
    teilweise = {"BELEG_ARCHIV_KEY": GEHEIM, "BELEG_ARCHIV_BUCKET": " "}

    with pytest.raises(ArchivNichtEingerichtet) as fehler:
        B2Ablage.aus_umgebung(teilweise, lambda: ZEIT)

    meldung = str(fehler.value)
    assert meldung.startswith(f"{NICHT_EINGERICHTET}: es fehlen ")
    assert fehler.value.fehlend == (
        "BELEG_ARCHIV_ENDPUNKT",
        "BELEG_ARCHIV_REGION",
        "BELEG_ARCHIV_BUCKET",
        "BELEG_ARCHIV_KEY_ID",
    )
    assert GEHEIM not in meldung


def test_ohne_bucket_nimmt_waehle_ablage_den_ordner_mit_hinweis(tmp_path, caplog):
    caplog.set_level(logging.WARNING)

    ablage, hinweis = waehle_ablage({}, tmp_path, lambda: ZEIT)
    bucket, kein_hinweis = waehle_ablage(_umgebung("http://x"), tmp_path, lambda: ZEIT)

    assert isinstance(ablage, LokaleAblage)
    assert hinweis.startswith(NICHT_EINGERICHTET)
    assert str(tmp_path) in hinweis
    assert NICHT_EINGERICHTET in caplog.text
    assert isinstance(bucket, B2Ablage)
    assert kein_hinweis is None
    assert set(UMGEBUNG.values()) == set(_umgebung("x"))


def test_archiv_ohne_bucket_nennt_nicht_eingerichtet_ohne_durchreichen(tmp_path):
    ablage, hinweis = waehle_ablage({}, tmp_path / "ordner", lambda: ZEIT)
    bucket, _ = waehle_ablage(_umgebung("http://x"), tmp_path, lambda: ZEIT)
    lauf = Klicklauf("Beispielanbieter", "http://127.0.0.1:8000/handy/beispielhandy-x")
    offen = Kombiergebnis(
        Variante("256", "S", 24), ERFASST, beleg=paket(), beleg_status=BELEG_OFFEN
    )
    leer = Klicklauf(lauf.anbieter, lauf.adresse)
    lauf.ergebnisse.append(offen)

    bericht = archiviere(lauf, ablage, tmp_path / "m", ZEIT, stempler=lambda d: ())
    ohne = archiviere(leer, ablage, tmp_path / "m", ZEIT, stempler=lambda d: ())

    assert ablage.hinweis == hinweis
    assert (bericht.zustand, ohne.zustand) == (ARCHIVIERT, OHNE_BELEG)
    assert bericht.hinweis.startswith(NICHT_EINGERICHTET)
    assert ohne.hinweis == bericht.hinweis
    assert bucket.hinweis is None


def _bucket(dateien: dict[str, bytes], status: int | None = None):
    def antworte(anfrage: Anfrage) -> Antwort:
        if status is not None:
            return Antwort(status)
        if anfrage.methode == "PUT":
            dateien[anfrage.pfad] = anfrage.koerper
            return Antwort(200)
        if anfrage.methode == "DELETE":
            dateien.pop(anfrage.pfad, None)
            return Antwort(204)
        if anfrage.pfad in dateien:
            return Antwort(200, dateien[anfrage.pfad])
        return Antwort(404)

    return antworte


def test_bucket_legt_liest_und_loescht_mit_signatur(caplog):
    caplog.set_level(logging.DEBUG)
    dateien: dict[str, bytes] = {}
    with belegserver(_bucket(dateien)) as server:
        ablage = B2Ablage.aus_umgebung(_umgebung(server.adresse()), lambda: ZEIT)
        ablage.lege(SCHLUESSEL, b"bild", "image/webp")
        gelesen = ablage.lies(SCHLUESSEL)
        ablage.loesche(SCHLUESSEL)
        fehlt = ablage.lies(SCHLUESSEL)

    pfad = f"/telco-belege/{SCHLUESSEL}"
    assert gelesen == b"bild"
    assert fehlt is None
    assert [(a.methode, a.pfad) for a in server.anfragen] == [
        ("PUT", pfad),
        ("GET", pfad),
        ("DELETE", pfad),
        ("GET", pfad),
    ]
    put = server.anfragen[0]
    assert put.koerper == b"bild"
    assert put.kopf["x-amz-content-sha256"] == hashlib.sha256(b"bild").hexdigest()
    assert put.kopf["x-amz-date"] == "20261003T050000Z"
    assert put.kopf["content-type"] == "image/webp"
    assert put.kopf["Authorization"].startswith(
        "AWS4-HMAC-SHA256 Credential=003beispielkennung/20261003/eu-central-003/s3/"
        "aws4_request, SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date"
    )
    alles = "".join(f"{a.kopf}{a.koerper!r}{a.pfad}" for a in server.anfragen)
    assert GEHEIM not in alles
    assert GEHEIM not in caplog.text
    assert GEHEIM not in repr(ablage)
    assert ablage.ort == f"{server.adresse()}/telco-belege"


@pytest.mark.parametrize("status", [403, 500, 503])
def test_stoerung_des_buckets_wirft_archivfehler_mit_status(status, caplog):
    with belegserver(_bucket({}, status)) as server:
        ablage = B2Ablage.aus_umgebung(_umgebung(server.adresse()), lambda: ZEIT)
        with pytest.raises(ArchivFehler, match=f"HTTP {status}"):
            ablage.lege(SCHLUESSEL, b"x", "image/webp")
        with pytest.raises(ArchivFehler, match=f"HTTP {status}"):
            ablage.lies(SCHLUESSEL)
    assert GEHEIM not in caplog.text


def test_bucket_ohne_antwort_in_der_frist_wirft_archivfehler(caplog):
    caplog.set_level(logging.WARNING)

    def troedelt(anfrage: Anfrage) -> Antwort:
        return Antwort(200, verzug=2.0)

    with belegserver(troedelt) as server:
        zugang = B2Ablage.aus_umgebung(_umgebung(server.adresse()), lambda: ZEIT)
        ablage = B2Ablage(zugang.zugang, zugang.uhr, frist=0.2)
        with pytest.raises(ArchivFehler, match="nicht erreichbar"):
            ablage.lege(SCHLUESSEL, b"x", "image/webp")

    assert "Beleg-Archiv: PUT" in caplog.text
    assert GEHEIM not in caplog.text
