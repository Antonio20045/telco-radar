"""Telekom-Zusatzlesepfad: die Produktseite MIT `tariffId` (B-TELEKOM-PRODUKTSEITE,
08.11.2026) fuer Pflichtmodell-Varianten, die die Buendel-Kategorieseite
(`telekom.lies_buendel`) an einem Tag nicht zeigt - sie ist je Tarif ein
Bestseller-Karussell mit 9-10 festen Plaetzen, kein Katalog (Pagination wirkt
nicht, arbeit/telekom-congstar-vollst-0811.md). `productDetailed.
installmentConfiguratorItems[str(laufzeit)]` traegt dieselbe Zahl je Variante
geraeteseitig rein (ohne Tarifanteil, tarifunabhaengig) in drei Anzahlungs-
stufen; `productDetailsData.tariff` die typisierten Tarifpreise, genauso
geformt wie `selectedPlan` der Buendelseite. Welche Geraete und Variantenslugs
geprueft werden, steht in `config/geraete_quellen.yaml` (Telekom-Block,
`zusatz_varianten`) - dieses Modul kennt kein einziges Geraet beim Namen.

Fail-closed: eine abweichende Schlussrate, ein Tarif, dessen `id` nicht zur
angefragten `tariffId` passt, oder eine Antwort ohne `__INITIAL_STATE__`
liefern `None` - die Zelle bleibt eine benannte Luecke, nie ein geratener
Preis (Entscheidung Antonio, 11.08.2026).
"""

from __future__ import annotations

import logging

from .basis import GeraeteAbrufFehler, _preis
from .telekom import _gleich, _plan_preise, _variante, zustand

log = logging.getLogger(__name__)

_ZUSATZ_LAUFZEIT_MONATE = 24


def _installment_plan(pd_aussen: dict, laufzeit_monate: int) -> dict | None:
    """Der Geraete-Ratenplan mit der niedrigsten Anzahlung aus
    `productDetailed.installmentConfiguratorItems[str(laufzeit)]` - drei
    geraeteseitig reine Anzahlungsstufen je Variante, keine als Standard
    markiert. Gemessen an Apple iPhone 18 Pro (199 EUR) und Apple iPhone
    Duo 256 GB (399 EUR, je 08.11.2026) zeigt die Buendelseite fuer jedes
    Geraet IMMER die NIEDRIGSTE Stufe - diese Funktion uebernimmt die
    gemessene Konvention, keine geratene. Eine abweichende Schlussrate
    macht den Plan nicht eindeutig - `None`, keine Zahl."""
    eintraege = pd_aussen.get("installmentConfiguratorItems")
    if not isinstance(eintraege, dict):
        return None
    plaene = [
        p for p in eintraege.get(str(laufzeit_monate)) or [] if isinstance(p, dict)
    ]
    bewertet = [
        (w, p) for p in plaene if (w := _preis(p.get("upfrontPrice"))) is not None
    ]
    if not bewertet:
        return None
    anzahlung, plan = min(bewertet, key=lambda t: t[0])
    rate = _preis(plan.get("recurringPrice"))
    schlussrate = _preis(plan.get("finalRecurringPrice"))
    installment_id = str(plan.get("installmentId") or "").strip()
    if rate is None or schlussrate is None or not installment_id:
        return None
    if not _gleich(rate, schlussrate):
        log.info(
            "Telekom-Zusatz: Ratenplan %r hat eine abweichende Schlussrate "
            "(%.2f statt %.2f) - nicht eindeutig, verworfen",
            installment_id,
            schlussrate,
            rate,
        )
        return None
    return {
        "anzahlung": anzahlung,
        "monatsrate": rate,
        "installment_id": installment_id,
    }


def _tarif_auf_produktseite(pd: dict, tarif_id: str) -> dict | None:
    """Name, Anschlusspreis und Monatsgebuehr des angefragten Tarifs.

    `productDetailsData.tariff` ist gleich geformt wie `selectedPlan` der
    Buendelseite, traegt aber ZUSAETZLICH Kartenoptionen anderer Angebote
    (primaryCard, secondaryCard, kidsCard) in DERSELBEN `prices`-Liste -
    nur ueber die `id`, die mit `tarif_id-` beginnt, gehoert ein Preis
    wirklich zum angefragten Tarif (dieselbe Disziplin wie `telekom.
    lies_buendel`s Abgleich gegen `selectedPlan`)."""
    tarif = pd.get("tariff")
    if not isinstance(tarif, dict):
        return None
    name = str(tarif.get("name") or "").strip()
    seiten_id = str(tarif.get("id") or "").strip()
    if not name or seiten_id != tarif_id:
        return None
    eigene_preise = {
        "prices": [
            p
            for p in tarif.get("prices") or []
            if isinstance(p, dict) and str(p.get("id") or "").startswith(f"{tarif_id}-")
        ]
    }
    anschluss, monatlich = _plan_preise(eigene_preise)
    if monatlich is None:
        return None
    return {
        "tarif_name": name,
        "anschlusspreis": anschluss,
        "tarif_monatlich": monatlich,
    }


def lies_zusatz_variante(
    text: str,
    url: str,
    tarif_id: str,
    produkt_slug: str,
    variante_slug: str,
    laufzeit_monate: int = _ZUSATZ_LAUFZEIT_MONATE,
) -> dict | None:
    """Produktseite MIT `tariffId` fuer EINE Variante x EINEN Tarif.

    `None` heisst: keine Zahl uebernommen - entweder, weil der Betrag nicht
    eindeutig ist (Modulkopf), oder weil die Antwort nicht zur angefragten
    Variante oder zum angefragten Tarif passt (Probe gegen `produkt_slug`,
    `variante_slug` und `tarif_id` - dieselbe Disziplin wie `telekom.
    lies_buendel`s Abgleich gegen `selectedPlan`)."""
    daten = zustand(text)
    pd_aussen = daten.get("productDetailed")
    if not isinstance(pd_aussen, dict):
        return None
    pd = pd_aussen.get("productDetailsData")
    if not isinstance(pd, dict):
        return None
    if str(pd.get("productSlug") or "").strip() != produkt_slug:
        return None
    if str(pd_aussen.get("variantSlug") or "").strip() != variante_slug:
        return None
    plan = _installment_plan(pd_aussen, laufzeit_monate)
    if plan is None:
        return None
    tarif = _tarif_auf_produktseite(pd, tarif_id)
    if tarif is None:
        return None
    name = str(pd.get("productName") or "").strip()
    if not name:
        return None
    farbe, speicher = _variante(variante_slug)
    titel = " ".join(
        x for x in (name, f"{speicher} GB" if speicher else "", farbe) if x
    )
    return {
        "titel": titel,
        "strukturierter_name": name,
        "farbe": farbe,
        "speicher_gb": speicher,
        "sku": plan["installment_id"],
        "tarif_name": tarif["tarif_name"],
        "tarif_slug": tarif_id,
        "tarif_monatlich": tarif["tarif_monatlich"],
        "geraet_zuzahlung": plan["anzahlung"],
        "geraet_monatsrate": plan["monatsrate"],
        "anschlusspreis": tarif["anschlusspreis"],
        "laufzeit_monate": laufzeit_monate,
        "url": url,
        "quelle": "telekom_produktseite_zusatz",
    }


def _vorhandene_speicher(rohsaetze: list) -> dict[str, set]:
    """Je Geraetename die Speichergroessen, die schon im Katalog stehen."""
    vorhanden: dict[str, set] = {}
    for satz in rohsaetze:
        name = str(satz.get("strukturierter_name") or "").strip()
        gb = satz.get("speicher_gb")
        if name and gb is not None:
            vorhanden.setdefault(name, set()).add(gb)
    return vorhanden


def _hole_zusatz_satz(
    hole, url: str, tarif_id: str, produkt_slug: str, variante_slug: str, z: dict
) -> dict | None:
    """EIN Abruf plus Lesung - oder eine benannte, gezaehlte Luecke."""
    z["abrufe"] = z.get("abrufe", 0) + 1
    try:
        text = hole(url)
    except GeraeteAbrufFehler as exc:
        z["unlesbar"] = z.get("unlesbar", 0) + 1
        log.info("Telekom-Zusatz: %s nicht abrufbar (%s)", url, exc)
        return None
    try:
        satz = lies_zusatz_variante(text, url, tarif_id, produkt_slug, variante_slug)
    except GeraeteAbrufFehler as exc:
        z["unlesbar"] = z.get("unlesbar", 0) + 1
        log.info("Telekom-Zusatz: %s unlesbar (%s)", url, exc)
        return None
    if satz is None:
        z["nicht_eindeutig"] = z.get("nicht_eindeutig", 0) + 1
        log.info(
            "Telekom-Zusatz: %s ohne eindeutigen %d-Monats-Betrag - Luecke "
            "bleibt benannt, keine Zahl uebernommen",
            url,
            _ZUSATZ_LAUFZEIT_MONATE,
        )
        return None
    z["gemessen"] = z.get("gemessen", 0) + 1
    return satz


def _fehlende_varianten(geraet: dict, schon_da: set) -> list[tuple[str, int]]:
    """(variante_slug, speicher_gb) dieses Geraets, die NICHT in `schon_da` stehen."""
    fehlend = []
    for variante in geraet.get("varianten") or []:
        if not isinstance(variante, dict):
            continue
        speicher_gb = variante.get("speicher_gb")
        variante_slug = str(variante.get("variante_slug") or "").strip()
        if variante_slug and speicher_gb is not None and speicher_gb not in schon_da:
            fehlend.append((variante_slug, speicher_gb))
    return fehlend


def vertiefe_buendel(
    hole,
    rohsaetze: list,
    weiter=None,
    zaehler: dict | None = None,
    zusatz: list | None = None,
) -> list[dict]:
    """Nachlese ueber Konfiguration: nur fehlende Varianten x Tarife.

    `zusatz` ist `Anbieter.zusatz_varianten` (`config/geraete_quellen.yaml`,
    Telekom-Block) - wessen Modell und welche Variantenslugs geprueft
    werden, steht dort, nicht hier. Fuer jede konfigurierte Variante, deren
    Speichergroesse unter diesem Tarif (`rohsaetze[0]["tarif_slug"]`) schon
    im Bestseller-Karussell steht, wird NICHTS abgerufen - genau so viele
    Seitenaufrufe wie fehlende Zellen, nie mehr (HAUSREGEL)."""
    z = zaehler if zaehler is not None else {}
    weiter = weiter or (lambda: True)
    konfiguriert = [g for g in zusatz or [] if isinstance(g, dict)]
    if not konfiguriert or not rohsaetze:
        return []
    tarif_id = str(rohsaetze[0].get("tarif_slug") or "").strip()
    if not tarif_id:
        return []
    vorhandene_speicher = _vorhandene_speicher(rohsaetze)

    out: list[dict] = []
    for geraet in konfiguriert:
        name = str(geraet.get("produkt_name") or "").strip()
        marke = str(geraet.get("marke") or "").strip()
        produkt_slug = str(geraet.get("produkt_slug") or "").strip()
        if not name or not marke or not produkt_slug:
            continue
        schon_da = vorhandene_speicher.get(name, set())
        for variante_slug, _speicher_gb in _fehlende_varianten(geraet, schon_da):
            if not weiter():
                z["frist"] = z.get("frist", 0) + 1
                return out
            url = (
                f"https://www.telekom.de/shop/geraet/{marke}/{produkt_slug}/"
                f"{variante_slug}?tariffId={tarif_id}"
            )
            satz = _hole_zusatz_satz(
                hole, url, tarif_id, produkt_slug, variante_slug, z
            )
            if satz is not None:
                out.append(satz)
    return out
