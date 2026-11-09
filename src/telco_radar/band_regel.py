"""Die eine Regel: welches Datenvolumen ist einem Zielwert am naechsten.

Report (`report/geraete_tco_band.band_von_gb`, Vodafone-Tarifleiter) und
Sammeln (`collect/geraete/tarifwelt.waehle_je_band`, Tarifwelt-Netzauswahl)
brauchen dieselbe Regel - "naechstes Volumen, bei Gleichstand das groessere"
- duerfen sich aber nicht gegenseitig importieren (`.importlinter`:
Schichten-Vertrag, Sammeln zitiert nie Berichten). Dieses Wurzelmodul ist
der gemeinsame Ort, denselben Baustein, nicht zwei gleiche.
"""

from __future__ import annotations

from pathlib import Path

import yaml

OBERSTE_STUFE = "xl"
"""Schluessel der obersten Stufe der Tarifleiter. Ein Tarif mit unbegrenztem
Datenvolumen gehoert dorthin - unabhaengig vom Anbieter und davon, welches
Volumen die Vodafone-Stufe selbst gerade traegt."""

PFAD_PREIS_WIDERSPRUCH = (
    Path(__file__).resolve().parents[2] / "config" / "tarif_preis_widerspruch.yaml"
)
""""Preis am Original widerspruechlich": Tarife dieser Liste bleiben ohne Stufe."""


def abstand_schluessel(gb: float, ziel_gb: float) -> tuple[float, float]:
    """Sortierschluessel fuer `min()`/`sorted()`: je kleiner, je naeher -
    bei gleichem Abstand gewinnt das groessere Volumen."""
    return (abs(gb - ziel_gb), -gb)


def stufe_fuer(gb: float | None, stufen) -> str | None:
    """Der Schluessel der Stufe, in die ein Datenvolumen faellt - oder `None`.

    `stufen` ist eine Folge `(key, gb)` (die Vodafone-Tarifleiter). `inf`
    (unbegrenzt) faellt in die oberste Stufe `OBERSTE_STUFE`, sofern die Leiter
    sie fuehrt (sonst `None`: nie in die groesste endliche rutschen); jedes
    endliche Volumen in die naechste endliche Stufe (`abstand_schluessel`,
    Gleichstand: die groessere). Fehlendes Volumen oder keine passende
    Stufe heisst `None`: nicht zuordenbar, nie eine geratene Stufe."""
    if gb is None or gb != gb:
        return None
    if gb == float("inf"):
        return next((k for k, _ in stufen if k == OBERSTE_STUFE), None)
    endlich = [(k, g) for k, g in stufen if g is not None and g != float("inf")]
    if not endlich:
        return None
    return min(endlich, key=lambda s: abstand_schluessel(s[1], gb))[0]


class Tarifbaender(dict):
    """`{tarif_id: Stufe}` wie `tarif_baender`, dazu `ohne_stufe`: die Bündel-IDs,
    die trotz der Stufe ihres Tarifs keine tragen (siehe `unbegrenzt_ohne_beleg`)."""

    def __init__(self, baender=(), ohne_stufe=()):
        super().__init__(baender)
        self.ohne_stufe = frozenset(ohne_stufe)


def band_fuer(baender, tarif_id: str | None, buendel_id: str | None = "") -> str | None:
    """Die Stufe einer Bündelzeile: die ihres Tarifs, außer die Zeile steht auf
    `ohne_stufe`. EINE Lesart für Karten, Export, Radar und Zeitreihe."""
    if buendel_id and buendel_id in getattr(baender, "ohne_stufe", ()):
        return None
    return baender.get(tarif_id or "")


def band_der_karte(baender, karte: dict) -> str | None:
    """Die Stufe einer Karte oder Zeile: ``band_fuer`` mit deren Tarif und Bündel."""
    return band_fuer(baender, karte.get("tarif_id"), karte.get("buendel_id"))


def unbegrenzt_ohne_beleg(gb: float | None, belegt: bool) -> bool:
    """Eine Zeile eines unbegrenzten Tarifs bekommt die oberste Stufe nur mit Beleg:
    Preis und Ablöse am Gerät gemessen (nicht aus einem Raster abgeleitet) und die
    jüngste Messung ohne widersprüchliche zweite Angabe. Lieber ein Preis weniger."""
    return gb is not None and gb == float("inf") and not belegt


def preis_widerspruch(pfad: Path | None = None) -> dict[str, dict]:
    """Die Tarife, die vorerst ohne Stufe bleiben, weil ihr Preis am Original
    widerspruechlich ist: `{tarif_id: Eintrag}` aus
    `config/tarif_preis_widerspruch.yaml` (Name, Grund, Beleg). Die Liste
    wirkt nur im Bericht (`tarif_baender`); das Sammeln arbeitet mit den
    IDs der Tarifwelt und liest sie nicht.

    Eine fehlende oder kaputte Datei ist ein Fehler, nie eine leere Liste:
    sonst bekaemen die Tarife still wieder eine Stufe (fail-closed)."""
    roh = yaml.safe_load(Path(pfad or PFAD_PREIS_WIDERSPRUCH).read_text("utf-8"))
    eintraege = (roh or {}).get("tarife")
    if not isinstance(eintraege, list):
        raise ValueError("tarif_preis_widerspruch.yaml: Liste `tarife` fehlt")
    out: dict[str, dict] = {}
    for e in eintraege:
        if not isinstance(e, dict) or not e.get("tarif_id"):
            raise ValueError(
                f"tarif_preis_widerspruch.yaml: Eintrag ohne tarif_id: {e!r}"
            )
        fehlt = [f for f in ("name", "grund", "beleg") if not e.get(f)]
        if fehlt:
            raise ValueError(
                f"{e['tarif_id']}: Feld(er) {fehlt} fehlen (Beleg ist Pflicht)"
            )
        out[str(e["tarif_id"])] = e
    return out


def ohne_preis_widerspruch(tarife: dict | None) -> dict:
    """Der Tarifbestand ohne die Tarife der Liste `preis_widerspruch()` -
    ihre Plus-Fassung (`-plus`) und eine Variante nach `#` (`#live_shop`)
    zaehlen als derselbe Tarif."""
    liste = preis_widerspruch()

    def gelistet(tid: str) -> bool:
        tid = tid.split("#", 1)[0]
        return tid in liste or tid.removesuffix("-plus") in liste

    return {t: s for t, s in (tarife or {}).items() if not gelistet(t)}
