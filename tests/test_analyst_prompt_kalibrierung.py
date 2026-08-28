"""Die Kalibrierungsregeln des Analysten-Prompts (Strategie E8, 27.08.2026).

Befund vom 27.08.2026: der Analyst vergab Top-Relevanz an einen
UK-Nischenanbieter (Nufibre eSIM, 15 Pfund - wurde Aufmacher) und
relevance=4/category="Sonstiges" an "iPhone 17 weltweit meistverkauft".
Drei Regeln sollen das kuenftig verhindern: (a) Relevanz 5 verlangt grosses
Marktgewicht des Absenders ODER unmittelbare Bedeutung fuer den deutschen/
europaeischen Endkundenmarkt - ein Nischenanbieter ohne Marktfolge ist bei
3 gedeckelt; (b) globale Geraete-/Marktmeldungen gehoeren in die Kategorie
"Produktlaunch" (die einzige Kategorie des Schemas, die zu einem Produkt
passt - "Geraete" gibt es als Highlight-Kategorie nicht), nicht "Sonstiges";
(c) Endkunden-Relevanz wiegt schwerer als Vendor-PR/AGM/Infrastruktur-
Finanzierung.

Mehr als den Text zu pruefen geht offline nicht - kein LLM steht hier zur
Verfuegung. Ob die Regeln beim Modell wirklich ankommen (insbesondere bei
deepseek-v4-flash, das kuenftig fuer die Vorsortierung laeuft und schwaecher
ist als pro), ist erst nach dem naechsten Actions-Lauf zu sehen (Strategie
§4 Messplan, Punkt 6: "fuehrt die hoechste Prioritaet, sind die EE-artigen
Dubletten gebuendelt?")."""
from __future__ import annotations

from telco_radar.analyze.agents import ANALYST_SYSTEM, TECH_ANALYST_SYSTEM


def test_relevanz_5_verlangt_marktgewicht_oder_heimatmarktbezug():
    for prompt in (ANALYST_SYSTEM, TECH_ANALYST_SYSTEM):
        assert "capped at 3" in prompt
        assert "followership" in prompt
        assert "German/" in prompt and "European consumer market" in prompt


def test_globale_geraetemeldung_ist_produktlaunch_nicht_sonstiges():
    for prompt in (ANALYST_SYSTEM, TECH_ANALYST_SYSTEM):
        assert "best-selling phone worldwide" in prompt
        assert '"Produktlaunch", never "Sonstiges"' in prompt


def test_endkundenbezug_wiegt_schwerer_als_vendor_pr():
    for prompt in (ANALYST_SYSTEM, TECH_ANALYST_SYSTEM):
        assert "outweighs vendor PR" in prompt
        assert "AGM notices" in prompt
        assert "infrastructure-financing" in prompt


def test_die_kategorie_geraete_gibt_es_im_schema_nicht():
    """Gegenprobe zur Wortwahl der Strategie ("Kategorie Geraete"): das
    Antwortschema kennt diese Kategorie nicht, die Regel muss also auf eine
    bestehende Kategorie zeigen (Produktlaunch) - sonst waere sie eine
    Anweisung, die das Modell nicht erfuellen kann."""
    for prompt in (ANALYST_SYSTEM, TECH_ANALYST_SYSTEM):
        assert "Geräte" not in prompt
        assert "one of: Produktlaunch | Tarif/Pricing" in prompt
