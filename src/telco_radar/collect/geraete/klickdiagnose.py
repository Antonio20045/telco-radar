"""Diagnose je Kachel des Weiter-Schritts: Folgeseite, beide Lesungen, Fundstellen.

Der erste Klick-Tageslauf (Actions 37740022815, 08.10.2026) las bei 1&1 je Start beide
Kacheln der Folgeseite; jede Kachel 24 blieb Befund „Antwort nennt 36 statt 24“. Die
zweite Lesung sind die Globalen der Produktseite, vor dem Weiter gelesen
(``klicklesung.Leser.vorlesung``), und die nennen nur 24+12: Das Seitenskript setzt
``currentHardwareOfferDuration = '36'`` fest. Eine zweite Quelle für die Kachel 24 steht
in keinem Mitschnitt: Die Folgeseite holt keine Preisdaten per XHR, und ihr Dokument
hält kein Mitschnitt.

``Diagnose`` hält darum je Kachel fest, wo sie gelesen wurde (``folgeseite``), ob
Kachel und zweite Lesung Bündelbetrag und Einmalzahlung nennen, ob beide denselben
Bündelbetrag nennen (``None``, wenn einer fehlt), welche Laufzeit die zweite Lesung
nennt (``antwort_laufzeit``) und wo auf der Folgeseite der Bündelbetrag der Kachel sonst
steht (``fundstellen``): Pfade von Globalen, Attribute von Elementen (mit Nummer der
Kachel, die sie enthält) und Inline-Skripte mit dem Schlüssel davor. Gespeichert werden
nur Orte und Ja/Nein-Merkmale, nie Beträge (Prüferbefund zu 3da878d3). Was in einem Ort
wie eine Kennung aussieht, wird ``KENNUNG`` (``ohne_kennungen``): JSON Web Tokens,
Folgen aus mindestens ``HEX_FOLGE`` Hex-Zeichen oder Bindestrichen (auch UUIDs), aus
mindestens ``ZIFFERN_FOLGE`` Ziffern, Wörter aus Buchstaben, Ziffern und ``_+/=`` mit
Ziffer und Groß- wie Kleinbuchstaben ab ``ZUFALL_KURZ`` Zeichen und mit Ziffer und
Buchstabe ab ``ZUFALL_LANG`` Zeichen (Warenkorb- und Sitzungskennungen, Base64). Die
Globalen werden bis ``HOECHSTE_TIEFE`` Stufen und ``HOECHSTE_KNOTEN`` Knoten
durchsucht. ``fundstellen`` ist ``None``, wenn nicht gesucht wurde, mit Grund in
``ohne_suche``; bricht die Suche an ``HOECHSTE_KNOTEN`` ab, nennt ``ohne_suche``
``GRUND_ABGEBROCHEN``, und ``fundstellen`` hält die bis dahin gefundenen Orte, ohne
solche ``None``. Ein leeres Tupel heißt nur: ganz gesucht und nichts gefunden.
"""

from __future__ import annotations

import re
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
ZIFFERN_FOLGE = 6
ZUFALL_KURZ = 10
ZUFALL_LANG = 16
KENNUNG = "*"
GRUND_OHNE_BETRAG = "Kachel ohne Bündelbetrag"
GRUND_GESCHEITERT = "Suche gescheitert"
GRUND_ABGEBROCHEN = f"Globale nach {HOECHSTE_KNOTEN} Knoten nicht weiter durchsucht"
_WORT = r"[\w+/=]"
_KENNUNGEN = (
    re.compile(r"eyJ[\w-]{4,}\.[\w-]{4,}(?:\.[\w-]*)?"),
    re.compile(
        rf"(?<!{_WORT})(?={_WORT}*\d)(?={_WORT}*[a-z])(?={_WORT}*[A-Z])"
        rf"{_WORT}{{{ZUFALL_KURZ},}}(?!{_WORT})"
    ),
    re.compile(
        rf"(?<!{_WORT})(?={_WORT}*\d)(?={_WORT}*[A-Za-z]){_WORT}{{{ZUFALL_LANG},}}"
        rf"(?!{_WORT})"
    ),
    re.compile(rf"[0-9a-f-]{{{HEX_FOLGE},}}", re.I),
    re.compile(rf"\d{{{ZIFFERN_FOLGE},}}"),
)

_FUNDSTELLEN_JS = """([muster, kachel, grenze, knotengrenze, tiefengrenze]) => {
  const treffer = new RegExp(muster);
  const funde = [];
  const merke = (ort) => {
    if (!funde.includes(ort) && funde.length < grenze) funde.push(ort);
  };
  const passt = (w) =>
    (typeof w === "number" || typeof w === "string") && treffer.test(String(w));
  const stufe = (k) => {
    const name = String(k);
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
    const bei = name ? " bei " + name[1] : "";
    merke("script " + (i + 1) + " (" + (s.type || "text/javascript") + ")" + bei);
  });
  const abgebrochen = stapel.length > 0 && knoten >= knotengrenze;
  return {funde, abgebrochen};
}"""


@dataclass(frozen=True)
class Diagnose:
    """Was Kachel und zweite Lesung nennen und wo der Betrag noch steht, ohne Beträge;
    ``antwort_*`` und ``gleicher_betrag`` sind ``None`` ohne zweite Lesung."""

    folgeseite: str
    kachel_betrag: bool
    kachel_einmalzahlung: bool
    antwort_betrag: bool | None
    antwort_einmalzahlung: bool | None
    gleicher_betrag: bool | None
    antwort_laufzeit: str | int | None
    fundstellen: tuple[str, ...] | None
    ohne_suche: str | None = None


@dataclass(frozen=True)
class Suche:
    """Gefundene Orte ohne Kennungen; ``abgebrochen`` mit Grund, wenn die Globalen
    nicht ganz durchsucht wurden."""

    funde: tuple[str, ...]
    abgebrochen: str | None = None


def betragsmuster(betrag: float) -> str:
    """Regulärer Ausdruck für ``betrag`` als „44,99“, „44.99“ oder Cent „4499“, nicht
    als Teil einer längeren Zahl oder eines Worts."""
    euro, cent = divmod(round(betrag * 100), 100)
    return rf"(?:^|[^\w.,])(?:{euro}[,.]{cent:02d}|{euro * 100 + cent})(?!\w|[.,]\d)"


def ohne_kennungen(ort: str) -> str:
    """``ort`` mit ``KENNUNG`` statt allem, was wie eine Kennung aussieht."""
    for muster in _KENNUNGEN:
        ort = muster.sub(KENNUNG, ort)
    return ort


def fundstellen(seite: Page, betrag: float, kachel: str | None) -> Suche:
    """Wo ``betrag`` auf der Seite außerhalb des Texts steht (siehe Modulkopf);
    ``kachel`` ist der Selektor der Kacheln, ohne ihn fehlt deren Nummer."""
    argumente = [
        betragsmuster(betrag),
        kachel,
        HOECHSTE_FUNDSTELLEN,
        HOECHSTE_KNOTEN,
        HOECHSTE_TIEFE,
    ]
    roh = seite.evaluate(_FUNDSTELLEN_JS, argumente)
    funde = tuple(dict.fromkeys(ohne_kennungen(f) for f in roh["funde"]))
    return Suche(funde, GRUND_ABGEBROCHEN if roh["abgebrochen"] else None)


def diagnose(
    seite: Page, ergebnis: Kombiergebnis, vorab: Vorlesung, kachel: str | None
) -> Diagnose:
    """Die Diagnose der Kachel, die ``ergebnis`` auf ``seite`` las."""
    lesung = vorab.zweite.lesung
    gezeigt = ergebnis.textbuendel
    betrag = None if gezeigt is None else gezeigt.buendelbetrag
    antwort = None if lesung is None else lesung.buendel
    funde: tuple[str, ...] | None = None
    ohne_suche = GRUND_OHNE_BETRAG if betrag is None else None
    if betrag is not None:
        try:
            suche = fundstellen(seite, betrag, kachel)
        except PlaywrightFehler as fehler:
            ohne_suche = f"{GRUND_GESCHEITERT}: {kurz(fehler)}"
        else:
            funde = None if suche.abgebrochen and not suche.funde else suche.funde
            ohne_suche = suche.abgebrochen
    return Diagnose(
        folgeseite=seite.url,
        kachel_betrag=betrag is not None,
        kachel_einmalzahlung=_nennt(gezeigt, "einmalzahlung") is True,
        antwort_betrag=_nennt(antwort, "buendelbetrag"),
        antwort_einmalzahlung=_nennt(antwort, "einmalzahlung"),
        gleicher_betrag=_gleich(gezeigt, antwort),
        antwort_laufzeit=None if lesung is None else lesung.variante.get(LAUFZEIT),
        fundstellen=funde,
        ohne_suche=ohne_suche,
    )


def _nennt(werte: Buendelwerte | None, feld: str) -> bool | None:
    return None if werte is None else getattr(werte, feld) is not None


def _gleich(kachel: Buendelwerte | None, antwort: Buendelwerte | None) -> bool | None:
    links = None if kachel is None else kachel.buendelbetrag
    rechts = None if antwort is None else antwort.buendelbetrag
    if links is None or rechts is None:
        return None
    return round(links * 100) == round(rechts * 100)


def diagnose_als_daten(diagnose: Diagnose) -> dict:
    """Die Diagnose als JSON, die Folgeseite ohne Geheimnisse."""
    daten = asdict(diagnose)
    daten["folgeseite"] = ohne_geheimnisse(diagnose.folgeseite)
    if diagnose.fundstellen is not None:
        daten["fundstellen"] = list(diagnose.fundstellen)
    return daten
