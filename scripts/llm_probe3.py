"""Dritte Diagnose: wie lange braucht v4-pro fuer einen ECHTEN Editor-Prompt?

Probe 2 hat gezeigt, dass v4-pro antwortet, aber 60-200s in der Provider-Queue
steht - fast die gesamte Zeit ist Wartezeit bis zum ersten Token, die Generierung
selbst dauert Sekundenbruchteile. Damit ist die Ursache ein zu kurzes Timeout in
llm.py, nicht ein defektes Modell.

Offene Frage: skaliert diese Wartezeit mit der Prompt-Groesse? Der Editor schickt
alle Regionalanalysen plus 300 gemerkte Themen und will 5000 Token zurueck. Diese
Messung baut einen Prompt in genau dieser Groessenordnung und misst mit grosszuegigem
Timeout, damit die Zahl fuer das neue Timeout gemessen und nicht geraten ist.

Gibt den Key niemals aus.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

BASE = (os.environ.get("LLM_API_BASE") or "https://integrate.api.nvidia.com/v1").rstrip("/")
KEY = (os.environ.get("LLM_API_KEY") or "").strip().strip('"').strip("'").strip()
URL = f"{BASE}/chat/completions"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

PRO = "deepseek-ai/deepseek-v4-pro"
FLASH = "deepseek-ai/deepseek-v4-flash"
PATIENT = 600.0


SYSTEM = (
    "Du bist Chefredakteur eines woechentlichen Wettbewerbsberichts fuer die "
    "Telekommunikationsbranche. Schreibe auf Deutsch, sachlich, ohne Floskeln. "
    "Struktur: ## Das Wichtigste, ## Die wichtigsten Signale, ## Muster der Woche."
)


def editor_payload(n_regions: int = 6, per_region: int = 15,
                   n_topics: int = 300) -> dict:
    """Baut einen Prompt in der Groessenordnung des echten Editor-Aufrufs."""
    regions = {}
    for r in range(n_regions):
        name = f"Region {r + 1}"
        regions[name] = [{
            "operator": f"Betreiber {r}-{i}",
            "title": f"Betreiber {r}-{i} startet neues Angebot fuer Geschaeftskunden",
            "url": f"https://example.com/{r}/{i}",
            "category": "Produkt",
            "relevance": 4,
            "urgency": 3,
            "assessment": ("Der Betreiber buendelt Konnektivitaet mit einer "
                           "Software-Plattform und adressiert damit mittelstaendische "
                           "Kunden. Preis und Verfuegbarkeit sind genannt, der "
                           "Rollout laeuft ueber zwei Quartale."),
        } for i in range(per_region)]
    topics = [f"Bereits berichtetes Thema Nummer {i} zu Netzausbau und Tarifen"
              for i in range(n_topics)]
    user = json.dumps({"regional_analyses": regions, "already_covered": topics},
                      ensure_ascii=False)
    return {
        "model": PRO,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
        "max_tokens": 5000,
        "temperature": 0.3,
        "chat_template_kwargs": {"thinking": False},
    }


def run(label: str, payload: dict, stream: bool, timeout: float) -> None:
    p = dict(payload)
    if stream:
        p["stream"] = True
    approx_in = sum(len(m["content"]) for m in p["messages"]) // 4
    t0 = time.monotonic()
    first = None
    chars = 0
    try:
        if not stream:
            r = httpx.post(URL, json=p, headers=HEADERS, timeout=timeout)
            dt = time.monotonic() - t0
            if r.status_code != 200:
                print(f"{label:44s} HTTP {r.status_code} {dt:7.1f}s {r.text[:150]}")
                return
            d = r.json()
            c = (d.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
            u = d.get("usage") or {}
            print(f"{label:44s} OK {dt:7.1f}s  in~{approx_in} tok  "
                  f"out={u.get('completion_tokens')} tok / {len(c)} Zeichen")
            return
        with httpx.stream("POST", URL, json=p, headers=HEADERS, timeout=timeout) as r:
            if r.status_code != 200:
                print(f"{label:44s} HTTP {r.status_code} "
                      f"{time.monotonic()-t0:7.1f}s {r.read()[:150]}")
                return
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = (json.loads(data).get("choices") or [{}])[0].get("delta", {})
                except json.JSONDecodeError:
                    continue
                piece = delta.get("content") or delta.get("reasoning_content") or ""
                if piece and first is None:
                    first = time.monotonic() - t0
                chars += len(piece)
        total = time.monotonic() - t0
        gen = total - first if first is not None else 0.0
        print(f"{label:44s} OK {total:7.1f}s  in~{approx_in} tok  "
              f"Warten bis 1. Token {first:.1f}s + Generierung {gen:.1f}s  "
              f"{chars} Zeichen" if first is not None else
              f"{label:44s} OK {total:7.1f}s  kein Token")
    except httpx.ReadTimeout:
        ttft = f"{first:.1f}s" if first is not None else "nie"
        print(f"{label:44s} TIMEOUT {time.monotonic()-t0:7.1f}s (1. Token: {ttft})")
    except Exception as exc:  # noqa: BLE001
        print(f"{label:44s} {type(exc).__name__} {time.monotonic()-t0:7.1f}s "
              f"{str(exc)[:150]}")
    sys.stdout.flush()


def main() -> None:
    if not KEY:
        print("LLM_API_KEY leer"); sys.exit(1)
    print(f"Endpunkt: {BASE} | Key-Laenge {len(KEY)}\n")

    full = editor_payload()
    print("=" * 78)
    print("Echter Editor-Prompt auf v4-pro, gestreamt, Timeout 600s")
    print("=" * 78, flush=True)
    run("PRO  Editor-Prompt, stream", full, True, PATIENT)
    run("PRO  Editor-Prompt, stream, 2. Messung", full, True, PATIENT)
    run("PRO  Editor-Prompt, blockierend", full, False, PATIENT)

    print("\n" + "=" * 78)
    print("Skaliert die Wartezeit mit der Prompt-Groesse?")
    print("=" * 78, flush=True)
    run("PRO  kleiner Prompt (1 Region, 0 Themen)",
        editor_payload(1, 3, 0), True, PATIENT)
    run("PRO  halber Prompt (3 Regionen, 150 Themen)",
        editor_payload(3, 15, 150), True, PATIENT)

    print("\n" + "=" * 78)
    print("Kontrolle: derselbe Prompt auf v4-flash")
    print("=" * 78, flush=True)
    flash_payload = dict(full, model=FLASH)
    run("FLASH Editor-Prompt, stream", flash_payload, True, PATIENT)

    print("\n" + "=" * 78)
    print("Fazit-Hilfe: das neue Timeout muss ueber der langsamsten Zeile liegen,")
    print("mit Reserve. Reines Warten in der Queue, keine Rechenzeit.")
    print("=" * 78)


if __name__ == "__main__":
    main()
