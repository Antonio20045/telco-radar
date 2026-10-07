"""Notbremse an der Modell-Kachel der Zeitreihe: dieselbe Definition wie der Satz.

Steht in einem Band nur eine Schätzung oder ein Satz mit abgelaufener Aktion, sagt
der Antwortsatz „steht kein Bündel im Vergleich: o2 (berechnet)“. Die Kachel darf
dort nicht „kein Bündel-Angebot in diesem Band“ behaupten, sondern nennt den
benannten Zustand (harte Regel 6, Clean Code 4 und 7). Gerendert aus dem Bestand
vom 2026-10-03; der Bezugstag kommt aus dem Bestand, nie vom heutigen Datum.
"""

from __future__ import annotations

import pytest
from bestand_pfad import abbild
from bs4 import BeautifulSoup

from telco_radar.config import load_config
from telco_radar.report.html import render_site

GESPERRT = "steht kein Bündel im Vergleich"


@pytest.fixture(scope="module")
def seite(tmp_path_factory):
    wurzel = tmp_path_factory.mktemp("notbremse-kachel")
    render_site(wurzel / "site", abbild(wurzel), load_config(wurzel))
    html = (wurzel / "site" / "geraete.html").read_text(encoding="utf-8")
    fragment = (wurzel / "site" / "data" / "geraete-zeitreihe.html").read_text(
        encoding="utf-8"
    )
    return BeautifulSoup(html, "html.parser"), BeautifulSoup(fragment, "html.parser")


def _antworten(fragment) -> dict[tuple, str]:
    """Je (Modell, Band, Ratenlaufzeit) der Antwortsatz - seit Datenkonzept
    Geräte Schritt 2 ist jede Laufzeit ein eigenes Paar."""
    return {
        (b["data-modell"], b["data-band"], b["data-laufzeit"]): b.select_one(
            ".gr-zr-antwort"
        ).get_text(" ", strip=True)
        for b in fragment.select(".gr-zr-lager")
    }


def _kachel_baender(html) -> dict[tuple, BeautifulSoup]:
    fertig = {}
    for knopf in html.select("#gr-zr-kacheln button[data-modell]"):
        for span in knopf.select("span.gr-zr-k-band[data-band]"):
            if (
                span["data-band"] == "__ohne"
                or span.select_one(".gr-zr-k-preis") is None
            ):
                continue
            fertig[(knopf["data-modell"], span["data-band"], span["data-lz"])] = span
    return fertig


def _text_und_titel(span) -> tuple[str, str]:
    text = span.get_text(" ", strip=True)
    titel = " ".join(e.get("title", "") for e in span.select("[title]"))
    return text, titel


def test_kachel_nennt_schaetzung_statt_kein_angebot(seite):
    html, fragment = seite
    antworten = _antworten(fragment)
    kacheln = _kachel_baender(html)
    nur_gesperrt = {
        paar: satz
        for paar, satz in antworten.items()
        if GESPERRT in satz and paar in kacheln
    }
    assert nur_gesperrt, "Fall fehlt: keine Kachel mit einem Band nur aus Schätzungen"
    falsch = []
    for paar, satz in sorted(nur_gesperrt.items()):
        text, titel = _text_und_titel(kacheln[paar])
        gruende = [g for g in ("berechnet", "Aktion abgelaufen") if f"({g})" in satz]
        if "kein Bündel-Angebot" in titel or not all(g in text for g in gruende):
            falsch.append(f"{paar}: Kachel „{text}“ ({titel}) gegen Satz „{satz}“")
    assert not falsch, (
        f"Kachel und Antwortsatz widersprechen sich in {len(falsch)} Bändern: "
        f"{falsch[:2]}"
    )


def test_gegenprobe_gemessener_preis_bleibt_in_der_kachel(seite):
    html, fragment = seite
    antworten = _antworten(fragment)
    mit_preis = [
        paar
        for paar, span in _kachel_baender(html).items()
        if span.select_one(".gr-zr-k-preis b") is not None
        and (
            "am günstigsten" in antworten.get(paar, "")
            or "führt" in antworten.get(paar, "")
        )
    ]
    assert mit_preis, "Gegenprobe: Kacheln mit gemessenem ab-Preis fehlen"
