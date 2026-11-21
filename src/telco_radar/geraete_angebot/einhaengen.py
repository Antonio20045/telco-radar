"""Die Angebotszählung des Messtags in die Lauf-Datei hängen (vor dem Wächter).

Der Gerätelauf (``geraete_nachtlauf.schliesse_ab``) ruft ``haenge_ein`` nach
``geraete_vollstaendigkeit.baue``. Je Anbieterzeile wird aus der Datei
``data/state/angebot/<messtag>-<schluessel>.json`` das unabhängige Soll gesetzt:

* **Modelle** (``art`` „browser_uebersicht“): jede Smartphone-Kachel der Übersicht.
  Schlüssel ist die Katalog-ID (``erkenne_geraet`` auf den Kacheltitel, der Titel dient
  nur zum Finden), ohne Katalogtreffer die normalisierte Adresse. Ein Modell, das nur
  als Paket („… mit AirPods“) vorkommt, trägt ``nur_paket``. Saturn/MediaMarkt: je Netz
  die Modelle, deren Seite in diesem Netz mindestens einen Tarif zeigt.
* **Modell × Speicher**: die wählbaren Speicher jeder gezählten Seite (``256gb``).
* **Kombinationen** (``art`` „browser_auswahl“): Modell × Speicher × Tarif × Laufzeit
  über ``SichtbareAuswahl``/``haenge_kombinationen_ein``; Tarife als ``grundtarif``,
  gleichnamige Tarife durchgezählt (``geraete_tarifschluessel``).

Zuordnung Soll↔Ist: gleiche Katalog-ID, gleiches Speichersegment, gleicher
Grundtarif, gleiche Ratenzahl. Eine Seite, die nicht gezählt wurde, steht in
``angebot.nicht_gezaehlt`` mit Grund; ihr Ist fällt aus dem Vergleich.

Gründe einer Lücke nur aus Signalen: Ausfallvermerk des Anbieters, Vermerk zum Modell
(``TcoDB.erfassung``) wenn Modell oder Speicher im Ist ganz fehlen, Katalog, Paket,
Tarifwelt-Stufe; sonst ``UNBENANNT`` (Wächter rot). Fehlt die Zählung des Messtags
oder ist sie gescheitert, steht ``ANGEBOT_FEHLT`` mit Grund da, nie das Ist als Soll.
"""

from __future__ import annotations

from pathlib import Path

from .. import geraete_angebot as ga
from ..geraete_model import erkenne_geraet
from ..geraete_tarifschluessel import (
    NUMMER,
    PREIS,
    grundtarif,
    mit_preis,
    ohne_variante,
)
from ..geraete_vollstaendigkeit import (
    Ist,
    SichtbareAuswahl,
    _ebene,
    _luecke,
    _modell_ebene,
    haenge_kombinationen_ein,
    ist_zaehlung,
    modell_der_kombination,
)
from ..models import normalize_url
from . import kaufwege
from .gruende import ZeilenSoll, grund_der_luecke, grund_ohne_angebot
from .lesen import ist_smartphone, speicher_segment

ANGEBOT_FEHLT = "Angebot heute nicht gezählt"
ART_UEBERSICHT = "browser_uebersicht"
ART_AUSWAHL = "browser_auswahl"
LISTE_HOECHSTENS = 200


def modell_von(titel: str, url: str, katalog) -> tuple[str, str, bool]:
    """(Schlüssel, Name, im Katalog) einer Kachel oder Seite."""
    geraet = erkenne_geraet(titel, katalog)
    if geraet is not None:
        return geraet.device_id, titel.split(" mit ")[0], True
    return normalize_url(url), titel, False


def _modell(soll: ZeilenSoll, titel: str, url: str, paket: bool, katalog) -> str:
    schluessel, name, im_katalog = modell_von(titel, url, katalog)
    alt = soll.modelle.get(schluessel)
    if alt is None:
        soll.modelle[schluessel] = {
            "schluessel": schluessel,
            "name": name,
            "url": url,
            "im_katalog": im_katalog,
            "nur_paket": paket,
        }
    elif alt["nur_paket"] and not paket:
        alt.update(nur_paket=False, url=url, name=name)
    return schluessel


def _nummeriere(
    eintraege: list[tuple[str, str, int]],
) -> tuple[tuple[str, str, int], ...]:
    zahl: dict[tuple[str, str, int], int] = {}
    ergebnis = []
    for seg, tarif, n in eintraege:
        zahl[(seg, tarif, n)] = zahl.get((seg, tarif, n), 0) + 1
        k = zahl[(seg, tarif, n)]
        ergebnis.append((seg, tarif if k == 1 else f"{tarif}~{k}", n))
    return tuple(ergebnis)


def _preis(k: list) -> str:
    return str(k[4]) if len(k) > 4 and k[4] else ""


def _auswahl(zeile: str, modell: str, seite: ga.Seite, z: ga.Zaehlung, netz=None):
    speicher = tuple(
        dict.fromkeys(
            s for o in seite.speicher if o.waehlbar and (s := speicher_segment(o.text))
        )
    )
    kombis = None
    if seite.kombinationen is not None:
        kombis = _nummeriere(
            [
                (seg, mit_preis(grundtarif(str(k[1])), _preis(k)), int(k[2]))
                for k in seite.kombinationen
                if (netz is None or (len(k) > 3 and k[3] == netz))
                and (seg := speicher_segment(str(k[0])))
            ]
        )
        speicher = tuple(dict.fromkeys(k[0] for k in kombis))
    return SichtbareAuswahl(
        anbieter=zeile,
        modell=modell,
        seite=seite.url,
        speicher=speicher,
        tarife=tuple(
            dict.fromkeys(grundtarif(o.text) for o in seite.tarife if o.waehlbar)
        ),
        laufzeiten=tuple(
            dict.fromkeys(int(o.wert) for o in seite.laufzeiten if o.waehlbar)
        ),
        gezaehlt_um=z.gezaehlt_bis or z.gezaehlt_von,
        kombinationen=kombis,
    )


def soll_aus(z: ga.Zaehlung, katalog) -> dict[str, ZeilenSoll]:
    """Das Soll je Anbieterzeile aus einer Zählung."""
    anbieter = ga.ANBIETER[z.schluessel]
    netze = {} if z.schluessel != "tarifwelt" else ga.SATURN_NETZE
    je = {name: ZeilenSoll() for name in anbieter.anbieterzeilen()}
    for k in z.kacheln:
        if not ist_smartphone(k.titel):
            continue
        if not netze:
            _modell(je[anbieter.name], k.titel, k.url, k.paket, katalog)
        for soll in je.values():
            soll.kachelmodelle.add(modell_von(k.titel, k.url, katalog)[0])
    for seite in z.seiten:
        if not ist_smartphone(seite.titel):
            continue
        ziele: list[tuple[str | None, ZeilenSoll]] = [
            (n, je[zeile]) for n, zeile in netze.items()
        ] or [(None, je[anbieter.name])]
        for netz, soll in ziele:
            schluessel = modell_von(seite.titel, seite.url, katalog)[0]
            if seite.status != ga.GELESEN:
                soll.nicht_gezaehlt.append(
                    {
                        "schluessel": schluessel,
                        "name": seite.titel,
                        "url": seite.url,
                        "grund": seite.grund or seite.status,
                    }
                )
                continue
            auswahl = _auswahl(
                anbieter.name if netz is None else netze[netz],
                schluessel,
                seite,
                z,
                netz,
            )
            if netz is not None and not auswahl.schluessel():
                continue
            _modell(soll, seite.titel, seite.url, False, katalog)
            soll.auswahlen.append(auswahl)
            namen = [o.text for o in seite.tarife] + [
                str(k[1]) for k in seite.kombinationen or ()
            ]
            soll.tarifnamen.update({grundtarif(n): n for n in namen})
            soll.speicher |= {f"{schluessel}-{s}" for s in auswahl.speicher}
            for tarif, monate in seite.ausgeschlossen:
                soll.ausgeschlossen[(schluessel, grundtarif(tarif), int(monate))] = (
                    tarif
                )
            soll.unvollstaendig += [f"{seite.titel}: {u}" for u in seite.unvollstaendig]
    return je


def _speicher_ebene(soll: ZeilenSoll, ist: Ist, grund) -> dict:
    ist_ms = {
        m
        for m in ist.modell_speicher
        if m in soll.speicher or m.rsplit("-", 1)[0] in soll.modelle
    }
    ebene = _ebene(len(soll.speicher), None, len(ist_ms))
    fehlend = sorted(soll.speicher - ist.modell_speicher)
    extra = sorted(ist_ms - soll.speicher)
    ebene.update(
        erfasst=len(soll.speicher & ist.modell_speicher),
        luecken=[_luecke(k, k, "", grund(k + "--")) for k in fehlend][
            :LISTE_HOECHSTENS
        ],
        luecken_zahl=len(fehlend),
        nicht_im_soll=[{"schluessel": k, "name": k} for k in extra][:LISTE_HOECHSTENS],
        nicht_im_soll_zahl=len(extra),
    )
    return ebene


def _euro(betrag: str) -> str:
    return betrag.replace(".", ",")


def lesbar(schluessel: str, soll: ZeilenSoll) -> tuple[str, str]:
    """(Name, Adresse) einer Lücke: „Samsung Galaxy S26 · 512 GB · Mobil XS · 24
    Monate“ statt des Schlüssels; Adresse ist die Modellseite."""
    teile = schluessel.split("--")
    modell = modell_der_kombination(schluessel)
    info = soll.modelle.get(modell or "") or {}
    ms = teile[0]
    speicher = ms[len(modell) + 1 :] if modell else ""
    gb = speicher.removesuffix("gb")
    stuecke = [info.get("name") or soll.namen.get(modell or "") or ms]
    if gb.isdigit():
        stuecke.append(f"{int(gb) // 1024} TB" if int(gb) >= 1024 else f"{gb} GB")
    if len(teile) > 2 and teile[1]:
        rest, _, nummer = teile[1].partition(NUMMER)
        tarif, _, preis = rest.partition(PREIS)
        name = soll.tarifnamen.get(tarif, tarif)
        if preis:
            geraet, _, monat = preis.partition("-")
            name += f" ({_euro(geraet)} € + {_euro(monat)} €/Monat)"
        stuecke.append(f"{name} ({nummer}.)" if nummer else name)
        stuecke.append(f"{teile[2].removesuffix('m')} Monate")
    return " · ".join(stuecke), str(info.get("url") or "")


def _benenne(ebene: dict, soll: ZeilenSoll) -> None:
    for eintrag in [*ebene["luecken"], *ebene["nicht_im_soll"]]:
        eintrag["name"], url = lesbar(eintrag["schluessel"], soll)
        if "url" in eintrag:
            eintrag["url"] = url


def _ohne_auswahl(zeile: dict, z: ga.Zaehlung, soll: ZeilenSoll, ist: Ist) -> None:
    """Keine gezählte Seite für diese Zeile: wurden Seiten gelesen (Tarifwelt: kein
    Tarif in diesem Netz), ist das Soll gezählt 0; sonst fehlt es benannt."""
    k = zeile["ebenen"]["kombinationen"]
    if any(s.status == ga.GELESEN for s in z.seiten):
        extra = sorted(ist.kombinationen)
        k.update(
            soll=0,
            soll_grund=None,
            erfasst=0,
            luecken_zahl=0,
            nicht_im_soll=[{"schluessel": e, "name": e} for e in extra][
                :LISTE_HOECHSTENS
            ],
            nicht_im_soll_zahl=len(extra),
            quelle={
                "art": ART_AUSWAHL,
                "gezaehlt_um": z.gezaehlt_bis or z.gezaehlt_von,
            },
        )
        return
    gruende = "; ".join(sorted({str(n["grund"]) for n in soll.nicht_gezaehlt}))
    k["soll_grund"] = (
        f"{ANGEBOT_FEHLT}: {len(soll.nicht_gezaehlt)} Seiten nicht gezählt ({gruende})"
    )[:300]


def _fehlt(zeile: dict, grund: str) -> None:
    ebene = zeile["ebenen"]["kombinationen"]
    if ebene["soll"] is None:
        ebene["soll_grund"] = f"{ANGEBOT_FEHLT}: {grund}"
    zeile["angebot"] = {"status": "fehlt", "grund": grund}


def deutsch(tag: str) -> str:
    """„2026-11-21“ -> „21.11.2026“."""
    teile = tag.split("-")
    return ".".join(reversed(teile)) if len(teile) == 3 else tag


def _lies(state_dir: Path, tag: str, schluessel: str) -> tuple[ga.Zaehlung | None, str]:
    try:
        z = ga.lies(state_dir, tag, schluessel)
    except ga.AngebotsdateiFehler as fehler:
        return None, f"Zählung nicht lesbar ({fehler})"
    if z is None:
        letzte = ga.juengste(state_dir, schluessel)
        return None, f"keine Zählung für den {deutsch(tag)}" + (
            f", letzte vom {deutsch(letzte)}" if letzte else ""
        )
    if not z.kacheln and not any(s.status == ga.GELESEN for s in z.seiten):
        return None, z.grund or f"Zählung ohne Ergebnis ({z.laufstatus})"
    return z, ""


def _ohne(ist: Ist, modelle: set[str]) -> Ist:
    return Ist(
        buendel=ist.buendel,
        modelle=ist.modelle - modelle,
        modell_speicher={
            m for m in ist.modell_speicher if m.rsplit("-", 1)[0] not in modelle
        },
        kombinationen=ist.kombinationen,
    )


def _zeile(voll, zeile, z, soll: ZeilenSoll, buendel, signale, ist_je, namen) -> None:
    name = zeile["name"]
    gezaehlt = {a.modell for a in soll.auswahlen}
    ohne_seite = (set(soll.modelle) | soll.kachelmodelle) - gezaehlt
    weg = ({n["schluessel"] for n in soll.nicht_gezaehlt} | ohne_seite) - gezaehlt
    soll.namen = dict(namen)
    for b in buendel:
        b = b if isinstance(b, dict) else vars(b)
        if b.get("anbieter") == name and b.get("tarif_name"):
            kern_name = ohne_variante(grundtarif(str(b["tarif_name"])))[0]
            soll.tarifnamen.setdefault(kern_name, str(b["tarif_name"]).split(" (")[0])
    herkunft = None
    if z.schluessel == "o2":
        herkunft = kaufwege.ergaenze(z, soll, buendel, name)
    voll_ist = ist_je.get(name, Ist())
    ist = _ohne(voll_ist, weg)
    grund = grund_der_luecke(name, soll, ist, signale, ist_je)
    ganz, beleg = ga.uebersicht_pruefung(z)
    ist_modelle = ist if z.schluessel == "tarifwelt" else voll_ist
    zeile["soll_quelle"] = {
        "art": ART_UEBERSICHT,
        "quelle": z.uebersicht,
        "gleiche_quelle_wie_sammler": False,
        "gezaehlt_um": z.gezaehlt_von,
        "genannt": z.genannt,
    }
    for schluessel, info in soll.modelle.items():
        if info["im_katalog"] and schluessel in namen:
            info["name"] = namen[schluessel]
    stufe1 = {"modelle": list(soll.modelle.values())}
    zeile["ebenen"]["modelle"] = _modell_ebene(
        name, stufe1, ist_modelle, signale, ist_je, namen
    )
    zeile["ebenen"]["modell_speicher"] = _speicher_ebene(soll, ist, grund)
    haenge_kombinationen_ein(
        voll,
        name,
        soll.auswahlen,
        buendel,
        signale,
        grund=grund,
        grund_extra=grund_ohne_angebot(soll),
        ausgenommen=weg,
        quelle={"art": ART_AUSWAHL, "gezaehlt_um": z.gezaehlt_bis or z.gezaehlt_von},
    )
    if not soll.auswahlen:
        _ohne_auswahl(zeile, z, soll, ist)
    _benenne(zeile["ebenen"]["kombinationen"], soll)
    _benenne(zeile["ebenen"]["modell_speicher"], soll)
    zeile["angebot"] = {
        "status": z.laufstatus,
        "grund": z.grund,
        "messtag": z.messtag,
        "gezaehlt_von": z.gezaehlt_von,
        "gezaehlt_bis": z.gezaehlt_bis,
        "nicht_gezaehlt": soll.nicht_gezaehlt[:LISTE_HOECHSTENS],
        "nicht_gezaehlt_zahl": len(soll.nicht_gezaehlt),
        "uebersicht": {
            "genannt": z.genannt,
            "gelesen": len(z.kacheln),
            "vollstaendig": ganz,
            "beleg": beleg,
        },
        "unvollstaendig": soll.unvollstaendig[:LISTE_HOECHSTENS],
        "konkurrenz": z.konkurrenz,
        "herkunft": herkunft,
    }
    if not ganz or soll.unvollstaendig:
        zeile["angebot"]["status"] = ga.TEILWEISE


def haenge_ein(voll, state_dir, tag, buendel, signale, katalog, namen=None) -> dict:
    """Hängt die Zählungen aller Anbieter des Messtags ``tag`` in ``voll`` ein."""
    buendel = list(buendel or ())
    ist_je = ist_zaehlung(buendel, tag)
    zeilen = {z["name"]: z for z in voll["anbieter"]}
    for anbieter in ga.ANBIETER.values():
        z, grund = _lies(Path(state_dir), tag, anbieter.schluessel)
        for name in anbieter.anbieterzeilen():
            if name not in zeilen:
                continue
            if z is None:
                _fehlt(zeilen[name], grund)
                continue
            soll = soll_aus(z, katalog)[name]
            _zeile(voll, zeilen[name], z, soll, buendel, signale, ist_je, namen or {})
    return voll
