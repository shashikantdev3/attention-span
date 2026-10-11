"""Free-tier LLM calls with a fallback chain, pacing, JSON output and a response cache.

Each step (editor, writer, checker) has a chain of provider:model pairs; the first that answers wins.
See CHAINS below; override any of them in .env.
Every response is cached in state/cache/ by a hash of the prompt, so a run that stops
half way can simply be started again and will not spend quota twice.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

from .http import post

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "state" / "cache"

PROVIDERS = {
    "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
               "key": "GEMINI_API_KEY", "min_gap": 4.5},
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions",
             "key": "GROQ_API_KEY", "min_gap": 8.0},  # free tier is about 8,000 tokens per minute
}
# Each step has its own chain. The editor runs once a day, so it gets the stronger Flash models
# (small daily quota). The checker uses a different model family from the writer, so a model
# never marks its own homework.
CHAINS = {
    "writer": ("gemini:gemini-3.5-flash-lite,gemini:gemini-3.1-flash-lite,"
               "groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b"),
    "editor": ("gemini:gemini-3.8-flash,gemini:gemini-3.5-flash,gemini:gemini-3.5-flash-lite,"
               "groq:openai/gpt-oss-120b"),
    "checker": ("groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b,gemini:gemini-3.1-flash-lite,"
                "gemini:gemini-3.5-flash-lite"),
}

_last_call = {}
_dead = set()          # provider:model pairs that hit a daily limit this run
STATS = {"calls": 0, "cache_hits": 0, "by_model": {}, "failures": [], "fallbacks": []}


def chain(step):
    """Override any step in .env, for example LLM_CHAIN_WRITER=gemini:gemini-3.5-flash-lite,groq:openai/gpt-oss-120b"""
    raw = os.getenv(f"LLM_CHAIN_{step.upper()}", CHAINS.get(step, CHAINS["writer"]))
    return [c.strip() for c in raw.split(",") if c.strip()]


def _pace(provider):
    gap = PROVIDERS[provider]["min_gap"]
    wait = _last_call.get(provider, 0) + gap - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call[provider] = time.time()


def _parse_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


def _as_object(result):
    """Every step expects one JSON object. Some models wrap it in a list; unwrap that, reject anything else."""
    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], dict):
        result = result[0]
    if not isinstance(result, dict):
        raise ValueError(f"expected a JSON object, got {type(result).__name__}")
    return result


def ask_json(system, user, max_tokens=1500, temperature=0.2, tag="call", reasoning="low"):
    """Return (parsed_json, model_used). Raises RuntimeError if every provider fails."""
    # the key includes the step's model chain, so changing models never reuses an older answer
    key = hashlib.sha256(f"{tag}|{','.join(chain(tag))}\n{system}\n---\n{user}".encode("utf-8")).hexdigest()[:24]
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{key}.json"
    if cached.exists():
        try:
            data = json.loads(cached.read_text(encoding="utf-8"))
            result = _as_object(data["result"])
            STATS["cache_hits"] += 1
            return result, data["model"]
        except (ValueError, KeyError, json.JSONDecodeError):
            cached.unlink(missing_ok=True)  # a bad answer was cached by an older version: ask again

    errors = []
    for entry in chain(tag):
        if entry in _dead:
            continue
        provider, model = entry.split(":", 1)
        api_key = os.getenv(PROVIDERS[provider]["key"])
        if not api_key:
            errors.append(f"{entry}: no key")
            continue
        body = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        # Thinking models spend output tokens on reasoning first; keep it low and leave room for the answer.
        if provider == "gemini" and "lite" not in model:
            body["reasoning_effort"] = reasoning
            body["max_tokens"] = max_tokens + 4096
        for attempt in range(2):
            _pace(provider)
            try:
                r = post(PROVIDERS[provider]["url"], json=body, timeout=90,
                         headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
            except Exception as exc:
                errors.append(f"{entry}: {type(exc).__name__}")
                continue
            if r.status_code == 200:
                try:
                    content = r.json()["choices"][0]["message"]["content"]
                    result = _as_object(_parse_json(content))
                except Exception as exc:
                    errors.append(f"{entry}: bad JSON ({type(exc).__name__})")
                    continue
                if errors:
                    STATS["fallbacks"].append({"tag": tag, "used": entry, "after": errors[-3:]})
                STATS["calls"] += 1
                STATS["by_model"][entry] = STATS["by_model"].get(entry, 0) + 1
                cached.write_text(json.dumps({"model": entry, "tag": tag, "result": result},
                                             ensure_ascii=False), encoding="utf-8")
                return result, entry
            text = r.text[:200]
            errors.append(f"{entry}: HTTP {r.status_code} {text}")
            if r.status_code == 429 and ("day" in text.lower() or "quota" in text.lower()):
                _dead.add(entry)  # daily quota gone: skip this model for the rest of the run
                break
            if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                try:
                    wait = float(r.headers.get("retry-after", 8))
                except ValueError:
                    wait = 8
                time.sleep(min(max(wait, 4), 40))
                continue
            break
    STATS["failures"].append({"tag": tag, "errors": errors[-4:]})
    raise RuntimeError(f"all providers failed for {tag}: {errors[-3:]}")
