"""LLM client.

Three backends, chosen by environment (first match wins):
  * Amazon Bedrock Messages API  -> AWS_BEARER_TOKEN_BEDROCK (+ BEDROCK_REGION)
  * OpenAI-compatible chat-completions endpoint -> LLM_API_KEY (+ LLM_API_BASE)
    (works for Moonshot/Kimi, DeepSeek, NVIDIA NIM, Gemini-OpenAI, Groq, ...)
  * Anthropic Messages API       -> ANTHROPIC_API_KEY

This keeps the provider swappable with one env var + the base URL, without
touching the agents. Public telco news only, so a non-Anthropic model is fine.

Bedrock note: this uses the classic bedrock-runtime invoke endpoint, NOT the
newer "Mantle" endpoint. Both speak the Anthropic Messages payload, but they
are gated separately, and measured on 01.08.2026 Mantle answers 403 for models
bedrock-runtime happily serves (Haiku 4.5: 403 on Mantle, reachable on
runtime). Runtime differences: the model id goes in the URL rather than the
body, it needs the regional inference-profile prefix ("us."), and the body
carries anthropic_version instead of a model field.
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
BEDROCK_DEFAULT_REGION = "us-east-1"


def _bedrock_region() -> str:
    return (os.environ.get("BEDROCK_REGION") or BEDROCK_DEFAULT_REGION).strip()


BEDROCK_API_VERSION = "bedrock-2023-05-31"


def _bedrock_profile(model: str) -> str:
    """Prefix a bare model id with its regional inference profile.

    Every current Claude model on Bedrock is INFERENCE_PROFILE-only (checked
    against the account's own foundation-models listing), so a bare
    "anthropic.claude-..." id is rejected. The prefix is derived from the
    region so an eu-* region does not silently ask for US capacity.
    """
    if model.split(".", 1)[0] in ("us", "eu", "apac", "global"):
        return model
    region = _bedrock_region()
    prefix = "eu" if region.startswith("eu-") else (
        "apac" if region.startswith("ap-") else "us")
    return f"{prefix}.{model}"


def _bedrock_url(model: str) -> str:
    from urllib.parse import quote
    # ":" stays literal - it is part of the versioned model id
    # (…-v1:0) and Bedrock does not accept it percent-encoded.
    return (f"https://bedrock-runtime.{_bedrock_region()}.amazonaws.com"
            f"/model/{quote(_bedrock_profile(model), safe=':')}/invoke")


def _use_bedrock() -> bool:
    return bool(os.environ.get("AWS_BEARER_TOKEN_BEDROCK"))


def _openai_base() -> str:
    return (os.environ.get("LLM_API_BASE") or "").rstrip("/")


def _use_openai() -> bool:
    return bool(os.environ.get("LLM_API_KEY") and _openai_base())


def llm_available() -> bool:
    return (_use_bedrock() or _use_openai()
            or bool(os.environ.get("ANTHROPIC_API_KEY")))


def active_backend() -> str:
    if _use_bedrock():
        return f"bedrock ({_bedrock_region()})"
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


class LLMModelUnavailable(LLMFatalError):
    """This ONE model is not usable on this account - another one may be.

    The exception to the rule above. Bedrock rejects a model the account has
    no agreement for with a 403, which looks fatal but says nothing about the
    other models: on 02.08.2026 Sonnet 5 answered "not available for this
    account" while Sonnet 4.6 got as far as the quota check. Treating that as
    plain-fatal would abort the run on the first model instead of moving down
    the preference chain.
    """


# Substrings that identify a per-MODEL access rejection rather than a broken
# request. Kept narrow on purpose: a genuinely malformed payload or a bad key
# must stay fatal, otherwise the run would walk the whole chain failing the
# same way each time.
_MODEL_ACCESS_MARKERS = (
    "is not available for this account",
    "invalid_payment_instrument",
    "model access is denied",
    "marketplace subscription",
    "does not exist",
    "provided model identifier is invalid",
    "use case details",
)


def _is_model_access_error(body: str) -> bool:
    low = body.lower()
    return any(marker in low for marker in _MODEL_ACCESS_MARKERS)


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


def set_model_chain(models: list[str]) -> str:
    """Register a preference chain (best first) and return its head.

    Each model falls back to the next, so the run uses the best model the
    provider actually serves without anyone having to know in advance which
    one that is. Duplicates and empty entries are ignored; an existing
    fallback for a model is not overwritten, so a caller-set editor->analyst
    preference still wins over the chain's own next link.
    """
    ordered: list[str] = []
    for name in models:
        name = (name or "").strip()
        if name and name not in ordered:
            ordered.append(name)
    for current, following in zip(ordered, ordered[1:]):
        _FALLBACKS.setdefault(current, following)
    return ordered[0] if ordered else ""


def _chain_from(model: str) -> list[str]:
    """Walk the registered fallbacks into a list, guarding against cycles."""
    chain, seen = [], set()
    current = model
    while current and current not in seen:
        chain.append(current)
        seen.add(current)
        current = _FALLBACKS.get(current, "")
    return chain


def reset_model_health() -> None:
    """Forget which models failed. Only needed by tests."""
    _DEAD_MODELS.clear()


def dead_models() -> set[str]:
    """Models that stopped answering during this run (for the run protocol)."""
    return set(_DEAD_MODELS)


def _is_daily_quota(resp) -> bool:
    """A 429 that means "come back tomorrow", not "come back in a second"."""
    if resp.status_code != 429:
        return False
    body = resp.text[:300].lower()
    return "per day" in body or "daily" in body


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
            if _is_daily_quota(resp):
                # Bedrock answers a spent DAILY token allowance with the same
                # 429 it uses for "slow down a moment". Retrying that one is
                # pointless by definition - and expensive: the cheap-failure
                # path would spend the full call budget (300s) on it, per
                # stage. Give up on this model at once so the run either falls
                # back or publishes the digest in seconds instead of hours.
                raise RuntimeError(
                    f"daily token quota exhausted: {resp.text[:200]}")
            if resp.status_code in (429, 529) or resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"retryable status {resp.status_code}: {resp.text[:200]}",
                    request=resp.request, response=resp)
            resp.raise_for_status()
            return parse(resp.json())
        except _FatalHTTP as exc:
            # no point retrying - surface immediately so the run fails fast
            if _is_model_access_error(str(exc)):
                log.warning("Model not usable on this account: %s", str(exc)[:300])
                raise LLMModelUnavailable(f"model not available: {exc}")
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


def _complete_bedrock(system: str, user: str, model: str,
                      max_tokens: int, retries: int) -> str:
    key = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    if not key:
        raise RuntimeError("AWS_BEARER_TOKEN_BEDROCK is not set")
    # The model is addressed by URL here, so the body carries the Bedrock API
    # version in its place - sending "model" as well is rejected.
    payload = {
        "anthropic_version": BEDROCK_API_VERSION,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "content-type": "application/json",
    }

    def parse(data):
        return "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")

    return _post_with_retries(_bedrock_url(model), payload, headers,
                              retries, parse)


def _dispatch(system: str, user: str, model: str,
              max_tokens: int, retries: int) -> str:
    if _use_bedrock():
        return _complete_bedrock(system, user, model, max_tokens, retries)
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

    Fallbacks chain: if the stand-in has a stand-in of its own, the call keeps
    walking down until one model answers. That is what makes "use the best
    model this account actually has" work without hard-coding the answer.

    A fatal error (bad key, malformed request) is NOT retried on the fallback -
    another model would fail the same way. A per-MODEL access rejection
    (LLMModelUnavailable) is the exception and does move to the next link.
    """
    chain = [m for m in _chain_from(model) if m not in _DEAD_MODELS]
    if not chain:
        # every link died earlier in this run - try the preferred one anyway so
        # the caller gets a real error rather than an IndexError
        chain = [model]
    last_exc: Exception | None = None

    for position, candidate in enumerate(chain):
        if position:
            log.warning("Falling back to %s", candidate)
        try:
            return _dispatch(system, user, candidate, max_tokens, retries)
        except LLMModelUnavailable as exc:
            _DEAD_MODELS.add(candidate)
            last_exc = exc
            log.warning("Model %s is not usable on this account - skipping it "
                        "for the rest of this run", candidate)
        except LLMFatalError:
            raise
        except RuntimeError as exc:
            _DEAD_MODELS.add(candidate)
            last_exc = exc
            log.warning("Model %s did not answer (%s)", candidate, str(exc)[:160])

    raise last_exc if last_exc else RuntimeError(f"no model answered for {model}")


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
