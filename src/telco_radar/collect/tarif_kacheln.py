"""Tarife aus den Preiskacheln einer Shop-Seite, die keine ld+json hat.

WARUM ES DIESEN DRITTEN WEG GIBT
--------------------------------
`tarif_pdf` liest Pflichtdokumente, `tarif_ldjson` liest strukturierte
Daten nach schema.org. o2 hat weder das eine noch das andere in
brauchbarer Menge:

* Die Rechtsseite `/recht/produktinformationsblatt/` verlinkt am
  04.09.2026 genau DREI PDFs, davon ein einziges zu einem Mobilfunktarif
  ("O2 Mobile Unlimited M Flex"). Der Bestand kannte deshalb drei
  o2-Tarife, und keiner davon war einer der beiden, die o2 heute mit
  Geraet verkauft.
* Die Blaetter zu den uebrigen Tarifen sind zwar verlinkt - aber unter
  `https://www.o2online.de/assets/blobs/pdfs/...`, und `/assets/` steht in
  der fuer uns gueltigen robots-Gruppe `User-agent: *` auf `Disallow`.
  Sie werden deshalb NICHT geholt. Das ist kein Ausweichmanoever, sondern
  die Regel: was die robots.txt sperrt, wird nicht gelesen, auch wenn ein
  Umweg offen stuende.
* `https://www.o2online.de/tarife/handyvertrag-ohne-handy/` traegt genau
  EIN ld+json, und das ist eine `BreadcrumbList`.

Die Tarife stehen dort trotzdem - serverseitig, in zwoelf Kacheln
(HTTP 200, 210 KB, gemessen 04.09.2026 mit dem Absender TelcoRadar/1.0).
Dieses Modul liest sie, und zwar aus der Auszeichnung, die o2 selbst
vergibt: `<article class="teaser ... teaser-with-price">`, darin ein
`<tef-price>` mit `slot="price"`. Das ist dieselbe Haltung wie bei der
Kachelernte im Geraetezweig (`einsundeins.ernte`): geerntet wird, was die
Seite selbst als Kachel auszeichnet, nicht was ein Pfadmuster errraet.

DIE GEGENPROBE, DIE DIESEM MODUL SEIN VERTRAUEN GIBT
-----------------------------------------------------
"O2 Mobile Unlimited M Flex" steht im Bestand mit 39,99 EUR - gelesen aus
dem Produktinformationsblatt, also aus der belastbarsten Quelle dieses
Marktes. Die Kachel derselben Seite nennt fuer denselben Tarif ebenfalls
39,99 EUR. Zwei voellig getrennte Wege, dieselbe Zahl. Genau eine solche
Ueberschneidung war der Grund, diesen Weg ueberhaupt zu wagen; ohne sie
waere er eine unbelegte Lesart.

WAS DIE KACHEL SAGT - UND WAS NICHT
-----------------------------------
Uebernommen werden nur Werte, die woertlich in der Kachel stehen:

    name              die erste `<span class="small">` der Ueberschrift
                      ("O2 Mobile S"). Der Rest der Ueberschrift ist
                      Datenvolumen und Netztechnik, kein Produktname.
    grundgebuehr      `<span slot="price">` ("19,99 €")
    anschlusspreis    `<span slot="after">` ("+ einm. Anschlusspreis
                      39,99 €"). Steht dort "0,00 € statt 39,99 €", gilt
                      die ERSTE Zahl - die zweite ist der durchgestrichene
                      Listenpreis, und was heute zu zahlen ist, ist die
                      Auskunft einer Shop-Seite.
    datenvolumen_gb   der Text zwischen den beiden `<span class="small">`
                      ("15 GB+"). Eine Kachel ohne GB-Angabe
                      ("Unbegrenzt") bekommt KEINEN Wert - `None` heisst
                      hier "die Kachel nennt keine Zahl", und eine
                      unbegrenzte Menge ist keine Zahl.
    laufzeit_monate   nur aus dem ANGEKREUZTEN Auswahlknopf
                      ("Mindestlaufzeit wählen: 24 Monate"). Steht dort
                      "Monatlich kündbar", bleibt das Feld leer: ein
                      Flex-Tarif hat keine Mindestlaufzeit, und 1 waere
                      eine erfundene.

Nicht uebernommen wird alles Uebrige. `allnet_flat` steht als Werbezeile
in der Kachel ("Allnet-Flat & EU-Roaming inklusive") - das ist ein
Verkaufsargument im Fliesstext und keine Zusage in einem Datenfeld;
dieselbe Regel wie in `tarif_ldjson` gegen "All-Net-Flat S".

DER SLUG, AN DEM DER BUENDELPREIS HAENGT
-----------------------------------------
Jede Kachel traegt einen Link "Handy hinzufügen":

    <a href="https://www.o2online.de/e-shop/?tarif=o2-mobile-on-demand-m-plus"
       title="Handy hinzufügen">

Das ist die Bruecke, ohne die kein o2-Buendel in den Bestand koennte. Der
Geraetekatalog nennt seinen Tarif als "O<sub>2</sub> Mobile on Demand M
Plus mit 50 GB+ (24 Mon.)" und als Slug `o2-mobile-on-demand-m-plus`; die
SIM-only-Kachel heisst "O2 Mobile on Demand M" und kostet 19,99 EUR. Die
zwei Namen treffen sich nie - der Slug tut es, und zwar weil O2 SELBST
ihn von dieser Kachel aus setzt. Er landet in `Tarif.buendel_slug`, und
`tarif_bezug.ueber_slug` loest damit auf.

Ohne diesen Weg gaebe es fuer o2 nur die Wahl zwischen zwei Fehlern: den
Buendelpreis ohne Tarif zu speichern (verboten, `TcoDB.upsert_buendel`)
oder den Kachelpreis unter dem Katalognamen abzulegen (eine Zuordnung,
die keine Quelle so herstellt).
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from ..tarif_model import HOCH, PREISTYP_LIVE_SHOP, Tarif, zahl
from .tarif_pdf import dokument_hash

log = logging.getLogger(__name__)

# Die Auszeichnung, an der o2 eine Preiskachel erkennbar macht. Bewusst
# eine TEILKLASSE und keine vollstaendige Klassenliste: die Kacheln tragen
# daneben `teaser-neuro`, `teaser-highlight` und `teaser-switchable`, und
# eine dieser Beigaben zu verlangen hiesse, an einer Designentscheidung zu
# haengen statt an der Sache.
_KACHEL_KLASSE = "teaser-with-price"

# "15 GB+" -> 15.0. Wie in `tarif_ldjson`: nur GB, kein MB. Eine MB-Zahl in
# einer Tarifkachel ist eine Geschwindigkeit ("5G mit max. 300 MBit/s") und
# kein Volumen - genau deshalb wird sie hier nur im Volumenteil der
# Ueberschrift gesucht und nicht in der ganzen Kachel.
_VOLUMEN_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*GB\b", re.I)

# "+ einm. Anschlusspreis 0,00 € statt 39,99 €" -> 0,00.
_ANSCHLUSS_RE = re.compile(r"Anschlusspreis\D{0,10}?(\d+(?:[.,]\d+)?)", re.I)

# "24 Monate" im angekreuzten Auswahlknopf.
_LAUFZEIT_RE = re.compile(r"(\d+)\s*Monate?\b", re.I)


def _entpacke_tiefstellungen(suppe) -> None:
    """`O<sub>2</sub>` zu `O2` machen - VOR jedem Textzugriff.

    Ohne diesen Schritt heisst der Tarif "O 2 Mobile S": `get_text(" ")`
    setzt zwischen zwei Textknoten ein Trennzeichen, und die Ziffer steht
    in einem eigenen Element. Der stabile Schluessel waere dann
    `o2:o-2-mobile-s` - und der Satz aus dem Produktinformationsblatt, der
    `o2:o2-mobile-unlimited-m-flex` heisst, waere ploetzlich ein anderer
    Tarif als dieselbe Kachel.

    `smooth()` ist der Teil, den man vergisst: `unwrap()` laesst zwei
    benachbarte Textknoten stehen, und zwei Textknoten sind fuer
    `get_text(" ")` weiterhin zwei Stellen mit einem Trenner dazwischen.
    """
    for tag in suppe.find_all(["sub", "sup"]):
        tag.unwrap()
    suppe.smooth()


def _text(knoten) -> str:
    """Sichtbarer Text, auf einfache Leerzeichen normalisiert.

    Muss dasselbe Ergebnis liefern wie die Normalisierung in
    `Tarif.fehlende_belege` (`" ".join(text.split())`) - sonst steht eine
    Fundstelle nicht woertlich im Rohtext und `pruefe_belege` wirft, obwohl
    der Wert sauber gelesen wurde.
    """
    if knoten is None:
        return ""
    roh = knoten if isinstance(knoten, str) else knoten.get_text(" ")
    return " ".join(str(roh).replace("\xa0", " ").split())


def _slot(kachel, name: str) -> str:
    """Der Text eines `<span slot="...">` der Preisauszeichnung."""
    treffer = kachel.find("span", attrs={"slot": name})
    return _text(treffer)


def _name_und_volumen(kachel) -> tuple[str, str]:
    """Produktname und Volumenzeile aus der Ueberschrift.

    Die Ueberschrift ist dreiteilig und trennt die drei Teile durch die
    Klasse `small`, nicht durch Elemente: Name (small), Volumen (nackter
    Text), Netztechnik (small). Der Name ist deshalb die ERSTE `small`,
    das Volumen ist, was uebrig bleibt, wenn man alle `small` entfernt.
    """
    kopf = kachel.find(class_="headline")
    if kopf is None:
        return "", ""
    kleine = kopf.find_all("span", class_="small")
    name = _text(kleine[0]) if kleine else ""
    # Auf einer KOPIE arbeiten: `extract()` veraendert den Baum, und die
    # Kachel wird danach noch fuer den Rohtext gebraucht.
    kopie = BeautifulSoup(str(kopf), "html.parser")
    for span in kopie.find_all("span", class_="small"):
        span.extract()
    return name, _text(kopie)


def _laufzeit(kachel) -> tuple[Optional[int], str]:
    """Die Mindestlaufzeit aus dem ANGEKREUZTEN Auswahlknopf.

    Nicht aus dem ersten und nicht aus allen: die Kachel bietet "24 Monate"
    und "Monatlich kündbar" nebeneinander an, und nur eine davon gehoert
    zum angezeigten Preis. Welche das ist, sagt `checked` - die Kachel
    selbst, nicht die Reihenfolge.
    """
    for eingabe in kachel.find_all("input", attrs={"type": "radio"}):
        if not eingabe.has_attr("checked"):
            continue
        beschriftung = eingabe.find_next("label")
        titel = _text(beschriftung.find(class_="radio-title")
                      if beschriftung else None)
        treffer = _LAUFZEIT_RE.search(titel)
        if treffer:
            return int(treffer.group(1)), titel
        # "Monatlich kündbar" - eine Aussage, aber keine Monatszahl.
        return None, titel
    return None, ""


def _buendel_slug(kachel) -> tuple[str, str]:
    """Der Tarif-Slug, unter dem derselbe Tarif MIT Geraet laeuft.

    Gelesen wird nur aus dem Link, den die Kachel selbst so beschriftet
    ("Handy hinzufügen"). Ein beliebiger `?tarif=`-Parameter irgendwo auf
    der Seite waere keine Zuordnung zu DIESER Kachel.
    """
    for anker in kachel.find_all("a", href=True):
        if "handy hinzu" not in (anker.get("title") or "").lower():
            continue
        href = anker["href"]
        werte = parse_qs(urlsplit(href).query).get("tarif") or []
        if werte and werte[0].strip():
            return werte[0].strip(), href
    return "", ""


def tarif_aus_kachel(kachel, *, anbieter: str, seiten_url: str,
                     abgerufen_am: str) -> Optional[tuple[Tarif, str]]:
    """Eine Preiskachel wird ein Tarif - oder nichts.

    Nichts wird sie, wenn Name oder Betrag fehlen oder wenn die Kachel
    nichts Bestellbares dieses Anbieters ist. Das letzte Kriterium ist
    STRUKTURELL und nicht namensbasiert: eine Tarifkachel traegt einen
    Bestellweg (`/e-shop/directbuy/offer;name=...`) oder den Weg ins
    Geraetebuendel (`?tarif=...`). Ein Werbeteaser mit Preis - "Internet
    schon ab 19,99 €" - traegt beides nicht und faellt heraus, ohne dass
    dieses Modul Produktnamen raten muesste.
    """
    name, volumenzeile = _name_und_volumen(kachel)
    betrag = zahl(_slot(kachel, "price"))
    if not name or betrag is None:
        return None

    slug, slug_href = _buendel_slug(kachel)
    bestellweg = any("directbuy/offer" in (a.get("href") or "")
                     for a in kachel.find_all("a", href=True))
    if not slug and not bestellweg:
        log.info("Preiskachel %r auf %s traegt keinen Bestellweg - kein "
                 "Tarif dieses Anbieters", name, seiten_url)
        return None

    preistext = _slot(kachel, "price")
    nachtext = _slot(kachel, "after")
    laufzeit, laufzeittext = _laufzeit(kachel)

    # Der Rohtext IST die Kachel - plus die eine Adresse, aus der der Slug
    # kommt. Ohne sie stuende `buendel_slug` mit einer Fundstelle da, die
    # im Rohtext nicht vorkommt, und `pruefe_belege()` wuerde zu Recht
    # werfen: ein Wert, dessen Beleg man nicht nachlesen kann.
    rohtext = _text(kachel)
    if slug_href:
        rohtext = f"{rohtext} | Handy hinzufügen: {slug_href}"

    tarif = Tarif(anbieter=anbieter, abgerufen_am=abgerufen_am,
                  rohtext=rohtext, preistyp=PREISTYP_LIVE_SHOP,
                  dokument_url=seiten_url)
    tarif.setze("name", name, name, HOCH)
    tarif.setze("grundgebuehr", betrag, preistext, HOCH)

    anschluss = _ANSCHLUSS_RE.search(nachtext)
    if anschluss:
        tarif.setze("anschlusspreis", zahl(anschluss.group(1)), nachtext, HOCH)

    volumen = _VOLUMEN_RE.search(volumenzeile)
    if volumen:
        tarif.setze("datenvolumen_gb", zahl(volumen.group(1)),
                    volumenzeile, HOCH)

    if laufzeit is not None:
        tarif.setze("laufzeit_monate", laufzeit, laufzeittext, HOCH)

    if slug:
        tarif.setze("buendel_slug", slug,
                    f"Handy hinzufügen: {slug_href}", HOCH)

    # Der Fingerabdruck haengt an der KACHEL, nicht an der Seite - genau
    # wie in `tarif_ldjson` am Knoten. Zwoelf Tarife auf einer Seite
    # haetten sonst denselben Hash, und eine Preisaenderung an einem
    # einzigen liesse alle zwoelf als geaendert gelten.
    hash_ = dokument_hash(rohtext)
    tarif.dokument_hash = hash_
    return tarif, hash_


def tarife_aus_html(html: str, *, anbieter: str, seiten_url: str,
                    abgerufen_am: str) -> list[tuple[Tarif, str]]:
    """Alle Tarife, die die Seite in ihren Preiskacheln zeigt.

    Gleiche Signatur wie `tarif_ldjson.tarife_aus_html` - der Sammler
    unterscheidet die zwei Lesarten an der `methode` der Quelle und nicht
    an ihrem Aufrufmuster.
    """
    suppe = BeautifulSoup(html or "", "html.parser")
    _entpacke_tiefstellungen(suppe)
    out: list[tuple[Tarif, str]] = []
    gesehen: set[str] = set()
    for kachel in suppe.find_all(class_=_KACHEL_KLASSE):
        ergebnis = tarif_aus_kachel(kachel, anbieter=anbieter,
                                    seiten_url=seiten_url,
                                    abgerufen_am=abgerufen_am)
        if ergebnis is None:
            continue
        tarif, hash_ = ergebnis
        if hash_ in gesehen:
            # Dieselbe Kachel zweimal auf derselben Seite. o2 liefert seine
            # Tarifuebersicht in mehreren Reitern aus; zwei identische
            # Kacheln waeren zwei Datensaetze desselben Tarifs.
            continue
        gesehen.add(hash_)
        out.append((tarif, hash_))
    return out
