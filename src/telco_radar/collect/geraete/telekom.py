"""Telekom: die Kategorieseite traegt ihre Preise serverseitig.

WAS SICH SEIT DEM 11.08.2026 GEAENDERT HAT - UND WAS NICHT
----------------------------------------------------------
Der alte `grund` in `geraete_quellen.yaml` bleibt in seinem Kern richtig:
auf der PRODUKTSEITE (`/shop/geraet/...`) traegt
`productDetailed.productDetailsData` je Speicherstufe nur einen
`deltaPrice`, also einen Aufschlag ohne Grundbetrag. Wer dort nach einem
Ladenpreis sucht, findet keinen.

Falsch war nur die Folgerung, dass Telekom deshalb gar nicht anzubinden
sei. Die KATEGORIEseite

    https://www.telekom.de/shop/geraete/smartphones/ohne-vertrag

liefert die absoluten Betraege serverseitig mit. Gemessen am 04.09.2026
(HTTP 200, 2,23 MB, Absender `TelcoRadar/1.0`, ohne Challenge) traegt
`window.__INITIAL_STATE__.productList.data` zehn Geraete, jedes so:

    "name": "Apple iPhone 17 Pro",
    "productSlug": "apple-iphone-17-pro", "variantSlug": "tiefblau-256-gb",
    "price": {"upfrontPrice": 99,
              "installments": [{"numberOfInstallments": 36,
                                "recurringPrice": 30.5,
                                "totalPrice": 1197}]}

DIE ZAHL IST KEIN BARPREIS, UND DAS IST DER GANZE PUNKT
-------------------------------------------------------
`totalPrice` ist der Gesamtbetrag eines Teilzahlungsgeschaefts ueber 36
Monate, kein Kassenpreis: 99 + 36 x 30,50 = 1197,00. Die Rechenprobe ging
am 04.09.2026 bei **10 von 10** Geraeten auf.

Genau das war die Bedingung, die der alte `grund` gestellt hat: "Ein
Adapter kann Telekom deshalb erst liefern, wenn er die Preisform
mitschreibt." Er schreibt sie mit - `anzahlung`, `monatsrate` und
`laufzeit_monate` wandern an die Listung, und `geraete_model.ratenhinweis`
setzt daneben "in 36 Raten". Dieselbe Bauart wie bei o2, dieselbe
Rechenprobe (`probe_geht_auf`), aus demselben Grund: o2s 721,00 EUR standen
bis zum 03.09.2026 in derselben Spalte wie freenets Barpreis von 949,00 EUR.

Geht die Probe NICHT auf, wird die Preisform verworfen und der Satz mit ihr.
Ein Gesamtbetrag, der seinen eigenen Bestandteilen widerspricht, ist keine
Messung - er ist ein geaendertes Nutzlastformat, und das soll auffallen und
nicht als Preis in den Bestand.

`zins_effektiv` bleibt `None`. Die Kategorieseite weist keinen Zinssatz
aus, und `None` heisst "unbekannt", nicht "null Prozent" - o2 bekommt seine
0.0 nur, weil die Produktseite sie woertlich als gesetzlichen
Finanzierungshinweis nennt.

MEHRERE RATENPLAENE JE GERAET: WAS GEMESSEN IST (FIX3, 21.09.2026)
-------------------------------------------------------------------
GEMESSEN an den beiden gespeicherten echten Abrufen - Kategorieseite
"ohne Vertrag" vom 04.09.2026 und Buendelseite MagentaMobil S vom
08.09.2026 - traegt `installments` bei JEDEM Eintrag GENAU EINEN Plan,
und `numberOfInstallments` traegt darin AUSSCHLIESSLICH 36 (10 von 10
bzw. 9 von 9 Eintraegen, je ein Plan). Dasselbe Bild im Bestand: die
Buendelhistorie `data/state/geraete_tco_historie.jsonl` fuehrt fuer
Telekom, o2, congstar und 1&1 in 1539 Zeilen ausnahmslos 36 Monate;
mehrere Laufzeiten nebeneinander stehen dort nur bei Vodafone (12/24/36).

Das ZIEL in CLAUDE.md nennt fuer Telekom 6/12/24/36 Monate nebeneinander.
Dieses Ziel ist NICHT erreicht und dieser Adapter behauptet es nicht: er
ist nur darauf VORBEREITET. `_preisformen()` liest die ganze Liste statt
`installments[0]`, und jeder Plan bekommt seine eigene Rechenprobe; ein
Plan, der nicht aufgeht, faellt nur fuer sich. Belegt ist diese
Vorbereitung an keinem echten Abruf - nur an synthetisch ergaenzten
zweiten Plaenen in den Tests, die sich als solche ausweisen.

CLAUDE.md Fallstrick 16 gilt damit unverkuerzt: dass ALLE Anbieter
ausnahmslos 36 Monate zeigen, ist zuerst ein Verdacht auf eine
ERFASSUNGSLUECKE und erst danach eine Aussage ueber den Markt. Gegenprobe
waere die Anbieterseite selbst. Aus dieser Umgebung ist sie nicht
erreichbar (gemessen 21.09.2026: `CONNECT tunnel failed, response 403`
fuer telekom.de und congstar.de). Der Verdacht bleibt deshalb OFFEN und
steht hier - er ist nicht ausgeraeumt.

EINE LISTUNG IST DAS GERAET, KEIN RATENPLAN (FIX3)
---------------------------------------------------
`geraete_model.listung_id` ist (Anbieter, SKU) und kennt keine Laufzeit.
Ein eigener LISTUNGS-Satz je Ratenplan kollidiert deshalb in
`GeraeteDB.upsert`: der zweite Satz wird mit der Begruendung "zwei Artikel
nicht unterscheidbar (etwa zwei Farben)" uebergangen, was fuer zwei
Laufzeiten desselben Geraets unwahr ist - und welcher Plan im Bestand
landet, entschied die REIHENFOLGE in `installments` (gemessen am zweiten,
selbstkonsistenten 24-Monats-Plan: Geraetepreis 1197 oder 1155 EUR, je
nach Sortierung). Die `listung_id` zu erweitern waere eine
Datenwanderung - der ganze Altbestand gaelte als ausgelistet und entstuende
neu -, deshalb loest `_listungsplan()` es auf der Listungsseite:

    Ein Geraet, eine Listung. Sie traegt den Plan mit dem HOECHSTEN
    Gesamtbetrag (bei Gleichstand den mit der laengeren Ratenlaufzeit).

DIE REGEL IST EINE WAHL UND KEINE MESSUNG (korrigiert P0-B-h5)
---------------------------------------------------------------
Welcher von zwei ECHTEN Plaenen der "richtige" Traeger ist, steht in der
Nutzlast nicht: sie markiert keinen als Standardangebot. Die Regel ist
also DEFINIERT, nicht belegt - und weil sie eine Wahl ist, braucht sie
einen Grund, der sich nachlesen laesst. Er ist zweiteilig:

1. Sie sortiert nach der Zahl, die sie entscheidet. Die Auswahl bestimmt
   `preis_ohne_vertrag`, und das IST `gesamt`. Bis P0-B-h5 sortierte sie
   nach der LAUFZEIT und nur bei Gleichstand nach dem Betrag - ein
   Kriterium neben dem entschiedenen. Das ist kein Schoenheitsfehler: die
   zwei koennen auseinanderlaufen. 24 Monate zu 1.203,00 EUR gegen 36
   Monate zu 1.197,00 EUR ergab nach der alten Regel die 1.197,00 - also
   ausgerechnet den NIEDRIGEREN Betrag, entgegen der Begruendung, mit der
   die Regel angetreten war.
2. Ein zu NIEDRIGER Preis ist der schaedlichere Fehler. CLAUDE.md sagt
   "Der niedrigste Preis ist der wahrscheinlichste Fehler", und auf dieser
   Seite gewinnt eine zu niedrige Zahl Vergleiche und Rangfolgen, die ihr
   nicht gehoeren. Die Wahl des hoechsten belegten Gesamtbetrags kann die
   Listung deshalb nicht unter den teuersten dokumentierten Kaufweg des
   Anbieters druecken.

Reihenfolgeunabhaengig ist sie weiterhin: `max()` ueber `(gesamt,
laufzeit)`, und ein Gleichstand in BEIDEN bedeutet gleiche Betraege - die
Rechenprobe nagelt dann auch die Rate fest. Deshalb steht die Regel an
genau einer Stelle (`_LISTUNGSPLAN_REGEL`) und jede Anwendung mit allen
Betraegen im Protokoll.

Am gemessenen Bestand aendert die Korrektur nichts: beide gespeicherten
echten Abrufe fuehren je Eintrag GENAU EINEN Plan, alte und neue Regel
treffen denselben. Nachgemessen in P0-B-h5, 10 von 10 bzw. 9 von 9
Eintraegen identisch.

WAS DIESE REGEL KOSTET - UND WO SIE NICHT REICHT
-------------------------------------------------
Im BUENDEL-Pfad ist die Laufzeit kein Problem: `tco_model.buendel_id()`
traegt sie seit B1 im Schluessel, `lies_buendel()` legt je Plan ein
eigenes Buendel an, nichts geht verloren.

Auf der Seite, die `lies()` liest, gilt das NICHT - und der Buendelpfad
kann dort nicht einspringen. Die Konfiguration gibt Telekom einen
`kind: static`-Einstieg (`/ohne-vertrag`) und fuenf `kind: buendel`-
Einstiege; die "ohne Vertrag"-Nutzlast erreicht `lies_buendel()` nie (sie
traegt keinen `selectedPlan` und waere dort ein Fehler). Sie KANN ihn auch
nicht erreichen: ein Buendel ist Geraet PLUS Tarif - `tco_model.buendel_id`
traegt den Tarifnamen im Schluessel, und `tco_buendel.aus_rohsaetzen`
verwirft einen Rohsatz, dessen Tarif sich nicht auf eine `tarif_id`
aufloesen laesst. Ein Geraet OHNE Vertrag hat keinen. Der zweite Ratenplan
eines vertragsfreien Geraets ist also nicht "woanders abgelegt" - er ist
fort.

OFFEN GEGEN REGEL 9: DAS PROTOKOLL IST NICHT DIE SEITE
-------------------------------------------------------
`_listungsplan()` nennt den uebergangenen Plan mit Anzahlung, Rate,
Laufzeit und Gesamtbetrag, sodass der erste echte Mehrplan-Fall
nachrechenbar ist. Das Log ist aber kein Leser der Website: auf der
Geraeteseite steht davon kein Wort, und CLAUDE.md Regel 9 verlangt, dass
ein Ausfall SICHTBAR wird statt still zu bleiben.

Ein Adapter kann das nicht heilen. `Listung` traegt genau eine Preisform
(`anzahlung`, `monatsrate`, `laufzeit_monate`), und die Sammelbilanz hat
fuer so eine Meldung keinen Kanal auf die Seite: `Anbieterbilanz.proben`
endet in `geraete_pipeline.melde_proben()` im Log, `unbekannt` in
`data/state/geraete_unbekannt.jsonl`. Beides erreicht keine Vorlage
(nachgemessen in P0-B-h5). Die Luecke gehoert damit nach `Listung`, in
die Bilanz und auf die Geraeteseite - drei Dateien, die diesem Modul
nicht gehoeren - und ist als Befund gemeldet, nicht hier behoben.

Was am gemessenen Bestand heute davon abhaengt: nichts. Kein Eintrag der
beiden echten Abrufe traegt zwei Plaene, die Luecke ist also eine
VORBEREITUNGS-Luecke und kein laufender Datenverlust. Sie steht hier,
damit sie beim ersten echten Fall nicht neu entdeckt werden muss.

DIE ADRESSE KOMMT AUS DEM HTML, NICHT AUS DEM SLUG
--------------------------------------------------
Aus `brandSlug`, `productSlug` und `variantSlug` liesse sich eine
Produktadresse zusammensetzen. Das waere eine geratene Adresse, und die
Hausregel dieses Projekts kennt dafuer nur eine Antwort. Stattdessen
werden die zehn `<a href="/shop/geraet/...">` der Seite geerntet und dem
Geraet zugeordnet, dessen drei Slugs in der Adresse stehen. Findet sich
keine, traegt der Satz die Kategorieseite als Quelle - sie ist die Seite,
auf der die Zahl wirklich stand.

Abgerufen wird ohnehin NUR die Kategorieseite (`direkt=True`): sie ist die
Nutzlast, keine Produktseite wird nachgeladen. Die geernteten Adressen sind
Beleglinks fuer den Leser, keine weiteren Abrufe.

DIE UMLEITUNGSKETTE
-------------------
`/mobilfunk/geraete/smartphone` und `/mobilfunk/tarife` laufen ueber eine
OAuth-Kette mit `prompt=none` auf die Shop-Adresse. Der Sammler folgt
Umleitungen ohnehin; die Kategorieadresse steht deshalb direkt in der
Konfiguration - eine Kette weniger ist eine Fehlerquelle weniger.

DER BUENDELKATALOG: DIE GLEICHE SEITE, EINMAL JE TARIF (B2, 08.09.2026)
-----------------------------------------------------------------------
Die Kategorieseite kennt einen Parameter, den sie selbst in ihrem
Pagination-Link nennt:

    /shop/geraete/smartphones?currentPage=2&tariffId=MF_17791&
        itemPerPage=24&excludedCurrentPage=1&bp=acquisition

Mit `tariffId` aendert sich die GANZE Preisstruktur der Antwort - Zuzahlung,
Geraeterate und Ratengesamtbetrag sind je Tarif andere (gemessen am
Google Pixel 11 Pro 256 GB: MagentaMobil S 99 € + 36 x 28,30 €,
MagentaMobil M 99 € + 36 x 25,50 €, MagentaMobil XL 1 € + 36 x 22,70 €).
Das ist genau die Geraet-x-Tarif-Kombinatorik, die kein Produktinformations-
blatt und keine Produktseite (T2-Befund: nur `deltaPrice`) liefert.

Die fuenf gueltigen `tariffId`-Werte nennt die Telekom selbst: die
Tarifuebersicht /shop/tarife/handyvertrag verlinkt je Kachel ihre ID
(MagentaMobil XS=MF_17779, S=MF_17785, M=MF_17791, L=MF_17797,
XL=MF_17803). Weder der Parameter noch ein Wert wird hier erraten - dieselbe
Regel wie bei o2, wo die Bündeladresse in der Nutzlast der ersten steht.

JE ANTWORT EIN TARIF, UNTER `productList.selectedPlan`
------------------------------------------------------
`selectedPlan.id` (MF_17785) und `selectedPlan.name` ("MagentaMobil S") -
der TARIFNAME STEHT IN DERSELBEN ANTWORT, es braucht keinen zweiten
Endpunkt und keine Aufloesung nach dem Sammeln (der Unterschied zu
Vodafone, dessen `offerCoreHash` einen eigenen GET je Geraet braucht).
Dazu zwei typisierte Preise in `selectedPlan.prices`:

    oneTimeTariffFee (priceType activationFee)  39,95 €  Anschlusspreis
    monthlyTariffFee (priceType recurringFee)   39,95 €  Tarif monatlich

UND DER GERÄTEPREIS JE EINTRAG WIRD DAGEGEN NACHGERECHNET
---------------------------------------------------------
Je Geraet steht unter `formattedPrices.recurringTariffPrice.price` der
Tarifpreis, den DIESE Seite fuer DIESEN Tarif nennt (id
"MF_17785-MRC-Price"). Zwei Proben sind Bedingung, nicht Protokoll:

    1. Die Preis-ID beginnt mit selectedPlan.id + "-" - sonst gehoerte der
       je-Geraet-Block zu einem anderen Tarif als der selectedPlan, und der
       Satz waere falsch etikettiert.
    2. formattedPrices.recurringTariffPrice == selectedPlan.monthlyTariffFee
       - sonst widerspricht die Antwort sich selbst; gemessen am 08.09.2026
       gehen beide bei 9 von 9 Geraeten auf.

Dazu kommt die Ratenprobe, die `lies()` schon kennt (`_preisformen`:
upfrontPrice + numberOfInstallments x recurringPrice == totalPrice, JE
Ratenplan) - auch fuer Buendel gilt: ein Plan, der nicht aufgeht, faellt
fuer sich, nicht der ganze Eintrag.

Eine Antwort OHNE selectedPlan (die ohne-vertrag-Seite traegt `null`)
ist keine Buendelantwort, und das ist kein Fehler sondern Auskunft:
`lies_buendel()` wirft in diesem Fall - dasselbe Muster wie o2s
HW_ONLY-Zustandscheck, aus demselben Grund (ein leeres Ergebnis waere die
falsche Meldung fuer ein geaendertes Nutzlastformat).

WAS DER SLUG HIER IST
---------------------
`tarif_slug` traegt die MF-ID des Tarifs. Der Telekom-Bestand loest heute
noch ueber den NAMEN auf (`tarif_bezug.ueber_namen`, "MagentaMobil S"
steht wortgleich im PIB-Bestand); die Kachel-Pipeline setzt noch kein
`buendel_slug`. Der Slug steht trotzdem im Satz: er ist die Ordnung des
ANBIETERS (dieselbe ID nennt die Kachel im "Tarif auswählen"-Link), und
wenn ein Tarif je umbenannt wird, ist diese Brücke bereits gelegt.

EIN EINTRAG OHEN `name` ist eine Werbekachel der Seite ("higherTariff-
Discount", tileType), kein Geraet - er wird uebergangen, nicht geraten.

DIE GRENZE, DIE BLEIBT
----------------------
Aus GitHub Actions antwortet telekom.de httpx mit HTTP 202 und rund 2 KB
Challenge-HTML (CLAUDE.md § 6). Dieser Adapter aendert daran nichts und
soll es nicht: ein Fingerprint-Trick waere eine Umgehung, keine Loesung.
Faellt der Abruf so aus, liefert die Nutzlast keine Geraete, und
`sammle_anbieter` fuehrt die Seite als ungelesen - die Bestandsdaten altern
dann NICHT. Genau dafuer ist die Unterscheidung gebaut.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import GeraeteAbrufFehler
from ...geraete_model import probe_geht_auf
# DIE EINE STELLE, die entscheidet, ob ein Rohwert eine Ratenlaufzeit IST
# (Clean Code 1): dieselbe Pruefung, die `buendel_id` und `Buendel` lesen.
from ...tco_model import laufzeit_in_monaten

log = logging.getLogger(__name__)

_STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*")

# "tiefblau-256-gb" -> Farbe "tiefblau", Speicher 256.
# Die Einheit steht am Ende und wird gebraucht: "silber-1-tb" ist 1 TB und
# nicht 1 GB, und eine Zahl ohne ihre Einheit zu lesen waere derselbe
# Fehler wie ein Preis ohne seine Preisform.
_VARIANTE_RE = re.compile(r"^(?P<farbe>.+)-(?P<zahl>\d+)-(?P<einheit>gb|tb)$",
                          re.I)


def zustand(html: str) -> dict:
    """`window.__INITIAL_STATE__` als Objekt.

    Der Zustand ist in eine Zuweisung eingebettet und endet nicht am
    Zeilenende - er wird deshalb mit dem JSON-Dekoder gelesen, der das
    Ende selbst findet. Ein Regex bis zum naechsten `;` schnitte beim
    ersten Semikolon in einem Marketingtext ab.
    """
    treffer = _STATE_RE.search(html or "")
    if not treffer:
        raise GeraeteAbrufFehler(
            "Telekom-Kategorieseite ohne window.__INITIAL_STATE__ "
            f"({len(html or '')} Bytes) - Challenge oder neues Format")
    try:
        daten, _ = json.JSONDecoder().raw_decode(html, treffer.end())
    except (json.JSONDecodeError, ValueError) as exc:
        raise GeraeteAbrufFehler(
            f"Telekom-Zustandsobjekt unlesbar: {exc}") from exc
    if not isinstance(daten, dict):
        raise GeraeteAbrufFehler("Telekom-Zustandsobjekt ist kein Objekt")
    return daten


def _produktlinks(html: str, basis_url: str) -> list[str]:
    """Die Produktadressen, die die Seite als echte `<a href>` fuehrt."""
    suppe = BeautifulSoup(html or "", "html.parser")
    gefunden = []
    for anker in suppe.find_all("a", href=True):
        ziel = anker["href"]
        if "/shop/geraet/" in ziel:
            gefunden.append(urljoin(basis_url or "https://www.telekom.de", ziel))
    return gefunden


def _passende_adresse(eintrag: dict, links: list[str]) -> str:
    """Die verlinkte Adresse DIESES Geraets - oder nichts.

    Verglichen werden die drei Slugs, die der Eintrag selbst nennt. Damit
    ist die Zuordnung eine Pruefung und keine Konstruktion: passt keine
    der geernteten Adressen, bleibt das Feld leer und der Satz erbt die
    Kategorieseite.
    """
    teile = [str(eintrag.get(feld) or "").strip()
             for feld in ("brandSlug", "productSlug", "variantSlug")]
    if not all(teile):
        return ""
    for link in links:
        if all(f"/{teil}" in link for teil in teile):
            return link
    return ""


def _variante(slug: str) -> tuple[str, Optional[int]]:
    treffer = _VARIANTE_RE.match((slug or "").strip())
    if not treffer:
        return (slug or "").replace("-", " ").strip(), None
    farbe = treffer.group("farbe").replace("-", " ").strip()
    gb = int(treffer.group("zahl"))
    if treffer.group("einheit").lower() == "tb":
        gb *= 1024
    return farbe, gb


def _preisformen(preis: dict) -> list[dict]:
    """ALLE Ratenplaene, die die Rechenprobe bestehen - nicht nur der erste.

    `installments` ist eine LISTE: die Kategorieseite kann mehrere
    Ratenplaene (verschiedene Laufzeiten desselben Geraets) nebeneinander
    fuehren. Jeder Plan wird EINZELN geprueft und benannt verworfen, wenn
    er nicht aufgeht - ein einzelner kaputter Plan kostet nicht die
    uebrigen, dieselbe Disziplin wie beim Gesamtbetrag selbst.

    Gemessen an den beiden gespeicherten echten Abrufen (Kategorieseite
    vom 04.09.2026, Buendelseite MagentaMobil S vom 08.09.2026) traegt
    JEDER Eintrag genau einen 36-Monats-Plan - kein Beleg zeigt bislang
    mehrere Plaene nebeneinander (Modulkopf: der Verdacht auf eine
    Erfassungsluecke bleibt offen). Diese Funktion bleibt trotzdem
    defensiv: sie liest die ganze Liste, nicht nur `installments[0]`.
    """
    raten = preis.get("installments") or []
    if not isinstance(raten, list) or not raten:
        return []
    try:
        anzahlung = float(preis.get("upfrontPrice"))
    except (TypeError, ValueError):
        return []
    formen: list[dict] = []
    for plan in raten:
        if not isinstance(plan, dict):
            log.info("Telekom: Eintrag in installments ist kein Objekt "
                     "(%r) - uebergangen", plan)
            continue
        # `laufzeit_in_monaten` ist DIE EINE STELLE, die entscheidet, ob ein
        # Rohwert eine Ratenlaufzeit IST (Clean Code 1) - eine eigene
        # `int()`-Zeile schnitte 24,5 still auf 24 ab.
        laufzeit = laufzeit_in_monaten(plan.get("numberOfInstallments"))
        try:
            monatsrate = float(plan.get("recurringPrice"))
            gesamt = float(plan.get("totalPrice"))
        except (TypeError, ValueError):
            monatsrate = gesamt = None
        if laufzeit is None or monatsrate is None or gesamt is None:
            # BENANNT, nicht still: die Listung waehlt ihren Traeger aus
            # `formen` (siehe `_listungsplan`), ein lautlos verlorener Plan
            # verschoebe also Preis und Laufzeit der Listung.
            log.info("Telekom: Ratenplan ohne lesbare Bestandteile "
                     "(Raten %r, Rate %r, Gesamt %r) - uebergangen",
                     plan.get("numberOfInstallments"),
                     plan.get("recurringPrice"), plan.get("totalPrice"))
            continue
        if not probe_geht_auf(anzahlung, monatsrate, laufzeit, gesamt):
            log.info(
                "Telekom: Ratenplan ueber %r Monate ohne aufgehende "
                "Rechenprobe (Anzahlung %s, Rate %s, Gesamt %s) - "
                "verworfen", plan.get("numberOfInstallments"), anzahlung,
                plan.get("recurringPrice"), plan.get("totalPrice"))
            continue
        formen.append({"anzahlung": anzahlung, "monatsrate": monatsrate,
                       "laufzeit_monate": laufzeit, "gesamt": gesamt})
    return formen


# Die Regel aus dem Modulkopf ("EINE LISTUNG IST DAS GERAET") - EINMAL
# formuliert, damit Protokoll und Auswahl nicht auseinanderlaufen koennen.
# Sie sortiert nach dem GESAMTBETRAG, weil der Gesamtbetrag die Zahl ist,
# die diese Auswahl bestimmt (`preis_ohne_vertrag`); die Laufzeit ist nur
# der Gleichstandsbrecher. Bis P0-B-h5 stand es umgekehrt - siehe
# Modulkopf "DIE REGEL IST EINE WAHL".
_LISTUNGSPLAN_REGEL = ("hoechster Gesamtbetrag, bei Gleichstand laengste "
                       "Ratenlaufzeit")


def _plan_text(form: dict) -> str:
    """Ein Ratenplan mit ALLEN gemessenen Betraegen, fuer das Protokoll.

    Ohne die Betraege ist ein uebergangener Plan im Protokoll nur eine
    Laufzeit: die Messung selbst waere verloren, und der erste echte
    Mehrplan-Fall liesse sich aus dem Log nicht nachrechnen. Mit ihnen
    steht die Rechenprobe (`anzahlung + n x rate = gesamt`) in der Zeile.
    """
    return (f"{form['laufzeit_monate']} Monate: "
            f"{form['anzahlung']:.2f} + {form['laufzeit_monate']} x "
            f"{form['monatsrate']:.2f} = {form['gesamt']:.2f} EUR")


def _listungsplan(formen: list[dict], name: str) -> dict:
    """Welcher Ratenplan die LISTUNG dieses Geraets traegt.

    Eine Listung ist das Geraet bei einem Anbieter (`listung_id` =
    Anbieter + SKU, ohne Laufzeit); mehrere Plaene ergeben deshalb nicht
    mehrere Listungen, sondern eine mit einer benannten Auswahl - siehe
    Modulkopf fuer die Begruendung und dafuer, dass die Regel eine WAHL
    ist und keine Messung. `max()` statt "der erste in der Liste": die
    Reihenfolge der Nutzlast entscheidet nichts.

    Die uebergangenen Plaene werden mit ihren BETRAEGEN genannt, und das
    Protokoll sagt ausdruecklich, dass sie nirgends erfasst sind - eine
    Listung kann nur eine Preisform tragen (Modulkopf: "wo sie nicht
    reicht"). Das Protokoll ist dabei NICHT die Seite: dass ein Plan
    fehlt, steht heute nur im Log (Modulkopf, offene Luecke zu Regel 9).
    """
    traeger = max(formen, key=lambda f: (f["gesamt"], f["laufzeit_monate"]))
    # `is not`, nicht `!=`: zwei Plaene mit gleichen Betraegen sind zwei
    # Plaene. Ein Vergleich auf Gleichheit schluckte den zweiten aus dem
    # Protokoll - genau das Verschwinden, das diese Zeile verhindern soll.
    uebergangen = [f for f in formen if f is not traeger]
    if uebergangen:
        log.info(
            "Telekom: %r nennt %d Ratenplaene - die LISTUNG traegt %s "
            "(Regel: %s, eine WAHL und keine Messung); NICHT erfasst, "
            "auch nicht im Buendelpfad: %s",
            name, len(formen), _plan_text(traeger), _LISTUNGSPLAN_REGEL,
            "; ".join(_plan_text(f) for f in uebergangen))
    return traeger


def lies(text: str, url: str = "") -> list[dict]:
    """Die Kategorieseite in Rohsaetze zerlegen. Sie IST die Nutzlast."""
    daten = zustand(text)
    eintraege = ((daten.get("productList") or {}).get("data") or [])
    if not isinstance(eintraege, list):
        raise GeraeteAbrufFehler("Telekom-Nutzlast: productList.data ist "
                                 "keine Liste")
    links = _produktlinks(text, url)

    out: list[dict] = []
    for eintrag in eintraege:
        if not isinstance(eintrag, dict):
            continue
        name = str(eintrag.get("name") or eintrag.get("productName")
                   or "").strip()
        if not name:
            continue
        formen = _preisformen(eintrag.get("price") or {})
        if not formen:
            # Kein Etikett heisst hier: kein Satz. Anders als bei o2, wo
            # eine unetikettierte Zahl immer noch ein `totalPrice` ist,
            # gibt es bei der Telekom NUR den Ratengesamtbetrag - ohne
            # seine Bestandteile waere er ein Barpreis, der er nicht ist.
            log.info("Telekom: %r ohne nachrechenbare Ratenform - verworfen",
                     name)
            continue
        farbe, speicher = _variante(str(eintrag.get("variantSlug") or ""))
        titel = " ".join(x for x in (name,
                                     f"{speicher} GB" if speicher else "",
                                     farbe) if x)
        adresse = _passende_adresse(eintrag, links)
        sku = str(eintrag.get("id") or "").strip()
        # EIN Geraet, EINE Listung - und der Plan, der sie traegt, wird
        # benannt ausgewaehlt statt von der Reihenfolge bestimmt (siehe
        # `_listungsplan` und Modulkopf). Ein eigener Satz je Plan
        # kollidierte in `GeraeteDB.upsert` unter derselben `listung_id`.
        form = _listungsplan(formen, name)
        out.append({
            "titel": titel,
            # Der strukturierte NAME (Feld `name`), unveraendert - die
            # einzige Grundlage der E4-Auto-Erkennung. Der TITEL darueber
            # ist zusammengesetzt (Name + Speicher + Farbe) und wuerde
            # als Namensquelle Saegezahn-IDs erzeugen ("iPhone 18 Pro
            # polar").
            "strukturierter_name": name,
            "preis": form["gesamt"],
            "anzahlung": form["anzahlung"],
            "monatsrate": form["monatsrate"],
            "laufzeit_monate": form["laufzeit_monate"],
            # Die Seite nennt keinen Zinssatz. `None` heisst unbekannt.
            "zins_effektiv": None,
            "waehrung": "EUR",
            "verfuegbarkeit": ("lieferbar"
                               if str(eintrag.get("availabilityStatus")
                                      or "").upper() == "IN_STOCK"
                               else "unbekannt"),
            "sku": sku,
            "ean": "",
            "farbe": farbe,
            "speicher_gb": speicher,
            "url": adresse,
            "quelle": "telekom_kategorie",
        })
    return out


# --------------------------------------------------------------------------
# DER BUENDELKATALOG - dieselbe Seite mit tariffId-Parameter (B2, siehe
# Modulkopf)
# --------------------------------------------------------------------------

def _gleich(a: Optional[float], b: Optional[float]) -> bool:
    """Ein Cent ist kein Rundungsfehler - dieselbe Toleranz wie bei o2
    und Vodafone."""
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) < 0.005


def _preis(wert) -> Optional[float]:
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def _selected_plan(product_list: dict) -> dict:
    """`selectedPlan` mit ID und Name - oder GeraeteAbrufFehler.

    Eine Antwort ohne gewaehlten Tarif (die ohne-vertrag-Seite traegt
    `null`) ist keine Buendelantwort. Ein leeres Ergebnis waere dafuer die
    falsche Meldung - dieselbe Unterscheidung wie bei o2s
    HW_ONLY-Zustandscheck.
    """
    plan = product_list.get("selectedPlan")
    if not isinstance(plan, dict):
        raise GeraeteAbrufFehler(
            "Telekom-Kategorieseite ohne productList.selectedPlan - keine "
            "Buendelantwort (tariffId-Parameter fehlt?)")
    if not str(plan.get("id") or "").strip() or \
            not str(plan.get("name") or "").strip():
        raise GeraeteAbrufFehler(
            "Telekom-selectedPlan ohne id oder name - kein Tarifname, "
            "keine Buendelaussage")
    return plan


def _plan_preise(plan: dict) -> tuple[Optional[float], Optional[float]]:
    """(Anschlusspreis, Tarif-Monatsgebuehr) aus den typisierten Preisen
    des selectedPlan - jeder ueber seinen `priceType`, nicht ueber die
    Reihenfolge in der Liste."""
    anschluss: Optional[float] = None
    monatlich: Optional[float] = None
    for p in (plan.get("prices") or []):
        if not isinstance(p, dict):
            continue
        wert = _preis(p.get("actualValue"))
        if wert is None:
            continue
        if p.get("priceType") == "activationFee":
            anschluss = wert
        elif p.get("priceType") == "recurringFee":
            monatlich = wert
    return anschluss, monatlich


# `proben` ist die Schnittstelle der Provider-Probe (FM-2, P5 - siehe
# Adapter-Docstring in collect/geraete/__init__.py); dieser Adapter
# traegt keine Feld-Proben hinein.
def lies_buendel(text: str, url: str = "",
                 proben: Optional[dict] = None) -> list[dict]:
    """Die Kategorieseite MIT Tariffilter in Buendel-Rohsaetze zerlegen.

    Sie IST die Nutzlast (`kind: buendel`-Einstieg, kein `ernte`, keine
    Produktseite wird nachgeladen). Der Tarifname kommt aus demselben
    Zustandsobjekt wie die Geraetepreise - `selectedPlan.name` - und wird
    nicht aus einer zweiten Quelle erraten.
    """
    daten = zustand(text)
    product_list = daten.get("productList") or {}
    eintraege = product_list.get("data")
    if not isinstance(eintraege, list):
        raise GeraeteAbrufFehler("Telekom-Nutzlast: productList.data ist "
                                 "keine Liste")
    plan = _selected_plan(product_list)
    tarif_id = str(plan.get("id") or "").strip()
    tarif_name = str(plan.get("name") or "").strip()
    anschluss, tarif_monatlich = _plan_preise(plan)
    if tarif_monatlich is None:
        # Ohne Tarif-Monatsgebuehr ist kein Buendel benennbar - der Satz
        # waere eine Zuzahlung ohne die Gegenleistung, die sie erkauft.
        raise GeraeteAbrufFehler(
            f"Telekom-selectedPlan {tarif_name!r} ohne recurringFee - "
            "keine Buendelaussage")

    links = _produktlinks(text, url)
    out: list[dict] = []
    for eintrag in eintraege:
        if not isinstance(eintrag, dict):
            continue
        name = str(eintrag.get("name") or "").strip()
        if not name:
            continue                      # Werbekachel, siehe Modulkopf

        formen = _preisformen(eintrag.get("price") or {})
        if not formen:
            log.info("Telekom-Buendel: %r ohne nachrechenbare Ratenform - "
                     "verworfen", name)
            continue

        # Die zwei Proben aus dem Modulkopf: der je-Geraet-Tarifpreis muss
        # zum selectedPlan gehoeren (ID) und ihm entsprechen (Betrag).
        geraet_tarif = (((eintrag.get("formattedPrices") or {})
                         .get("recurringTariffPrice") or {}).get("price")
                        or {})
        geraet_tarif_id = str(geraet_tarif.get("id") or "").strip()
        if not geraet_tarif_id.startswith(f"{tarif_id}-"):
            log.info("Telekom-Buendel: %r nennt Tarifpreis %r statt "
                     "selectedPlan %r - verworfen", name, geraet_tarif_id,
                     tarif_id)
            continue
        if not _gleich(_preis(geraet_tarif.get("actualValue")),
                       tarif_monatlich):
            log.info("Telekom-Buendel: %r widerspricht dem selectedPlan-"
                     "Tarifpreis - verworfen", name)
            continue

        farbe, speicher = _variante(str(eintrag.get("variantSlug") or ""))
        titel = " ".join(x for x in (name,
                                     f"{speicher} GB" if speicher else "",
                                     farbe) if x)
        adresse = _passende_adresse(eintrag, links)
        sku = str(eintrag.get("id") or "").strip()
        # JEDER Ratenplan wird ein EIGENES Buendel mit eigener
        # `laufzeit_monate` - `tco_model.buendel_id()` traegt die Laufzeit
        # im Schluessel, die Zahlweisen ueberschreiben sich also nicht mehr
        # gegenseitig (B1).
        for form in formen:
            out.append({
                "titel": titel,
                "strukturierter_name": name,
                "farbe": farbe,
                "speicher_gb": speicher,
                "sku": sku,
                "tarif_name": tarif_name,
                # Die MF-ID des Tarifs - die Ordnung des Anbieters, siehe
                # Modulkopf ("WAS DER SLUG HIER IST").
                "tarif_slug": tarif_id,
                "tarif_monatlich": tarif_monatlich,
                "geraet_zuzahlung": form["anzahlung"],
                "geraet_monatsrate": form["monatsrate"],
                "anschlusspreis": anschluss,
                "laufzeit_monate": form["laufzeit_monate"],
                "url": adresse,
                "quelle": "telekom_buendel",
            })
    return out
