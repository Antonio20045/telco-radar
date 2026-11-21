"""Beleg je Preis: Quelle, gelesen am, Rechenweg, Screenshot und Gegenprobe.

Ein Beleg ist ein Wörterbuch für die Vorlage ``_geraete_preisbeleg.html.j2``; er
rechnet nichts. Der Rechenweg sind die Summanden, die ``tco_kosten.kosten_ueber``
gerechnet hat (``Kosten.rechnung``, ungebündelt: Tarif und Gerät je für sich), mit
ihrem Wort aus ``geraete_rechnung``; ihre Summe ist die Kernzahl der Zeile.

Das Konfigurationsbild (``konfig``) ist das Bild der Gegenprobe, die an der Zeile steht
(``gegenprobe_belege.des_preises``): der Browser hat Speicher, Tarif und Raten gewählt
und den Preis gelesen, das Bild zeigt beides (``bild_zeigt``, sonst nennt die Seite,
was fehlt). Das Bild des Klick-Laufs (``geraete_zeilenbelege``, fail closed) bleibt als
Zusatz (``zusatz``): es entstand beim Messen, nicht beim Prüfen. Fehlt das
Konfigurationsbild, steht ``konfig_fehlt`` mit Grund da. Ein Bild, das das Belege-
Manifest nicht mehr führt (``gegenprobe_ablage.Liste``), zeigt die Seite nicht.
Die Gegenprobe gehört zu einem Preis, wenn ihre gespeicherten Gesamtkosten die der
Zeile sind (``gesamt_gespeichert``); eine ältere Gegenprobe eines anderen Preises steht
nicht an der Zeile (``gegenprobe_fenster.Gegenproben``, dieselbe Stelle, an der die
Gegenprobe ihr Fenster rechnet). Fehlt etwas, nennt der Beleg es (``SATZ_*``), nie leer.

Gelesen wird nur ``data/state/gegenprobe/<datum>.jsonl`` (``telco_radar.gegenprobe``);
eine unlesbare Datei ist der Ausfall „Gegenprobe“ (Regel 6).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .. import gegenprobe as gp
from .. import gegenprobe_belege as gb
from ..analyze.beleg_position import lies_buendel
from ..gegenprobe_ablage import Liste
from ..gegenprobe_ablage import liste as lies_liste
from ..gegenprobe_fenster import SPEICHER_MUSTER, Gegenproben, frist, im_fenster
from ..gegenprobe_fenster import angebot as angebot
from ..tco_model import buendel_id
from .ausfall import Ausfall
from .geraete_belegbild import ZEITZONE as ZEITZONE
from .geraete_belegbild import datum_de as datum_de
from .geraete_belegbild import konfig, messzeit, rohwerte, seite_roh
from .geraete_belegbild import uhrzeit as uhrzeit
from .geraete_belegbild import zeitpunkt as _zeitpunkt
from .geraete_gegenprobe_stand import stand as gegenprobe_stand
from .geraete_tco_grafik import euro

log = logging.getLogger(__name__)

TEIL = "Gegenprobe"
GLOBAL = "preisbelege"
SATZ_OHNE_GEGENPROBE = "Noch nicht gegengeprüft"
SATZ_OHNE_BILD = "Kein Screenshot zu diesem Preis"
SATZ_OHNE_ROHWERTE = "Keine Rohwerte gespeichert"
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


def versuch_ist_neuer(gezeigt: gp.Ergebnis | None, versuch: gp.Ergebnis | None) -> bool:
    """Ist ``versuch`` ein jüngerer, gescheiterter Besuch als die gezeigte Prüfung?"""
    if gezeigt is None or versuch is None or versuch is gezeigt:
        return False
    zeit = (versuch.datum, versuch.geprueft_um or "")
    return versuch.status == gp.NICHT_PRUEFBAR and zeit > (
        gezeigt.datum,
        gezeigt.geprueft_um or "",
    )


def versuch_hinweis(versuch: gp.Ergebnis | None) -> str:
    """„letzter Versuch 21.11.2026: nicht prüfbar (Timeout beim Laden)“."""
    if versuch is None:
        return ""
    return f"letzter Versuch {datum_de(versuch.datum)}: nicht prüfbar ({versuch.grund})"


def beleg(
    *,
    quelle_url: str,
    abgerufen_am: str,
    schritte: list[dict] | None,
    gesamt: float | None,
    bild: dict | None,
    gegenprobe: gp.Ergebnis | None,
    buendel_id: str = "",
    versuch: gp.Ergebnis | None = None,
    posten: Mapping | None = None,
    liste: Liste | None = None,
    faellig: str = "",
    datum: str = "",
    ohne_probe: str = gb.GRUND_KEINE,
) -> dict:
    """Ein Beleg: jede Angabe da oder als benannte Lücke. Ist ``versuch`` (der
    letzte geöffnete Besuch) jünger als die gezeigte Gegenprobe und gescheitert,
    nennt ein Hinweis Tag und Grund. ``bild`` ist das Bild des Klick-Laufs (Zusatz),
    ``posten`` die gespeicherte Messung (Rohwerte), ``faellig`` die Frist der nächsten
    Gegenprobe, ``datum`` der Stand der Seite (Aufbewahrung des Bilds),
    ``ohne_probe`` der Grund, wenn es keine Gegenprobe gibt."""
    anzeige = gegenprobe_anzeige(gegenprobe, buendel_id, abgerufen_am)
    if anzeige is not None and versuch_ist_neuer(gegenprobe, versuch):
        anzeige["hinweise"].append(versuch_hinweis(versuch))
    zusatz = bild
    if bild is None and gegenprobe is not None and gegenprobe.bild:
        bild = {"url": gegenprobe.bild, "datum": gegenprobe.datum, "art": "Gegenprobe"}
    bild_konfig, grund = konfig(gegenprobe, liste, datum, ohne_probe)
    return {
        "quelle_url": quelle_url,
        "quelle": host(quelle_url),
        "gelesen_am": datum_de(abgerufen_am),
        "messzeit": messzeit(abgerufen_am, gegenprobe),
        "rohwerte": rohwerte(posten),
        "rohwerte_fehlt": SATZ_OHNE_ROHWERTE,
        "seite_roh": seite_roh(gegenprobe),
        "rechenweg": rechenweg(schritte, gesamt),
        "rechenweg_fehlt": SATZ_OHNE_RECHENWEG,
        "bild": None
        if bild is None
        else {**bild, "datum": datum_de(bild.get("datum")), "art": bild.get("art")},
        "bild_fehlt": SATZ_OHNE_BILD,
        "konfig": bild_konfig,
        "konfig_fehlt": f"{SATZ_OHNE_BILD}: {grund}",
        "zusatz": None
        if zusatz is None
        else {**zusatz, "datum": datum_de(zusatz.get("datum"))},
        "gegenprobe": anzeige,
        "gegenprobe_fehlt": SATZ_OHNE_GEGENPROBE + (f" ({faellig})" if faellig else ""),
        "faellig": faellig,
    }


def _ohne_teile(schritte: list[dict] | None) -> list[dict] | None:
    """Summanden ohne zusammengelegte Teile (Referenzrechnung), sonst None."""
    if not schritte or any(s.get("teile") for s in schritte):
        return None
    return schritte


def _schluessel(satz: dict) -> list[str]:
    """Der gespeicherte Schlüssel und der, den ``tco_model`` daraus bildet (die Karte
    trägt den gebildeten; ältere Bestände tragen noch den alten)."""
    out = [str(satz.get("id") or "")]
    try:
        out.append(
            buendel_id(
                str(satz.get("sku_id") or ""),
                str(satz.get("anbieter") or ""),
                str(satz.get("tarif_name") or ""),
                satz.get("laufzeit_monate"),
            )
        )
    except (TypeError, ValueError) as fehler:
        log.info("Preisbelege: Schlüssel von %s nicht bildbar: %s", out[0], fehler)
    return out


class Preisbelege:
    """Was die Vorlagen brauchen: Gegenproben, Ordner des Bestands, Zeilenbilder,
    die Liste der aufbewahrten Bilder und (beim ersten Gebrauch) der Bestand."""

    def __init__(
        self,
        state_dir: Path,
        gegenproben: Gegenproben,
        zeilenbild: Callable[[dict], dict | None],
        liste: Liste | None = None,
    ) -> None:
        self.state_dir = state_dir
        self.gegenproben = gegenproben
        self.zeilenbild = zeilenbild
        self.liste = liste
        self._bestand: dict[str, dict] | None = None
        self.datum = ""
        """Messtag des Bestands (``updated``), Bezug für „fällig bis“."""

    def satz(self, buendel_id: str) -> dict:
        """Der Bestandssatz (``geraete_tco.json``); {} ohne Bestand."""
        if self._bestand is None:
            try:
                saetze = lies_buendel(self.state_dir / "geraete_tco.json")
            except ValueError as fehler:
                log.error("Preisbelege: Bestand unlesbar: %s", fehler)
                saetze = []
            self._bestand = {k: s for s in saetze for k in _schluessel(s)}
            self.datum = max(
                (str(s.get("abgerufen_am") or "") for s in saetze), default=""
            )
        return self._bestand.get(buendel_id, {})

    def faellig(self, satz: dict, gute: gp.Ergebnis | None) -> str:
        """„fällig bis 28.11.2026“ ohne gute Gegenprobe im Fenster; sonst leer."""
        if gute is not None and self.datum and im_fenster(self.datum, gute.datum):
            return ""
        if not self.datum and not satz.get("first_seen") and gute is None:
            return ""
        return f"fällig bis {datum_de(frist(self.datum, satz, gute))}"

    def der_karte(self, karte: dict) -> dict:
        """Der Beleg einer Preiszeile der Geräteseite: die letzte gute Gegenprobe des
        Preises (``Gegenproben.letzte_gute``, dieselbe wie Fenster und Bilanz), ohne
        sie der letzte Versuch (``gegenprobe_belege.des_preises``); ein jüngerer
        gescheiterter Versuch steht als Hinweis daneben."""
        bid = karte.get("buendel_id") or ""
        satz = self.satz(bid)
        gute = self.gegenproben.letzte_gute(bid, karte.get("gesamt"))
        versuch = self.gegenproben.letzter_versuch(bid, karte.get("gesamt"))
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
            gegenprobe=gute if gute is not None else versuch,
            buendel_id=bid,
            versuch=versuch,
            posten=satz or None,
            liste=self.liste,
            faellig=self.faellig(satz, gute),
            datum=self.datum,
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
    try:
        liste = lies_liste(state_dir / "belege_manifest.json")
    except ValueError as fehler:
        log.error("Preisbelege: Liste der Gegenprobe-Bilder unlesbar: %s", fehler)
        liste = None
    belege = Preisbelege(
        state_dir,
        Gegenproben(ergebnisse),
        lambda karte: zeilen_stand["fuer"](karte),
        liste,
    )
    env.globals[GLOBAL] = belege
    env.globals["preisbeleg"] = belege.der_karte
    env.globals["gegenprobe_stand"] = partial(gegenprobe_stand, state_dir)
    return ausfaelle
