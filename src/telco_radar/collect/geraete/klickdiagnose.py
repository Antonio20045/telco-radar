"""Diagnose je Kachel des Weiter-Schritts: Folgeseite, beide Lesungen, Fundstellen.

Der erste Klick-Tageslauf (Actions 37740022815, 08.10.2026) las bei 1&1 je Start beide
Kacheln der Folgeseite; jede Kachel 24 blieb Befund „Antwort nennt 36 statt 24“. Die
zweite Lesung sind die Globalen der Produktseite, vor dem Weiter gelesen
(``klicklesung.Leser.vorlesung``), und die nennen nur 24+12: Das Seitenskript setzt
``currentHardwareOfferDuration = '36'`` fest. Eine zweite Quelle für die Kachel 24 steht
in keinem Mitschnitt: Die Folgeseite holt keine Preisdaten per XHR, und ihr Dokument
hält kein Mitschnitt.

``Diagnose`` hält darum je Kachel fest, wo sie gelesen wurde (``folgeseite``), was die
Kachel zeigte (``kachel``), was die zweite Lesung nannte (``antwort``,
``antwort_laufzeit``) und wo auf der Folgeseite der Bündelbetrag der Kachel sonst
steht (``fundstellen``): Pfade von Globalen, Attribute von Elementen (mit Nummer der
Kachel, die sie enthält) und Inline-Skripte mit dem Schlüssel davor. Gespeichert werden
nur Orte, nie Werte; Folgen aus mindestens ``HEX_FOLGE`` Hex-Zeichen in Schlüsseln
werden ``*``. ``fundstellen`` ist ``None``, wenn nicht gesucht wurde, mit Grund in
``ohne_suche``; ein leeres Tupel heißt gesucht und nichts gefunden.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from playwright.sync_api import Error as PlaywrightFehler

from .klickecho import LAUFZEIT
from .klickspur import ohne_geheimnisse
from .klicktor import kurz

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from .klicklauf import Kombiergebnis
    from .klicklesung import Vorlesung
    from .klicktext import Buendelwerte

HOECHSTE_FUNDSTELLEN = 12
HOECHSTE_KNOTEN = 50_000
HOECHSTE_TIEFE = 8
HEX_FOLGE = 12
GRUND_OHNE_BETRAG = "Kachel ohne Bündelbetrag"
GRUND_GESCHEITERT = "Suche gescheitert"

_FUNDSTELLEN_JS = """([muster, kachel, grenze, knotengrenze, tiefengrenze, hex]) => {
  const treffer = new RegExp(muster);
  const maske = new RegExp("[0-9a-f-]{" + hex + ",}", "gi");
  const funde = [];
  const merke = (ort) => {
    if (!funde.includes(ort) && funde.length < grenze) funde.push(ort);
  };
  const passt = (w) =>
    (typeof w === "number" || typeof w === "string") && treffer.test(String(w));
  const stufe = (k) => {
    const name = String(k).replace(maske, "*");
    const bezeichner = /^[A-Za-z_$][\\w$]*$/.test(name);
    return bezeichner ? "." + name : "[" + JSON.stringify(name) + "]";
  };
  const fremd = (w) => typeof w === "function" || w instanceof Node || w === window;
  const gesehen = new WeakSet();
  const stapel = Object.keys(window).map((k) => ["window" + stufe(k), k, window, 0]);
  let knoten = 0;
  while (stapel.length && knoten < knotengrenze && funde.length < grenze) {
    const [pfad, k, eltern, tiefe] = stapel.pop();
    knoten++;
    let w;
    try { w = eltern[k]; } catch (e) { continue; }
    if (w === null || w === undefined || fremd(w)) continue;
    if (typeof w !== "object") { if (passt(w)) merke(pfad); continue; }
    if (gesehen.has(w) || tiefe >= tiefengrenze) continue;
    gesehen.add(w);
    let namen;
    try { namen = Object.keys(w); } catch (e) { continue; }
    for (const n of namen) {
      const weiter = Array.isArray(w) ? "[" + n + "]" : stufe(n);
      stapel.push([pfad + weiter, n, w, tiefe + 1]);
    }
  }
  const kacheln = kachel === null ? [] : [...document.querySelectorAll(kachel)];
  for (const el of document.querySelectorAll("*")) {
    for (const a of el.attributes) {
      if (a.name === "class" || a.name === "style" || !passt(a.value)) continue;
      const nummer = kacheln.findIndex((k) => k.contains(el));
      const in_kachel = nummer < 0 ? "" : " in Kachel " + (nummer + 1);
      merke(el.localName + "[" + a.name + "]" + in_kachel);
    }
  }
  [...document.scripts].forEach((s, i) => {
    const m = s.src ? null : treffer.exec(s.textContent);
    if (!m) return;
    const davor = s.textContent.slice(Math.max(0, m.index - 80), m.index);
    const name = /([A-Za-z_$][\\w$-]{0,60})['"]?\\s*[:=]\\s*[\\[{'"\\s]*$/.exec(davor);
    const bei = name ? " bei " + name[1].replace(maske, "*") : "";
    merke("script " + (i + 1) + " (" + (s.type || "text/javascript") + ")" + bei);
  });
  return funde;
}"""


@dataclass(frozen=True)
class Diagnose:
    """Was die Kachel zeigte, was die zweite Lesung nannte, wo der Betrag noch steht."""

    folgeseite: str
    kachel: Buendelwerte | None
    antwort: Buendelwerte | None
    antwort_laufzeit: str | int | None
    fundstellen: tuple[str, ...] | None
    ohne_suche: str | None = None


def betragsmuster(betrag: float) -> str:
    """Regulärer Ausdruck für ``betrag`` als „44,99“, „44.99“ oder Cent „4499“, nicht
    als Teil einer längeren Zahl oder eines Worts."""
    euro, cent = divmod(round(betrag * 100), 100)
    return rf"(?:^|[^\w.,])(?:{euro}[,.]{cent:02d}|{euro * 100 + cent})(?!\w|[.,]\d)"


def fundstellen(seite: Page, betrag: float, kachel: str | None) -> tuple[str, ...]:
    """Wo ``betrag`` auf der Seite außerhalb des Texts steht (siehe Modulkopf);
    ``kachel`` ist der Selektor der Kacheln, ohne ihn fehlt deren Nummer."""
    argumente = [
        betragsmuster(betrag),
        kachel,
        HOECHSTE_FUNDSTELLEN,
        HOECHSTE_KNOTEN,
        HOECHSTE_TIEFE,
        HEX_FOLGE,
    ]
    return tuple(seite.evaluate(_FUNDSTELLEN_JS, argumente))


def diagnose(
    seite: Page, ergebnis: Kombiergebnis, vorab: Vorlesung, kachel: str | None
) -> Diagnose:
    """Die Diagnose der Kachel, die ``ergebnis`` auf ``seite`` las."""
    lesung = vorab.zweite.lesung
    gezeigt = ergebnis.textbuendel
    betrag = None if gezeigt is None else gezeigt.buendelbetrag
    funde: tuple[str, ...] | None = None
    ohne_suche = GRUND_OHNE_BETRAG if betrag is None else None
    if betrag is not None:
        try:
            funde = fundstellen(seite, betrag, kachel)
        except PlaywrightFehler as fehler:
            ohne_suche = f"{GRUND_GESCHEITERT}: {kurz(fehler)}"
    return Diagnose(
        folgeseite=seite.url,
        kachel=gezeigt,
        antwort=None if lesung is None else lesung.buendel,
        antwort_laufzeit=None if lesung is None else lesung.variante.get(LAUFZEIT),
        fundstellen=funde,
        ohne_suche=ohne_suche,
    )


def diagnose_als_daten(diagnose: Diagnose) -> dict:
    """Die Diagnose als JSON, die Folgeseite ohne Geheimnisse."""
    return {
        "folgeseite": ohne_geheimnisse(diagnose.folgeseite),
        "kachel": None if diagnose.kachel is None else asdict(diagnose.kachel),
        "antwort": None if diagnose.antwort is None else asdict(diagnose.antwort),
        "antwort_laufzeit": diagnose.antwort_laufzeit,
        "fundstellen": None
        if diagnose.fundstellen is None
        else list(diagnose.fundstellen),
        "ohne_suche": diagnose.ohne_suche,
    }
