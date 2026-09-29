"""P2/D4a - die Erklärtext-Inventur der Geräteseite.

Tor der Phase: "Kein Satz auf der Geräteseite, der erklärt, wie man sie
liest." Diese Datei hält zwei Zusicherungen gegeneinander, damit die eine
die andere nicht trivial macht:

  * NEGATIVLISTE: die gemessenen Lesehilfe-Sätze (wie gerechnet/gruppiert
    wird) stehen NICHT MEHR als sichtbarer Fließtext auf geraete.html.
    Gegen den Stand vor D4a ist dieser Teil ROT - die Sätze standen dort
    wörtlich als <p class="gr-erklaer">/<p class="gr-achsenlabel"> etc.
  * GEGENPROBE: echte DATEN-Aussagen bleiben stehen - seit dem
    Neuentwurf (29.09.2026) die Zeilen der Kosten-Rangliste mit Betrag.
    Ohne diese Gegenprobe wäre die Negativliste auch an einer leeren Seite
    erfüllt (CLAUDE.md Clean Code 3, Regel 9).

Die entfernte Methodik landet nicht im Nichts: geraete-quellen.html trägt
seit D4a eine Methodik-Sektion (`#methodik`), die dieselben Sätze sinngleich
wiederholt, und der Link "Quellen" im Fuß von geraete.html führt dorthin.
"""
from __future__ import annotations

import pathlib

from bs4 import BeautifulSoup

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
    # Gegenprobe: die Seite ist nicht leer - die Rangliste steht mit
    # Beträgen da, sonst wäre die Negativliste trivial erfüllt.
    zeilen = geraete.select("#kosten .kv-zeile .kv-summe")
    assert zeilen, "keine Zeile der Kosten-Rangliste - Test prüft nichts"
    assert all("€" in _sichtbarer_text(z) for z in zeilen)


def test_die_entfernten_lesehilfen_stehen_nicht_im_nichts(tmp_path):
    """Gegenprobe zur Negativliste: nichts ist gelöscht, nur umgezogen.

    S2-Fix (Review D4a): `title`-Attribute sind auf dem Handy nicht
    erreichbar (kein Antippen-Tooltip auf iOS/Android). Der Nachweis ist
    deshalb ausschließlich die Methodik-Sektion (`#methodik` auf
    geraete-quellen.html), NICHT das `title`-Attribut - `title` bleibt
    nur die Desktop-Abkürzung. Jeder der umgezogenen Sätze (Kern der
    Aussage, aus derselben `_ENTFERNTE_LESEHILFEN`-Liste oben) muss
    SICHTBAR in der Methodik-Sektion stehen, und geraete.html muss die
    Seite mit der Methodik verlinken."""
    geraete, quellen = _gebaut(tmp_path)
    methodik = quellen.select_one("section#methodik")
    assert methodik is not None, "die Methodik-Sektion fehlt"
    methodik_text = _sichtbarer_text(methodik)

    # Seit dem Neuentwurf (29.09.2026) führt der EINE Link "Quellen" im
    # Fuß der Geräteseite auf die Seite, die die Methodik trägt.
    quellen_links = [a for a in geraete.select("#kosten .kv-fuss a")
                     if a.get("href") == "geraete-quellen.html"]
    assert len(quellen_links) == 1, (
        f"{len(quellen_links)} Quellen-Links im Fuß von geraete.html")

    # Kernfragment je umgezogenem Satz -> muss WÖRTLICH oder sinngleich in
    # der Methodik-Sektion stehen. Wo der Kern nicht wortgleich uebernommen
    # wurde (Ab-Preis, Nachfolger-Spalte), steht das Fragment, das die
    # gleiche Auskunft in der Methodik-Formulierung traegt.
    fragmente = {
        "Ein fehlender Punkt heißt":
            "Ein fehlender Punkt heißt",
        # P3-E1: seit der Tarifleiter mit neuem Wortlaut.
        "Unbegrenzte Tarife und Tarife ohne erhobenes Datenvolumen":
            "Tarife ohne erhobenes Datenvolumen und unbegrenzte Tarife",
        "Balkenlänge = Abstand in Euro zum Vodafone-Preis":
            "Balkenlänge = Abstand in Euro zum Vodafone-Preis",
        "Diese Geräte führen nur":
            "nennt den günstigsten Anbieter, der das Gerät führt",
        "jede Zeile ein Modell, gerechnet gegen Vodafone im selben Tarifband":
            "jede Zeile ein Modell, gerechnet gegen Vodafone in derselben "
            "Stufe der Tarifleiter",
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


# ---------------------------------------------------------------------------
# Die Daten-Aussagen, die bleiben MÜSSEN (Positivliste, Gegenprobe)
# ---------------------------------------------------------------------------


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
