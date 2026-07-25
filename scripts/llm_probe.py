"""Diagnose des LLM-Providers.

Beantwortet genau eine Frage: antwortet der konfigurierte Endpunkt auf die
Modelle, die config/settings.yaml verwendet - und wenn nicht, woran es liegt.

Gibt niemals den API-Key aus. Nur Statuscodes, Laufzeiten und gekuerzte
Fehlertexte landen im Log.
"""
from __future__ import annotations

import os
import sys
import time

import httpx

BASE = (os.environ.get("LLM_API_BASE") or "https://integrate.api.nvidia.com/v1").rstrip("/")
KEY = (os.environ.get("LLM_API_KEY") or "").strip().strip('"').strip("'").strip()

PROBE_TIMEOUT = 90.0
PRO = "deepseek-ai/deepseek-v4-pro"
FLASH = "deepseek-ai/deepseek-v4-flash"


def head(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72, flush=True)


def key_shape() -> None:
    head("1. Key-Form (ohne Inhalt)")
    if not KEY:
        print("LLM_API_KEY ist LEER -> Abbruch")
        sys.exit(1)
    print(f"Laenge            : {len(KEY)}")
    print(f"Prefix            : {KEY[:5]}...")
    print(f"Nur ASCII         : {KEY.isascii()}")
    print(f"Whitespace innen  : {any(c.isspace() for c in KEY)}")
    print(f"Endpunkt          : {BASE}", flush=True)


def list_models() -> set[str]:
    head("2. GET /models - welche Slugs bedient der Endpunkt wirklich?")
    ids: set[str] = set()
    try:
        t0 = time.monotonic()
        r = httpx.get(f"{BASE}/models",
                      headers={"Authorization": f"Bearer {KEY}"},
                      timeout=30)
        dt = time.monotonic() - t0
        print(f"HTTP {r.status_code} in {dt:.1f}s")
        if r.status_code == 200:
            ids = {m.get("id", "") for m in r.json().get("data", [])}
            print(f"Modelle insgesamt : {len(ids)}")
            for name in (PRO, FLASH):
                print(f"  {name:38s} -> {'GELISTET' if name in ids else 'NICHT GELISTET'}")
            print("  deepseek-Slugs im Katalog:")
            for m in sorted(x for x in ids if "deepseek" in x.lower()):
                print(f"    - {m}")
        else:
            print(f"Body: {r.text[:400]}")
    except Exception as exc:  # noqa: BLE001
        print(f"FEHLER: {type(exc).__name__}: {str(exc)[:300]}")
    sys.stdout.flush()
    return ids


def probe(label: str, model: str, thinking_off: bool, max_tokens: int = 16) -> None:
    """Ein minimaler Chat-Call. Misst die Zeit bis zur vollen Antwort."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Antworte mit genau dem Wort: OK"}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    if thinking_off:
        payload["chat_template_kwargs"] = {"thinking": False}
    t0 = time.monotonic()
    try:
        r = httpx.post(f"{BASE}/chat/completions", json=payload,
                       headers={"Authorization": f"Bearer {KEY}",
                                "Content-Type": "application/json"},
                       timeout=PROBE_TIMEOUT)
        dt = time.monotonic() - t0
        if r.status_code == 200:
            data = r.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
            usage = data.get("usage") or {}
            print(f"{label:44s} HTTP 200 in {dt:6.1f}s | out={content.strip()[:40]!r}"
                  f" | tokens={usage.get('completion_tokens')}")
        else:
            print(f"{label:44s} HTTP {r.status_code} in {dt:6.1f}s | {r.text[:220]}")
    except httpx.ReadTimeout:
        print(f"{label:44s} READ-TIMEOUT nach {time.monotonic()-t0:6.1f}s"
              f" (Verbindung stand, Modell lieferte nichts)")
    except Exception as exc:  # noqa: BLE001
        print(f"{label:44s} {type(exc).__name__} nach {time.monotonic()-t0:6.1f}s"
              f" | {str(exc)[:200]}")
    sys.stdout.flush()


def main() -> None:
    key_shape()
    ids = list_models()

    head(f"3. Minimal-Calls, 16 Token, Timeout {PROBE_TIMEOUT:.0f}s")
    print("Antwortet FLASH und PRO nicht, ist der Key gueltig und das Problem")
    print("liegt am Modell bzw. seiner Kapazitaet - nicht am Schluessel.\n")
    probe("FLASH + thinking:False (wie Analysten)", FLASH, True)
    probe("PRO   + thinking:False (wie Editor)", PRO, True)
    probe("PRO   ohne chat_template_kwargs", PRO, False)
    probe("PRO   zweiter Versuch", PRO, True)

    head("4. Gegenprobe: Editor-artige Last auf FLASH")
    probe("FLASH 400 Token Ausgabe", FLASH, True, max_tokens=400)

    head("Fazit-Hilfe")
    if ids and PRO not in ids:
        print(f"-> {PRO} ist am Endpunkt NICHT gelistet: der Slug ist die Ursache.")
    elif ids:
        print("-> Slug ist gelistet. Entscheidend sind die Laufzeiten unter 3.")
    else:
        print("-> /models nicht abrufbar, siehe Statuscode unter 2.")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
