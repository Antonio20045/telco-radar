"""Zweite Diagnose: liegt der Ausfall von v4-pro an UNSEREM Request?

Die erste Messung hat pro nur mit max_tokens=16 getestet. Bei einem
Reasoning-Modell ist das kein fairer Test - der Reasoning-Trace passt nicht in
16 Token. Dieses Skript isoliert jede Variable einzeln, statt sie zu mischen:

  A max_tokens   16 vs 1000 vs 5000 (was editor.py wirklich schickt)
  B thinking     chat_template_kwargs gesetzt / weggelassen
  C temperature  0.3 (unser Wert) vs 1.0
  D streaming    stream:true misst die Zeit bis zum ERSTEN Token
  E Geduld       240s statt 90s - langsam ist nicht dasselbe wie tot

Antwortet pro in irgendeiner dieser Varianten, liegt der Fehler in llm.py.
Gibt der Key niemals aus.
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
PROMPT = "Nenne drei Trends im Mobilfunkmarkt. Kurze Stichpunkte."


def head(t: str) -> None:
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78, flush=True)


def build(model, max_tokens, thinking=None, temperature=0.3, stream=False):
    p = {"model": model,
         "messages": [{"role": "user", "content": PROMPT}],
         "max_tokens": max_tokens,
         "temperature": temperature}
    if thinking is not None:
        p["chat_template_kwargs"] = {"thinking": thinking}
    if stream:
        p["stream"] = True
    return p


def blocking(label, payload, timeout):
    """Nicht-gestreamter Request - genau das, was llm.py heute macht."""
    t0 = time.monotonic()
    try:
        r = httpx.post(URL, json=payload, headers=HEADERS, timeout=timeout)
        dt = time.monotonic() - t0
        if r.status_code == 200:
            d = r.json()
            c = (d.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
            u = d.get("usage") or {}
            print(f"{label:52s} OK   {dt:6.1f}s  out={len(c):5d} Zeichen  "
                  f"completion_tokens={u.get('completion_tokens')}")
        else:
            print(f"{label:52s} HTTP {r.status_code} {dt:6.1f}s  {r.text[:170]}")
    except httpx.ReadTimeout:
        print(f"{label:52s} TIMEOUT nach {time.monotonic()-t0:6.1f}s")
    except Exception as exc:  # noqa: BLE001
        print(f"{label:52s} {type(exc).__name__} {time.monotonic()-t0:6.1f}s "
              f"{str(exc)[:150]}")
    sys.stdout.flush()


def streaming(label, payload, timeout):
    """Gestreamt: misst die Zeit bis zum ERSTEN Token.

    Der entscheidende Test. Kommt hier schnell ein Token, waehrend der
    blockierende Request haengt, ist das Modell gesund und unser Code falsch.
    """
    t0 = time.monotonic()
    first = None
    chars = 0
    try:
        with httpx.stream("POST", URL, json=payload, headers=HEADERS,
                          timeout=timeout) as r:
            if r.status_code != 200:
                body = r.read()[:170]
                print(f"{label:52s} HTTP {r.status_code} "
                      f"{time.monotonic()-t0:6.1f}s  {body}")
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
        ttft = f"{first:.1f}s" if first is not None else "nie"
        print(f"{label:52s} OK   {total:6.1f}s  erstes Token nach {ttft}, "
              f"{chars} Zeichen")
    except httpx.ReadTimeout:
        ttft = f"{first:.1f}s" if first is not None else "nie"
        print(f"{label:52s} TIMEOUT nach {time.monotonic()-t0:6.1f}s "
              f"(erstes Token: {ttft})")
    except Exception as exc:  # noqa: BLE001
        print(f"{label:52s} {type(exc).__name__} {time.monotonic()-t0:6.1f}s "
              f"{str(exc)[:150]}")
    sys.stdout.flush()


def main() -> None:
    if not KEY:
        print("LLM_API_KEY leer"); sys.exit(1)
    print(f"Endpunkt: {BASE} | Key-Laenge {len(KEY)}, Prefix {KEY[:5]}...")

    head("D  STREAMING - der entscheidende Test")
    print("Kommt gestreamt schnell ein Token, ist das Modell gesund und der")
    print("blockierende Request in llm.py ist das Problem.\n")
    streaming("PRO   stream, 1000 tok, thinking:False", 
              build(PRO, 1000, thinking=False, stream=True), 120)
    streaming("PRO   stream, 1000 tok, ohne kwargs",
              build(PRO, 1000, stream=True), 120)
    streaming("FLASH stream, 1000 tok (Kontrolle)",
              build(FLASH, 1000, thinking=False, stream=True), 120)

    head("A  max_tokens - war 16 einfach zu wenig fuer ein Reasoning-Modell?")
    blocking("PRO   16 tok, thinking:False (alter Test)",
             build(PRO, 16, thinking=False), 120)
    blocking("PRO   1000 tok, thinking:False",
             build(PRO, 1000, thinking=False), 120)
    blocking("PRO   5000 tok, thinking:False (wie editor.py)",
             build(PRO, 5000, thinking=False), 120)

    head("B/C  thinking-Flag und temperature")
    blocking("PRO   1000 tok, ohne chat_template_kwargs",
             build(PRO, 1000), 120)
    blocking("PRO   1000 tok, thinking:True",
             build(PRO, 1000, thinking=True), 120)
    blocking("PRO   1000 tok, temperature 1.0",
             build(PRO, 1000, thinking=False, temperature=1.0), 120)

    head("E  Geduld - langsam oder tot?")
    blocking("PRO   1000 tok, Timeout 240s",
             build(PRO, 1000, thinking=False), 240)

    head("Kontrolle FLASH (blockierend)")
    blocking("FLASH 1000 tok, thinking:False",
             build(FLASH, 1000, thinking=False), 120)
    blocking("FLASH 5000 tok, thinking:False",
             build(FLASH, 5000, thinking=False), 120)


if __name__ == "__main__":
    main()
