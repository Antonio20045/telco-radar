"""Vierte Diagnose: kann v4-flash den ECHTEN Editor-Prompt zuverlaessig bedienen?

Vorgeschichte der Messungen:
  Probe 2  v4-pro antwortet, braucht aber 60-200s Wartezeit in der Queue.
  Probe 3  mit dem echten 14k-Token-Editor-Prompt antwortet v4-pro in 2 von 5
           Faellen auch nach 600s nicht. Die Wartezeit haengt nicht an unserem
           Request (kleiner Prompt hing genauso), also ist kein Timeout-Wert
           sicher. Die flash-Kontrollzeile war wegen eines Auswertungsfehlers
           in probe3 ungueltig ("OK 0.3s kein Token").

Diese Messung schliesst genau diese Luecke: mehrere Wiederholungen auf flash mit
dem echten Editor-Prompt, und im Fehlerfall wird Statuscode UND Rohantwort
ausgegeben, statt einen leeren Stream als Erfolg zu zaehlen.

Gibt den Key niemals aus.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_probe3 import editor_payload  # noqa: E402

BASE = (os.environ.get("LLM_API_BASE") or "https://integrate.api.nvidia.com/v1").rstrip("/")
KEY = (os.environ.get("LLM_API_KEY") or "").strip().strip('"').strip("'").strip()
URL = f"{BASE}/chat/completions"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

FLASH = "deepseek-ai/deepseek-v4-flash"
PRO = "deepseek-ai/deepseek-v4-pro"
TIMEOUT = 300.0


def attempt(model: str, payload: dict, label: str) -> dict:
    """Ein blockierender Request mit vollstaendiger Fehlererfassung."""
    p = dict(payload, model=model)
    t0 = time.monotonic()
    out = {"label": label, "model": model, "ok": False, "seconds": 0.0,
           "detail": ""}
    try:
        r = httpx.post(URL, json=p, headers=HEADERS, timeout=TIMEOUT)
        out["seconds"] = time.monotonic() - t0
        if r.status_code != 200:
            out["detail"] = f"HTTP {r.status_code}: {r.text[:200]}"
            return out
        data = r.json()
        # Eine 200er Antwort ist NICHT automatisch ein Erfolg: der Endpunkt
        # liefert gelegentlich leere choices oder eine Fehlerstruktur mit 200.
        if "error" in data:
            out["detail"] = f"HTTP 200 mit Fehlerobjekt: {str(data['error'])[:200]}"
            return out
        choices = data.get("choices") or []
        if not choices:
            out["detail"] = f"HTTP 200 ohne choices: {json.dumps(data)[:200]}"
            return out
        msg = choices[0].get("message") or {}
        content = (msg.get("content") or "").strip()
        finish = choices[0].get("finish_reason")
        usage = data.get("usage") or {}
        if not content:
            out["detail"] = (f"HTTP 200 mit leerem content, finish_reason="
                             f"{finish}, usage={json.dumps(usage)}")
            return out
        out["ok"] = True
        out["detail"] = (f"{len(content)} Zeichen, {usage.get('completion_tokens')} "
                         f"Token, finish_reason={finish}")
        out["content"] = content
        return out
    except httpx.ReadTimeout:
        out["seconds"] = time.monotonic() - t0
        out["detail"] = "READ-TIMEOUT (kein Byte)"
        return out
    except Exception as exc:  # noqa: BLE001
        out["seconds"] = time.monotonic() - t0
        out["detail"] = f"{type(exc).__name__}: {str(exc)[:180]}"
        return out


def series(model: str, payload: dict, label: str, n: int) -> None:
    print(f"\n--- {label} ({n} Versuche, Timeout {TIMEOUT:.0f}s) ---", flush=True)
    ok = 0
    times = []
    for i in range(1, n + 1):
        res = attempt(model, payload, label)
        times.append(res["seconds"])
        flag = "OK  " if res["ok"] else "FEHL"
        print(f"  {i}/{n} {flag} {res['seconds']:6.1f}s  {res['detail']}",
              flush=True)
        if res["ok"]:
            ok += 1
            if ok == 1:
                first_lines = "\n      ".join(res["content"].splitlines()[:4])
                print(f"      Anfang der Antwort: {first_lines}", flush=True)
    print(f"  => {ok}/{n} erfolgreich, Zeiten "
          f"{min(times):.0f}-{max(times):.0f}s", flush=True)


def main() -> None:
    if not KEY:
        print("LLM_API_KEY leer"); sys.exit(1)
    print(f"Endpunkt: {BASE} | Key-Laenge {len(KEY)}")

    full = editor_payload()                 # 6 Regionen, 15 Items, 300 Themen
    slim = editor_payload(6, 8, 60)         # gekuerzt: weniger Items und Themen

    print("\n" + "=" * 78)
    print("FLASH mit dem echten Editor-Prompt - die offene Frage")
    print("=" * 78)
    series(FLASH, full, "FLASH, voller Editor-Prompt (14k Token, 5000 out)", 5)
    series(FLASH, slim, "FLASH, gekuerzter Editor-Prompt", 3)

    print("\n" + "=" * 78)
    print("PRO zum Vergleich, gleiche Bedingungen")
    print("=" * 78)
    series(PRO, full, "PRO, voller Editor-Prompt", 3)

    print("\n" + "=" * 78)
    print("Fazit-Hilfe")
    print("=" * 78)
    print("Traegt FLASH den vollen Prompt zuverlaessig, gehoert der Editor dorthin.")
    print("Traegt es nur den gekuerzten, muss der Prompt kleiner werden.")
    print("Traegt es keinen von beiden, reicht dieser Endpunkt nicht und die")
    print("Redaktionsstufe braucht einen anderen Anbieter.")


if __name__ == "__main__":
    main()
