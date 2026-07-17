"""LLM client.

Two backends, chosen by environment:
  * OpenAI-compatible chat-completions endpoint  -> used when LLM_API_KEY is set
    (works for Moonshot/Kimi, DeepSeek, NVIDIA NIM, Gemini-OpenAI, Groq, ...)
  * Anthropic Messages API                        -> fallback (ANTHROPIC_API_KEY)

This keeps the provider swappable with one env var + the base URL, without
touching the agents. Public telco news only, so a non-Anthropic model is fine.
"""
from __future__ import annotations

import json
import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TEMPERATURE = 0.3


def _openai_base() -> str:
    return (os.environ.get("LLM_API_BASE") or "").rstrip("/")


def _use_openai() -> bool:
    return bool(os.environ.get("LLM_API_KEY") and _openai_base())


def llm_available() -> bool:
    return _use_openai() or bool(os.environ.get("ANTHROPIC_API_KEY"))


def active_backend() -> str:
    if _use_openai():
        return f"openai-compatible ({_openai_base()})"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "none"


# Client errors that will never succeed on retry (bad key, bad request, bad model)
_FATAL_STATUSES = {400, 401, 403, 404, 405, 422}


class _FatalHTTP(Exception):
    pass


def _post_with_retries(url, payload, headers, retries, parse):
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=180)
            if resp.status_code in _FATAL_STATUSES:
                raise _FatalHTTP(f"HTTP {resp.status_code}: {resp.text[:300]}")
            if resp.status_code in (429, 529) or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"retryable status {resp.status_code}: {resp.text[:200]}",
                    request=resp.request, response=resp)
            resp.raise_for_status()
            return parse(resp.json())
        except _FatalHTTP as exc:
            # no point retrying - surface immediately so the run fails fast
            log.error("LLM call fatal (no retry): %s", str(exc)[:300])
            raise RuntimeError(f"LLM fatal error: {exc}")
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
            last_err = exc
            wait = min(4 * attempt, 12)
            log.warning("LLM call failed (attempt %d/%d): %s - retrying in %ds",
                        attempt, retries, str(exc)[:160], wait)
            time.sleep(wait)
    raise RuntimeError(f"LLM call failed after {retries} attempts: {last_err}")


def _complete_openai(system: str, user: str, model: str,
                     max_tokens: int, retries: int) -> str:
    key = os.environ["LLM_API_KEY"].strip().strip('"').strip("'").strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": DEFAULT_TEMPERATURE,
    }
    if "deepseek" in model.lower():
        # NVIDIA DeepSeek NIM: turn off the reasoning trace (clean output, cheaper)
        payload["chat_template_kwargs"] = {"thinking": False}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def parse(data):
        return data["choices"][0]["message"].get("content", "") or ""

    return _post_with_retries(_openai_base() + "/chat/completions",
                              payload, headers, retries, parse)


def _complete_anthropic(system: str, user: str, model: str,
                        max_tokens: int, retries: int) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    def parse(data):
        return "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")

    return _post_with_retries(ANTHROPIC_URL, payload, headers, retries, parse)


def complete(system: str, user: str, model: str,
             max_tokens: int = 4096, retries: int = 5) -> str:
    """Single-turn completion via the active backend."""
    if _use_openai():
        return _complete_openai(system, user, model, max_tokens, retries)
    return _complete_anthropic(system, user, model, max_tokens, retries)


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
