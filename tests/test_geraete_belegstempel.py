"""Zeitstempel des Manifests (Datenkonzept Geräteradar, Abschnitt 10), ohne Netz.

RFC 3161 beantwortet ein lokaler Zeitstempeldienst: ``openssl ts -reply`` mit einem
eigens erzeugten Testschlüssel, kein echter Dienst. Die Calendar-Server von
OpenTimestamps sind ein lokaler Server, der eine BEISPIEL-Antwort mit ausstehender
Bestätigung liefert.
"""

from __future__ import annotations

import hashlib
import subprocess

import pytest
from belegserver import Anfrage, Antwort, belegserver

from telco_radar.collect.geraete.belegstempel import (
    AUSGEFALLEN,
    GESTEMPELT,
    OPENTIMESTAMPS,
    OTS_AUSSTEHEND,
    RFC3161,
    stemple,
    stemple_ots,
    stemple_rfc3161,
)

DIGEST = hashlib.sha256(b"BEISPIEL-Manifest").hexdigest()
ANDERER = hashlib.sha256(b"anderes Manifest").hexdigest()
OTS_ANTWORT = (
    b"\xf0\x10"
    + bytes(16)
    + b"\x08\x00"
    + OTS_AUSSTEHEND
    + b"\x1chttps://beispiel.invalid"
)
FRIST = 0.5


@pytest.fixture(scope="module")
def tsa(tmp_path_factory):
    """Schlüssel, Zertifikat und Einstellung eines Test-Zeitstempeldienstes."""
    ordner = tmp_path_factory.mktemp("tsa")
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "ec",
            "-pkeyopt",
            "ec_paramgen_curve:prime256v1",
            "-nodes",
            "-keyout",
            str(ordner / "k.pem"),
            "-out",
            str(ordner / "c.pem"),
            "-days",
            "2",
            "-subj",
            "/CN=Test-TSA",
            "-addext",
            "extendedKeyUsage=critical,timeStamping",
        ],
        check=True,
        capture_output=True,
    )
    (ordner / "t.cnf").write_text(
        "[ tsa ]\ndefault_tsa = t\n[ t ]\n"
        f"serial = {ordner / 'serial'}\ndefault_policy = 1.2.3.4.1\n"
        "digests = sha256\nsigner_digest = sha256\ness_cert_id_alg = sha256\n",
        "utf-8",
    )
    return ordner


def _antworte_tsa(ordner, digest_ersetzen: str | None = None):
    def antworte(anfrage: Anfrage) -> Antwort:
        frage = ordner / "q.tsq"
        frage.write_bytes(anfrage.koerper)
        if digest_ersetzen is not None:
            befehl = ["-query", "-digest", digest_ersetzen, "-sha256", "-cert"]
            frage.write_bytes(_openssl(*befehl))
        _openssl(
            "-reply",
            "-config",
            str(ordner / "t.cnf"),
            "-queryfile",
            str(frage),
            "-signer",
            str(ordner / "c.pem"),
            "-inkey",
            str(ordner / "k.pem"),
            "-out",
            str(ordner / "r.tsr"),
        )
        return Antwort(
            200, (ordner / "r.tsr").read_bytes(), "application/timestamp-reply"
        )

    return antworte


def _openssl(*argumente: str) -> bytes:
    lauf = subprocess.run(
        ["openssl", "ts", *argumente], capture_output=True, check=True
    )
    return lauf.stdout


def test_rfc3161_stempel_vom_dienst_mit_demselben_digest(tsa):
    with belegserver(_antworte_tsa(tsa)) as server:
        stempel = stemple_rfc3161(DIGEST, tsa=server.adresse("/tsr"), frist=5)

    assert stempel.zustand == GESTEMPELT, stempel.grund
    assert stempel.verfahren == RFC3161
    assert stempel.grund is None
    assert stempel.token
    anfrage = server.anfragen[0]
    assert (anfrage.methode, anfrage.pfad) == ("POST", "/tsr")
    assert anfrage.kopf["Content-Type"] == "application/timestamp-query"


def test_rfc3161_antwort_fuer_einen_anderen_digest_ist_ein_ausfall(tsa):
    with belegserver(_antworte_tsa(tsa, ANDERER)) as server:
        stempel = stemple_rfc3161(DIGEST, tsa=server.adresse("/tsr"), frist=5)

    assert stempel.zustand == AUSGEFALLEN
    assert stempel.grund == "Antwort stempelt einen anderen Digest"
    assert stempel.token is None


@pytest.mark.parametrize(
    ("antwort", "grund"),
    [
        (Antwort(500), "HTTP 500"),
        (Antwort(503), "HTTP 503"),
        (Antwort(200, b"kein Stempel"), "Antwort unlesbar"),
        (Antwort(200, verzug=2.0), f"keine Antwort in {FRIST:g} s"),
    ],
)
def test_rfc3161_ausfall_ist_ein_benannter_zustand(antwort, grund):
    with belegserver(lambda anfrage: antwort) as server:
        stempel = stemple_rfc3161(DIGEST, tsa=server.adresse("/tsr"), frist=FRIST)

    assert stempel.zustand == AUSGEFALLEN
    assert stempel.grund.startswith(grund)
    assert stempel.token is None


def test_ohne_openssl_ist_rfc3161_ein_benannter_ausfall():
    with belegserver(lambda anfrage: Antwort(200)) as server:
        stempel = stemple_rfc3161(
            DIGEST, tsa=server.adresse(), openssl="/gibt/es/nicht/openssl", frist=FRIST
        )

    assert stempel.zustand == AUSGEFALLEN
    assert stempel.grund == "openssl fehlt (/gibt/es/nicht/openssl)"
    assert server.anfragen == []


def test_nicht_erreichbarer_dienst_ist_ein_benannter_ausfall():
    with belegserver(lambda anfrage: Antwort(200)) as server:
        adresse = server.adresse("/tsr")

    stempel = stemple_rfc3161(DIGEST, tsa=adresse, frist=FRIST)

    assert stempel.zustand == AUSGEFALLEN
    assert stempel.grund.startswith("nicht erreichbar")


def test_opentimestamps_schickt_den_digest_an_jeden_kalender():
    def antworte(anfrage: Anfrage) -> Antwort:
        if anfrage.pfad == "/kaputt/digest":
            return Antwort(500)
        if anfrage.pfad == "/leer/digest":
            return Antwort(200, b"\x00")
        return Antwort(200, OTS_ANTWORT)

    with belegserver(antworte) as server:
        kalender = tuple(server.adresse(p) for p in ("/a", "/kaputt", "/leer/"))
        stempel = stemple_ots(DIGEST, kalender=kalender, frist=FRIST)

    assert [s.verfahren for s in stempel] == [OPENTIMESTAMPS] * 3
    assert [s.zustand for s in stempel] == [GESTEMPELT, AUSGEFALLEN, AUSGEFALLEN]
    assert [s.grund for s in stempel] == [
        None,
        "HTTP 500",
        "Antwort unlesbar: keine ausstehende Bestätigung",
    ]
    assert stempel[0].dienst == kalender[0]
    anfragen = server.anfragen
    assert [a.pfad for a in anfragen] == ["/a/digest", "/kaputt/digest", "/leer/digest"]
    assert all(a.koerper == bytes.fromhex(DIGEST) for a in anfragen)
    assert anfragen[0].kopf["Accept"] == "application/vnd.opentimestamps.v1"


def test_opentimestamps_timeout_und_falscher_digest_sind_benannt():
    with belegserver(lambda anfrage: Antwort(200, OTS_ANTWORT, verzug=2.0)) as server:
        langsam = stemple_ots(DIGEST, kalender=(server.adresse(),), frist=FRIST)
        falsch = stemple_ots("xyz", kalender=(server.adresse(),), frist=FRIST)

    assert langsam[0].grund == f"keine Antwort in {FRIST:g} s"
    assert falsch[0].grund == "Digest ist kein SHA-256 in Hex"
    assert len(server.anfragen) == 1


def test_stemple_wirft_nie_und_nennt_jeden_dienst():
    with belegserver(lambda anfrage: Antwort(500)) as server:
        stempel = stemple(
            DIGEST,
            tsa=server.adresse("/tsr"),
            kalender=(server.adresse("/a"), server.adresse("/b")),
            frist=FRIST,
        )

    assert [s.verfahren for s in stempel] == [RFC3161, OPENTIMESTAMPS, OPENTIMESTAMPS]
    assert {s.zustand for s in stempel} == {AUSGEFALLEN}
    assert all(s.grund == "HTTP 500" for s in stempel)
