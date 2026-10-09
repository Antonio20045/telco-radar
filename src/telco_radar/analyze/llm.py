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

from ..textwerkzeug import extract_json as extract_json
from . import llm_frei
from .llm_kosten import _zaehle_usage as _zaehle_usage
from .llm_kosten import budget_setzen as budget_setzen
from .llm_kosten import budget_ueberschritten as budget_ueberschritten
from .llm_kosten import kosten_reset as kosten_reset
from .llm_kosten import kosten_stand as kosten_stand
from .llm_sitzung import LlmSitzung

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
    prefix = (
        "eu"
        if region.startswith("eu-")
        else ("apac" if region.startswith("ap-") else "us")
    )
    return f"{prefix}.{model}"


def _bedrock_url(model: str) -> str:
    from urllib.parse import quote

    return (
        f"https://bedrock-runtime.{_bedrock_region()}.amazonaws.com"
        f"/model/{quote(_bedrock_profile(model), safe=':')}/invoke"
    )


def _use_bedrock() -> bool:
    return bool(os.environ.get("AWS_BEARER_TOKEN_BEDROCK"))


def _openai_base() -> str:
    return (os.environ.get("LLM_API_BASE") or "").rstrip("/")


def _use_openai() -> bool:
    return bool(os.environ.get("LLM_API_KEY") and _openai_base())


def llm_available() -> bool:
    return (
        llm_frei.verfuegbar()
        or _use_bedrock()
        or _use_openai()
        or bool(os.environ.get("ANTHROPIC_API_KEY"))
    )


def active_backend() -> str:
    if llm_frei.registriert():
        return "frei (kostenlose Modelle mehrerer Anbieter)"
    if _use_bedrock():
        return f"bedrock ({_bedrock_region()})"
    if _use_openai():
        return f"openai-compatible ({_openai_base()})"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "none"


_FATAL_STATUSES = frozenset({400, 401, 402, 403, 404, 405, 422})

DEFAULT_HTTP_TIMEOUT = 180.0

DEFAULT_CALL_BUDGET = 300.0

MAX_SLOW_FAILURES = 2
CHEAP_BACKOFF_SECONDS = (1, 2, 3, 5, 5, 8, 8, 10)
LANGSAM_AB_ANTEIL_TIMEOUT = 0.5


def _s() -> LlmSitzung:
    return LlmSitzung.aktive()


class _FatalHTTP(Exception):
    pass


class LLMAnfrageZuGross(Exception):
    """HTTP 413: nur DIESE Anfrage ist zu groß; das Modell bleibt lebendig."""


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
        _s().ausweich[model] = fallback


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
        _s().ausweich.setdefault(current, following)
    return ordered[0] if ordered else ""


def _chain_from(model: str) -> list[str]:
    """Walk the registered fallbacks into a list, guarding against cycles."""
    chain, seen = [], set()
    current = model
    while current and current not in seen:
        chain.append(current)
        seen.add(current)
        current = _s().ausweich.get(current, "")
    return chain


def _kette(model: str, ausweich: str = "") -> list[str]:
    """Die Modellkette DIESES Aufrufs - registrierte Kette oder Sonderweg.

    `LlmSitzung.ausweich` haengt am MODELLNAMEN, nicht an der Rolle des Aufrufers, und
    das ist genau dann zu grob, wenn zwei Rollen dasselbe Modell fahren. In
    jeder heutigen Anbieter-Konfiguration ist `analyst_model ==
    editor_model` ("deepseek-v4-pro"), also kann es fuer diesen Namen nur
    EINEN registrierten Nachfolger geben - und der gehoert der Redaktion, weil
    ein ausgefallener Wochenbericht schwerer wiegt als ein Analyst auf dem
    teureren Claude-Modell. Der Analyst erbte damit den REDAKTIONSanker
    (Sonnet), obwohl er die allermeisten Aufrufe macht und in den kleinsten
    gehoert.

    `ausweich` loest genau das auf: der Aufrufer nennt seinen eigenen
    Ausweichweg, und er schlaegt fuer diesen einen Aufruf die registrierte
    Kette. Registriert wird dabei nichts - der naechste Aufrufer desselben
    Modells bekommt wieder die Kette, die ihm gehoert.

    Die Kette des Ausweichmodells laeuft weiter mit: ein Anker, der selbst
    einen Nachfolger hat, behaelt ihn.
    """
    if not ausweich or ausweich == model:
        return _chain_from(model)
    kette, gesehen = [model], {model}
    for weiter in _chain_from(ausweich):
        if weiter not in gesehen:
            kette.append(weiter)
            gesehen.add(weiter)
    return kette


def reset_model_health() -> None:
    """Forget which models failed. Only needed by tests."""
    _s().tote_modelle.clear()


def dead_models() -> set[str]:
    """Models that stopped answering during this run (for the run protocol)."""
    return set(_s().tote_modelle)


def _anthropic_text(data: dict) -> str:
    """Text aus einer Anthropic-Antwort ziehen - und erklaeren, wenn keiner da ist.

    Im Lauf #65 (04.08.2026) kam die Editor-Antwort nach 80s Rechenzeit voellig
    leer zurueck, zweimal. Aus "Ausgabe ist leer" allein laesst sich nicht
    ableiten, warum: eine am Token-Limit abgeschnittene Antwort, eine Antwort
    ganz ohne Textbloecke und eine inhaltliche Verweigerung sehen an dieser
    Stelle identisch aus. stop_reason und die Blocktypen unterscheiden sie.
    """
    bloecke = data.get("content") or []
    text = "".join(b.get("text", "") for b in bloecke if b.get("type") == "text")
    if not text.strip():
        log.warning(
            "Leere Modellantwort: stop_reason=%s, Blocktypen=%s, Verbrauch=%s",
            data.get("stop_reason"),
            [b.get("type") for b in bloecke] or "keine",
            data.get("usage"),
        )
    return text


def _is_daily_quota(resp) -> bool:
    """A 429 that means "come back tomorrow", not "come back in a second"."""
    if resp.status_code != 429:
        return False
    body = resp.text.lower()
    return "per day" in body or "perday" in body or "daily" in body


def _pruefe_status(resp) -> None:
    """Wirft je nach Status: endgültig, dieses Modell tot, zu groß oder wiederholbar."""
    if resp.status_code == 402:
        raise LLMModelUnavailable(
            f"HTTP 402 Payment Required (Guthaben aufgebraucht): {resp.text[:200]}"
        )
    if resp.status_code == 413:
        raise LLMAnfrageZuGross(f"HTTP 413: {resp.text[:200]}")
    if resp.status_code in _FATAL_STATUSES:
        raise _FatalHTTP(f"HTTP {resp.status_code}: {resp.text[:300]}")
    if _is_daily_quota(resp):
        raise RuntimeError(f"daily token quota exhausted: {resp.text[:200]}")
    if resp.status_code in (429, 529) or resp.status_code >= 500:
        raise httpx.HTTPStatusError(
            f"retryable status {resp.status_code}: {resp.text[:200]}",
            request=resp.request,
            response=resp,
        )
    resp.raise_for_status()


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
            transport = _s().transport
            post = httpx.Client(transport=transport).post if transport else httpx.post
            resp = post(url, json=payload, headers=headers, timeout=http_timeout())
            _pruefe_status(resp)
            return parse(resp.json())
        except _FatalHTTP as exc:
            if _is_model_access_error(str(exc)):
                log.warning("Model not usable on this account: %s", str(exc)[:300])
                raise LLMModelUnavailable(f"model not available: {exc}")
            log.error("LLM call fatal (no retry): %s", str(exc)[:300])
            raise LLMFatalError(f"LLM fatal error: {exc}")
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError) as exc:
            last_err = exc
            elapsed = time.monotonic() - started
            if elapsed >= http_timeout() * LANGSAM_AB_ANTEIL_TIMEOUT:
                slow_failures += 1
                if slow_failures >= max(1, min(retries, MAX_SLOW_FAILURES)):
                    raise RuntimeError(
                        f"LLM call failed after {attempt} attempts "
                        f"({slow_failures} slow): {last_err}"
                    )
                wait = 2.0
            else:
                cheap_failures += 1
                wait = CHEAP_BACKOFF_SECONDS[
                    min(cheap_failures - 1, len(CHEAP_BACKOFF_SECONDS) - 1)
                ]

            remaining = deadline - time.monotonic()
            if remaining <= wait:
                raise RuntimeError(
                    f"LLM call failed after {attempt} attempts / "
                    f"{budget:.0f}s budget: {last_err}"
                )
            log.warning(
                "LLM call failed (attempt %d, %s after %.1fs): %s "
                "- retrying in %.0fs (%.0fs budget left)",
                attempt,
                "slow" if elapsed >= http_timeout() * 0.5 else "busy",
                elapsed,
                str(last_err)[:140],
                wait,
                remaining,
            )
            time.sleep(wait)


def _complete_openai(
    system: str, user: str, model: str, max_tokens: int, retries: int
) -> str:
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
        payload["chat_template_kwargs"] = {"thinking": False}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return _post_with_retries(
        _openai_base() + "/chat/completions",
        payload,
        headers,
        retries,
        _openai_parser(model, max_tokens),
    )


def _openai_parser(model: str, max_tokens: int):
    """Liest den Antworttext; Denkspur ohne Antwort ist ein Fehler, kein Text."""

    def parse(data):
        _zaehle_usage(model, data)
        nachricht = data["choices"][0]["message"]
        inhalt = nachricht.get("content", "") or ""
        if inhalt.strip():
            return inhalt
        denkspur = (
            nachricht.get("reasoning_content") or nachricht.get("reasoning") or ""
        )
        grund = data["choices"][0].get("finish_reason", "?")
        if denkspur:
            raise ValueError(
                f"Modell {model} lieferte KEINE Antwort, nur {len(denkspur)} "
                f"Zeichen Denkspur (finish_reason={grund}, max_tokens="
                f"{max_tokens}). Das Token-Budget dieser Stufe reicht fuer "
                f"dieses Modell nicht - erhoehen, nicht wiederholen."
            )
        raise ValueError(
            f"Modell {model} lieferte eine leere Antwort "
            f"(finish_reason={grund}, max_tokens={max_tokens})."
        )

    return parse


def _complete_frei(
    system: str, user: str, model: str, max_tokens: int, retries: int
) -> str:
    """Ein Glied von ``frei``; ein 401 tötet nur dieses Glied (Fehler 07.10.2026)."""
    ep = llm_frei.endpunkt(model)
    if ep is None:
        raise LLMModelUnavailable(f"{model} ist kein Glied von frei_endpunkte")
    key = ep.schluessel()
    if key is None:
        raise LLMModelUnavailable(f"Schluessel {ep.key_env} fehlt fuer {model}")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = llm_frei.nutzlast(ep, system, user, max_tokens)
    llm_frei.drosseln(ep)
    try:
        return _post_with_retries(
            ep.url(), payload, headers, retries, _openai_parser(model, max_tokens)
        )
    except LLMModelUnavailable:
        raise
    except LLMFatalError as exc:
        raise LLMModelUnavailable(str(exc)) from exc


def _complete_anthropic(
    system: str, user: str, model: str, max_tokens: int, retries: int
) -> str:
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
        _zaehle_usage(model, data)
        return _anthropic_text(data)

    return _post_with_retries(ANTHROPIC_URL, payload, headers, retries, parse)


def _complete_bedrock(
    system: str, user: str, model: str, max_tokens: int, retries: int
) -> str:
    key = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    if not key:
        raise RuntimeError("AWS_BEARER_TOKEN_BEDROCK is not set")
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
        _zaehle_usage(model, data)
        return _anthropic_text(data)

    return _post_with_retries(_bedrock_url(model), payload, headers, retries, parse)


def _dispatch(system: str, user: str, model: str, max_tokens: int, retries: int) -> str:
    if llm_frei.endpunkt(model):
        return _complete_frei(system, user, model, max_tokens, retries)
    if model.startswith("claude") and os.environ.get("ANTHROPIC_API_KEY"):
        return _complete_anthropic(system, user, model, max_tokens, retries)
    if _use_bedrock():
        return _complete_bedrock(system, user, model, max_tokens, retries)
    if _use_openai():
        return _complete_openai(system, user, model, max_tokens, retries)
    return _complete_anthropic(system, user, model, max_tokens, retries)


def complete(
    system: str,
    user: str,
    model: str,
    max_tokens: int = 4096,
    retries: int = 3,
    ausweich: str = "",
) -> str:
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

    `ausweich` setzt fuer DIESEN Aufruf einen eigenen Ausweichweg, statt der
    registrierten Kette zu folgen - siehe `_kette`. Der Analyst braucht das,
    weil er sich seinen Modellnamen mit der Redaktion teilt.
    """
    sitzung = _s()
    chain = [m for m in _kette(model, ausweich) if m not in sitzung.tote_modelle]
    if not chain:
        chain = [model]
    last_exc: Exception | None = None

    for position, candidate in enumerate(chain):
        if position:
            log.warning("Falling back to %s", candidate)
        try:
            aufruf = sitzung.client or _dispatch
            return aufruf(system, user, candidate, max_tokens, retries)
        except LLMModelUnavailable as exc:
            sitzung.tote_modelle[candidate] = str(exc)[:300]
            last_exc = exc
            log.warning(
                "Model %s is not usable on this account - skipping it "
                "for the rest of this run",
                candidate,
            )
        except LLMAnfrageZuGross as exc:
            last_exc = exc
            log.warning("Anfrage zu gross fuer %s - naechstes Glied", candidate)
        except LLMFatalError:
            raise
        except RuntimeError as exc:
            sitzung.tote_modelle[candidate] = str(exc)[:300]
            last_exc = exc
            log.warning("Model %s did not answer (%s)", candidate, str(exc)[:160])

    if isinstance(last_exc, LLMAnfrageZuGross):
        raise RuntimeError(str(last_exc)) from last_exc
    raise last_exc if last_exc else RuntimeError(f"no model answered for {model}")
