"""Thin Anthropic Messages API client (no SDK dependency, just httpx)."""
from __future__ import annotations

import json
import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def complete(system: str, user: str, model: str,
             max_tokens: int = 4096, retries: int = 5) -> str:
    """Single-turn completion. Raises RuntimeError after exhausting retries."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "content-type": "application/json",
    }

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = httpx.post(API_URL, json=payload, headers=headers, timeout=180)
            if resp.status_code in (429, 529) or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"retryable status {resp.status_code}",
                    request=resp.request, response=resp)
            resp.raise_for_status()
            data = resp.json()
            return "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            last_err = exc
            wait = min(12 * attempt, 45)  # 529/overload needs patience
            log.warning("LLM call failed (attempt %d/%d): %s - retrying in %ds",
                        attempt, retries, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"LLM call failed after {retries} attempts: {last_err}")


def extract_json(text: str):
    """Parse JSON from an LLM response, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0),
                default=-1)
    if start > 0:
        text = text[start:]
    return json.loads(text)
