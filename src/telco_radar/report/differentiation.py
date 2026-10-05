"""Differenzierungs-Radar (Endkonsumenten, jenseits des Preises).

Clustert die (vom Analyse-Agenten bewerteten) Meldungen der letzten Wochen nach
Differenzierungs-Hebeln, mit denen sich Wettbewerber im Endkundengeschaeft abheben -
externe Services UND Value-Add-Versprechen (Garantie, Geraete-Programme,
Versicherung, Perks). Bewusst KEIN Netz-/5G-Ausbau, kein Broadband-Infrastruktur.
Alles zur Render-Zeit in Python (kein LLM), Anzeige Deutsch. Jede Kategorie hat eine
Inspirations-Tafel (Vorbilder + Impuls fuer Vodafone), auch fuer ruhige Wochen.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from ..analyze.differenzierung_hebel import classify
from . import anbieter_farben as farben

DIFF_THEMES = [
    {
        "key": "garantie",
        "label": "Garantie & Service-Versprechen",
        "color": farben.VODAFONE_ROT,
        "blurb": '„Sorglos"-Versprechen differenzieren ohne Preisnachlass und zahlen '
        "voll auf Vertrauen ein: verlaengerte Garantie, Akkutausch, Preis-, "
        "Netz- und Zufriedenheitsgarantien.",
        "vorbilder": [
            {
                "name": "T-Mobile US · Preisgarantie / Price Lock",
                "desc": 'warb mit „5 Jahre kein Preisanstieg" – ein starkes Vertrauens-Signal (2025/26 teils aufgeweicht, als Marketing-Hebel aber prägend).',
            },
            {
                "name": 'AT&T · „AT&T Guarantee"',
                "desc": "Gutschrift-/Geld-zurück-Versprechen bei Netzausfällen und schlechtem Service als Zufriedenheitsgarantie.",
            },
            {
                "name": "Vodafone UK · Lifetime Service Promise + 5-J-Garantie",
                "desc": "lebenslanges Service-Versprechen plus 5 Jahre Herstellergarantie inkl. Akkutausch (eigene Vodafone-Stärke).",
            },
            {
                "name": "Zufriedenheits-/Netzgarantien",
                "desc": "Test-/Geld-zurück-Modelle senken die Wechselhürde spürbar.",
            },
        ],
        "impuls": "Genau die Richtung, die interessiert: Versprechen statt Rabatt. "
        "Vodafone ist mit 5-Jahres-Garantie und Lifetime-Promise schon "
        "Vorreiter – der Impuls ist, das lauter zu vermarkten und um eine "
        "Preis- bzw. Netz-/Zufriedenheitsgarantie zu ergänzen.",
    },
    {
        "key": "geraete",
        "label": "Geräte-Programme & Zubehör",
        "color": farben.ROT_TIEF,
        "blurb": "Der Gerätekauf als Bindungsanker: jährliches Upgrade, faire "
        "Inzahlungnahme, refurbished, exklusive Geräte und gebündeltes "
        "Zubehör – Value ohne Preiskampf.",
        "vorbilder": [
            {
                "name": "T-Mobile US · jährliches Upgrade (Phone Freedom)",
                "desc": "garantiert jedes Jahr ein neues Top-Smartphone – gleiche Konditionen für Neu- und Bestandskunden.",
            },
            {
                "name": "US-Carrier · Trade-in (Assurant)",
                "desc": "2025 flossen ~6,4 Mrd. $ über Inzahlungnahme/Upgrade an Kunden zurück – Trade-in als zentraler Kaufanreiz.",
            },
            {
                "name": "SoftBank/Docomo (JP) · exklusive & KI-Geräte",
                "desc": "carrier-exklusive Smartphones (z. B. KI-Phone) binden Kunden ans Ökosystem.",
            },
            {
                "name": "Zubehör & Wearables",
                "desc": "gebündelte Kinder-Smartwatches, Kameras und AI-Gadgets erweitern den Haushalt über das Handy hinaus.",
            },
        ],
        "impuls": 'Ein einfaches „immer das neueste Gerät"-Versprechen plus starke, '
        "transparente Trade-in-/Refurbished-Angebote differenzieren und "
        "zahlen zugleich auf Nachhaltigkeit ein – ohne den Preis zu senken.",
    },
    {
        "key": "ki",
        "label": "KI & Assistenten",
        "color": farben.VIOLETT,
        "blurb": "Wettbewerber verschenken eine kostenpflichtige Premium-KI oder bauen "
        "sie fest ins Gerät ein und machen den Assistenten zum Tarif-Vorteil.",
        "vorbilder": [
            {
                "name": "Telekom · AI Phone",
                "desc": "18 Monate Perplexity Pro gratis – KI fest im Smartphone, eigener Magenta-Knopf.",
            },
            {
                "name": "Free/Iliad (FR) · Le Chat Pro",
                "desc": "12 Monate Mistral-Premium-KI gratis für alle Mobilfunkkunden.",
            },
            {
                "name": "SoftBank (JP)",
                "desc": "Perplexity Pro gratis plus exklusives, KI-natives Smartphone.",
            },
            {
                "name": "Jio (IN)",
                "desc": "18 Monate Google Gemini AI Pro + 2 TB Cloud gratis zum Tarif.",
            },
        ],
        "impuls": "Vodafone hat TOBi als Service-Bot, aber keinen kostenlosen Premium-"
        "KI-Assistenten als Tarif-Bonus. Ein „Perplexity/Gemini/Mistral "
        'gratis"-Bundle wäre ein sofort verständliches Signal.',
    },
    {
        "key": "entertainment",
        "label": "Entertainment & Streaming",
        "color": farben.BEERE,
        "blurb": "Streaming, Sport- und TV-Rechte als Bindungsanker. Die Besten "
        "bündeln nicht nur ein Abo, sondern ein Aggregator-Erlebnis.",
        "vorbilder": [
            {
                "name": "Telekom · MagentaTV",
                "desc": "ein Interface und eine Fernbedienung über lineares TV und alle Streaming-Apps.",
            },
            {
                "name": "Telia (Nordics) · Telia Play",
                "desc": "bündelt Netflix, Disney+, HBO Max, Viaplay & Sport in EINER durchsuchbaren App.",
            },
            {
                "name": "EE (UK) · Inclusive Extras",
                "desc": "ein wählbarer Premium-Dienst pro Monat, alle 30 Tage tauschbar.",
            },
            {
                "name": "Deutsche Telekom · WM-Rechte",
                "desc": "exklusive Sportrechte (FIFA-WM 2030) als Neukunden-Turbo.",
            },
        ],
        "impuls": "Vodafone bündelt Disney+/Prime/YouTube als lose Add-ons. Nächster "
        "Schritt: das Aggregator-Erlebnis – ein Interface über alle Dienste.",
    },
    {
        "key": "security",
        "label": "Security & Betrugsschutz",
        "color": farben.GRUEN,
        "blurb": "Schutz vor Betrug, Spam und Deepfakes wird vom Add-on zum Marken-"
        "Asset – oft kostenlos und automatisch im Netz.",
        "vorbilder": [
            {
                "name": "Airtel (IN)",
                "desc": "KI-Spam-/Betrugserkennung direkt im Netz – gratis und automatisch für alle.",
            },
            {
                "name": "KT (KR)",
                "desc": "erkennt KI-Fake-Stimmen (Deepfakes) am Telefon in Echtzeit.",
            },
            {
                "name": "Orange (FR) · Cybersecure",
                "desc": "Schutzdienst, den sogar Nicht-Kunden nutzen können.",
            },
            {
                "name": "Telekom · Digital-Schutzpaket",
                "desc": "ID-/Darkweb-Monitoring, Betrugsabsicherung, Hilfe bei Cybermobbing.",
            },
        ],
        "impuls": "Vodafone hat Secure Net. Trend: weg vom Geräte-Antivirus, hin zu "
        "netz-/identitätsbasiertem Schutz plus KI-Betrugserkennung.",
    },
    {
        "key": "fintech",
        "label": "Fintech & Payment",
        "color": farben.OCKER,
        "blurb": "Wallet, Kredit, Versicherung und Banking direkt in der Telco-App – "
        "in Wachstumsmärkten die stärksten Ökosysteme überhaupt.",
        "vorbilder": [
            {
                "name": "Safaricom/Vodacom · M-Pesa & VodaPay",
                "desc": "Afrikas führendes Telco-Fintech – Wallet + 220+ Mini-Apps (eigene Vodafone-Familie!).",
            },
            {
                "name": "MTN (Afrika) · MoMo",
                "desc": "Fintech-Wallet, per Alipay-Partnerschaft zum Mini-App-Marktplatz ausgebaut.",
            },
            {
                "name": "GCash / Maya (PH)",
                "desc": "aus Telcos entstandene Fintech-Unicorns.",
            },
            {
                "name": "Turkcell (TR) · Paycell",
                "desc": "eigenes Bezahlsystem in der hauseigenen Digital-Suite.",
            },
        ],
        "impuls": "Vodafone besitzt mit M-Pesa/VodaPay das stärkste Telco-Fintech – nur "
        "in Afrika. Impuls: das Mini-App-Modell in europäische Apps übertragen.",
    },
    {
        "key": "superapp",
        "label": "Super-App & Ökosystem",
        "color": farben.BLAU,
        "blurb": "Die Telco-App wird von der Selfcare-App zur Alltags-Plattform mit "
        "eingebauten Partner-Diensten.",
        "vorbilder": [
            {
                "name": "Jio (IN) · MyJio",
                "desc": "eine App als Zugang zu Streaming, Musik, Shopping, Zahlung, Cloud, Games.",
            },
            {
                "name": "Turkcell (TR)",
                "desc": "komplette eigene Digital-Suite (BiP, fizy, TV+, Lifebox, Paycell).",
            },
            {
                "name": "EE (UK) · EE-ID",
                "desc": 'offene Login-ID, auch für Nicht-Kunden – „mehr als ein Netz".',
            },
            {
                "name": "Orange · Max it (MEA)",
                "desc": "Super-App mit Konto, Money, Shopping, Musik, TV, Ticketing.",
            },
        ],
        "impuls": "MeinVodafone könnte zur Alltags-Plattform werden: offene Login-ID, "
        "Partner-Mini-Apps, Services über den Tarif hinaus.",
    },
    {
        "key": "cloud",
        "label": "Cloud & Speicher",
        "color": farben.TUERKIS,
        "blurb": "Kostenloser, oft datensouveräner Cloud-Speicher als Tarif-Extra – "
        "günstig und ein guter Bindungsanker.",
        "vorbilder": [
            {"name": "Rakuten (JP)", "desc": "50 GB Cloud-Speicher gratis zum Tarif."},
            {"name": "Jio (IN)", "desc": "großzügiger Gratis-Speicher im 5G-Angebot."},
            {
                "name": "Swisscom (CH) · myCloud",
                "desc": "Schweiz-gehostet – Datensouveränität als Argument.",
            },
            {
                "name": "O2 (ES)",
                "desc": "Gratis-Speicher für Mobilfunkkunden, bis 10 TB.",
            },
        ],
        "impuls": "EU-gehosteter Gratis-Cloud-Speicher als Tarif-Extra – zugleich "
        "Vertrauens- und Bindungsanker, gerade im deutschen Markt.",
    },
    {
        "key": "smarthome",
        "label": "Smart Home & IoT",
        "color": farben.ROSTBRAUN,
        "blurb": "Sicherheit und Steuerung fürs Zuhause am Anschluss – margenstark und "
        "bindet den ganzen Haushalt.",
        "vorbilder": [
            {
                "name": "Telekom · Magenta Home",
                "desc": "eine App mit Routinen (Alarm, Anwesenheits-Simulation, Heizung).",
            },
            {
                "name": "au (JP) · au HOME",
                "desc": "Kamera, smartes Schloss, Sensoren, Notruf-Dienst.",
            },
            {
                "name": "Movistar (ES)",
                "desc": "Alarmanlage (Prosegur-JV) plus digitaler Schutz.",
            },
            {
                "name": "e& (VAE)",
                "desc": "Smart-Home-Überwachung und -Steuerung am Anschluss.",
            },
        ],
        "impuls": "Smart-Home/-Security als margenstarke Zusatzwelt, die den Haushalt "
        "an die Vodafone-Konnektivität bindet.",
    },
    {
        "key": "gaming",
        "label": "Gaming",
        "color": farben.LILA,
        "blurb": "Cloud-Gaming als greifbarer Netz-Beweis – niedrige Latenz wird zum "
        "Erlebnis statt zur Technik-Folie.",
        "vorbilder": [
            {
                "name": "Telekom · 5G+ Gaming",
                "desc": "GeForce NOW gebündelt, über niedrige Latenz vermarktet.",
            },
            {
                "name": "EE (UK)",
                "desc": "Game Pass als Extra plus Cloud-Gaming-Bundles mit Hardware.",
            },
            {
                "name": "SK Telecom (KR)",
                "desc": "Xbox Game Pass im Abo-Marktplatz T Universe.",
            },
            {
                "name": "MTN (Afrika) · Arcade",
                "desc": "Gaming-Abo mit Premium-Titeln zum Tagespreis.",
            },
        ],
        "impuls": "Cloud-Gaming als Bundle (GeForce NOW / Game Pass) statt eigener "
        "Plattform – kostengünstiger Beweis fürs Netz.",
    },
    {
        "key": "loyalty",
        "label": "Loyalty & Perks",
        "color": farben.ORANGE,
        "blurb": "Erlebnis-Perks und exklusive Vorverkäufe machen das tägliche "
        "App-Öffnen zur Gewohnheit – Bindung über Nutzen.",
        "vorbilder": [
            {
                "name": "O2 (UK) · Priority",
                "desc": "Goldstandard: Ticket-Vorverkäufe und tägliche, lokale Erlebnis-Perks.",
            },
            {
                "name": "Telekom · Magenta Moments",
                "desc": "täglich wechselnde Vorteile, Trials, Konzert-Presales.",
            },
            {
                "name": "KPN (NL) · Voor Jou",
                "desc": "wöchentliche Überraschungen als fester App-Anlass.",
            },
            {
                "name": "Vodafone · VeryMe",
                "desc": "gute Basis – Ausbau Richtung Erlebnis/Presales fehlt.",
            },
        ],
        "impuls": "Von O2 Priority lernen: exklusive Presales und tägliche, lokale "
        "Erlebnis-Perks, die einen echten Grund geben, die App zu öffnen.",
    },
    {
        "key": "health",
        "label": "Health & Wellbeing",
        "color": farben.PETROL,
        "blurb": "Telemedizin und Wellbeing als Differenzierung mit Nutzenversprechen – "
        "in Wachstumsmärkten erprobt.",
        "vorbilder": [
            {
                "name": "NTT Docomo (JP) · d Healthcare",
                "desc": "belohnt Gesundheits-Missionen (Schritte, Blutdruck) mit Punkten – 18 Mio.+ Nutzer.",
            },
            {
                "name": "Globe (PH) · KonsultaMD",
                "desc": "Telemedizin mit über 1 Mio. Nutzern im Telco-Ökosystem.",
            },
        ],
        "impuls": "Gesundheits-Services (Telemedizin, Wellbeing) als Differenzierung "
        "mit gesellschaftlichem Nutzen.",
    },
]

_THEME_BY_KEY = {t["key"]: t for t in DIFF_THEMES}
_ORDER = {t["key"]: i for i, t in enumerate(DIFF_THEMES)}


def _domain(url: str) -> str:
    return urlsplit(url or "").netloc.removeprefix("www.")


def _split_first(text: str) -> tuple[str, str]:
    t = " ".join((text or "").split())
    if not t:
        return "", ""
    for sep in (". ", "! ", "? "):
        k = t.find(sep)
        if 8 < k < 160:
            return t[: k + 1], t[k + 2 :]
    return t, ""


def build_differentiation(highlights: list[dict]) -> dict:
    """Klassifiziert Highlights (mehrerer Wochen) nach Differenzierungs-Hebel."""
    moves_by_theme: dict[str, list] = {t["key"]: [] for t in DIFF_THEMES}
    seen: set[str] = set()
    total = 0
    for hl in highlights or []:
        best = classify(hl)
        if best is None:
            continue
        key = (hl.get("url") or hl.get("title") or "").strip().lower()
        if key in seen:
            continue
        seen.add(key)
        theme = _THEME_BY_KEY[best]
        head, rest = _split_first(hl.get("summary") or "")
        de_title = head or (hl.get("summary") or hl.get("title") or "")
        moves_by_theme[best].append(
            {
                "op": hl.get("operator")
                or hl.get("source_label")
                or _domain(hl.get("url")),
                "de_title": de_title,
                "rest": rest,
                "summary": hl.get("summary"),
                "why": hl.get("why_it_matters"),
                "url": hl.get("url"),
                "region": hl.get("region"),
                "date": hl.get("date"),
                "cat": (hl.get("category") or "").strip(),
                "rel": hl.get("relevance") or 0,
                "domain": _domain(hl.get("url")),
                "color": theme["color"],
                "theme_label": theme["label"],
            }
        )
        total += 1

    themes = []
    for t in DIFF_THEMES:
        mv = sorted(
            moves_by_theme[t["key"]],
            key=lambda m: (m["rel"], m.get("date") or ""),
            reverse=True,
        )
        themes.append(
            {
                **{
                    k: t[k]
                    for k in ("key", "label", "color", "blurb", "vorbilder", "impuls")
                },
                "moves": mv,
                "n": len(mv),
            }
        )

    active = sorted(
        [t for t in themes if t["n"]], key=lambda t: (-t["n"], _ORDER[t["key"]])
    )
    quiet = [t for t in themes if not t["n"]]
    top = sorted(
        [m for t in active for m in t["moves"]],
        key=lambda m: (m["rel"], m.get("date") or ""),
        reverse=True,
    )[:3]
    return {
        "total": total,
        "n_active": len(active),
        "themes": themes,
        "active": active,
        "quiet": quiet,
        "top": top,
    }
