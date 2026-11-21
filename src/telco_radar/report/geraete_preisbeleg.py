"""Beleg je Preis: Quelle, gelesen am, Rechenweg, Screenshot und Gegenprobe.

Ein Beleg ist ein Wörterbuch für die Vorlage ``_geraete_preisbeleg.html.j2``; er
rechnet nichts. Der Rechenweg sind die Summanden, die ``tco_kosten.kosten_ueber``
gerechnet hat (``Kosten.rechnung``, ungebündelt: Tarif und Gerät je für sich), mit
ihrem Wort aus ``geraete_rechnung``; ihre Summe ist die Kernzahl der Zeile.

Der Screenshot einer Zeile kommt nur aus der Zuordnung ``geraete_zeilenbelege`` (fail
closed, nie das Bild eines anderen Tarifs) oder aus der Gegenprobe desselben Preises.
Die Gegenprobe gehört zu einem Preis, wenn ihre gespeicherten Gesamtkosten die der
Zeile sind (``gesamt_gespeichert``); eine ältere Gegenprobe eines anderen Preises steht
nicht an der Zeile (``gegenprobe_fenster.Gegenproben``, dieselbe Stelle, an der die
Gegenprobe ihr Fenster rechnet). Fehlt etwas, nennt der Beleg es (``SATZ_*``), nie leer.

Gelesen wird nur ``data/state/gegenprobe/<datum>.jsonl`` (``telco_radar.gegenprobe``);
eine unlesbare Datei ist der Ausfall „Gegenprobe“ (Regel 6).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .. import gegenprobe as gp
from ..gegenprobe_fenster import SPEICHER_MUSTER, Gegenproben
from ..gegenprobe_fenster import angebot as angebot
from .ausfall import Ausfall
from .geraete_tco_grafik import euro

TEIL = "Gegenprobe"
GLOBAL = "preisbelege"
ZEITZONE = ZoneInfo("Europe/Berlin")
SATZ_OHNE_GEGENPROBE = "Noch nicht gegengeprüft"
SATZ_OHNE_BILD = "Kein Screenshot zu diesem Preis"
SATZ_OHNE_RECHENWEG = "Kein vollständiger Rechenweg"
SATZ_ZEIT_ABSTAND = "Preis kann sich zwischen Messung und Gegenprobe geändert haben"
SATZ_ZEIT_UNBEKANNT = (
    "Zeit der Messung nicht gespeichert; der Preis kann sich seither geändert haben"
)
STATUS_WORT = {
    gp.BESTAETIGT: "bestätigt",
    gp.TEILWEISE: "teilweise bestätigt",
    gp.ABWEICHEND: "abweichend",
    gp.ERFASSUNGSLUECKE: "Erfassungslücke",
    gp.NICHT_PRUEFBAR: "nicht prüfbar",
    gp.NICHT_GEGENGEPRUEFT: "nicht gegengeprüft",
}


def datum_de(iso: str | None) -> str:
    """„20.11.2026“ aus „2026-11-20“; leer bleibt leer."""
    if not iso:
        return ""
    jahr, monat, tag = iso[:10].split("-")
    return f"{tag}.{monat}.{jahr}"


def uhrzeit(iso: str | None) -> str:
    """„17:34 Uhr“ (Berlin) aus einem ISO-Zeitpunkt mit Zone; sonst leer."""
    if not iso:
        return ""
    try:
        zeit = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if zeit.tzinfo is None:
        return ""
    return f"{zeit.astimezone(ZEITZONE):%H:%M} Uhr"


def term(schritt: dict) -> str:
    """„24 × 32,70 € Tarif“ bzw. „1,00 € Anzahlung“."""
    anzahl = schritt.get("anzahl")
    vorne = f"{anzahl} × " if anzahl else ""
    return f"{vorne}{euro(schritt['betrag'])} {schritt['wort']}"


def summe(schritte: Iterable[dict]) -> float:
    """Die Summe der Terme, wie ein Leser sie nachrechnet (Anzahl × Betrag)."""
    return round(sum((s.get("anzahl") or 1) * s["betrag"] for s in schritte), 2)


def rechenweg(schritte: list[dict] | None, gesamt: float | None) -> dict | None:
    """Die Terme und ihr Ergebnis; None ohne Kernzahl oder ohne Summanden."""
    if gesamt is None or not schritte:
        return None
    terme = [term(s) for s in schritte]
    return {
        "terme": terme,
        "gesamt": gesamt,
        "text": " + ".join(terme) + f" = {euro(gesamt)}",
    }


def host(url: str) -> str:
    """„telekom.de“ aus einer Adresse."""
    return urlsplit(url or "").netloc.removeprefix("www.")


def _wert(feld: str, wert: Any) -> str:
    if feld in gp.GANZZAHLFELDER:
        return f"{wert} Raten"
    return euro(wert)


def _zaehlt(feld: str, gespeichert: dict) -> bool:
    """Trägt der nicht gelesene Posten zur Summe bei? 0 € und die Ratenzahl einer
    Rate von 0 € tun es nicht (Tarifwelt: Gerät einmalig, keine Rate)."""
    if feld in gp.GANZZAHLFELDER:
        return bool(gespeichert.get("geraet_monatsrate"))
    return bool(gespeichert.get(feld))


def _abweichung(a: dict) -> str:
    """„Geräterate: gespeichert 5,00 €, Seite 9,50 €“."""
    feld = a["feld"]
    alt = "fehlt" if a["gespeichert"] is None else _wert(feld, a["gespeichert"])
    neu = _wert(feld, a["gelesen"])
    return f"{gp.FELDNAMEN.get(feld, feld)}: gespeichert {alt}, Seite {neu}"


def farbe(buendel_id: str) -> str:
    """Die Farbe im Bündel-Schlüssel (Teil der SKU hinter dem Speicher), lesbar."""
    teile = buendel_id.split("--")
    treffer = SPEICHER_MUSTER.match(teile[2]) if len(teile) == 5 else None
    rest = teile[2][len(treffer.group(1)) :].strip("-") if treffer else ""
    return rest.replace("-", " ")


def hinweise(e: gp.Ergebnis, buendel_id: str, abgerufen_am: str) -> list[str]:
    """Was an einer Gegenprobe anders ist als an der Zeile: andere Farbe desselben
    Angebots oder ein anderer Tag als die Messung des Preises."""
    out = []
    if buendel_id and e.buendel_id != buendel_id:
        name = farbe(e.buendel_id)
        bekannt = name and name != "ohne farbe"
        out.append(f"andere Farbe ({name})" if bekannt else "andere Farbvariante")
    if e.status == gp.ABWEICHEND:
        abstand = gp.abstand_stunden(e.gemessen_um, e.geprueft_um)
        if abstand is None:
            out.append(SATZ_ZEIT_UNBEKANNT)
        elif abstand > gp.ABSTAND_STUNDEN:
            out.append(SATZ_ZEIT_ABSTAND)
    if abgerufen_am and e.datum != abgerufen_am:
        gelesen = datum_de(abgerufen_am)
        out.append(f"Prüfung vom {datum_de(e.datum)}, Preis gelesen am {gelesen}")
    return out


def _zeitpunkt(iso: str | None) -> str:
    """„20.11.2026, 03:48 Uhr“ (Berlin) aus einem ISO-Zeitpunkt; sonst leer."""
    if not uhrzeit(iso):
        return ""
    zeit = datetime.fromisoformat(iso or "").astimezone(ZEITZONE)
    return f"{zeit:%d.%m.%Y, %H:%M} Uhr"


def gegenprobe_anzeige(
    e: gp.Ergebnis | None, buendel_id: str = "", abgerufen_am: str = ""
) -> dict | None:
    """Was die Seite von einer Gegenprobe zeigt; None ohne Gegenprobe. Mit
    ``buendel_id`` und ``abgerufen_am`` der Zeile nennt ``hinweise`` eine andere Farbe
    oder einen anderen Tag."""
    if e is None:
        return None
    return {
        "hinweise": hinweise(e, buendel_id, abgerufen_am),
        "status": e.status,
        "wort": STATUS_WORT[e.status],
        "datum": datum_de(e.datum),
        "uhrzeit": uhrzeit(e.geprueft_um),
        "messung": _zeitpunkt(e.gemessen_um),
        "grund": e.grund or "",
        "abweichungen": [_abweichung(a) for a in e.abweichungen],
        "luecken": [_abweichung(a) for a in e.luecken],
        "nicht_gelesen": [
            gp.FELDNAMEN.get(f, f) for f in e.nicht_gelesen if _zaehlt(f, e.gespeichert)
        ],
        "seite": e.seite,
        "bild": e.bild,
    }


def beleg(
    *,
    quelle_url: str,
    abgerufen_am: str,
    schritte: list[dict] | None,
    gesamt: float | None,
    bild: dict | None,
    gegenprobe: gp.Ergebnis | None,
    buendel_id: str = "",
) -> dict:
    """Ein Beleg: jede Angabe da oder als benannte Lücke."""
    anzeige = gegenprobe_anzeige(gegenprobe, buendel_id, abgerufen_am)
    if bild is None and gegenprobe is not None and gegenprobe.bild:
        bild = {"url": gegenprobe.bild, "datum": gegenprobe.datum, "art": "Gegenprobe"}
    return {
        "quelle_url": quelle_url,
        "quelle": host(quelle_url),
        "gelesen_am": datum_de(abgerufen_am),
        "rechenweg": rechenweg(schritte, gesamt),
        "rechenweg_fehlt": SATZ_OHNE_RECHENWEG,
        "bild": None
        if bild is None
        else {**bild, "datum": datum_de(bild.get("datum")), "art": bild.get("art")},
        "bild_fehlt": SATZ_OHNE_BILD,
        "gegenprobe": anzeige,
        "gegenprobe_fehlt": SATZ_OHNE_GEGENPROBE,
    }


def _ohne_teile(schritte: list[dict] | None) -> list[dict] | None:
    """Summanden ohne zusammengelegte Teile (Referenzrechnung), sonst None."""
    if not schritte or any(s.get("teile") for s in schritte):
        return None
    return schritte


class Preisbelege:
    """Was die Vorlagen brauchen: Gegenproben, Ordner des Bestands, Zeilenbilder."""

    def __init__(
        self,
        state_dir: Path,
        gegenproben: Gegenproben,
        zeilenbild: Callable[[dict], dict | None],
    ) -> None:
        self.state_dir = state_dir
        self.gegenproben = gegenproben
        self.zeilenbild = zeilenbild

    def der_karte(self, karte: dict) -> dict:
        """Der Beleg einer Preiszeile der Geräteseite."""
        bild = self.zeilenbild(karte)
        if bild is not None:
            bild = {"url": bild["url"], "datum": bild["datum"], "art": "Messung"}
        return beleg(
            quelle_url=karte.get("quelle_url") or "",
            abgerufen_am=karte.get("abgerufen_am") or "",
            schritte=karte.get("rechnung_einzeln")
            or _ohne_teile(karte.get("rechnung")),
            gesamt=karte.get("gesamt"),
            bild=bild,
            gegenprobe=self.gegenproben.zum_preis(
                karte.get("buendel_id") or "", karte.get("gesamt")
            ),
            buendel_id=karte.get("buendel_id") or "",
        )


def installiere(env: Any, state_dir: Path, zeilen_stand: dict) -> list[Ausfall]:
    """Macht ``preisbeleg(karte)`` und ``preisbelege`` für die Vorlagen verfügbar.

    ``zeilen_stand`` ist der Zustand der Zeilenbilder aus ``geraete_belege``; sein
    ``fuer`` wird erst beim Rendern gelesen (``zeilenbelege`` setzt es später).
    """
    ausfaelle: list[Ausfall] = []
    ergebnisse: Iterable[gp.Ergebnis]
    try:
        ergebnisse = gp.lies_alle(state_dir / gp.ORDNER.name).values()
    except gp.GegenprobeFehler as fehler:
        ausfaelle.append(Ausfall.aus_ausnahme(TEIL, fehler))
        ergebnisse = []
    belege = Preisbelege(
        state_dir, Gegenproben(ergebnisse), lambda karte: zeilen_stand["fuer"](karte)
    )
    env.globals[GLOBAL] = belege
    env.globals["preisbeleg"] = belege.der_karte
    return ausfaelle
