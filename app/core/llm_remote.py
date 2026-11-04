"""Remote LLM providers for the assistants (optional; Ollama stays the default).

A remote model is written in `base_model` as ``@<provider_id>/<model>``
(for example ``@openrouter/meta-llama/llama-3.3-70b-instruct``). ``@`` is
not valid in Ollama model names, so local models are never confused with
remote ones.

Everything in AuraVox talks to the LLM with Ollama's /api/chat body
(messages with base64 ``images``, ``tools``, ``format`` for structured JSON,
``options``, ``stream``). :func:`post` is a drop-in for ``requests.post``:
for local models it calls Ollama as before; for remote ones it translates
the body to the provider API and returns a response object shaped like
Ollama's (``.json()`` / ``.iter_lines()`` with NDJSON chunks), so the tool
loop, streaming, the reviewer and vision work unchanged.

Provider kinds:
- ``openai``: any OpenAI-compatible ``/v1/chat/completions`` server
  (OpenAI, OpenRouter, LM Studio, llama-server, vLLM, Groq, Ollama's /v1…).
- ``anthropic``: Anthropic Messages API.
- ``gemini``: Google Gemini API (generativelanguage.googleapis.com).

Config: config/llm_providers.json (no secrets) + API keys in
config/secrets.json (app/core/secrets_store.py, DPAPI on Windows).
"""
import json
import os
import re
import threading
import time

import requests

from app import paths
from app.core import secrets_store

PROVIDERS_JSON = os.path.join(paths.CONFIG_DIR, "llm_providers.json")
KINDS = ("openai", "anthropic", "gemini")
DEFAULT_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096
_lock = threading.RLock()


# ── Config ─────────────────────────────────────────────────────────────

def is_remote(model) -> bool:
    return isinstance(model, str) and model.startswith("@")


def split_model(model: str):
    """'@prov/some/model' → ('prov', 'some/model')."""
    rest = model[1:]
    pid, _, name = rest.partition("/")
    return pid, name


def _key_name(pid: str) -> str:
    return f"llm:{pid}"


def load() -> list:
    try:
        with open(PROVIDERS_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for p in (data.get("providers") if isinstance(data, dict) else None) or []:
        if isinstance(p, dict) and ID_RE.match(str(p.get("id") or "")) and p.get("kind") in KINDS:
            out.append(p)
    return out


def get_provider(pid: str):
    return next((p for p in load() if p["id"] == pid), None)


def public() -> list:
    """Providers for the browser: never the key, only whether there is one."""
    return [{**{k: v for k, v in p.items() if k != "api_key"}, "has_key": secrets_store.has(_key_name(p["id"]))}
            for p in load()]


def _clean_caps(caps) -> list:
    return [c for c in ("tools", "vision") if c in (caps or [])]


def save(providers: list) -> list:
    """Replaces the provider list. Each item: id, name, kind, base_url,
    models [{name, caps}], enabled; `api_key` only when it changes (empty
    string = keep the stored one, `clear_key` true = remove it)."""
    if not isinstance(providers, list) or len(providers) > 20:
        raise ValueError("invalid providers")
    clean, seen = [], set()
    for p in providers:
        if not isinstance(p, dict):
            raise ValueError("invalid provider")
        pid = str(p.get("id") or "").strip().lower()
        kind = p.get("kind")
        if not ID_RE.match(pid) or pid in seen:
            raise ValueError(f"invalid provider id: {pid!r}")
        if kind not in KINDS:
            raise ValueError(f"invalid provider kind: {kind!r}")
        url = str(p.get("base_url") or DEFAULT_URLS[kind]).strip().rstrip("/")
        if not re.match(r"^https?://[^\s]+$", url) or len(url) > 300:
            raise ValueError(f"invalid URL: {url!r}")
        models = []
        for m in (p.get("models") or [])[:100]:
            name = str((m or {}).get("name") or "").strip()
            if name and len(name) <= 200 and not re.search(r"\s", name):
                models.append({"name": name, "caps": _clean_caps(m.get("caps", ["tools", "vision"]))})
        seen.add(pid)
        clean.append({"id": pid, "name": str(p.get("name") or pid)[:60], "kind": kind, "base_url": url,
                      "enabled": p.get("enabled", True) is not False, "models": models})
        key = p.get("api_key")
        if p.get("clear_key"):
            secrets_store.set(_key_name(pid), "")
        elif isinstance(key, str) and key.strip():
            secrets_store.set(_key_name(pid), key.strip())
    with _lock:
        os.makedirs(os.path.dirname(PROVIDERS_JSON), exist_ok=True)
        tmp = PROVIDERS_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"providers": clean}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, PROVIDERS_JSON)
    secrets_store.delete_prefix("llm:", keep={_key_name(p["id"]) for p in clean})
    return public()


def remote_models() -> list:
    """Models of the enabled providers, shaped like list_models() entries."""
    out = []
    for p in load():
        if not p.get("enabled", True):
            continue
        for m in p.get("models") or []:
            caps = ["completion"] + _clean_caps(m.get("caps"))
            out.append({"name": f"@{p['id']}/{m['name']}", "size": 0, "family": p.get("name") or p["id"],
                        "parameter_size": "", "quantization": "", "capabilities": caps,
                        "remote": True, "provider": p["id"], "provider_name": p.get("name") or p["id"],
                        "provider_kind": p["kind"]})
    return out


def model_caps(model: str):
    if not is_remote(model):
        return None
    pid, name = split_model(model)
    p = get_provider(pid)
    m = next((x for x in (p or {}).get("models") or [] if x["name"] == name), None)
    return _clean_caps(m.get("caps")) if m else None


# ── HTTP helpers ───────────────────────────────────────────────────────

class RemoteError(requests.exceptions.RequestException):
    pass


# Providers used only by test_provider (not saved).
_ADHOC = {}


def _resolve(model: str):
    pid, name = split_model(model)
    if pid in _ADHOC:
        p, key = _ADHOC[pid]
        return p, name, key
    p = get_provider(pid)
    if not p:
        raise RemoteError(f"unknown LLM provider '{pid}' (Settings → Models → API providers)")
    if not p.get("enabled", True):
        raise RemoteError(f"LLM provider '{pid}' is disabled")
    return p, name, secrets_store.get(_key_name(pid))


def _headers(p: dict, key: str) -> dict:
    h = {"Content-Type": "application/json"}
    if p["kind"] == "openai":
        if key:
            h["Authorization"] = f"Bearer {key}"
        if "openrouter.ai" in p["base_url"]:
            h["X-Title"] = "AuraVox"
    elif p["kind"] == "anthropic":
        h["x-api-key"] = key
        h["anthropic-version"] = ANTHROPIC_VERSION
    elif p["kind"] == "gemini":
        h["x-goog-api-key"] = key
    return h


def _err_text(r) -> str:
    try:
        data = r.json()
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            return str(err.get("message") or err)[:400]
        if err:
            return str(err)[:400]
    except ValueError:
        pass
    return (r.text or "").strip()[:400] or f"HTTP {r.status_code}"


def _mime(b64: str) -> str:
    head = (b64 or "")[:12]
    if head.startswith("iVBOR"):
        return "image/png"
    if head.startswith("R0lG"):
        return "image/gif"
    if head.startswith("UklG"):
        return "image/webp"
    return "image/jpeg"


def _strip_data_url(img: str) -> str:
    return img.split(",", 1)[1] if isinstance(img, str) and img.startswith("data:") else img


def _args_dict(args):
    if isinstance(args, dict):
        return args
    try:
        val = json.loads(args or "{}")
        return val if isinstance(val, dict) else {}
    except (TypeError, ValueError):
        return {}


def _schema_note(schema) -> str:
    return ("Reply ONLY with a JSON object (no code fences, no other text) that matches this JSON schema:\n"
            + json.dumps(schema, ensure_ascii=False))


def _extract_json(text: str) -> str:
    """The JSON object inside a reply (some providers wrap it in ``` or text)."""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    if not text.startswith("{"):
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            text = text[a:b + 1]
    return text


# ── Ollama body → provider request ─────────────────────────────────────

def _openai_messages(messages: list) -> list:
    out, pending, n = [], [], 0
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "tool":
            if pending:
                cid, name = pending.pop(0)
                out.append({"role": "tool", "tool_call_id": cid, "content": str(content)})
            else:
                out.append({"role": "user", "content": f"[tool result]\n{content}"})
            continue
        pending = []
        if role == "assistant" and m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                n += 1
                fn = c.get("function") or {}
                cid = c.get("id") or f"call_{n}"
                pending.append((cid, fn.get("name")))
                calls.append({"id": cid, "type": "function", "function": {
                    "name": fn.get("name"), "arguments": json.dumps(_args_dict(fn.get("arguments")), ensure_ascii=False)}})
            out.append({"role": "assistant", "content": content or None, "tool_calls": calls})
            continue
        images = m.get("images") or []
        if images and role == "user":
            parts = [{"type": "text", "text": content}] if content else []
            for img in images:
                b64 = _strip_data_url(img)
                parts.append({"type": "image_url", "image_url": {"url": f"data:{_mime(b64)};base64,{b64}"}})
            out.append({"role": "user", "content": parts})
        else:
            out.append({"role": role if role in ("system", "user", "assistant") else "user", "content": content})
    return out


def _openai_request(p, name, body):
    opts = body.get("options") or {}
    req = {"model": name, "messages": _openai_messages(body.get("messages") or [])}
    if "temperature" in opts:
        req["temperature"] = opts["temperature"]
    if "top_p" in opts:
        req["top_p"] = opts["top_p"]
    if opts.get("num_predict"):
        req["max_tokens"] = opts["num_predict"]
    fmt = body.get("format")
    if body.get("tools") and not fmt:
        req["tools"] = body["tools"]
    if isinstance(fmt, dict):
        req["response_format"] = {"type": "json_schema",
                                  "json_schema": {"name": "output", "schema": fmt, "strict": False}}
        req["messages"] = req["messages"] + [{"role": "system", "content": _schema_note(fmt)}]
    elif fmt == "json":
        req["response_format"] = {"type": "json_object"}
    if body.get("stream"):
        req["stream"] = True
        req["stream_options"] = {"include_usage": True}
    return f"{p['base_url']}/chat/completions", req


def _anthropic_messages(messages: list):
    system, out, pending, n = [], [], [], 0

    def add(role, blocks):
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "system":
            if content:
                system.append(content)
            continue
        if role == "tool":
            if pending:
                cid = pending.pop(0)
                add("user", [{"type": "tool_result", "tool_use_id": cid, "content": str(content)}])
            else:
                add("user", [{"type": "text", "text": f"[tool result]\n{content}"}])
            continue
        pending = []
        if role == "assistant":
            blocks = [{"type": "text", "text": content}] if content else []
            for c in m.get("tool_calls") or []:
                n += 1
                fn = c.get("function") or {}
                cid = c.get("id") or f"toolu_{n:04d}"
                pending.append(cid)
                blocks.append({"type": "tool_use", "id": cid, "name": fn.get("name"), "input": _args_dict(fn.get("arguments"))})
            if blocks:
                add("assistant", blocks)
            continue
        blocks = []
        for img in m.get("images") or []:
            b64 = _strip_data_url(img)
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": _mime(b64), "data": b64}})
        blocks.append({"type": "text", "text": content or "."})
        add("user", blocks)
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"type": "text", "text": "."}]})
    return "\n\n".join(system), out


def _anthropic_request(p, name, body):
    opts = body.get("options") or {}
    system, messages = _anthropic_messages(body.get("messages") or [])
    req = {"model": name, "messages": messages, "max_tokens": int(opts.get("num_predict") or DEFAULT_MAX_TOKENS)}
    if system:
        req["system"] = system
    if "temperature" in opts:
        req["temperature"] = max(0.0, min(1.0, float(opts["temperature"])))
    fmt = body.get("format")
    if isinstance(fmt, dict):
        # Structured output: a forced tool whose input is the JSON object.
        req["tools"] = [{"name": "output", "description": "Return the answer.", "input_schema": fmt}]
        req["tool_choice"] = {"type": "tool", "name": "output"}
    elif body.get("tools"):
        req["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                         "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}}}
                        for t in body["tools"]]
    if body.get("stream") and not isinstance(fmt, dict):
        req["stream"] = True
    return f"{p['base_url']}/messages", req


_GEMINI_DROP = {"additionalProperties", "$schema", "default", "examples", "title"}


def _gemini_schema(s):
    """JSON schema → the subset Gemini accepts (property NAMES are kept even
    if they are called "title" or "default")."""
    if isinstance(s, dict):
        out = {}
        for k, v in s.items():
            if k == "properties" and isinstance(v, dict):
                out[k] = {name: _gemini_schema(sub) for name, sub in v.items()}
            elif k not in _GEMINI_DROP:
                out[k] = _gemini_schema(v)
        return out
    if isinstance(s, list):
        return [_gemini_schema(x) for x in s]
    return s


def _gemini_contents(messages: list):
    system, out, pending = [], [], []

    def add(role, parts):
        if out and out[-1]["role"] == role:
            out[-1]["parts"].extend(parts)
        else:
            out.append({"role": role, "parts": list(parts)})

    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "system":
            if content:
                system.append(content)
            continue
        if role == "tool":
            name = pending.pop(0) if pending else "tool"
            add("user", [{"functionResponse": {"name": name, "response": {"result": str(content)}}}])
            continue
        pending = []
        if role == "assistant":
            parts = [{"text": content}] if content else []
            for c in m.get("tool_calls") or []:
                fn = c.get("function") or {}
                pending.append(fn.get("name"))
                part = {"functionCall": {"name": fn.get("name"), "args": _args_dict(fn.get("arguments"))}}
                if c.get("thought_signature"):
                    part["thoughtSignature"] = c["thought_signature"]
                parts.append(part)
            if parts:
                add("model", parts)
            continue
        parts = [{"text": content or "."}]
        for img in m.get("images") or []:
            b64 = _strip_data_url(img)
            parts.append({"inlineData": {"mimeType": _mime(b64), "data": b64}})
        add("user", parts)
    return "\n\n".join(system), out


def _gemini_request(p, name, body):
    opts = body.get("options") or {}
    system, contents = _gemini_contents(body.get("messages") or [])
    req = {"contents": contents}
    if system:
        req["systemInstruction"] = {"parts": [{"text": system}]}
    gen = {}
    for src, dst in (("temperature", "temperature"), ("top_p", "topP"), ("top_k", "topK"), ("num_predict", "maxOutputTokens")):
        if opts.get(src) is not None:
            gen[dst] = opts[src]
    fmt = body.get("format")
    if isinstance(fmt, dict):
        gen["responseMimeType"] = "application/json"
        gen["responseSchema"] = _gemini_schema(fmt)
    elif body.get("tools"):
        req["tools"] = [{"functionDeclarations": [
            {"name": t["function"]["name"], "description": t["function"].get("description", ""),
             **({"parameters": _gemini_schema(t["function"]["parameters"])}
                if (t["function"].get("parameters") or {}).get("properties") else {})}
            for t in body["tools"]]}]
    if gen:
        req["generationConfig"] = gen
    model = name if name.startswith("models/") else f"models/{name}"
    if body.get("stream") and not isinstance(fmt, dict):
        return f"{p['base_url']}/{model}:streamGenerateContent?alt=sse", req
    return f"{p['base_url']}/{model}:generateContent", req


_BUILDERS = {"openai": _openai_request, "anthropic": _anthropic_request, "gemini": _gemini_request}


# ── Provider response → Ollama shape ──────────────────────────────────

def _ollama_calls(calls: list) -> list:
    return [{"function": {"name": c["name"], "arguments": _args_dict(c.get("arguments"))},
             **({"id": c["id"]} if c.get("id") else {}),
             **({"thought_signature": c["sig"]} if c.get("sig") else {})}
            for c in calls if c.get("name")]


def _parse_openai(data, fmt):
    choice = ((data.get("choices") or [{}])[0]) or {}
    msg = choice.get("message") or {}
    calls = [{"id": c.get("id"), "name": (c.get("function") or {}).get("name"),
              "arguments": (c.get("function") or {}).get("arguments")} for c in msg.get("tool_calls") or []]
    text = msg.get("content") or ""
    if isinstance(text, list):
        text = "".join(x.get("text", "") for x in text if isinstance(x, dict))
    return text, calls, ((data.get("usage") or {}).get("completion_tokens"))


def _parse_anthropic(data, fmt):
    text, calls = [], []
    for b in data.get("content") or []:
        if b.get("type") == "text":
            text.append(b.get("text") or "")
        elif b.get("type") == "tool_use":
            if isinstance(fmt, dict) and b.get("name") == "output":
                text = [json.dumps(b.get("input") or {}, ensure_ascii=False)]
                calls = []
                break
            calls.append({"id": b.get("id"), "name": b.get("name"), "arguments": b.get("input") or {}})
    return "".join(text), calls, ((data.get("usage") or {}).get("output_tokens"))


def _parse_gemini(data, fmt):
    cand = (data.get("candidates") or [{}])[0] or {}
    text, calls = [], []
    for part in (cand.get("content") or {}).get("parts") or []:
        if part.get("thought"):
            continue
        if "text" in part:
            text.append(part["text"])
        if part.get("functionCall"):
            fc = part["functionCall"]
            calls.append({"name": fc.get("name"), "arguments": fc.get("args") or {},
                          "sig": part.get("thoughtSignature")})
    if not cand and data.get("promptFeedback", {}).get("blockReason"):
        raise RemoteError(f"Gemini blocked the request: {data['promptFeedback']['blockReason']}")
    return "".join(text), calls, ((data.get("usageMetadata") or {}).get("candidatesTokenCount"))


_PARSERS = {"openai": _parse_openai, "anthropic": _parse_anthropic, "gemini": _parse_gemini}


def _final(text, calls, tokens, t0, fmt) -> dict:
    if fmt:
        text = _extract_json(text)
    msg = {"role": "assistant", "content": text}
    if calls:
        msg["tool_calls"] = _ollama_calls(calls)
    return {"message": msg, "done": True, "eval_count": tokens or 0,
            "total_duration": int((time.time() - t0) * 1e9), "remote": True}


class _Response:
    """What callers expect from requests.post(...) against Ollama."""

    def __init__(self, status=200, data=None, lines=None, closer=None, error=None):
        self.status_code = status
        self._data = data
        self._lines = lines
        self._closer = closer
        self._error = error
        self.text = json.dumps(data) if data is not None else (error or "")

    def raise_for_status(self):
        if self._error:
            raise RemoteError(self._error)

    def json(self):
        return self._data

    def iter_lines(self):
        if self._lines is None:
            if self._data is not None:
                yield json.dumps(self._data).encode()
            return
        for line in self._lines:
            yield line

    def close(self):
        if self._closer:
            self._closer()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _sse(r):
    """(event, data dict) from a Server-Sent Events response."""
    event = None
    for raw in r.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        line = raw.strip()
        if not line:
            event = None
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            payload = line[5:].strip()
            if payload == "[DONE]":
                return
            try:
                yield event, json.loads(payload)
            except ValueError:
                continue


def _stream_lines(kind, r, t0):
    """Provider SSE → Ollama NDJSON lines (content pieces, then a final
    chunk with the tool calls and done: true)."""
    calls, tokens = {}, 0
    order = []

    def piece(text):
        return json.dumps({"message": {"role": "assistant", "content": text}, "done": False}).encode()

    try:
        for event, d in _sse(r):
            if kind == "openai":
                if d.get("error"):
                    yield json.dumps({"error": str(d["error"].get("message") if isinstance(d["error"], dict) else d["error"])}).encode()
                    return
                if d.get("usage"):
                    tokens = d["usage"].get("completion_tokens") or tokens
                for ch in d.get("choices") or []:
                    delta = ch.get("delta") or {}
                    if delta.get("content"):
                        yield piece(delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        c = calls.setdefault(idx, {"id": None, "name": "", "arguments": ""})
                        if idx not in order:
                            order.append(idx)
                        c["id"] = tc.get("id") or c["id"]
                        fn = tc.get("function") or {}
                        c["name"] += fn.get("name") or ""
                        c["arguments"] += fn.get("arguments") or ""
            elif kind == "anthropic":
                t = d.get("type")
                if t == "error":
                    yield json.dumps({"error": str((d.get("error") or {}).get("message") or d)}).encode()
                    return
                if t == "content_block_start":
                    b = d.get("content_block") or {}
                    if b.get("type") == "tool_use":
                        idx = d.get("index", 0)
                        calls[idx] = {"id": b.get("id"), "name": b.get("name") or "", "arguments": ""}
                        order.append(idx)
                elif t == "content_block_delta":
                    delta = d.get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield piece(delta["text"])
                    elif delta.get("type") == "input_json_delta":
                        c = calls.get(d.get("index", 0))
                        if c is not None:
                            c["arguments"] += delta.get("partial_json") or ""
                elif t == "message_delta":
                    tokens = (d.get("usage") or {}).get("output_tokens") or tokens
            elif kind == "gemini":
                text, gcalls, tk = _parse_gemini(d, None)
                if text:
                    yield piece(text)
                for c in gcalls:
                    idx = len(order)
                    calls[idx] = c
                    order.append(idx)
                tokens = tk or tokens
    except requests.exceptions.RequestException as e:
        yield json.dumps({"error": str(e)}).encode()
        return
    final = _final("", [calls[i] for i in order], tokens, t0, None)
    final["message"]["content"] = ""
    yield json.dumps(final).encode()


def post(url, json=None, stream=False, timeout=120, **kw):  # noqa: A002 — mirrors requests.post
    """requests.post(url, json=body) for Ollama, or the translated call for
    a remote model (body["model"] starting with "@")."""
    body = json or {}
    model = body.get("model")
    if not is_remote(model):
        return requests.post(url, json=body, stream=stream, timeout=timeout, **kw)
    if not body.get("messages"):
        # keep_alive: 0 / preload requests: nothing to do for remote models.
        return _Response(data={"message": {"role": "assistant", "content": ""}, "done": True})
    return chat(body, stream=bool(body.get("stream") and stream), timeout=timeout)


def _openai_compat(req: dict) -> dict:
    """Second try for OpenAI-compatible servers that reject a parameter
    (reasoning models without temperature/top_p and with
    max_completion_tokens; servers without stream_options)."""
    out = {k: v for k, v in req.items() if k not in ("temperature", "top_p", "stream_options", "max_tokens")}
    if req.get("max_tokens"):
        out["max_completion_tokens"] = req["max_tokens"]
    return out


def chat(body: dict, stream=False, timeout=120):
    p, name, key = _resolve(body["model"])
    kind = p["kind"]
    if kind in ("anthropic", "gemini") and not key:
        raise RemoteError(f"provider '{p['id']}' has no API key")
    fmt = body.get("format")
    req_body = {**body, "stream": stream}
    url, req = _BUILDERS[kind](p, name, req_body)
    headers = _headers(p, key)
    t0 = time.time()
    to = timeout if isinstance(timeout, tuple) else (15, timeout)
    if stream and (req.get("stream") or ":streamGenerateContent" in url):
        r = requests.post(url, json=req, headers=headers, stream=True, timeout=to)
        if r.status_code == 400 and kind == "openai":
            r.close()
            r = requests.post(url, json=_openai_compat(req), headers=headers, stream=True, timeout=to)
        if r.status_code >= 400:
            msg = _err_text(r)
            r.close()
            return _Response(status=r.status_code, error=f"{p['id']}: {msg}")
        return _Response(lines=_stream_lines(kind, r, t0), closer=r.close)
    r = requests.post(url, json=req, headers=headers, timeout=to)
    if r.status_code >= 400 and fmt and kind in ("openai", "gemini"):
        # Some compatible servers don't support JSON schemas: retry with only
        # the instruction in the prompt.
        if kind == "openai":
            req.pop("response_format", None)
        else:
            req["generationConfig"].pop("responseSchema", None)
            req["contents"][-1]["parts"].append({"text": _schema_note(fmt)})
        r = requests.post(url, json=req, headers=headers, timeout=to)
    if r.status_code == 400 and kind == "openai":
        r = requests.post(url, json=_openai_compat(req), headers=headers, timeout=to)
    if r.status_code >= 400:
        return _Response(status=r.status_code, error=f"{p['id']}: {_err_text(r)}")
    try:
        text, calls, tokens = _PARSERS[kind](r.json(), fmt)
    except ValueError as e:
        return _Response(status=502, error=f"{p['id']}: invalid reply ({e})")
    data = _final(text, calls, tokens, t0, fmt)
    if stream:
        # Structured / non-streamable request asked as a stream: one chunk.
        return _Response(lines=iter([json.dumps(data).encode()]))
    return _Response(data=data)


# ── Provider admin: list models, test ──────────────────────────────────

def _provider_from(data: dict):
    """Provider being edited in the UI (may not be saved yet): its key is
    the typed one or, if empty, the stored one."""
    kind = data.get("kind")
    if kind not in KINDS:
        raise ValueError("invalid provider kind")
    url = str(data.get("base_url") or DEFAULT_URLS[kind]).strip().rstrip("/")
    if not re.match(r"^https?://[^\s]+$", url):
        raise ValueError("invalid URL")
    key = str(data.get("api_key") or "").strip()
    if not key and ID_RE.match(str(data.get("id") or "")):
        key = secrets_store.get(_key_name(data["id"]))
    return {"id": data.get("id") or "new", "kind": kind, "base_url": url}, key


def list_provider_models(data: dict) -> list:
    p, key = _provider_from(data)
    h = _headers(p, key)
    kind = p["kind"]
    if kind == "gemini":
        r = requests.get(f"{p['base_url']}/models?pageSize=1000", headers=h, timeout=20)
    else:
        r = requests.get(f"{p['base_url']}/models" + ("?limit=1000" if kind == "anthropic" else ""), headers=h, timeout=20)
    if r.status_code >= 400:
        raise RemoteError(_err_text(r))
    data = r.json()
    out = []
    if kind == "gemini":
        for m in data.get("models") or []:
            if "generateContent" in (m.get("supportedGenerationMethods") or []):
                out.append({"name": m["name"].split("/", 1)[-1], "label": m.get("displayName") or ""})
    else:
        for m in data.get("data") or []:
            mid = m.get("id")
            if not mid:
                continue
            item = {"name": mid, "label": m.get("display_name") or m.get("name") or ""}
            # OpenRouter reports modalities / supported parameters.
            arch = m.get("architecture") or {}
            if arch.get("input_modalities"):
                item["vision"] = "image" in arch["input_modalities"]
            if m.get("supported_parameters"):
                item["tools"] = "tools" in m["supported_parameters"]
            out.append(item)
    out.sort(key=lambda x: x["name"].lower())
    return out


def test_provider(data: dict) -> dict:
    """Sends a tiny request (and a tool-calling one) to check the provider."""
    p, key = _provider_from(data)
    model = str(data.get("model") or "").strip()
    if not model:
        raise ValueError("model required")
    tmp_id = "_test"
    saved = {**p, "id": tmp_id, "enabled": True}
    t0 = time.time()
    _ADHOC[tmp_id] = (saved, key)
    try:
        r = chat({"model": f"@{tmp_id}/{model}", "messages": [
            {"role": "user", "content": "Reply with the single word: ok"}], "options": {"temperature": 0, "num_predict": 20}})
        r.raise_for_status()
        reply = (r.json()["message"].get("content") or "").strip()
        ms = int((time.time() - t0) * 1000)
        tools_ok = None
        if data.get("check_tools", True):
            r2 = chat({"model": f"@{tmp_id}/{model}", "messages": [
                {"role": "user", "content": "What time is it? Use the tool."}],
                "tools": [{"type": "function", "function": {"name": "get_time", "description": "Current time",
                                                            "parameters": {"type": "object", "properties": {}}}}],
                "options": {"temperature": 0, "num_predict": 60}})
            try:
                r2.raise_for_status()
                tools_ok = bool(r2.json()["message"].get("tool_calls"))
            except requests.exceptions.RequestException:
                tools_ok = False
        return {"ok": True, "reply": reply[:200], "ms": ms, "tools": tools_ok}
    finally:
        _ADHOC.pop(tmp_id, None)

