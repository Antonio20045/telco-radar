"""Zeitstempel des Manifests (Datenkonzept Geräteradar, Abschnitt 10), ohne Netz.

RFC 3161 beantwortet ein lokaler Zeitstempeldienst: ``openssl ts -reply`` mit einer
eigens erzeugten Test-CA und einem von ihr unterschriebenen TSA-Zertifikat, das hier
für die Zertifikate von freetsa.org steht; dazu ein fremder, selbst unterschriebener
Unterzeichner. Kein echter Dienst, keine echten Zertifikate. Die Calendar-Server von
OpenTimestamps sind ein lokaler Server, der eine BEISPIEL-Antwort mit ausstehender
Bestätigung liefert.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from belegserver import Anfrage, Antwort, belegserver

from telco_radar.collect.geraete.belegstempel import (
    AUSGEFALLEN,
    FREETSA,
    FREETSA_DIENST,
    GESTEMPELT,
    OHNE_TOKEN,
    OHNE_ZERTIFIKAT,
    OPENTIMESTAMPS,
    OTS_AUSSTEHEND,
    RFC3161,
    UNGEPRUEFT,
    UNGUELTIG,
    Zeitstempeldienst,
    freetsa,
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
SCHLUESSEL = "req -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes"
STEMPELZWECK = "-addext extendedKeyUsage=critical,timeStamping"


def _ssl(befehl: str, ordner: Path) -> bytes:
    """openssl mit Dateinamen relativ zu ``ordner``; kein Wert enthält Leerzeichen."""
    lauf = subprocess.run(
        ["openssl", *befehl.split()], cwd=ordner, capture_output=True, check=True
    )
    return lauf.stdout


def _tlv(tag: int, inhalt: bytes) -> bytes:
    """DER-Element mit kurzer Länge; reicht für die kleine abgelehnte Antwort."""
    return bytes([tag, len(inhalt)]) + inhalt


ABGELEHNT = _tlv(
    0x30,
    _tlv(0x30, _tlv(0x02, b"\x02") + _tlv(0x30, _tlv(0x0C, b"Status: Granted."))),
)


@pytest.fixture(scope="module")
def pki(tmp_path_factory):
    """Test-CA, ein von ihr unterschriebener Dienst und ein fremder Unterzeichner."""
    o = tmp_path_factory.mktemp("pki")
    _ssl(
        f"{SCHLUESSEL} -x509 -days 2 -keyout ca.key -out ca.pem -subj /CN=Test-CA "
        "-addext basicConstraints=critical,CA:TRUE "
        "-addext keyUsage=critical,keyCertSign,cRLSign",
        o,
    )
    _ssl(f"{SCHLUESSEL} -keyout tsa.key -out tsa.csr -subj /CN=Test-TSA", o)
    (o / "ext.cnf").write_text(
        "extendedKeyUsage=critical,timeStamping\nbasicConstraints=CA:FALSE\n", "utf-8"
    )
    _ssl(
        "x509 -req -in tsa.csr -CA ca.pem -CAkey ca.key -CAcreateserial -days 2 "
        "-extfile ext.cnf -out tsa.crt",
        o,
    )
    _ssl(
        f"{SCHLUESSEL} -x509 -days 2 -keyout fremd.key -out fremd.crt "
        f"-subj /CN=Fremd {STEMPELZWECK}",
        o,
    )
    (o / "t.cnf").write_text(
        "[ tsa ]\ndefault_tsa = t\n[ t ]\nserial = serial\n"
        "default_policy = 1.2.3.4.1\ndigests = sha256\nsigner_digest = sha256\n"
        "ess_cert_id_alg = sha256\ness_cert_id_chain = no\n",
        "utf-8",
    )
    return o


def _antworte_tsa(pki: Path, unterzeichner: str = "tsa", neu: str | None = None):
    """Dienst, der die Anfrage stempelt; ``neu`` stempelt eine neue Anfrage."""

    def antworte(anfrage: Anfrage) -> Antwort:
        (pki / "q.tsq").write_bytes(anfrage.koerper)
        if neu is not None:
            _ssl(f"ts -query -digest {neu} -sha256 -cert -out q.tsq", pki)
        _ssl(
            f"ts -reply -config t.cnf -queryfile q.tsq -signer {unterzeichner}.crt "
            f"-inkey {unterzeichner}.key -out r.tsr",
            pki,
        )
        return Antwort(200, (pki / "r.tsr").read_bytes(), "application/timestamp-reply")

    return antworte


def _dienst(adresse: str, pki: Path, mit_zertifikat: bool = True) -> Zeitstempeldienst:
    if mit_zertifikat:
        return Zeitstempeldienst(adresse, pki / "ca.pem", pki / "tsa.crt")
    return Zeitstempeldienst(adresse, pki / "fehlt-ca.pem", pki / "fehlt-tsa.crt")


def test_rfc3161_stempel_gilt_nach_pruefung_gegen_ca_und_tsa_zertifikat(pki):
    with belegserver(_antworte_tsa(pki)) as server:
        dienst = _dienst(server.adresse("/tsr"), pki)
        stempel = stemple_rfc3161(DIGEST, dienst=dienst, frist=5)

    assert stempel.zustand == GESTEMPELT, stempel.grund
    assert (stempel.verfahren, stempel.dienst) == (RFC3161, dienst.adresse)
    assert stempel.grund is None
    assert stempel.token
    anfrage = server.anfragen[0]
    assert (anfrage.methode, anfrage.pfad) == ("POST", "/tsr")
    assert anfrage.kopf["Content-Type"] == "application/timestamp-query"


def test_rfc3161_fremder_unterzeichner_ist_ungueltig(pki):
    with belegserver(_antworte_tsa(pki, unterzeichner="fremd")) as server:
        dienst = _dienst(server.adresse("/tsr"), pki)
        stempel = stemple_rfc3161(DIGEST, dienst=dienst, frist=5)

    assert stempel.zustand == UNGUELTIG
    assert stempel.grund.startswith("Unterzeichner nicht vom festgelegten Zertifikat")
    assert stempel.token is None


def test_rfc3161_ohne_zertifikat_heisst_gestempelt_ungeprueft(pki):
    with belegserver(_antworte_tsa(pki, unterzeichner="fremd")) as server:
        dienst = _dienst(server.adresse("/tsr"), pki, mit_zertifikat=False)
        stempel = stemple_rfc3161(DIGEST, dienst=dienst, frist=5)

    assert stempel.zustand == UNGEPRUEFT
    assert stempel.zustand != GESTEMPELT
    assert stempel.grund.startswith(f"{OHNE_ZERTIFIKAT}: Zertifikat fehlt")
    assert str(dienst.ca) in stempel.grund and str(dienst.zertifikat) in stempel.grund
    assert stempel.token


@pytest.mark.parametrize("mit_zertifikat", [True, False])
def test_rfc3161_abgelehnte_antwort_mit_falschem_freitext_ist_ungueltig(
    pki, mit_zertifikat
):
    with belegserver(lambda anfrage: Antwort(200, ABGELEHNT)) as server:
        dienst = _dienst(server.adresse("/tsr"), pki, mit_zertifikat)
        stempel = stemple_rfc3161(DIGEST, dienst=dienst, frist=5)

    assert stempel.zustand == UNGUELTIG
    assert stempel.token is None
    if mit_zertifikat:
        assert stempel.grund.startswith("Antwort abgelehnt (no time stamp token")
    else:
        assert stempel.grund == OHNE_TOKEN


@pytest.mark.parametrize("mit_zertifikat", [True, False])
@pytest.mark.parametrize(
    ("neu", "grund"),
    [
        (ANDERER, "Antwort stempelt einen anderen Digest"),
        (DIGEST, "Antwort gehört zu einer anderen Anfrage"),
    ],
    ids=["anderer_digest", "andere_nonce"],
)
def test_rfc3161_antwort_auf_eine_andere_anfrage_ist_ungueltig(
    pki, mit_zertifikat, neu, grund
):
    with belegserver(_antworte_tsa(pki, neu=neu)) as server:
        dienst = _dienst(server.adresse("/tsr"), pki, mit_zertifikat)
        stempel = stemple_rfc3161(DIGEST, dienst=dienst, frist=5)

    assert stempel.zustand == UNGUELTIG
    assert stempel.grund.startswith(grund)
    assert stempel.token is None


@pytest.mark.parametrize(
    ("mit_zertifikat", "grund"),
    [(True, "Antwort unlesbar"), (False, OHNE_TOKEN)],
)
def test_rfc3161_unlesbare_antwort_ist_ungueltig(pki, mit_zertifikat, grund):
    with belegserver(lambda anfrage: Antwort(200, b"kein Stempel")) as server:
        dienst = _dienst(server.adresse("/tsr"), pki, mit_zertifikat)
        stempel = stemple_rfc3161(DIGEST, dienst=dienst, frist=5)

    assert stempel.zustand == UNGUELTIG
    assert stempel.grund.startswith(grund)
    assert stempel.token is None


def test_freetsa_zertifikate_liegen_unter_config_zeitstempel(tmp_path):
    dienst = freetsa(tmp_path)

    assert dienst.adresse == FREETSA == FREETSA_DIENST.adresse
    assert dienst.ca == tmp_path / "config" / "zeitstempel" / "freetsa-cacert.pem"
    assert dienst.zertifikat == tmp_path / "config" / "zeitstempel" / "freetsa-tsa.crt"
    assert FREETSA_DIENST.ca == Path("config/zeitstempel/freetsa-cacert.pem")


@pytest.mark.parametrize(
    ("antwort", "grund"),
    [
        (Antwort(500), "HTTP 500"),
        (Antwort(503), "HTTP 503"),
        (Antwort(200, verzug=2.0), f"keine Antwort in {FRIST:g} s"),
    ],
)
def test_rfc3161_ausfall_ist_ein_benannter_zustand(pki, antwort, grund):
    with belegserver(lambda anfrage: antwort) as server:
        dienst = _dienst(server.adresse("/tsr"), pki)
        stempel = stemple_rfc3161(DIGEST, dienst=dienst, frist=FRIST)

    assert stempel.zustand == AUSGEFALLEN
    assert stempel.grund.startswith(grund)
    assert stempel.token is None


def test_ohne_openssl_ist_rfc3161_ein_benannter_ausfall(pki):
    with belegserver(lambda anfrage: Antwort(200)) as server:
        stempel = stemple_rfc3161(
            DIGEST,
            dienst=_dienst(server.adresse(), pki),
            openssl="/gibt/es/nicht/openssl",
            frist=FRIST,
        )

    assert stempel.zustand == AUSGEFALLEN
    assert stempel.grund == "openssl fehlt (/gibt/es/nicht/openssl)"
    assert server.anfragen == []


def test_nicht_erreichbarer_dienst_ist_ein_benannter_ausfall(pki):
    with belegserver(lambda anfrage: Antwort(200)) as server:
        adresse = server.adresse("/tsr")

    stempel = stemple_rfc3161(DIGEST, dienst=_dienst(adresse, pki), frist=FRIST)

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


def test_stemple_wirft_nie_und_nennt_jeden_dienst(pki):
    with belegserver(lambda anfrage: Antwort(500)) as server:
        stempel = stemple(
            DIGEST,
            dienst=_dienst(server.adresse("/tsr"), pki),
            kalender=(server.adresse("/a"), server.adresse("/b")),
            frist=FRIST,
        )

    assert [s.verfahren for s in stempel] == [RFC3161, OPENTIMESTAMPS, OPENTIMESTAMPS]
    assert {s.zustand for s in stempel} == {AUSGEFALLEN}
    assert all(s.grund == "HTTP 500" for s in stempel)
