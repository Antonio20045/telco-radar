"""Ein schlankes Stylesheet für alle Seiten außer der Geräteseite.

Rund ein Drittel von style.css (über 100 KB) gilt nur Elementen mit den
Klassen `gr-`, `gx-` und `wr-` der Geräteseite. Jede andere Seite lud und
las diese Regeln vor dem ersten Bild mit (Seite schneller, 11.10.2026).

Nach dem Rendern behält die Geräteseite das vollständige ``style.css``;
jede andere Seite verweist auf ``seiten.css``, dem jede Regel fehlt, die
eine solche Klasse verlangt, die auf keiner dieser Seiten vorkommt. Eine Regel, die
auf einer Seite nichts trifft, ändert dort nichts, und die Reihenfolge des
Blatts bleibt erhalten. Gepflegt wird weiter nur eine Datei. Liegt
außerhalb von ``report/``, weil die Seiten dort keine Dateien öffnen.
"""

from __future__ import annotations

import re
from pathlib import Path

VOLL = "style.css"
SCHLANK = "seiten.css"
VOLLE_SEITEN = ("geraete.html",)

_KLASSE = re.compile(r"\.((?:gr|gx|wr)-[\w-]+)")
_IM_HTML = re.compile(r"""class=["']([^"']*)["']""")
_NICHT = re.compile(r":not\([^()]*\)")
_KOMMENTAR = re.compile(r"/\*.*?\*/", re.S)
_VERWEIS = re.compile(r'(<link rel="stylesheet" href="[^"]*?)style\.css"')


def bloecke(css: str) -> list[str]:
    """Zerlegt CSS in Blöcke oberster Ebene; Kommentare und Strings bleiben ganz."""
    teile: list[str] = []
    start = tiefe = i = 0
    while i < len(css):
        if css.startswith("/*", i):
            ende = css.find("*/", i + 2)
            i = len(css) if ende < 0 else ende + 2
            continue
        zeichen = css[i]
        if zeichen in "\"'":
            ende = css.find(zeichen, i + 1)
            i = len(css) if ende < 0 else ende + 1
            continue
        if zeichen == "{":
            tiefe += 1
        elif zeichen == "}" and tiefe > 0:
            tiefe -= 1
            if tiefe == 0:
                teile.append(css[start : i + 1])
                start = i + 1
        elif zeichen == ";" and tiefe == 0:
            teile.append(css[start : i + 1])
            start = i + 1
        i += 1
    if css[start:].strip():
        teile.append(css[start:])
    return teile


def _klammer(block: str) -> int:
    """Stelle der ersten ``{`` außerhalb von Kommentaren, sonst -1."""
    return _KOMMENTAR.sub(lambda m: " " * len(m.group()), block).find("{")


def _kopf(block: str) -> str:
    stelle = _klammer(block)
    return "" if stelle < 0 else _KOMMENTAR.sub("", block[:stelle]).strip()


def _trifft_nie(regel: str, genutzt: set[str]) -> bool:
    kopf = _kopf(regel)
    if not kopf or kopf.startswith("@") or "}" in kopf:
        return False
    return all(
        set(_KLASSE.findall(_NICHT.sub("", teil))) - genutzt for teil in kopf.split(",")
    )


def ohne_unbenutzte(css: str, genutzt: set[str]) -> str:
    """Das Blatt ohne Regeln, deren Geräteklassen in ``genutzt`` fehlen."""
    behalten: list[str] = []
    for block in bloecke(css):
        if _kopf(block).startswith("@media") and block.rstrip().endswith("}"):
            stelle = _klammer(block)
            ende = block.rstrip().rindex("}")
            rest = [
                r
                for r in bloecke(block[stelle + 1 : ende])
                if not _trifft_nie(r, genutzt)
            ]
            if any(r.strip() for r in rest):
                behalten.append(block[: stelle + 1] + "".join(rest) + block[ende:])
            continue
        if not _trifft_nie(block, genutzt):
            behalten.append(block)
    return "".join(behalten)


def genutzte_klassen(html: str) -> set[str]:
    """Alle Geräteklassen, die ein Dokument im class-Attribut trägt."""
    klassen: set[str] = set()
    for wert in _IM_HTML.findall(html):
        klassen.update(k for k in wert.split() if k[:3] in ("gr-", "gx-", "wr-"))
    return klassen


def teile_blaetter(site_dir: Path) -> None:
    """Schreibt ``seiten.css`` und stellt jede Seite außer der Geräteseite darauf um."""
    voll = (site_dir / VOLL).read_text(encoding="utf-8")
    genutzt: set[str] = set()
    umstellen: dict[Path, str] = {}
    for seite in sorted(site_dir.rglob("*.html")):
        teil = seite.relative_to(site_dir).parts
        if teil[0] == "data" or (len(teil) == 1 and teil[0] in VOLLE_SEITEN):
            continue
        text = seite.read_text(encoding="utf-8")
        genutzt |= genutzte_klassen(text)
        umstellen[seite] = _VERWEIS.sub(rf'\g<1>{SCHLANK}"', text, count=1)
    (site_dir / SCHLANK).write_text(ohne_unbenutzte(voll, genutzt), encoding="utf-8")
    for seite, text in umstellen.items():
        seite.write_text(text, encoding="utf-8")
