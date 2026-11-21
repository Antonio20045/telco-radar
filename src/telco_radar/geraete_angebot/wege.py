"""Die Wege der Angebotszählung je Anbieter: Übersicht bis zum Ende, Modellseite.

Jeder Weg bedient eine ``Sitzung`` und gibt die Leser (``lesen``/``lesen_seiten``)
den gesehenen Zuständen. Was ein Weg nicht gesehen hat, steht nicht im Ergebnis; was
er annimmt, steht in ``Seite.annahmen`` (z. B. „Tarife einmal je Gerät gelesen“).
Am 21.11.2026 an je einer Seite je Anbieter im Browser erprobt (ein Abruf der
Übersicht, bis zu drei Modellseiten); gemessene Zeiten stehen in der Vorlage
``angebot.yml``.
"""

from __future__ import annotations

import re

from . import Kachel, Option, Seite
from . import lesen as L
from . import lesen_seiten as LS
from .sitzung import Sitzung

ANNAHME_TARIFE_EINMAL = "Tarife einmal je Gerät gelesen (vorgewählter Speicher)"
ANNAHME_RATEN_JE_TARIF = "Raten je Tarif auf dem vorgewählten Speicher gelesen"
ANNAHME_TW_LAUFZEIT = "Tarifwelt: Gerät einmalig bezahlt, Vertragslaufzeit 24 Monate"


NACHLADEN = r"^(mehr|weitere)\b.*\b(anzeigen|laden)$"
"""Ein Knopf, der weitere Kacheln nachlädt („Weitere Geräte anzeigen“)."""
HOECHSTENS_NACHLADEN = 30


def _nachladen(s: Sitzung, muster: str, warte_ms: int) -> str | None:
    """Klickt „mehr anzeigen“, bis der Knopf fehlt; Beleg nur, wenn er am Ende fehlt."""
    for n in range(HOECHSTENS_NACHLADEN):
        if not s.klicke_text(muster):
            return f"Nachladen bis zum Ende ({n}-mal), danach kein Knopf mehr"
        s.page.wait_for_timeout(warte_ms)
    return None


def _ohne_knopf(s: Sitzung) -> str | None:
    s.scrolle_bis_stabil("a[href]", runden=4)
    if s.hat_text(NACHLADEN):
        return None
    return "Seite ohne Nachlade-Knopf, ganz gescrollt"


Uebersicht = tuple[list[Kachel], int | None, str | None]


def uebersicht(schluessel: str, s: Sitzung, url: str) -> Uebersicht:
    """Die Kacheln der Übersicht, die vom Anbieter genannte Zahl und der Beleg, dass
    bis zum Ende gelesen wurde (``None``, wenn es keinen gibt)."""
    s.oeffne(url)
    if schluessel == "telekom":
        ende = _nachladen(s, r"^weitere geräte anzeigen$", 3000)
        return L.telekom_kacheln(s.html("uebersicht")), None, ende
    if schluessel == "vodafone":
        ende = _nachladen(s, r"^mehr smartphones anzeigen$", 2500)
        genannt = L.genannte_zahl(s.text(), r"(\d+) Smartphones sortiert")
        return L.vodafone_kacheln(s.html("uebersicht")), genannt, ende
    if schluessel == "o2":
        return _o2_uebersicht(s)
    if schluessel == "1und1":
        ende = _ohne_knopf(s)
        return L.einsundeins_kacheln(s.html("uebersicht")), None, ende
    if schluessel == "congstar":
        ende = _ohne_knopf(s)
        return L.congstar_kacheln(s.html("uebersicht")), None, ende
    ende = _ohne_knopf(s)
    genannt = L.genannte_zahl(s.text(), r"Alle Smartphones\s*\((\d+)\)")
    return L.tarifwelt_kacheln(s.html("uebersicht")), genannt, ende


def _o2_uebersicht(s: Sitzung) -> Uebersicht:
    """Der Shop lädt unter „Alle“ höchstens 36 Kacheln nach; je Herstellerfilter
    lädt er alle. Gezählt wird je Hersteller bis zum Ende, verglichen mit der Zahl,
    die der Filter nennt („Apple (33)“); Beleg nur, wenn jede Zahl erreicht ist."""
    filter_ = s.page.locator("label.filter-item-label")
    texte = [filter_.nth(i).inner_text() for i in range(filter_.count())]
    genannt = next(
        (int(m.group(1)) for t in texte if (m := re.match(r"Alle \((\d+)\)", t))), None
    )
    kacheln: dict[str, Kachel] = {}
    abweichend = []
    for i, text in enumerate(texte):
        if text.startswith("Alle"):
            continue
        filter_.nth(i).click()
        s.page.wait_for_timeout(3000)
        s.scrolle_bis_stabil("div.hardware-item")
        gelesen = L.o2_kacheln(s.html(f"uebersicht-{text}"))
        zahl = L.genannte_zahl(text, r"\((\d+)\)")
        if zahl != len(gelesen):
            abweichend.append(f"{text}: {len(gelesen)} gelesen")
        for k in gelesen:
            kacheln.setdefault(k.url, k)
    ende = None
    if texte and not abweichend:
        ende = "je Herstellerfilter so viele Kacheln wie genannt"
    return list(kacheln.values()), genannt, ende


def o2_tarifuebersicht(s: Sitzung) -> list[Option]:
    """Die Tarifübersicht einmal je Lauf: Tarife mit „Handy hinzufügen“."""
    s.oeffne(LS.O2_TARIFUEBERSICHT)
    return LS.o2_tarifuebersicht(s.html("tarifuebersicht"))


NICHT_GEWAEHLT = "Option „{option}“ ließ sich nicht wählen, nicht gelesen"


def _nicht_gewaehlt(seite: Seite, option: str) -> None:
    """Eine wählbare Option ließ sich nicht wählen: die Auswahl dieses Geräts ist
    nur teilweise gelesen (``Seite.unvollstaendig``), nie still übergangen."""
    seite.unvollstaendig.append(NICHT_GEWAEHLT.format(option=option))


def _setze(seite: Seite, geraet: dict) -> None:
    seite.speicher = geraet["speicher"]
    seite.laufzeiten = geraet.get("laufzeiten", [])
    seite.ausserhalb = geraet.get("ausserhalb", [])
    farben = geraet.get("farben") or []
    seite.farben = len(farben) if farben else None
    seite.farben_nicht_waehlbar = (
        sum(1 for f in farben if not f.waehlbar) if farben else None
    )


def _kreuz(
    speicher: list[Option], tarife: list[str], laufzeiten: list[Option]
) -> list[list]:
    return [
        [sp.text, t, int(lz.wert)]
        for sp in speicher
        if sp.waehlbar
        for t in tarife
        for lz in laufzeiten
        if lz.waehlbar
    ]


def telekom(s: Sitzung, seite: Seite) -> None:
    """Je Tarif des Dialogs „Tarif ändern“ die Speicher und Raten der Seite; der
    vorgewählte Tarif gilt mit dem ersten Zustand der Seite."""
    s.oeffne(seite.url)
    erster = LS.telekom_geraet(s.html("geraet"))
    _setze(seite, erster)
    s.klicke_text(r"^tarif ändern$")
    s.page.wait_for_timeout(3000)
    dialog = s.html("tarife")
    tarife = LS.telekom_tarife(dialog)
    gewaehlt = LS.telekom_gewaehlt(dialog)
    seite.tarife = tarife
    kombis: list[list] = []
    for tarif in tarife:
        if not tarif.waehlbar:
            continue
        if tarif.wert == gewaehlt:
            stand = erster
        else:
            if not s.page.locator(f"#service-{tarif.wert}").count():
                s.klicke_text(r"^tarif ändern$")
                s.page.wait_for_timeout(3000)
            gewaehlt_ok = s.klicke(
                f"label[for='service-{tarif.wert}'], #service-{tarif.wert}", 500
            )
            if not (gewaehlt_ok and s.klicke_text(r"^tarif auswählen$")):
                _nicht_gewaehlt(seite, tarif.text)
                continue
            s.page.wait_for_timeout(3500)
            stand = LS.telekom_geraet(s.html(f"tarif-{tarif.text}"))
        if not stand["laufzeiten"]:
            seite.annahmen.append(f"{tarif.text}: nur Einmalpreis sichtbar")
        kombis += _kreuz(stand["speicher"], [tarif.text], stand["laufzeiten"])
    seite.kombinationen = kombis
    seite.annahmen.append(ANNAHME_RATEN_JE_TARIF)


def vodafone(s: Sitzung, seite: Seite) -> None:
    """Speicher × Raten auf der Produktseite (Raten je Speicher); Tarife direkt auf
    der Seite oder nach „Zur Tarifauswahl“ je Kachel angeklickt (Name aus der
    Angebotsübersicht). Was die Seite ausschließt („XS und S nicht in 36 Raten“),
    fällt aus den Kombinationen."""
    s.oeffne(seite.url)
    erste = s.html("geraet")
    geraet = L.vodafone_geraet(erste)
    _setze(seite, geraet)
    raten_je = {geraet["speicher"][0].wert: geraet["laufzeiten"]}
    for sp in geraet["speicher"][1:]:
        if not sp.waehlbar:
            continue
        if not s.waehle_radio("capacity|speicher|storage", sp.wert):
            _nicht_gewaehlt(seite, sp.text)
            continue
        raten_je[sp.wert] = L.vodafone_geraet(s.html(f"speicher-{sp.text}"))[
            "laufzeiten"
        ]
    namen = [o.text for o in L.vodafone_tarife_inline(erste) if o.waehlbar]
    ausschluss = set(L.vodafone_ausschluesse(erste))
    if not namen:
        if not s.navigiere_per_klick(r"^zur tarifauswahl$"):
            raise L.LeserFehler("Vodafone: weder Tarifwahl noch „Zur Tarifauswahl“")
        auswahl = s.html("tarifauswahl")
        ausschluss |= set(L.vodafone_ausschluesse(auswahl))
        for o in L.vodafone_tarifoptionen(auswahl):
            if not o.waehlbar:
                continue
            if not s.waehle_radio("tariff", o.wert, 2500):
                _nicht_gewaehlt(seite, o.text)
                continue
            namen.append(L.vodafone_tarifname(s.html(f"tarif-{o.wert}")))
        seite.annahmen.append(ANNAHME_TARIFE_EINMAL)
    seite.tarife = [Option(n, n) for n in namen]
    kurz = {n: m.group(0) for n in namen if (m := L._VF_NAME.search(n))}
    seite.kombinationen = [
        k
        for sp in geraet["speicher"]
        if sp.wert in raten_je
        for k in _kreuz([sp], namen, raten_je[sp.wert])
        if (kurz.get(k[1], ""), k[2]) not in ausschluss
    ]
    seite.ausgeschlossen = [[t, n] for t, n in sorted(ausschluss)]


def o2(s: Sitzung, seite: Seite) -> None:
    """Tarifkacheln und Zahlungsplan je Speicher (der Speicherwechsel lädt neu)."""
    s.oeffne(seite.url)
    geraet = LS.o2_geraet(s.html("geraet"))
    _setze(seite, geraet)
    seite.tarife = geraet["tarife"]
    kombis = _kreuz(
        geraet["speicher"][:1],
        [t.text for t in geraet["tarife"] if t.waehlbar],
        geraet["laufzeiten"],
    )
    for sp in geraet["speicher"][1:]:
        if not sp.waehlbar:
            continue
        s.tor.passiere(seite.url)
        if not s.waehle_radio("^storage$", sp.wert, 4000):
            _nicht_gewaehlt(seite, sp.text)
            continue
        stand = LS.o2_geraet(s.html(f"speicher-{sp.text}"))
        kombis += _kreuz(
            [sp], [t.text for t in stand["tarife"] if t.waehlbar], stand["laufzeiten"]
        )
    seite.kombinationen = kombis


def einsundeins(s: Sitzung, seite: Seite) -> None:
    """Speicher und „24/36 Monate Fix“ der Produktseite, Tarife der Tarifauswahl."""
    s.oeffne(seite.url)
    _setze(seite, LS.einsundeins_geraet(s.html("geraet")))
    if not s.navigiere_per_klick(r"^weiter zur tarifauswahl$"):
        raise L.LeserFehler("1&1: kein Knopf „Weiter zur Tarifauswahl“")
    seite.tarife = LS.einsundeins_tarife(s.html("tarifauswahl"))
    seite.annahmen.append(ANNAHME_TARIFE_EINMAL)


def congstar(s: Sitzung, seite: Seite) -> None:
    """Je Tarifkachel und Bindung („Ohne Laufzeit“ = Tarif „… Flex“) der Name aus
    „Tarifdetails: …“; Speicher und Zahlungen der Produktseite."""
    s.oeffne(seite.url)
    geraet = LS.congstar_geraet(s.html("geraet"))
    _setze(seite, geraet)
    namen = []
    bindungen = [b for b in geraet["bindung"] if b.waehlbar] or [None]
    for kachel in geraet["tarifkacheln"]:
        if not kachel.waehlbar:
            continue
        if not s.waehle_radio(".", kachel.wert, 1500):
            _nicht_gewaehlt(seite, kachel.text)
            continue
        for b in bindungen:
            if b is not None and not s.klicke_text("^" + re.escape(b.text) + "$"):
                _nicht_gewaehlt(seite, f"{kachel.text}, {b.text}")
                continue
            if b is not None:
                s.page.wait_for_timeout(1500)
            namen.append(LS.congstar_tarifname(s.html(f"tarif-{kachel.wert}")))
        if bindungen[0] is not None:
            s.klicke_text("^" + re.escape(bindungen[0].text) + "$")
    seite.tarife = [Option(n, n) for n in dict.fromkeys(namen)]
    seite.annahmen.append(ANNAHME_TARIFE_EINMAL)


def tarifwelt(s: Sitzung, seite: Seite) -> None:
    """Je wählbarem Speicher der Dialog „Tarif ändern“, je Netzfilter die Tarife;
    die genannte Zahl je Netz ist die Gegenprobe der gelesenen Namen."""
    s.oeffne(seite.url)
    geraet = LS.tarifwelt_geraet(s.html("geraet"))
    _setze(seite, geraet)
    kombis: list[list] = []
    for i, sp in enumerate(geraet["speicher"]):
        if not sp.waehlbar:
            continue
        if i and not s.klicke(f"button[role=radio][value='{sp.wert}']", 3500):
            _nicht_gewaehlt(seite, sp.text)
            continue
        kombis += _tarifwelt_dialog(s, seite, sp.text)
        s.page.keyboard.press("Escape")
        s.page.wait_for_timeout(800)
    seite.kombinationen = kombis
    seite.annahmen.append(ANNAHME_TW_LAUFZEIT)


def _tarifwelt_dialog(s: Sitzung, seite: Seite, speicher: str) -> list[list]:
    from . import NETZ_ALIAS

    s.klicke_text(r"^tarif ändern$")
    s.page.wait_for_timeout(3500)
    zahlen = LS.tarifwelt_netzzahlen(s.html(f"dialog-{speicher}"))
    kombis = []
    for netz, zahl in zahlen.items():
        if not zahl:
            continue
        label = f"label[for='form-rhf-checkbox-carrier_{netz}']"
        if not s.klicke(label, 2300):
            _nicht_gewaehlt(seite, f"{speicher}, Netz {netz}")
            continue
        weitere, gewaehlt = LS.tarifwelt_tarifnamen(s.html(f"netz-{netz}-{speicher}"))
        karten = weitere + ([gewaehlt] if gewaehlt and zahl == len(weitere) + 1 else [])
        if len(karten) != zahl:
            seite.unvollstaendig.append(
                f"{speicher}, Netz {netz}: Seite nennt {zahl} Tarife, "
                f"gelesen {len(karten)}"
            )
        ziel = NETZ_ALIAS.get(netz, netz)
        kombis += [[speicher, n, 24, ziel, code] for n, code in karten]
        s.klicke(label, 1200)
    return kombis


SEITEN = {
    "telekom": telekom,
    "vodafone": vodafone,
    "o2": o2,
    "1und1": einsundeins,
    "congstar": congstar,
    "tarifwelt": tarifwelt,
}
