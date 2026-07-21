"""Differenzierungs-Radar (Endkonsumenten, jenseits des Preises).

Clustert die (vom Analyse-Agenten bewerteten) Meldungen der letzten Wochen nach
Differenzierungs-Hebeln, mit denen sich Wettbewerber im Endkundengeschaeft abheben -
externe Services UND Value-Add-Versprechen (Garantie, Geraete-Programme,
Versicherung, Perks). Bewusst KEIN Netz-/5G-Ausbau, kein Broadband-Infrastruktur.

Alles zur Render-Zeit in Python (kein LLM). Anzeige durchgehend Deutsch. Zusaetzlich
liefert jede Kategorie eine evergreen Inspirations-Tafel (Vorbilder + Impuls fuer
Vodafone) - so traegt die Seite auch in einer ruhigen Nachrichtenwoche.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

NON_DIFF_CATEGORIES = {
    "Tarif/Pricing", "Verbal/Pricing", "Finanzen", "Regulierung", "Personal",
    "Sonstiges", "Strategie",
}

# Harte Ausschluesse: Netz-/Infrastruktur, B2B/Enterprise, Konzernfinanzen. Der
# Nutzer will Endkunden-Differenzierung, keinen 5G-/Broadband-Ausbau.
_EXCLUDE = re.compile(
    r"ai[- ]ran|open ran|o-ran|\bv-?ran\b|\bran\b|spectrum|backbone|subsea|"
    r"data cent(er|re)|ground station|network slicing|\bslicing\b|outage|"
    r"network operation|network performance|drive test|private network|"
    r"campus network|\btower(s)?\b|fib(er|re)|glasfaser|ftth|broadband|breitband|"
    r"fixed wireless|\bfwa\b|capex|teleport|core network|cell site|base station|"
    r"quantum|\b6g\b|white paper|patching|greenfield|"
    r"zero trust|\bsase\b|enterprise|b2b|workforce|\bsme(s)?\b|\bsmb(s)?\b|"
    r"critical infrastructure|managed security|\bsoc\b|"
    r"\bipo\b|valuation|merger|acquisition|acquire|\bstake\b|fundrais|"
    r"\bshares\b|\bstock\b|earnings|\brevenue(s)?\b|\bprofit\b|subsidy|"
    r"billion|\bbn\b|\bm\&a\b|invests?\b|investment|raises\s|hires|"
    r"data analytics|multi-operator|\bm2m\b|constellation|automotive|"
    r"connected vehicle|agentic network|infrastructure upgrade|modernis|"
    r"spectrum license|satellite ground|d2d service launch",
    re.I,
)

DIFF_THEMES = [
    {
        "key": "garantie", "label": "Garantie & Service-Versprechen", "color": "#e60000",
        "blurb": "„Sorglos\"-Versprechen differenzieren ohne Preisnachlass und zahlen "
                 "voll auf Vertrauen ein: verlaengerte Garantie, Akkutausch, Preis-, "
                 "Netz- und Zufriedenheitsgarantien.",
        "anchors": ["warranty", "garantie", "gewährleistung", "price lock",
                    "preisgarantie", "price guarantee", "5-year price", "lifetime service",
                    "service promise", "service-versprechen", "money-back", "geld-zurück",
                    "zufriedenheitsgarantie", "battery replacement", "akkutausch",
                    "reparaturgarantie", "network guarantee", "netzgarantie",
                    "happiness guarantee", "device protection", "geräteschutz",
                    "schutzbrief", "coverage guarantee"],
        "vorbilder": [
            {"name": "T-Mobile US · Preisgarantie / Price Lock", "desc": "warb mit „5 Jahre kein Preisanstieg\" – ein starkes Vertrauens-Signal (2025/26 teils aufgeweicht, als Marketing-Hebel aber prägend)."},
            {"name": "AT&T · „AT&T Guarantee\"", "desc": "Gutschrift-/Geld-zurück-Versprechen bei Netzausfällen und schlechtem Service als Zufriedenheitsgarantie."},
            {"name": "Vodafone UK · Lifetime Service Promise + 5-J-Garantie", "desc": "lebenslanges Service-Versprechen plus 5 Jahre Herstellergarantie inkl. Akkutausch (eigene Vodafone-Stärke)."},
            {"name": "Zufriedenheits-/Netzgarantien", "desc": "Test-/Geld-zurück-Modelle senken die Wechselhürde spürbar."},
        ],
        "impuls": "Genau die Richtung, die interessiert: Versprechen statt Rabatt. "
                  "Vodafone ist mit 5-Jahres-Garantie und Lifetime-Promise schon "
                  "Vorreiter – der Impuls ist, das lauter zu vermarkten und um eine "
                  "Preis- bzw. Netz-/Zufriedenheitsgarantie zu ergänzen.",
    },
    {
        "key": "geraete", "label": "Geräte-Programme & Zubehör", "color": "#ac1811",
        "blurb": "Der Gerätekauf als Bindungsanker: jährliches Upgrade, faire "
                 "Inzahlungnahme, refurbished, exklusive Geräte und gebündeltes "
                 "Zubehör – Value ohne Preiskampf.",
        "anchors": ["trade-in", "trade in", "inzahlungnahme", "eintausch",
                    "refurbished", "generalüberholt", "gebrauchtgerät", "annual upgrade",
                    "jährliches upgrade", "upgrade program", "upgrade-programm",
                    "gerätewechsel", "carrier-exclusive", "exclusive phone",
                    "own-brand phone", "device as a service", "gerät im abo",
                    "hardware-abo", "kinder-smartwatch", "kids watch", "wearable bundle",
                    "phone freedom", "foldable bundle"],
        "vorbilder": [
            {"name": "T-Mobile US · jährliches Upgrade (Phone Freedom)", "desc": "garantiert jedes Jahr ein neues Top-Smartphone – gleiche Konditionen für Neu- und Bestandskunden."},
            {"name": "US-Carrier · Trade-in (Assurant)", "desc": "2025 flossen ~6,4 Mrd. $ über Inzahlungnahme/Upgrade an Kunden zurück – Trade-in als zentraler Kaufanreiz."},
            {"name": "SoftBank/Docomo (JP) · exklusive & KI-Geräte", "desc": "carrier-exklusive Smartphones (z. B. KI-Phone) binden Kunden ans Ökosystem."},
            {"name": "Zubehör & Wearables", "desc": "gebündelte Kinder-Smartwatches, Kameras und AI-Gadgets erweitern den Haushalt über das Handy hinaus."},
        ],
        "impuls": "Ein einfaches „immer das neueste Gerät\"-Versprechen plus starke, "
                  "transparente Trade-in-/Refurbished-Angebote differenzieren und "
                  "zahlen zugleich auf Nachhaltigkeit ein – ohne den Preis zu senken.",
    },
    {
        "key": "ki", "label": "KI & Assistenten", "color": "#7b3fe4",
        "blurb": "Wettbewerber verschenken eine kostenpflichtige Premium-KI oder bauen "
                 "sie fest ins Gerät ein und machen den Assistenten zum Tarif-Vorteil.",
        "anchors": ["perplexity", "gemini", "chatgpt", "openai", "copilot",
                    "le chat", "mistral", " claude ", "ai assistant", "ai-assistent",
                    "ki-assistent", "ki assistent", "ai phone", "ai-phone",
                    "natural ai", " adot ", "ai translation", "translation feature",
                    "personal ai", "ai companion", "ai-companion", "sprachassistent",
                    "gen-ai assistant", "smart assistant"],
        "vorbilder": [
            {"name": "Telekom · AI Phone", "desc": "18 Monate Perplexity Pro gratis – KI fest im Smartphone, eigener Magenta-Knopf."},
            {"name": "Free/Iliad (FR) · Le Chat Pro", "desc": "12 Monate Mistral-Premium-KI gratis für alle Mobilfunkkunden."},
            {"name": "SoftBank (JP)", "desc": "Perplexity Pro gratis plus exklusives, KI-natives Smartphone."},
            {"name": "Jio (IN)", "desc": "18 Monate Google Gemini AI Pro + 2 TB Cloud gratis zum Tarif."},
        ],
        "impuls": "Vodafone hat TOBi als Service-Bot, aber keinen kostenlosen Premium-"
                  "KI-Assistenten als Tarif-Bonus. Ein „Perplexity/Gemini/Mistral "
                  "gratis\"-Bundle wäre ein sofort verständliches Signal.",
    },
    {
        "key": "entertainment", "label": "Entertainment & Streaming", "color": "#c2185b",
        "blurb": "Streaming, Sport- und TV-Rechte als Bindungsanker. Die Besten "
                 "bündeln nicht nur ein Abo, sondern ein Aggregator-Erlebnis.",
        "anchors": ["netflix", "disney", "prime video", "amazon prime", "spotify",
                    "youtube premium", " dazn", "hbo max", "paramount", "apple tv",
                    "apple music", "viaplay", "crunchyroll", "fola play", "u-next",
                    "magentatv", "magenta tv", "tv rights", "tv-rechte", "sportrechte",
                    "world cup", "fifa", "champions league", "bundesliga",
                    "serie a", "free streaming", "streaming channel", "music streaming",
                    "streaming-dienst", "streaming service", "content bundle",
                    "entertainment bundle", "sport-streaming"],
        "vorbilder": [
            {"name": "Telekom · MagentaTV", "desc": "ein Interface und eine Fernbedienung über lineares TV und alle Streaming-Apps."},
            {"name": "Telia (Nordics) · Telia Play", "desc": "bündelt Netflix, Disney+, HBO Max, Viaplay & Sport in EINER durchsuchbaren App."},
            {"name": "EE (UK) · Inclusive Extras", "desc": "ein wählbarer Premium-Dienst pro Monat, alle 30 Tage tauschbar."},
            {"name": "Deutsche Telekom · WM-Rechte", "desc": "exklusive Sportrechte (FIFA-WM 2030) als Neukunden-Turbo."},
        ],
        "impuls": "Vodafone bündelt Disney+/Prime/YouTube als lose Add-ons. Nächster "
                  "Schritt: das Aggregator-Erlebnis – ein Interface über alle Dienste.",
    },
    {
        "key": "security", "label": "Security & Betrugsschutz", "color": "#2f8f5b",
        "blurb": "Schutz vor Betrug, Spam und Deepfakes wird vom Add-on zum Marken-"
                 "Asset – oft kostenlos und automatisch im Netz.",
        "anchors": ["secure net", "securenet", "norton", "mcafee", "f-secure",
                    " scam", "fraud detection", "betrugserkennung", "phishing",
                    "voice phishing", "anti-spam", "spam detection", "spam alert",
                    "antivirus", "cybersecure", "schutzpaket", "deepfake",
                    "identity protection", "identitätsschutz", "dark web",
                    "fake-anruf", "scam-schutz", "kinderschutz", "parental control",
                    "jugendschutz"],
        "vorbilder": [
            {"name": "Airtel (IN)", "desc": "KI-Spam-/Betrugserkennung direkt im Netz – gratis und automatisch für alle."},
            {"name": "KT (KR)", "desc": "erkennt KI-Fake-Stimmen (Deepfakes) am Telefon in Echtzeit."},
            {"name": "Orange (FR) · Cybersecure", "desc": "Schutzdienst, den sogar Nicht-Kunden nutzen können."},
            {"name": "Telekom · Digital-Schutzpaket", "desc": "ID-/Darkweb-Monitoring, Betrugsabsicherung, Hilfe bei Cybermobbing."},
        ],
        "impuls": "Vodafone hat Secure Net. Trend: weg vom Geräte-Antivirus, hin zu "
                  "netz-/identitätsbasiertem Schutz plus KI-Betrugserkennung.",
    },
    {
        "key": "fintech", "label": "Fintech & Payment", "color": "#c98a00",
        "blurb": "Wallet, Kredit, Versicherung und Banking direkt in der Telco-App – "
                 "in Wachstumsmärkten die stärksten Ökosysteme überhaupt.",
        "anchors": ["m-pesa", "mpesa", "vodapay", "paypay", "gcash", " maya ",
                    "paycell", " momo", "mobile money", "e-wallet", " wallet",
                    "digital bank", "payments bank", "paypal", " bnpl",
                    "buy now pay later", "microloan", "micro-loan", "micro-insurance",
                    "mikroversicherung", "digital wallet", "super-wallet",
                    "remittance", "geldbörse"],
        "vorbilder": [
            {"name": "Safaricom/Vodacom · M-Pesa & VodaPay", "desc": "Afrikas führendes Telco-Fintech – Wallet + 220+ Mini-Apps (eigene Vodafone-Familie!)."},
            {"name": "MTN (Afrika) · MoMo", "desc": "Fintech-Wallet, per Alipay-Partnerschaft zum Mini-App-Marktplatz ausgebaut."},
            {"name": "GCash / Maya (PH)", "desc": "aus Telcos entstandene Fintech-Unicorns."},
            {"name": "Turkcell (TR) · Paycell", "desc": "eigenes Bezahlsystem in der hauseigenen Digital-Suite."},
        ],
        "impuls": "Vodafone besitzt mit M-Pesa/VodaPay das stärkste Telco-Fintech – nur "
                  "in Afrika. Impuls: das Mini-App-Modell in europäische Apps übertragen.",
    },
    {
        "key": "superapp", "label": "Super-App & Ökosystem", "color": "#3860be",
        "blurb": "Die Telco-App wird von der Selfcare-App zur Alltags-Plattform mit "
                 "eingebauten Partner-Diensten.",
        "anchors": ["super app", "super-app", "superapp", "mini-app", "mini app",
                    "mini program", "mini-programm", "ayoba", "myjio", "mytelkomsel",
                    "max it", "one app", "oneapp", "everyday app", "capcut",
                    "video-editing", "content platform", "content-plattform",
                    "in-app", "rewards app", "lifestyle app", "digital hub",
                    "eingebaut in", "integriert die", "in die app", "into its app",
                    "in seine app", "app-ökosystem"],
        "vorbilder": [
            {"name": "Jio (IN) · MyJio", "desc": "eine App als Zugang zu Streaming, Musik, Shopping, Zahlung, Cloud, Games."},
            {"name": "Turkcell (TR)", "desc": "komplette eigene Digital-Suite (BiP, fizy, TV+, Lifebox, Paycell)."},
            {"name": "EE (UK) · EE-ID", "desc": "offene Login-ID, auch für Nicht-Kunden – „mehr als ein Netz\"."},
            {"name": "Orange · Max it (MEA)", "desc": "Super-App mit Konto, Money, Shopping, Musik, TV, Ticketing."},
        ],
        "impuls": "MeinVodafone könnte zur Alltags-Plattform werden: offene Login-ID, "
                  "Partner-Mini-Apps, Services über den Tarif hinaus.",
    },
    {
        "key": "cloud", "label": "Cloud & Speicher", "color": "#0d9488",
        "blurb": "Kostenloser, oft datensouveräner Cloud-Speicher als Tarif-Extra – "
                 "günstig und ein guter Bindungsanker.",
        "anchors": ["google one", "icloud", "cloud storage", "cloud-speicher",
                    "free storage", "gratis speicher", "fotospeicher", "photo storage",
                    "rakuten drive", "personal cloud", "mycloud", "onedrive bundle",
                    "backup-speicher", "gb gratis", "tb gratis"],
        "vorbilder": [
            {"name": "Rakuten (JP)", "desc": "50 GB Cloud-Speicher gratis zum Tarif."},
            {"name": "Jio (IN)", "desc": "großzügiger Gratis-Speicher im 5G-Angebot."},
            {"name": "Swisscom (CH) · myCloud", "desc": "Schweiz-gehostet – Datensouveränität als Argument."},
            {"name": "O2 (ES)", "desc": "Gratis-Speicher für Mobilfunkkunden, bis 10 TB."},
        ],
        "impuls": "EU-gehosteter Gratis-Cloud-Speicher als Tarif-Extra – zugleich "
                  "Vertrauens- und Bindungsanker, gerade im deutschen Markt.",
    },
    {
        "key": "smarthome", "label": "Smart Home & IoT", "color": "#b5551d",
        "blurb": "Sicherheit und Steuerung fürs Zuhause am Anschluss – margenstark und "
                 "bindet den ganzen Haushalt.",
        "anchors": ["smart home", "smarthome", "smart-home", "magenta home",
                    "home security", "überwachungskamera", "smart lock", "türschloss",
                    "thermostat", "connected home", "haussteuerung",
                    "hausautomation", "smart-home-paket", "alarmanlage"],
        "vorbilder": [
            {"name": "Telekom · Magenta Home", "desc": "eine App mit Routinen (Alarm, Anwesenheits-Simulation, Heizung)."},
            {"name": "au (JP) · au HOME", "desc": "Kamera, smartes Schloss, Sensoren, Notruf-Dienst."},
            {"name": "Movistar (ES)", "desc": "Alarmanlage (Prosegur-JV) plus digitaler Schutz."},
            {"name": "e& (VAE)", "desc": "Smart-Home-Überwachung und -Steuerung am Anschluss."},
        ],
        "impuls": "Smart-Home/-Security als margenstarke Zusatzwelt, die den Haushalt "
                  "an die Vodafone-Konnektivität bindet.",
    },
    {
        "key": "gaming", "label": "Gaming", "color": "#8a2be2",
        "blurb": "Cloud-Gaming als greifbarer Netz-Beweis – niedrige Latenz wird zum "
                 "Erlebnis statt zur Technik-Folie.",
        "anchors": ["game pass", "gamepass", "geforce now", "cloud gaming",
                    "cloud-gaming", " xbox", "playstation", " ps5", "esports",
                    "e-sports", "spiele-abo", "gaming-plattform", "gameloft",
                    "gaming bundle", "gaming-bundle", "spieleplattform"],
        "vorbilder": [
            {"name": "Telekom · 5G+ Gaming", "desc": "GeForce NOW gebündelt, über niedrige Latenz vermarktet."},
            {"name": "EE (UK)", "desc": "Game Pass als Extra plus Cloud-Gaming-Bundles mit Hardware."},
            {"name": "SK Telecom (KR)", "desc": "Xbox Game Pass im Abo-Marktplatz T Universe."},
            {"name": "MTN (Afrika) · Arcade", "desc": "Gaming-Abo mit Premium-Titeln zum Tagespreis."},
        ],
        "impuls": "Cloud-Gaming als Bundle (GeForce NOW / Game Pass) statt eigener "
                  "Plattform – kostengünstiger Beweis fürs Netz.",
    },
    {
        "key": "loyalty", "label": "Loyalty & Perks", "color": "#e07a00",
        "blurb": "Erlebnis-Perks und exklusive Vorverkäufe machen das tägliche "
                 "App-Öffnen zur Gewohnheit – Bindung über Nutzen.",
        "anchors": ["veryme", "magenta moments", "o2 priority", " priority ",
                    "rewards program", "treueprogramm", "loyalty program", "payback",
                    "tuesdays", "bonga", "cashback", "erlebnis-perks", "presale",
                    "vorteilsprogramm", "bonusprogramm", "kundenvorteil", "reward-app"],
        "vorbilder": [
            {"name": "O2 (UK) · Priority", "desc": "Goldstandard: Ticket-Vorverkäufe und tägliche, lokale Erlebnis-Perks."},
            {"name": "Telekom · Magenta Moments", "desc": "täglich wechselnde Vorteile, Trials, Konzert-Presales."},
            {"name": "KPN (NL) · Voor Jou", "desc": "wöchentliche Überraschungen als fester App-Anlass."},
            {"name": "Vodafone · VeryMe", "desc": "gute Basis – Ausbau Richtung Erlebnis/Presales fehlt."},
        ],
        "impuls": "Von O2 Priority lernen: exklusive Presales und tägliche, lokale "
                  "Erlebnis-Perks, die einen echten Grund geben, die App zu öffnen.",
    },
    {
        "key": "health", "label": "Health & Wellbeing", "color": "#2b7a9e",
        "blurb": "Telemedizin und Wellbeing als Differenzierung mit Nutzenversprechen – "
                 "in Wachstumsmärkten erprobt.",
        "anchors": ["telehealth", "telemedizin", "gesundheits-app", "gesundheitsapp",
                    "konsultamd", "d healthcare", "healthcare app", "wellbeing",
                    " calm ", "mental health app", "digital health app",
                    "fitness-abo", "gesundheitsdienst"],
        "vorbilder": [
            {"name": "NTT Docomo (JP) · d Healthcare", "desc": "belohnt Gesundheits-Missionen (Schritte, Blutdruck) mit Punkten – 18 Mio.+ Nutzer."},
            {"name": "Globe (PH) · KonsultaMD", "desc": "Telemedizin mit über 1 Mio. Nutzern im Telco-Ökosystem."},
        ],
        "impuls": "Gesundheits-Services (Telemedizin, Wellbeing) als Differenzierung "
                  "mit gesellschaftlichem Nutzen.",
    },
]

_THEME_BY_KEY = {t["key"]: t for t in DIFF_THEMES}
_ORDER = {t["key"]: i for i, t in enumerate(DIFF_THEMES)}


def _norm_tokens(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9äöüß]+", " ", text.lower()).strip() + " "


def _score(text: str) -> dict:
    raw = " " + " ".join(text.lower().split()) + " "
    tok = _norm_tokens(text)
    scores: dict[str, int] = {}
    for theme in DIFF_THEMES:
        n = 0
        for a in theme["anchors"]:
            if a.startswith(" ") or a.endswith(" "):
                if a in tok:
                    n += 1
            elif a in raw:
                n += 1
        if n:
            scores[theme["key"]] = n
    return scores


def _domain(url: str) -> str:
    return urlsplit(url or "").netloc.removeprefix("www.")


def _split_first(text: str) -> tuple[str, str]:
    t = " ".join((text or "").split())
    if not t:
        return "", ""
    for sep in (". ", "! ", "? "):
        k = t.find(sep)
        if 8 < k < 160:
            return t[:k + 1], t[k + 2:]
    return t, ""


def classify(hl: dict) -> str | None:
    """Ordne ein Highlight einem Differenzierungs-Hebel zu.

    Gibt den Theme-Key zurueck oder None, wenn es kein Differenzierungs-Move ist
    (reine Preis-/Netz-/B2B-/Finanz-Meldung oder kein Anchor-Treffer). Wird von
    build_differentiation UND vom Kurator (analyze/diff_curator.py) genutzt, damit
    Klassifikation und Persistenz dieselbe Logik teilen.
    """
    cat = (hl.get("category") or "").strip()
    if cat in NON_DIFF_CATEGORIES:
        return None
    text = f"{hl.get('title','')} {hl.get('summary','')}"
    if _EXCLUDE.search(text):
        return None
    scores = _score(text)
    if not scores:
        return None
    return sorted(scores.items(), key=lambda kv: (-kv[1], _ORDER[kv[0]]))[0][0]


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
        moves_by_theme[best].append({
            "op": hl.get("operator") or hl.get("source_label") or _domain(hl.get("url")),
            "de_title": de_title, "rest": rest,
            "summary": hl.get("summary"), "why": hl.get("why_it_matters"),
            "url": hl.get("url"), "region": hl.get("region"), "date": hl.get("date"),
            "cat": (hl.get("category") or "").strip(), "rel": hl.get("relevance") or 0,
            "domain": _domain(hl.get("url")), "color": theme["color"],
            "theme_label": theme["label"],
        })
        total += 1

    themes = []
    for t in DIFF_THEMES:
        # Relevanteste zuerst, Aktualität als Tiebreak: so bleibt ein starker
        # Move (z. B. Perplexity-Bundle, 5/5) auch nach Wochen oben stehen und
        # faellt nicht nur wegen des Datums aus der (gedeckelten) Anzeige.
        mv = sorted(moves_by_theme[t["key"]],
                    key=lambda m: (m["rel"], m.get("date") or ""), reverse=True)
        themes.append({**{k: t[k] for k in
                          ("key", "label", "color", "blurb", "vorbilder", "impuls")},
                       "moves": mv, "n": len(mv)})

    active = sorted([t for t in themes if t["n"]], key=lambda t: (-t["n"], _ORDER[t["key"]]))
    quiet = [t for t in themes if not t["n"]]
    top = sorted([m for t in active for m in t["moves"]],
                 key=lambda m: (m["rel"], m.get("date") or ""), reverse=True)[:3]
    return {"total": total, "n_active": len(active),
            "themes": themes, "active": active, "quiet": quiet, "top": top}
