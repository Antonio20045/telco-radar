"""Differenzierungs-Hebel: welche Meldung zu welchem Hebel gehört.

Die Anker je Hebel und die Ausschlüsse entscheiden ohne LLM. Anzeige
(``report/differentiation``) und Kurator (``diff_curator``) teilen diese
eine Klassifikation; Farben, Texte und Vorbilder bleiben in der Anzeige.
"""

from __future__ import annotations

import re

NON_DIFF_CATEGORIES = {
    "Tarif/Pricing",
    "Verbal/Pricing",
    "Finanzen",
    "Regulierung",
    "Personal",
    "Sonstiges",
    "Strategie",
}

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

ANKER: dict[str, list[str]] = {
    "garantie": [
        "warranty",
        "garantie",
        "gewährleistung",
        "price lock",
        "preisgarantie",
        "price guarantee",
        "5-year price",
        "lifetime service",
        "service promise",
        "service-versprechen",
        "money-back",
        "geld-zurück",
        "zufriedenheitsgarantie",
        "battery replacement",
        "akkutausch",
        "reparaturgarantie",
        "network guarantee",
        "netzgarantie",
        "happiness guarantee",
        "device protection",
        "geräteschutz",
        "schutzbrief",
        "coverage guarantee",
    ],
    "geraete": [
        "trade-in",
        "trade in",
        "inzahlungnahme",
        "eintausch",
        "refurbished",
        "generalüberholt",
        "gebrauchtgerät",
        "annual upgrade",
        "jährliches upgrade",
        "upgrade program",
        "upgrade-programm",
        "gerätewechsel",
        "carrier-exclusive",
        "exclusive phone",
        "own-brand phone",
        "device as a service",
        "gerät im abo",
        "hardware-abo",
        "kinder-smartwatch",
        "kids watch",
        "wearable bundle",
        "phone freedom",
        "foldable bundle",
    ],
    "ki": [
        "perplexity",
        "gemini",
        "chatgpt",
        "openai",
        "copilot",
        "le chat",
        "mistral",
        " claude ",
        "ai assistant",
        "ai-assistent",
        "ki-assistent",
        "ki assistent",
        "ai phone",
        "ai-phone",
        "natural ai",
        " adot ",
        "ai translation",
        "translation feature",
        "personal ai",
        "ai companion",
        "ai-companion",
        "sprachassistent",
        "gen-ai assistant",
        "smart assistant",
    ],
    "entertainment": [
        "netflix",
        "disney",
        "prime video",
        "amazon prime",
        "spotify",
        "youtube premium",
        " dazn",
        "hbo max",
        "paramount",
        "apple tv",
        "apple music",
        "viaplay",
        "crunchyroll",
        "fola play",
        "u-next",
        "magentatv",
        "magenta tv",
        "tv rights",
        "tv-rechte",
        "sportrechte",
        "world cup",
        "fifa",
        "champions league",
        "bundesliga",
        "serie a",
        "free streaming",
        "streaming channel",
        "music streaming",
        "streaming-dienst",
        "streaming service",
        "content bundle",
        "entertainment bundle",
        "sport-streaming",
    ],
    "security": [
        "secure net",
        "securenet",
        "norton",
        "mcafee",
        "f-secure",
        " scam",
        "fraud detection",
        "betrugserkennung",
        "phishing",
        "voice phishing",
        "anti-spam",
        "spam detection",
        "spam alert",
        "antivirus",
        "cybersecure",
        "schutzpaket",
        "deepfake",
        "identity protection",
        "identitätsschutz",
        "dark web",
        "fake-anruf",
        "scam-schutz",
        "kinderschutz",
        "parental control",
        "jugendschutz",
    ],
    "fintech": [
        "m-pesa",
        "mpesa",
        "vodapay",
        "paypay",
        "gcash",
        " maya ",
        "paycell",
        " momo",
        "mobile money",
        "e-wallet",
        " wallet",
        "digital bank",
        "payments bank",
        "paypal",
        " bnpl",
        "buy now pay later",
        "microloan",
        "micro-loan",
        "micro-insurance",
        "mikroversicherung",
        "digital wallet",
        "super-wallet",
        "remittance",
        "geldbörse",
    ],
    "superapp": [
        "super app",
        "super-app",
        "superapp",
        "mini-app",
        "mini app",
        "mini program",
        "mini-programm",
        "ayoba",
        "myjio",
        "mytelkomsel",
        "max it",
        "one app",
        "oneapp",
        "everyday app",
        "capcut",
        "video-editing",
        "content platform",
        "content-plattform",
        "in-app",
        "rewards app",
        "lifestyle app",
        "digital hub",
        "eingebaut in",
        "integriert die",
        "in die app",
        "into its app",
        "in seine app",
        "app-ökosystem",
    ],
    "cloud": [
        "google one",
        "icloud",
        "cloud storage",
        "cloud-speicher",
        "free storage",
        "gratis speicher",
        "fotospeicher",
        "photo storage",
        "rakuten drive",
        "personal cloud",
        "mycloud",
        "onedrive bundle",
        "backup-speicher",
        "gb gratis",
        "tb gratis",
    ],
    "smarthome": [
        "smart home",
        "smarthome",
        "smart-home",
        "magenta home",
        "home security",
        "überwachungskamera",
        "smart lock",
        "türschloss",
        "thermostat",
        "connected home",
        "haussteuerung",
        "hausautomation",
        "smart-home-paket",
        "alarmanlage",
    ],
    "gaming": [
        "game pass",
        "gamepass",
        "geforce now",
        "cloud gaming",
        "cloud-gaming",
        " xbox",
        "playstation",
        " ps5",
        "esports",
        "e-sports",
        "spiele-abo",
        "gaming-plattform",
        "gameloft",
        "gaming bundle",
        "gaming-bundle",
        "spieleplattform",
    ],
    "loyalty": [
        "veryme",
        "magenta moments",
        "o2 priority",
        " priority ",
        "rewards program",
        "treueprogramm",
        "loyalty program",
        "payback",
        "tuesdays",
        "bonga",
        "cashback",
        "erlebnis-perks",
        "presale",
        "vorteilsprogramm",
        "bonusprogramm",
        "kundenvorteil",
        "reward-app",
    ],
    "health": [
        "telehealth",
        "telemedizin",
        "gesundheits-app",
        "gesundheitsapp",
        "konsultamd",
        "d healthcare",
        "healthcare app",
        "wellbeing",
        " calm ",
        "mental health app",
        "digital health app",
        "fitness-abo",
        "gesundheitsdienst",
    ],
}

_ORDER = {key: i for i, key in enumerate(ANKER)}


def _norm_tokens(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9äöüß]+", " ", text.lower()).strip() + " "


def _score(text: str) -> dict:
    raw = " " + " ".join(text.lower().split()) + " "
    tok = _norm_tokens(text)
    scores: dict[str, int] = {}
    for key, anker in ANKER.items():
        n = 0
        for a in anker:
            if a.startswith(" ") or a.endswith(" "):
                if a in tok:
                    n += 1
            elif a in raw:
                n += 1
        if n:
            scores[key] = n
    return scores


def classify(hl: dict) -> str | None:
    """Ordne ein Highlight einem Differenzierungs-Hebel zu.

    Gibt den Theme-Key zurueck oder None, wenn es kein Differenzierungs-Move ist
    (reine Preis-/Netz-/B2B-/Finanz-Meldung oder kein Anchor-Treffer). Die
    Anzeige und der Kurator rufen dieselbe Funktion, damit Klassifikation und
    Persistenz dieselbe Logik teilen.
    """
    cat = (hl.get("category") or "").strip()
    if cat in NON_DIFF_CATEGORIES:
        return None
    text = f"{hl.get('title', '')} {hl.get('summary', '')}"
    if _EXCLUDE.search(text):
        return None
    scores = _score(text)
    if not scores:
        return None
    return sorted(scores.items(), key=lambda kv: (-kv[1], _ORDER[kv[0]]))[0][0]
