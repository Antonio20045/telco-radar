"""P2/D4a - die Erklärtext-Inventur der Geräteseite.

Tor der Phase: "Kein Satz auf der Geräteseite, der erklärt, wie man sie
liest." Diese Datei hält zwei Zusicherungen gegeneinander, damit die eine
die andere nicht trivial macht:

  * NEGATIVLISTE: die gemessenen Lesehilfe-Sätze (wie gerechnet/gruppiert
    wird) stehen NICHT MEHR als sichtbarer Fließtext auf geraete.html.
    Gegen den Stand vor D4a ist dieser Teil ROT - die Sätze standen dort
    wörtlich als <p class="gr-erklaer">/<p class="gr-achsenlabel"> etc.
  * POSITIVLISTE (Gegenprobe): echte DATEN-Aussagen - Zahlen, Quellen,
    benannte Lücken - bleiben stehen. Ohne diese Gegenprobe wäre die
    Negativliste erfüllt, auch wenn irrtümlich Daten mitgelöscht worden
    wären (CLAUDE.md Clean Code 3, Regel 9).

Die entfernte Methodik landet nicht im Nichts: geraete-quellen.html trägt
seit D4a eine Methodik-Sektion (`#methodik`), die dieselben Sätze sinngleich
wiederholt, und der EINE Fußzeilen-Link "Methodik" auf geraete.html führt
dorthin.
"""
from __future__ import annotations

import pathlib
from unittest import mock

from bs4 import BeautifulSoup

from telco_radar.report import geraete_radar
from test_geraete_radar_tafel import _seite


def _gebaut(tmp_path: pathlib.Path) -> tuple[BeautifulSoup, BeautifulSoup]:
    """geraete.html UND geraete-quellen.html derselben Site."""
    seiten = _seite(tmp_path)
    geraete = BeautifulSoup(seiten["geraete.html"], "html.parser")
    quellen_pfad = tmp_path / "site-bau" / "site" / "geraete-quellen.html"
    quellen = BeautifulSoup(quellen_pfad.read_text(encoding="utf-8"),
                             "html.parser")
    return geraete, quellen


def _sichtbarer_text(suppe: BeautifulSoup) -> str:
    """Wie ein Leser die Seite sieht: ohne title-Attribute, ohne Markup -
    `get_text()` liest nur, was zwischen Tags steht, nie ein Attribut."""
    return " ".join(suppe.get_text(" ", strip=True).split())


# ---------------------------------------------------------------------------
# Die entfernten Lesehilfen (Negativliste)
# ---------------------------------------------------------------------------

_ENTFERNTE_LESEHILFEN = [
    "Ein fehlender Punkt heißt",
    "Unbegrenzte Tarife und Tarife ohne erhobenes Datenvolumen",
    "Balkenlänge = Abstand in Euro zum Vodafone-Preis",
    "Diese Geräte führen nur",
    "jede Zeile ein Modell, gerechnet gegen Vodafone im selben Tarifband",
    "Abweichung je Zeile = Wettbewerber-Kosten",
    "Fachhändler verkaufen ohne eigenen Tarif",
    "Gezählt werden Jahrgänge, nicht Varianten",
    "Bleibt ein Vorjahresmodell nach dem Start seines",
    "Verglichen werden ausschließlich Neugeräte ohne Tarifvertrag",
    "Eine Zeile je Modell; der Umschalter darüber wählt",
]


def test_keine_lesehilfe_steht_noch_sichtbar_auf_der_geraeteseite(tmp_path):
    """NEGATIVLISTE. Gegen den Stand vor D4a ist dieser Test ROT: jeder
    dieser elf Sätze stand wörtlich als sichtbarer Absatz auf geraete.html
    (siehe git-Historie dieser Datei / des Auftrags D4a)."""
    geraete, _ = _gebaut(tmp_path)
    sichtbar = _sichtbarer_text(geraete)
    treffer = [satz for satz in _ENTFERNTE_LESEHILFEN if satz in sichtbar]
    assert not treffer, (
        "Lesehilfe(n) stehen noch sichtbar auf der Geräteseite: "
        f"{treffer}")


def test_die_entfernten_lesehilfen_stehen_nicht_im_nichts(tmp_path):
    """Gegenprobe zur Negativliste: nichts ist gelöscht, nur umgezogen.

    S2-Fix (Review D4a): `title`-Attribute sind auf dem Handy nicht
    erreichbar (kein Antippen-Tooltip auf iOS/Android). Der Nachweis ist
    deshalb ausschließlich die Methodik-Sektion (`#methodik` auf
    geraete-quellen.html), NICHT das `title`-Attribut - `title` bleibt
    nur die Desktop-Abkürzung. Jeder der umgezogenen Sätze (Kern der
    Aussage, aus derselben `_ENTFERNTE_LESEHILFEN`-Liste oben) muss
    SICHTBAR in der Methodik-Sektion stehen, und der EINE Fußzeilen-Link
    "Methodik" auf geraete.html muss genau auf diesen Anker zeigen."""
    geraete, quellen = _gebaut(tmp_path)
    methodik = quellen.select_one("section#methodik")
    assert methodik is not None, "die Methodik-Sektion fehlt"
    methodik_text = _sichtbarer_text(methodik)

    # Der Fußzeilen-Link zeigt auf GENAU diesen Anker (nicht nur auf die
    # Seite) - sonst landet ein Handy-Leser auf der Quellenübersicht,
    # nie bei der Methodik selbst.
    methodik_links = [a for a in geraete.select("a")
                      if a.get_text(strip=True) == "Methodik"]
    assert methodik_links, "kein Fußzeilen-Link 'Methodik' auf geraete.html"
    assert methodik_links[0]["href"].endswith("geraete-quellen.html#methodik")

    # Kernfragment je umgezogenem Satz -> muss WÖRTLICH oder sinngleich in
    # der Methodik-Sektion stehen. Wo der Kern nicht wortgleich uebernommen
    # wurde (Ab-Preis, Nachfolger-Spalte), steht das Fragment, das die
    # gleiche Auskunft in der Methodik-Formulierung traegt.
    fragmente = {
        "Ein fehlender Punkt heißt":
            "Ein fehlender Punkt heißt",
        "Unbegrenzte Tarife und Tarife ohne erhobenes Datenvolumen":
            "Unbegrenzte Tarife und Tarife ohne erhobenes Datenvolumen",
        "Balkenlänge = Abstand in Euro zum Vodafone-Preis":
            "Balkenlänge = Abstand in Euro zum Vodafone-Preis",
        "Diese Geräte führen nur":
            "nennt den günstigsten Anbieter, der das Gerät führt",
        "jede Zeile ein Modell, gerechnet gegen Vodafone im selben Tarifband":
            "jede Zeile ein Modell, gerechnet gegen Vodafone im selben Tarifband",
        "Abweichung je Zeile = Wettbewerber-Kosten":
            "Abweichung je Zeile = Wettbewerber-Kosten",
        "Fachhändler verkaufen ohne eigenen Tarif":
            "Fachhändler verkaufen ohne eigenen Tarif",
        "Gezählt werden Jahrgänge, nicht Varianten":
            "Gezählt werden Jahrgänge, nicht Varianten",
        "Bleibt ein Vorjahresmodell nach dem Start seines":
            "Zählt die Tage seit dem Marktstart des Nachfolgers",
        "Verglichen werden ausschließlich Neugeräte ohne Tarifvertrag":
            "Verglichen werden ausschließlich Neugeräte ohne Tarifvertrag",
        "Eine Zeile je Modell; der Umschalter darüber wählt":
            "Eine Zeile je Modell; der Umschalter darüber wählt",
    }
    assert set(fragmente) == set(_ENTFERNTE_LESEHILFEN), (
        "die Fragmente-Liste deckt nicht mehr dieselben Sätze wie die "
        "Negativliste oben ab")
    fehlend = [satz for satz, fragment in fragmente.items()
              if fragment not in methodik_text]
    assert not fehlend, (
        "Lesehilfe(n) stehen NICHT (mehr nur als title) in der "
        f"Methodik-Sektion - die Auskunft ist auf dem Handy verloren: "
        f"{fehlend}")


def test_geraeteseite_verlinkt_genau_einmal_auf_die_methodik(tmp_path):
    """Die Geräteseite bekommt höchstens EINEN Fußzeilen-Link 'Methodik'
    (Auftrag D4a) - kein Wissen geht verloren, es zieht nur um."""
    geraete, _ = _gebaut(tmp_path)
    links = [a for a in geraete.select("a")
             if a.get_text(strip=True) == "Methodik"]
    assert len(links) == 1, f"{len(links)} Methodik-Links statt genau einem"
    assert links[0]["href"].endswith("geraete-quellen.html#methodik"), \
        links[0]["href"]


# ---------------------------------------------------------------------------
# Die Daten-Aussagen, die bleiben MÜSSEN (Positivliste, Gegenprobe)
# ---------------------------------------------------------------------------

def test_daten_aussagen_bleiben_sichtbar_auf_der_geraeteseite(tmp_path):
    """POSITIVLISTE. Ohne diese Gegenprobe wäre die Negativliste oben
    trivial erfüllbar (auch durch versehentliches Mitlöschen echter
    Daten). Jede geprüfte Zeile ist eine Aussage über die DATEN - eine
    Zahl, ein Anbietername, ein Preis, ein Beleglink -, keine Lesehilfe,
    und CLAUDE.md Clean Code 3/Regel 9 verlangt sie namentlich."""
    # S1-Fix (Review D4a): `wr.grafik.basis` (geraete_radar.py, len(alle)
    # aus grafik_zeilen()) ist eine echte gezählte Zahl, keine Lesehilfe -
    # sie muss sichtbar bleiben. Gegenprobe gegen den ECHTEN Aufruf
    # waehrend des Renderns (CLAUDE.md Regel 10: ein Test ohne Gegenprobe
    # gegen die Daten ist grün und prüft nichts), nicht gegen eine im Test
    # neu erfundene Zahl.
    echte_basis = []
    original_grafik_zeilen = geraete_radar.grafik_zeilen

    def _erfasst(vergleich_ohne_vertrag):
        zeilen = original_grafik_zeilen(vergleich_ohne_vertrag)
        echte_basis.append(len(zeilen))
        return zeilen

    with mock.patch.object(geraete_radar, "grafik_zeilen",
                           side_effect=_erfasst):
        geraete, _ = _gebaut(tmp_path)
    assert echte_basis, ("grafik_zeilen() wurde beim Bauen der Seite nicht "
                         "aufgerufen - der Test prüfte nichts")
    erwartete_basis = echte_basis[-1]

    grafik_meta = geraete.select_one("#wr-grafik .gr-v-meta")
    assert grafik_meta is not None, (
        "die gezählte Modellzahl (wr.grafik.basis) an der Radar-Grafik "
        "fehlt - sie ist beim Kürzen des Achslabels nirgends mehr "
        "sichtbar")
    assert str(erwartete_basis) in _sichtbarer_text(grafik_meta), (
        f"die sichtbare Zahl ({_sichtbarer_text(grafik_meta)!r}) stimmt "
        f"nicht mit dem echten len(alle) = {erwartete_basis} überein")

    sichtbar = _sichtbarer_text(geraete)

    # Die Kachel-Summe der Alarmtabelle bleibt als Datensatz stehen - nur
    # ihr methodischer Nachsatz ("Verglichen werden ausschließlich …")
    # ist gefallen (siehe Negativliste).
    assert "Modelle mit ihren Speichergrößen stehen einem Wettbewerber" \
        in sichtbar

    # Die Händler-Sektion nennt weiterhin den echten Händlernamen und die
    # echten Preise/Prozente der Fixture (Saturn, iPhone 15) - keine
    # Lesehilfe, sondern der Bestand selbst.
    haendler = geraete.select_one("#wr-haendler")
    assert haendler is not None, "die Händler-Sektion fehlt"
    haendler_text = _sichtbarer_text(haendler)
    assert "Saturn" in haendler_text
    assert "%" in haendler_text

    # Der Leer-Satz der Alarmtabelle ist eine Daten-Aussage (keine Zeile
    # der aktuellen Auswahl) und bleibt im DOM, auch wenn `hidden`.
    leer = geraete.select_one("#wr-alarme .gr-a-leer")
    assert leer is not None
    assert "günstiger" in _sichtbarer_text(leer)

    # Belegpflicht: mindestens ein Quellenlink mit Abrufdatum steht in der
    # Modell-Liste des Radars (jede Aussage verlinkt auf ihre Quelle,
    # CLAUDE.md "Antonios Stil").
    beleg = geraete.select_one("#wr-abweichung a.gr-a-quelle")
    assert beleg is not None and beleg.get("href", "").startswith("http")


def test_methodik_sektion_traegt_die_umgezogenen_saetze(tmp_path):
    """Die Methodik-Sektion auf geraete-quellen.html ist das neue Zuhause
    der Lesehilfen - mit id (Ziel des Fußzeilen-Links) und ihrem eigenen,
    aussagekräftigen Titel."""
    _, quellen = _gebaut(tmp_path)
    methodik = quellen.select_one("section#methodik")
    assert methodik is not None
    ueberschrift = methodik.select_one("h2")
    assert ueberschrift is not None and len(ueberschrift.get_text(strip=True)) > 5
    eintraege = methodik.select("li.list-row")
    assert len(eintraege) >= 8, \
        f"nur {len(eintraege)} Methodik-Einträge - fehlt eine umgezogene Regel?"
