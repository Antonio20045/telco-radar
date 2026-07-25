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

# Read timeout for a single request. Measured on 2026-07-25 against
# integrate.api.nvidia.com with the real editor prompt: a served request answers
# in 8-21s, so 180s is generous. Lowering this to 75s (as an earlier attempt did)
# only turns slow successes into failures - it does not help.
DEFAULT_HTTP_TIMEOUT = 180.0

# Wall clock for ONE logical completion, across all its retries. Replaces the
# old "fixed number of attempts" budget, which behaved completely differently
# depending on whether the failures were instant or slow.
DEFAULT_CALL_BUDGET = 300.0

# The two failure modes cost wildly different amounts of time, and the old code
# treated them the same - which was the actual bug behind runs #29-#34:
#
#   cheap  HTTP 503 "ResourceExhausted: Worker local total request limit
#          reached" comes back in 0.3-0.4s. It means "busy, ask again", and
#          retrying is nearly free. The old policy gave up after 3 tries and
#          ~24s of backoff on exactly this.
#   slow   a read timeout burns the full HTTP timeout with nothing to show.
#          The old policy happily spent 3x180s = 9.4 min on it, per stage.
#
# So: retry the cheap failures generously, the slow ones barely at all.
MAX_SLOW_FAILURES = 2
CHEAP_BACKOFF_SECONDS = (1, 2, 3, 5, 5, 8, 8, 10)

# model -> stand-in, consulted only after the preferred model failed hard.
_FALLBACKS: dict[str, str] = {}
# Models that already failed hard in this process. Later stages skip them
# instead of retrying, so a dead model costs the run ONE timeout budget
# rather than one per stage.
_DEAD_MODELS: set[str] = set()


class _FatalHTTP(Exception):
    pass


class LLMFatalError(RuntimeError):
    """The provider rejected the request itself (bad key, model or payload).

    Distinct from a capacity/timeout failure, because falling back to another
    model cannot help here.
    """


def http_timeout() -> float:
    """Per-request read timeout; override with LLM_HTTP_TIMEOUT (seconds)."""
    try:
        value = float(os.environ.get("LLM_HTTP_TIMEOUT") or DEFAULT_HTTP_TIMEOUT)
    except ValueError:
        return DEFAULT_HTTP_TIMEOUT
    return value if value > 0 else DEFAULT_HTTP_TIMEOUT


def call_budget() -> float:
    """Wall clock for one completion incl. retries; LLM_CALL_BUDGET overrides."""
    try:
        value = float(os.environ.get("LLM_CALL_BUDGET") or DEFAULT_CALL_BUDGET)
    except ValueError:
        return DEFAULT_CALL_BUDGET
    return value if value > 0 else DEFAULT_CALL_BUDGET


def set_fallback(model: str, fallback: str) -> None:
    """Register `fallback` as the stand-in for `model`."""
    if model and fallback and model != fallback:
        _FALLBACKS[model] = fallback


def reset_model_health() -> None:
    """Forget which models failed. Only needed by tests."""
    _DEAD_MODELS.clear()


def dead_models() -> set[str]:
    """Models that stopped answering during this run (for the run protocol)."""
    return set(_DEAD_MODELS)


def _post_with_retries(url, payload, headers, retries, parse):
    """Retry until the time budget is spent, weighted by what each failure cost.

    `retries` is kept for call-site compatibility but now only caps the slow
    failures; the cheap "server is busy" retries are governed by the budget.
    """
    budget = call_budget()
    deadline = time.monotonic() + budget
    slow_failures = 0
    cheap_failures = 0
    last_err: Exception | None = None
    attempt = 0

    while True:
        attempt += 1
        started = time.monotonic()
        try:
            resp = httpx.post(url, json=payload, headers=headers,
                              timeout=http_timeout())
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
            raise LLMFatalError(f"LLM fatal error: {exc}")
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
            last_err = exc
            elapsed = time.monotonic() - started
            # A failure that came back fast is a capacity signal, not a broken
            # request: ask again. One that ate the whole HTTP timeout is not
            # worth repeating more than a couple of times.
            if elapsed >= http_timeout() * 0.5:
                slow_failures += 1
                if slow_failures >= max(1, min(retries, MAX_SLOW_FAILURES)):
                    raise RuntimeError(
                        f"LLM call failed after {attempt} attempts "
                        f"({slow_failures} slow): {last_err}")
                wait = 2.0
            else:
                cheap_failures += 1
                wait = CHEAP_BACKOFF_SECONDS[
                    min(cheap_failures - 1, len(CHEAP_BACKOFF_SECONDS) - 1)]

            remaining = deadline - time.monotonic()
            if remaining <= wait:
                raise RuntimeError(
                    f"LLM call failed after {attempt} attempts / "
                    f"{budget:.0f}s budget: {last_err}")
            log.warning("LLM call failed (attempt %d, %s after %.1fs): %s "
                        "- retrying in %.0fs (%.0fs budget left)",
                        attempt, "slow" if elapsed >= http_timeout() * 0.5
                        else "busy", elapsed, str(last_err)[:140], wait,
                        remaining)
            time.sleep(wait)


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


def _dispatch(system: str, user: str, model: str,
              max_tokens: int, retries: int) -> str:
    if _use_openai():
        return _complete_openai(system, user, model, max_tokens, retries)
    return _complete_anthropic(system, user, model, max_tokens, retries)


def complete(system: str, user: str, model: str,
             max_tokens: int = 4096, retries: int = 3) -> str:
    """Single-turn completion via the active backend.

    Survives a provider that stops serving one model. If `model` has a
    registered fallback (see set_fallback) and it either already died earlier in
    this run or exhausts its retries now, the call is served by the fallback
    instead of failing the stage. The preference is not persisted anywhere, so
    the next run tries the preferred model again and returns to it by itself
    once the provider has capacity.

    A fatal error (bad key, unknown model, malformed request) is NOT retried on
    the fallback - another model would fail the same way.
    """
    fallback = _FALLBACKS.get(model)
    if fallback and model in _DEAD_MODELS:
        log.info("Model %s already unavailable in this run - using %s directly",
                 model, fallback)
        return _dispatch(system, user, fallback, max_tokens, retries)
    try:
        return _dispatch(system, user, model, max_tokens, retries)
    except LLMFatalError:
        raise
    except RuntimeError as exc:
        if not fallback:
            raise
        _DEAD_MODELS.add(model)
        log.warning("Model %s did not answer (%s) - switching to %s for the "
                    "remainder of this run", model, str(exc)[:160], fallback)
        return _dispatch(system, user, fallback, max_tokens, retries)


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
