"""Inventar einer Produktseite für die Klick-Erkundung: Bedienelemente und Preise.

``lies_inventar`` liest im Browser jedes Bedienelement (Knöpfe, Radios, Checkboxen,
Selects, Labels, Links, Elemente mit Rolle, ``aria-pressed|checked|selected``,
``onclick`` oder ``tabindex``) mit Rolle, Text, ``aria-*`` und ``data-*``, id, Klassen,
einem CSS-Pfad (``#id`` oder ``nth-of-type`` ab dem nächsten eindeutigen ``id``),
Sichtbarkeit, Sperre und der Marke, an der die Wahl erkennbar ist. Behälter ist der
nächste Vorfahr mit mindestens zwei Bedienelementen; je Behälter entsteht eine Gruppe,
jedes Select ist eine eigene. ``art_der_gruppe`` ordnet sie Speicher, Laufzeit, Tarif
oder Farbe zu, sonst ``unbekannt``. ``preise`` nennt jedes kleinste Element mit einem
€-Betrag samt Text, Kontext und Pfad. Shadow-DOM bleibt außen vor; Elemente über
``HOECHSTE_ELEMENTE`` und Preise über ``HOECHSTE_PREISE`` fallen weg, mit Zählung.
Links und die Adresse verlieren geheime Parameter, Felder mit geheimem Namen ihren Wert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .klickspur import ENTFERNT, GEHEIM, ohne_geheimnisse

if TYPE_CHECKING:
    from playwright.sync_api import Page

HOECHSTE_ELEMENTE = 1500
HOECHSTE_PREISE = 400
KURZTEXT = 40
MINDESTANTEIL_ART = 0.5
NAMENSBONUS = 0.5
UNBEKANNT = "unbekannt"
SPEICHER, LAUFZEIT, TARIF, FARBE = "speicher", "laufzeit", "tarif", "farbe"
KLICKARTEN = (SPEICHER, LAUFZEIT, TARIF)
ARTEN = {
    SPEICHER: re.compile(r"\b(?:32|64|128|256|512)\s?GB\b|\b[12]\s?TB\b", re.I),
    LAUFZEIT: re.compile(r"\b(?:0|1|6|12|24|36|48)\s*(?:Monate?n?\b|Mon\.|M\b)", re.I),
    TARIF: re.compile(
        r"(?i:tarif|allnet|all-net|unlimited|magenta|\bmobil|\bflat\b|\bgiga)"
        r"|\b(?:XS|S|M|L|XL|XXL)\b"
    ),
    FARBE: re.compile(
        r"schwarz|wei(?:ß|ss)|silber|gold|blau|gr(?:ü|ue)n|\brot\b|lila|violett|titan"
        r"|orange|rosa|pink|grau|beige|creme|frost|obsidian|black|white|blue|green"
        r"|graphite|purple|cobalt|mint|lavender|sky|navy|sand|jade|indigo",
        re.I,
    ),
}
NAMEN = {
    SPEICHER: re.compile(r"speicher|kapazit", re.I),
    LAUFZEIT: re.compile(r"laufzeit|raten|monat", re.I),
    TARIF: re.compile(r"tarif", re.I),
    FARBE: re.compile(r"farbe", re.I),
}
KURZE_ARTEN = frozenset({SPEICHER, LAUFZEIT})

_HELFER = r"""
const kurz = (s, n) => (s || "").replace(/\s+/g, " ").trim().slice(0, n);
const pfad = (e) => {
  const teile = [];
  for (let k = e; k && k.nodeType === 1 && k !== document.documentElement;
       k = k.parentElement) {
    if (k.id && document.querySelectorAll("#" + CSS.escape(k.id)).length === 1) {
      teile.unshift("#" + CSS.escape(k.id));
      return teile.join(" > ");
    }
    if (k === document.body) { teile.unshift("body"); break; }
    let n = 1;
    for (let s = k.previousElementSibling; s; s = s.previousElementSibling) {
      if (s.tagName === k.tagName) n++;
    }
    teile.unshift(`${k.tagName.toLowerCase()}:nth-of-type(${n})`);
  }
  return teile.join(" > ");
};
const sichtbar = (e) => {
  const r = e.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden";
};
const KLASSE = /(^|[_-]|is)(active|selected|checked|current|chosen)$/i;
const marke = (e) => {
  if (e.checked === true) return "checked";
  for (const a of ["aria-pressed", "aria-checked", "aria-selected"]) {
    if (e.getAttribute(a) === "true") return a;
  }
  const jetzt = e.getAttribute("aria-current");
  if (jetzt && jetzt !== "false") return "aria-current";
  if (e.tagName === "LABEL" && e.control && e.control.checked) return "label-checked";
  const klassen = (e.getAttribute("class") || "").split(/\s+/);
  const treffer = klassen.find((k) => KLASSE.test(k));
  return treffer ? "klasse:" + treffer : null;
};
const gesperrt = (e) => e.disabled === true
  || e.getAttribute("aria-disabled") === "true"
  || (e.tagName === "LABEL" && !!e.control && e.control.disabled === true);
"""

_INVENTAR_JS = (
    "(grenze) => {"
    + _HELFER
    + r"""
const AUSWAHL = "button, input[type=radio], input[type=checkbox], select, label, "
  + "a[href], [role=button], [role=radio], [role=tab], [role=option], [role=switch], "
  + "[role=checkbox], [role=menuitemradio], [role=link], [aria-pressed], "
  + "[aria-checked], [aria-selected], [onclick], [tabindex]:not([tabindex='-1'])";
const ROLLE = {BUTTON: "button", A: "link", SELECT: "combobox", LABEL: "label"};
const alle = [...document.body.querySelectorAll(AUSWAHL)];
const menge = [...alle.filter((e) => e.tagName !== "A"),
               ...alle.filter((e) => e.tagName === "A")].slice(0, grenze);
const zahl = new Map();
for (const e of menge) {
  for (let k = e.parentElement; k && k !== document.body; k = k.parentElement) {
    zahl.set(k, (zahl.get(k) || 0) + 1);
  }
}
const name = (k) => {
  const aria = k.getAttribute("aria-label");
  if (aria) return kurz(aria, 120);
  const kopf = k.querySelector(":scope > legend, :scope > h1, :scope > h2, "
    + ":scope > h3, :scope > h4, :scope > h5, :scope > h6");
  if (kopf) return kurz(kopf.innerText, 120);
  let s = k.previousElementSibling;
  for (let i = 0; s && i < 3; i++, s = s.previousElementSibling) {
    if (/^(H[1-6]|LEGEND|LABEL|P|SPAN|DIV)$/.test(s.tagName) && s.innerText.trim()
        && s.innerText.length < 120) return kurz(s.innerText, 120);
  }
  return null;
};
const behaelter = [], stelle = new Map();
const elemente = menge.map((e) => {
  let k = e.parentElement;
  while (k && k !== document.body && (zahl.get(k) || 0) < 2) k = k.parentElement;
  let gruppe = null;
  if (k && k !== document.body) {
    if (!stelle.has(k)) {
      stelle.set(k, behaelter.length);
      behaelter.push({pfad: pfad(k), name: name(k)});
    }
    gruppe = stelle.get(k);
  }
  const aria = {}, daten = {};
  for (const a of [...e.attributes].slice(0, 60)) {
    if (a.name.startsWith("aria-")) aria[a.name] = kurz(a.value, 200);
    if (a.name.startsWith("data-")) daten[a.name] = kurz(a.value, 200);
  }
  const typ = (e.getAttribute("type") || "").toLowerCase();
  return {
    tag: e.tagName.toLowerCase(),
    rolle: e.getAttribute("role") || ROLLE[e.tagName]
      || (typ === "radio" || typ === "checkbox" ? typ : e.tagName.toLowerCase()),
    text: kurz(e.innerText || e.value || "", 200),
    aria, daten,
    id: e.id || null,
    klassen: (e.getAttribute("class") || "").split(/\s+/).filter(Boolean).slice(0, 20),
    name: e.getAttribute("name"),
    wert: e.getAttribute("value"),
    typ: typ || null,
    href: e.tagName === "A" ? e.href : null,
    ziel: e.getAttribute("target"),
    pfad: pfad(e),
    sichtbar: sichtbar(e),
    deaktiviert: gesperrt(e),
    gewaehlt: marke(e),
    optionen: e.tagName === "SELECT" ? [...e.options].map((o) => ({
      wert: o.value, text: kurz(o.text, 120), gewaehlt: o.selected,
      deaktiviert: o.disabled})) : null,
    behaelter: gruppe,
  };
});
return {elemente, behaelter, gesamt: alle.length};
}"""
)

_PREISE_JS = (
    "(grenze) => {"
    + _HELFER
    + r"""
const BETRAG = /\d[\d.]*(?:,\d{1,2}|,[-–]{1,2})?\s*(?:€|EUR\b|Euro\b)|€\s*\d/i;
const gesehen = new Set(), aus = [];
let gesamt = 0;
const gang = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
for (let t = gang.nextNode(); t; t = gang.nextNode()) {
  if (!/€|EUR|Euro/i.test(t.nodeValue)) continue;
  let e = t.parentElement;
  if (!e || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(e.tagName)) continue;
  while (e && e !== document.body && !BETRAG.test(e.textContent)
         && e.textContent.length <= 120) e = e.parentElement;
  if (!e || e === document.body || !BETRAG.test(e.textContent) || gesehen.has(e)) {
    continue;
  }
  gesehen.add(e);
  gesamt++;
  if (aus.length >= grenze) continue;
  const k = e.parentElement;
  aus.push({pfad: pfad(e), text: kurz(e.innerText || e.textContent, 300),
            kontext: k ? kurz(k.innerText || k.textContent, 300) : null,
            sichtbar: sichtbar(e)});
}
return {preise: aus, gesamt};
}"""
)

_ZUSTAND_JS = (
    "(ort) => {"
    + _HELFER
    + r"""
const e = document.querySelector(ort);
if (!e) return null;
return {gewaehlt: marke(e), deaktiviert: gesperrt(e),
        wert: e.tagName === "SELECT" ? e.value : null};
}"""
)


@dataclass(frozen=True)
class Gruppe:
    """Bedienelemente in einem Behälter, oder ein Select mit seinen Optionen."""

    nummer: int
    pfad: str
    name: str | None
    art: str
    anteile: dict[str, float]
    elemente: tuple[int, ...]
    select: bool = False
    mit_marke: bool = False


@dataclass(frozen=True)
class Inventar:
    """Was die Seite unter ``adresse`` zum Bedienen anbietet und wo Beträge stehen."""

    adresse: str
    elemente: list[dict]
    gruppen: list[Gruppe]
    gesamt: int
    preise: list[dict]
    preise_gesamt: int

    def als_daten(self) -> dict:
        """Bedienelemente und Gruppen als JSON-fähige Zuordnung."""
        return {
            "elemente_gesamt": self.gesamt,
            "elemente_gelesen": len(self.elemente),
            "gruppen": [vars(g) for g in self.gruppen],
            "elemente": self.elemente,
        }


def lies_inventar(seite: Page) -> Inventar:
    """Bedienelemente, Gruppen und Preis-Kandidaten im aktuellen Zustand der Seite."""
    roh = seite.evaluate(_INVENTAR_JS, HOECHSTE_ELEMENTE)
    elemente: list[dict] = [_ohne_geheimes(e) for e in roh["elemente"]]
    gruppen: list[Gruppe] = []
    for nummer, behaelter in enumerate(roh["behaelter"]):
        glieder = tuple(i for i, e in enumerate(elemente) if e["behaelter"] == nummer)
        texte = [texte_von(elemente[i]) for i in glieder]
        art, anteile = art_der_gruppe(texte, behaelter["name"])
        marke = any(elemente[i]["gewaehlt"] for i in glieder)
        gruppen.append(
            Gruppe(
                len(gruppen),
                behaelter["pfad"],
                behaelter["name"],
                art,
                anteile,
                glieder,
                mit_marke=marke,
            )
        )
    for i, element in enumerate(elemente):
        if element["optionen"]:
            texte = [(o["text"], o["text"]) for o in element["optionen"]]
            art, anteile = art_der_gruppe(texte, element["aria"].get("aria-label"))
            gruppen.append(
                Gruppe(
                    len(gruppen), element["pfad"], None, art, anteile, (i,), True, True
                )
            )
    preise = preis_kandidaten(seite)
    adresse = ohne_geheimnisse(seite.url)
    return Inventar(
        adresse, elemente, gruppen, roh["gesamt"], preise["preise"], preise["gesamt"]
    )


def _ohne_geheimes(element: dict) -> dict:
    """Ein Link ohne geheime Parameter, ein Feld mit geheimem Namen ohne Wert."""
    if element["href"] is not None:
        element["href"] = ohne_geheimnisse(element["href"])
    name = element["name"]
    if name is not None and element["wert"] is not None and GEHEIM.search(name):
        element["wert"] = ENTFERNT
    return element


def preis_kandidaten(seite: Page) -> dict:
    """Jedes kleinste Element mit €-Betrag: Pfad, Text, Kontext, Sichtbarkeit."""
    roh: dict = seite.evaluate(_PREISE_JS, HOECHSTE_PREISE)
    return roh


def preistexte(seite: Page) -> dict[str, str]:
    """Pfad und Text jedes Preis-Kandidaten, für den Vergleich vor und nach Klicks."""
    return {p["pfad"]: p["text"] for p in preis_kandidaten(seite)["preise"]}


def zustand(seite: Page, pfad: str) -> dict | None:
    """Marke, Sperre und Wert des Elements unter ``pfad``; ``None``, wenn es fehlt."""
    roh: dict | None = seite.evaluate(_ZUSTAND_JS, pfad)
    return roh


def art_der_gruppe(
    texte: list[tuple[str, str]], name: str | None
) -> tuple[str, dict[str, float]]:
    """Art einer Gruppe aus den Texten ihrer Glieder (kurz, lang) und ihrem Namen.

    Speicher und Laufzeit zählen nur kurze Texte (höchstens ``KURZTEXT`` Zeichen, sonst
    ``aria-label``, Wert und ``data-*``), Tarif und Farbe den ganzen Text. Ein passender
    Name gibt ``NAMENSBONUS``; die Art gilt ab ``MINDESTANTEIL_ART``, sonst
    ``unbekannt``.
    """
    if not texte:
        return UNBEKANNT, {}
    anteile: dict[str, float] = {}
    for art, muster in ARTEN.items():
        stelle = 0 if art in KURZE_ARTEN else 1
        treffer = sum(bool(muster.search(t[stelle])) for t in texte)
        anteil = treffer / len(texte)
        if name and NAMEN[art].search(name):
            anteil += NAMENSBONUS
        anteile[art] = round(anteil, 2)
    beste = max(ARTEN, key=lambda a: anteile[a])
    return (beste if anteile[beste] >= MINDESTANTEIL_ART else UNBEKANNT), anteile


def texte_von(element: dict) -> tuple[str, str]:
    """Kurzer und ganzer Text eines Elements für ``art_der_gruppe``."""
    text = element["text"] or ""
    nebenbei = " ".join(
        [
            element["aria"].get("aria-label", ""),
            element["wert"] or "",
            *element["daten"].values(),
        ]
    )
    kurz = text if len(text) <= KURZTEXT else nebenbei
    return kurz, f"{text} {nebenbei}"
